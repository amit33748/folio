"""Interactive PDF editor API.

Edits existing text in its *original* font and size: each span's embedded font program is
re-used when it contains every glyph the new text needs; otherwise a metric-compatible
substitute is picked through fontconfig (Arial→Liberation Sans, Calibri→Carlito, …).
Old glyphs are removed with a tight redaction that leaves images and vector art untouched.
"""
from __future__ import annotations

import base64
from urllib.parse import quote
import json
import re
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
from functools import lru_cache
from pathlib import Path

import pymupdf as fitz
from fastapi import APIRouter, HTTPException, Request
from starlette.datastructures import UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, JSONResponse, Response

router = APIRouter(prefix="/api/editor")
ROOT = Path(tempfile.gettempdir()) / "folio-sessions"
ROOT.mkdir(exist_ok=True)
TTL = 3 * 3600
SID = re.compile(r"^[0-9a-f]{32}$")
SUBSET = re.compile(r"^[A-Z]{6}\+")


def _janitor():
    while True:
        cutoff = time.time() - TTL
        for d in ROOT.iterdir():
            try:
                if d.stat().st_mtime < cutoff:
                    shutil.rmtree(d, ignore_errors=True)
            except FileNotFoundError:
                pass
        time.sleep(600)


threading.Thread(target=_janitor, daemon=True).start()


def session(sid: str) -> Path:
    if not SID.match(sid or ""):
        raise HTTPException(404, "Unknown session")
    d = ROOT / sid
    if not (d / "doc.pdf").exists():
        raise HTTPException(410, "This editing session has expired — open the file again.")
    d.touch()
    return d


def clean_name(name: str) -> str:
    return SUBSET.sub("", name or "")


def hexcol(c: int) -> str:
    return f"#{c:06x}"


def rgb_from_hex(h: str) -> tuple[float, float, float]:
    h = (h or "#000000").lstrip("#")
    if len(h) != 6:
        h = "000000"
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def font_map(page: fitz.Page) -> dict[str, tuple[int, str]]:
    """basefont (without subset tag) -> (xref, ext)"""
    out = {}
    for xref, ext, _type, basefont, _name, *_ in page.get_fonts(full=True):
        out.setdefault(clean_name(basefont), (xref, ext))
    return out


def page_spans(page: fitz.Page) -> list[dict]:
    fmap = font_map(page)
    spans = []
    d = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE | fitz.TEXT_PRESERVE_LIGATURES | fitz.TEXT_MEDIABOX_CLIP)
    for bi, block in enumerate(d["blocks"]):
        if block.get("type") != 0:
            continue
        for li, line in enumerate(block["lines"]):
            horizontal = abs(line["dir"][1]) < 1e-3 and line["dir"][0] > 0
            for si, sp in enumerate(line["spans"]):
                if not sp["text"].strip():
                    continue
                name = clean_name(sp["font"])
                xref, ext = fmap.get(name, (0, ""))
                spans.append({
                    "id": f"{bi}-{li}-{si}", "text": sp["text"], "bbox": [round(v, 2) for v in sp["bbox"]],
                    "origin": [round(v, 2) for v in sp["origin"]], "size": round(sp["size"], 2), "font": name,
                    "flags": sp["flags"], "color": hexcol(sp["color"]), "xref": xref,
                    "web": ext in ("ttf", "otf") and xref > 0, "editable": horizontal,
                    "bold": bool(sp["flags"] & 16) or "bold" in name.lower(),
                    "italic": bool(sp["flags"] & 2) or bool(re.search(r"italic|oblique", name, re.I)),
                    "serif": bool(sp["flags"] & 4), "mono": bool(sp["flags"] & 8),
                    "ascender": sp.get("ascender", 0.9), "descender": sp.get("descender", -0.2),
                })
    return spans


def page_widgets(page: fitz.Page) -> list[dict]:
    out = []
    for w in page.widgets() or []:
        item = {"name": w.field_name, "type": w.field_type_string.lower(), "rect": [round(v, 2) for v in w.rect],
                "value": w.field_value if not isinstance(w.field_value, bool) else bool(w.field_value),
                "label": w.field_label or w.field_name, "flags": w.field_flags}
        if w.field_type in (fitz.PDF_WIDGET_TYPE_COMBOBOX, fitz.PDF_WIDGET_TYPE_LISTBOX):
            item["options"] = [c if isinstance(c, str) else c[0] for c in (w.choice_values or [])]
        if w.field_type in (fitz.PDF_WIDGET_TYPE_CHECKBOX, fitz.PDF_WIDGET_TYPE_RADIOBUTTON):
            item["on"] = w.on_state() or "Yes"
            item["value"] = w.field_value not in (None, "", "Off", False)
        out.append(item)
    return out


# --------------------------------------------------------------------------- #
# Font resolution
# --------------------------------------------------------------------------- #


STYLE_WORDS = r"(?:Regular|Roman|Bold|Italic|Oblique|Light|Medium|Semi ?Bold|Demi ?Bold|Extra ?Bold|Black|Heavy|Thin|Condensed|Narrow|Book|Plain|Normal)"
GENERIC = {"dejavu sans", "dejavu serif", "noto sans", "noto serif", "dejavu sans mono"}


def _family_guess(name: str) -> tuple[str, bool, bool]:
    base = re.split(r"[-,]", name, maxsplit=1)
    fam = base[0]
    style = base[1] if len(base) > 1 else ""
    fam = re.sub(r"(PSMT|PS|MT|Std|Pro|LT|OT)$", "", fam)
    fam = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", fam).strip()
    keep_roman = fam.lower().startswith("times")
    while True:  # "Carlito Regular", "Arial Bold Italic" -> family + style
        m = re.search(rf"\s+{STYLE_WORDS}$", fam, re.I)
        if not m or (keep_roman and m.group(0).strip().lower() == "roman"):
            break
        style += " " + m.group(0)
        fam = fam[: m.start()].strip()
    bold = bool(re.search(r"bold|black|heavy|demi", style + " " + name, re.I))
    italic = bool(re.search(r"italic|oblique", style + " " + name, re.I))
    return fam or "Sans", bold, italic


@lru_cache(maxsize=256)
def fc_match(family: str, bold: bool, italic: bool) -> tuple[str, str]:
    """-> (file, matched family list) for a fontconfig pattern."""
    pattern = family + (":bold" if bold else "") + (":italic" if italic else "")
    try:
        proc = subprocess.run(["fc-match", "-f", "%{file}|%{family}", pattern], capture_output=True, text=True, timeout=10)
        file, _, fams = proc.stdout.strip().partition("|")
        return file, fams.lower()
    except (OSError, subprocess.TimeoutExpired):
        return "", ""


def fc_file(family: str, bold: bool, italic: bool, strict: bool = False) -> str:
    file, fams = fc_match(family, bold, italic)
    if strict and family.lower() not in GENERIC and any(g == f.strip() for f in fams.split(",") for g in GENERIC):
        return ""  # fontconfig fell back to a generic face: not a real match
    return file


@lru_cache(maxsize=64)
def _font_from_file(path: str) -> fitz.Font:
    return fitz.Font(fontfile=path)


def covers(font: fitz.Font, text: str) -> bool:
    return all(font.has_glyph(ord(c)) for c in text if c not in "\n\r\t")


def _usage_map(doc: fitz.Document, fontname: str) -> dict[int, int]:
    """unicode -> glyph id for one font, learned from how the document itself draws text."""
    want = clean_name(fontname)
    m: dict[int, int] = {}
    for page in doc:
        for sp in page.get_texttrace():
            if clean_name(sp.get("font", "")) != want:
                continue
            for ch in sp["chars"]:
                ucs, gid = ch[0], ch[1]
                if ucs > 0 and gid > 0:
                    m.setdefault(ucs, gid)
    return m


def _with_cmap(buf: bytes, usage: dict[int, int]) -> fitz.Font | None:
    """Give a subset CID TrueType/OpenType program (no usable cmap) a Unicode cmap so it can be reused."""
    if not usage:
        return None
    from io import BytesIO

    from fontTools.ttLib import TTFont, newTable
    from fontTools.ttLib.tables._c_m_a_p import cmap_format_4, cmap_format_12

    try:
        tt = TTFont(BytesIO(buf), lazy=False)
        order = tt.getGlyphOrder()
        mapping = {u: order[g] for u, g in usage.items() if g < len(order)}
        if not mapping:
            return None
        cmap = newTable("cmap")
        cmap.tableVersion = 0
        sub4 = cmap_format_4(4)
        sub4.platformID, sub4.platEncID, sub4.language = 3, 1, 0
        sub4.cmap = {u: n for u, n in mapping.items() if u <= 0xFFFF}
        tables = [sub4]
        if any(u > 0xFFFF for u in mapping):
            sub12 = cmap_format_12(12)
            sub12.platformID, sub12.platEncID, sub12.language = 3, 10, 0
            sub12.cmap = mapping
            tables.append(sub12)
        cmap.tables = tables
        tt["cmap"] = cmap
        if "post" in tt:
            tt["post"].formatType = 3.0  # drop glyph-name table that subsetters often leave inconsistent
        out = BytesIO()
        tt.save(out)
        return fitz.Font(fontbuffer=out.getvalue())
    except Exception:  # noqa: BLE001 - CFF-only or damaged programs: caller falls back
        return None


def resolve_font(doc: fitz.Document, span: dict, text: str, cache: dict) -> tuple[fitz.Font, str]:
    """Original embedded program if it has every glyph; else the same family installed locally
    (or its metric-compatible alias, e.g. Calibri->Carlito); else a generic face of the same class."""
    key = ("x", span.get("xref"))
    xref = span.get("xref") or 0
    if xref:
        if key not in cache:
            try:
                _, ext, _, buf = doc.extract_font(xref)
                f = fitz.Font(fontbuffer=buf) if buf and ext != "n/a" else None
                sample = [c for c in span.get("text", "") if not c.isspace()]
                if f is not None and ext in ("ttf", "otf") and sample and not any(f.has_glyph(ord(c)) for c in sample):
                    # Identity-H subsets ship without a Unicode cmap: rebuild one from the document's own text.
                    f = _with_cmap(buf, _usage_map(doc, span.get("font") or "")) or f
                cache[key] = f
            except Exception:  # noqa: BLE001 - unreadable embedded program
                cache[key] = None
        f = cache[key]
        if f is not None and covers(f, text):
            return f, "original"
    fam, bold, italic = _family_guess(span.get("font") or "")
    bold = bold or span.get("bold", False)
    italic = italic or span.get("italic", False)
    generic = "Liberation Mono" if span.get("mono") else "Liberation Serif" if span.get("serif") else "Liberation Sans"
    candidates = [(fam, True), (generic, False), ("Noto Sans", False), ("DejaVu Sans", False)]
    for family, strict in candidates:
        path = fc_file(family, bold, italic, strict)
        if path:
            f = _font_from_file(path)
            if covers(f, text):
                return f, f"substitute:{Path(path).stem}"
    return fitz.Font("helv"), "fallback"


BASE14 = {"helv": "Liberation Sans", "tiro": "Liberation Serif", "cour": "Liberation Mono"}


# --------------------------------------------------------------------------- #
# Routes
# --------------------------------------------------------------------------- #


@router.post("/open")
async def open_doc(request: Request):
    form = await request.form()
    up = form.get("file")
    if not isinstance(up, UploadFile) or not up.filename.lower().endswith(".pdf"):
        return JSONResponse({"error": "Choose a PDF file."}, status_code=422)
    sid = uuid.uuid4().hex
    d = ROOT / sid
    d.mkdir()
    raw = d / "orig.pdf"
    with raw.open("wb") as fh:
        while chunk := await up.read(1 << 20):
            fh.write(chunk)
    password = str(form.get("password") or "")

    def prepare():
        doc = fitz.open(raw)
        if doc.needs_pass and not doc.authenticate(password):
            raise PermissionError
        for page in doc:
            if page.rotation:
                page.remove_rotation()  # keep one coordinate space for the editor
        doc.save(d / "doc.pdf", garbage=1, deflate=True)
        doc = fitz.open(d / "doc.pdf")
        pages = []
        for page in doc:
            pages.append({"w": round(page.rect.width, 2), "h": round(page.rect.height, 2),
                          "spans": page_spans(page), "widgets": page_widgets(page)})
        (d / "meta.json").write_text(json.dumps({"name": Path(up.filename).stem}), encoding="utf-8")
        return pages

    try:
        pages = await run_in_threadpool(prepare)
    except PermissionError:
        shutil.rmtree(d, ignore_errors=True)
        return JSONResponse({"error": "This PDF is password protected.", "needs_password": True}, status_code=422)
    except Exception as e:  # noqa: BLE001
        shutil.rmtree(d, ignore_errors=True)
        return JSONResponse({"error": f"Can't open this PDF: {e}"}, status_code=422)
    return {"sid": sid, "name": Path(up.filename).stem, "pages": pages}


@router.get("/{sid}/page/{n}.jpg")
def page_image(sid: str, n: int, w: int = 1000):
    d = session(sid)
    w = max(200, min(2400, w // 100 * 100))
    cache = d / f"p{n}_{w}.jpg"
    if not cache.exists():
        doc = fitz.open(d / "doc.pdf")
        if not 0 <= n < doc.page_count:
            raise HTTPException(404)
        page = doc[n]
        pix = page.get_pixmap(matrix=fitz.Matrix(w / page.rect.width, w / page.rect.width), alpha=False)
        cache.write_bytes(pix.tobytes("jpg", jpg_quality=84))
    return FileResponse(cache, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=3600"})


@router.get("/{sid}/font/{xref}")
def font_file(sid: str, xref: int):
    d = session(sid)
    doc = fitz.open(d / "doc.pdf")
    try:
        _, ext, _, buf = doc.extract_font(xref)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(404) from e
    if not buf or ext not in ("ttf", "otf"):
        raise HTTPException(404)
    return Response(buf, media_type="font/ttf" if ext == "ttf" else "font/otf",
                    headers={"Cache-Control": "private, max-age=3600"})


@router.post("/{sid}/save")
async def save(sid: str, request: Request):
    d = session(sid)
    body = await request.json()
    ops = body.get("ops") or []
    if not isinstance(ops, list):
        raise HTTPException(422, "ops must be a list")
    name = json.loads((d / "meta.json").read_text(encoding="utf-8")).get("name", "document")
    out = d / f"{name}_edited.pdf"
    try:
        report = await run_in_threadpool(apply_ops, d / "doc.pdf", out, ops, bool(body.get("flatten")))
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=422)
    return FileResponse(out, filename=out.name, media_type="application/pdf",
                        headers={"X-Folio-Note": quote(report, safe=" ,.:()"), "Access-Control-Expose-Headers": "X-Folio-Note, Content-Disposition"})


@router.delete("/{sid}")
def close(sid: str):
    if SID.match(sid or ""):
        shutil.rmtree(ROOT / sid, ignore_errors=True)
    return {"ok": True}


# --------------------------------------------------------------------------- #
# Applying edits
# --------------------------------------------------------------------------- #


def _write_lines(page, font, text, origin, size, color, line_gap=1.2):
    tw = fitz.TextWriter(page.rect)
    x, y = origin
    for i, line in enumerate(text.split("\n")):
        if line:
            tw.append((x, y + i * size * line_gap), line, font=font, fontsize=size)
    tw.write_text(page, color=color)


def _decode_image(data_url: str) -> bytes:
    m = re.match(r"^data:image/(png|jpe?g|webp);base64,(.+)$", data_url or "", re.S)
    if not m:
        raise ValueError("Unsupported image data")
    raw = base64.b64decode(m.group(2))
    if len(raw) > 15 * 1024 * 1024:
        raise ValueError("Image too large")
    if m.group(1) == "webp":
        from io import BytesIO

        from PIL import Image

        b = BytesIO()
        Image.open(BytesIO(raw)).save(b, "PNG")
        raw = b.getvalue()
    return raw


def apply_ops(src: Path, out: Path, ops: list[dict], flatten: bool) -> str:
    doc = fitz.open(src)
    font_cache: dict = {}
    by_page: dict[int, list[dict]] = {}
    for op in ops:
        p = int(op.get("page", -1))
        if not 0 <= p < doc.page_count:
            raise ValueError("Edit refers to a page that doesn't exist")
        by_page.setdefault(p, []).append(op)
    kept, subs = 0, set()

    for pno, page_ops in by_page.items():
        page = doc[pno]
        spans = {s["id"]: s for s in page_spans(page)}
        edits = [o for o in page_ops if o.get("type") == "edit-text"]
        for o in page_ops:
            if o.get("type") == "add-text" and spans.get(o.get("like")) and str(o.get("text", "")).strip():
                o["_font"] = resolve_font(doc, spans[o["like"]], str(o["text"]), font_cache)
        # 1) remove original glyphs of edited spans (tight box around the glyph bodies)
        for o in edits:
            s = spans.get(o.get("span"))
            if not s:
                raise ValueError("A text item changed underneath the edit; reopen the file")
            x0, y0, x1, y1 = s["bbox"]
            oy = s["origin"][1]
            sz = s["size"]
            r = fitz.Rect(x0 + 0.2, max(y0, oy - sz * 0.62), x1 - 0.2, min(y1, oy - sz * 0.05))
            page.add_redact_annot(r, fill=False)
            o["_span"] = s
            text = str(o.get("text", ""))
            if text.strip():  # resolve before redaction: the glyph map is learned from the text being replaced
                o["_font"] = resolve_font(doc, s, text, font_cache)
        if edits:
            kw = {"images": fitz.PDF_REDACT_IMAGE_NONE}
            if hasattr(fitz, "PDF_REDACT_LINE_ART_NONE"):
                kw["graphics"] = fitz.PDF_REDACT_LINE_ART_NONE
            page.apply_redactions(**kw)
        # 2) everything else, in the order the user made it
        for o in page_ops:
            t = o.get("type")
            if t == "edit-text":
                s = o["_span"]
                text = str(o.get("text", ""))
                if not text.strip():
                    continue
                font, how = o["_font"]
                if how == "original":
                    kept += 1
                else:
                    subs.add(how.split(":", 1)[-1].replace("-", " "))
                size = float(o.get("size") or s["size"])
                color = rgb_from_hex(o.get("color") or s["color"])
                _write_lines(page, font, text, s["origin"], size, color)
            elif t == "add-text":
                text = str(o.get("text", ""))
                if not text.strip():
                    continue
                size = max(2.0, min(400.0, float(o.get("size") or 12)))
                ref = spans.get(o.get("like")) if o.get("like") else None
                if ref:
                    font, how = o.get("_font") or resolve_font(doc, ref, text, font_cache)
                else:
                    fam = BASE14.get(o.get("font", "helv"), "Liberation Sans")
                    path = fc_file(fam, bool(o.get("bold")), bool(o.get("italic")))
                    font = _font_from_file(path) if path else fitz.Font("helv")
                    if not covers(font, text):
                        font, _ = resolve_font(doc, {"font": "Noto Sans", "bold": o.get("bold")}, text, font_cache)
                x, y = float(o["x"]), float(o["y"])
                _write_lines(page, font, text, (x, y + size * font.ascender), size, rgb_from_hex(o.get("color")))
            elif t == "image":
                r = fitz.Rect(o["rect"])
                if r.is_empty:
                    continue
                page.insert_image(r, stream=_decode_image(o.get("data", "")), keep_proportion=False, overlay=True)
            elif t == "rect":
                r = fitz.Rect(o["rect"])
                fill = rgb_from_hex(o.get("fill") or "#ffffff")
                page.draw_rect(r, color=None, fill=fill, fill_opacity=float(o.get("opacity", 1)), overlay=True)
            elif t == "highlight":
                a = page.add_highlight_annot(fitz.Rect(o["rect"]))
                a.set_colors(stroke=rgb_from_hex(o.get("color") or "#ffe14d"))
                a.update()
            elif t == "line":
                pts = o.get("points") or []
                if len(pts) >= 2:
                    shape = page.new_shape()
                    shape.draw_polyline([fitz.Point(p) for p in pts])
                    shape.finish(color=rgb_from_hex(o.get("color") or "#000000"), width=float(o.get("width", 1.5)),
                                 closePath=False, lineCap=1, lineJoin=1)
                    shape.commit()
            elif t == "field":
                for w in page.widgets() or []:
                    if w.field_name != o.get("name"):
                        continue
                    if w.field_type in (fitz.PDF_WIDGET_TYPE_CHECKBOX, fitz.PDF_WIDGET_TYPE_RADIOBUTTON):
                        w.field_value = w.on_state() if o.get("value") else "Off"
                    else:
                        w.field_value = str(o.get("value", ""))
                    w.update()
    if flatten:
        doc.bake(annots=True, widgets=True)
    doc.save(out, garbage=3, deflate=True)
    if not subs:
        return "Original embedded fonts kept for every edit." if kept else ""
    note = f"Closest installed match used where the embedded subset lacked characters: {', '.join(sorted(subs))}."
    return (f"Original font kept for {kept} edit{'s' if kept != 1 else ''}. " if kept else "") + note
