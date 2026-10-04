"""Tool registry and shared helpers.

Each tool is a plain function ``handler(files, opts, work) -> Result`` where
``files`` are uploaded paths, ``opts`` the submitted form options (plus
``opts["asset"]`` for an optional secondary upload) and ``work`` a scratch
directory that is removed after the response is sent.
"""
from __future__ import annotations

import ipaddress
import os
import re
import socket
import subprocess
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

import pikepdf
import pymupdf as fitz

# --------------------------------------------------------------------------- #
# Result + registry types
# --------------------------------------------------------------------------- #


@dataclass
class Result:
    kind: str  # "file" | "markdown" | "html"
    path: Path | None = None
    docs: list[dict] = field(default_factory=list)  # markdown: [{name, markdown}]
    html: str = ""
    original_size: int = 0
    meta: dict = field(default_factory=dict)  # sent as X-Folio-* headers


class ToolError(Exception):
    """Raised for user-facing errors (bad password, bad range, ...)."""


@dataclass
class Tool:
    id: str
    name: str
    category: str
    description: str
    accept: list[str]
    handler: Callable[[list[Path], dict, Path], Result] | None
    multiple: bool = False
    min_files: int = 1
    options: list[dict] = field(default_factory=list)
    reorder: bool = False
    glyph: str = "doc"
    kind: str = "form"  # "form" | "editor"
    popular: bool = False
    capture: bool = False  # offer the camera on phones
    keywords: str = ""

    def meta(self) -> dict:
        return {
            "id": self.id, "name": self.name, "category": self.category,
            "description": self.description, "accept": self.accept,
            "multiple": self.multiple, "min_files": self.min_files,
            "options": self.options, "reorder": self.reorder, "glyph": self.glyph,
            "kind": self.kind, "popular": self.popular, "capture": self.capture,
            "keywords": self.keywords,
        }


CATEGORIES = [
    {"id": "markdown", "name": "Markdown", "blurb": "Powered by Microsoft MarkItDown — turn any document into clean, LLM-ready Markdown."},
    {"id": "edit", "name": "Edit & sign", "blurb": "Change text in its original font, sign, fill forms, stamp and annotate."},
    {"id": "organize", "name": "Organize PDF", "blurb": "Merge, split, reorder, trim and impose pages."},
    {"id": "optimize", "name": "Optimize PDF", "blurb": "Shrink to an exact size, repair, OCR and resize pages."},
    {"id": "to-pdf", "name": "Convert to PDF", "blurb": "Office files, images, scans, web pages, eBooks and Markdown into PDF."},
    {"id": "from-pdf", "name": "Convert from PDF", "blurb": "Pull PDFs back into editable formats."},
    {"id": "security", "name": "PDF security", "blurb": "Lock, unlock, redact and sanitize."},
    {"id": "image", "name": "Image", "blurb": "Resize to exact KB and dimensions, crop to any ratio, convert, and touch up."},
    {"id": "media", "name": "Audio & video", "blurb": "Convert, compress to a target size, trim, reframe for any aspect ratio."},
    {"id": "files", "name": "Docs, data & files", "blurb": "Documents, spreadsheets, eBooks, archives and fonts between formats."},
]

TOOLS: dict[str, Tool] = {}


def tool(**kw):
    def deco(fn):
        t = Tool(handler=fn, **kw)
        TOOLS[t.id] = t
        return fn

    return deco


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

PDF = [".pdf"]
OFFICE_WORD = [".doc", ".docx", ".odt", ".rtf", ".txt"]
OFFICE_PPT = [".ppt", ".pptx", ".odp", ".pps", ".ppsx"]
OFFICE_XLS = [".xls", ".xlsx", ".ods", ".csv"]
IMAGES = [".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff", ".gif", ".heic", ".heif", ".avif"]
VIDEO = [".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v", ".wmv", ".flv", ".3gp", ".mpeg", ".mpg", ".ts"]
AUDIO = [".mp3", ".wav", ".m4a", ".aac", ".ogg", ".oga", ".opus", ".flac", ".wma", ".aiff", ".amr"]

PAGES_OPT = {
    "name": "pages",
    "label": "Pages",
    "type": "text",
    "placeholder": "e.g. 1-3, 5, 8-",
    "help": "Leave empty for all pages.",
    "default": "",
}


def run(cmd: list[str], timeout: int = 600) -> None:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError as e:
        raise ToolError(f"Required engine not installed: {cmd[0]}") from e
    except subprocess.TimeoutExpired as e:
        raise ToolError(f"{cmd[0]} timed out") from e
    if proc.returncode != 0:
        msg = (proc.stderr or proc.stdout or "").strip().splitlines()
        raise ToolError(f"{cmd[0]} failed: {msg[-1] if msg else proc.returncode}")


def parse_ranges(spec: str, n: int) -> list[tuple[int, int]]:
    """'1-3, 5, 8-' -> [(1,3),(5,5),(8,n)] (1-based, inclusive). Empty -> all."""
    spec = (spec or "").replace(" ", "")
    if not spec:
        return [(1, n)]
    out = []
    for part in spec.split(","):
        if not part:
            continue
        m = re.fullmatch(r"(\d*)-(\d*)|(\d+)", part)
        if not m:
            raise ToolError(f"Invalid page range: '{part}'")
        if m.group(3):
            a = b = int(m.group(3))
        else:
            a = int(m.group(1) or 1)
            b = int(m.group(2) or n)
        if a < 1 or b > n or a > b:
            raise ToolError(f"Range '{part}' is outside 1-{n}")
        out.append((a, b))
    return out


def page_set(spec: str, n: int) -> list[int]:
    """0-based page indices in the order given, without duplicates."""
    seen, out = set(), []
    for a, b in parse_ranges(spec, n):
        for i in range(a - 1, b):
            if i not in seen:
                seen.add(i)
                out.append(i)
    return out


def out_path(work: Path, src: Path, suffix: str, tag: str = "") -> Path:
    stem = src.stem + (f"_{tag}" if tag else "")
    return work / "out" / f"{stem}{suffix}"


def zip_files(paths: list[Path], dest: Path) -> Path:
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
        for p in paths:
            z.write(p, p.name)
    return dest


def single_or_zip(paths: list[Path], work: Path, zip_name: str) -> Result:
    if len(paths) == 1:
        return Result("file", paths[0])
    return Result("file", zip_files(paths, work / "out" / zip_name))


def open_pdf(path: Path) -> fitz.Document:
    doc = fitz.open(path)
    if doc.needs_pass:
        raise ToolError(f"{path.name} is password protected — unlock it first.")
    return doc


def pike(path: Path) -> pikepdf.Pdf:
    """Open with pikepdf; if the file is malformed, let MuPDF rebuild it first."""
    try:
        return pikepdf.open(path)
    except pikepdf.PasswordError as e:
        raise ToolError(f"{path.name} is password protected — unlock it first.") from e
    except pikepdf.PdfError:
        fixed = path.with_name(path.stem + ".rebuilt.pdf")
        try:
            fitz.open(path).save(fixed, garbage=3, deflate=True)
            return pikepdf.open(fixed)
        except Exception as e:  # noqa: BLE001
            raise ToolError(f"{path.name} is not a readable PDF.") from e


def hex_color(value: str) -> tuple[float, float, float]:
    v = (value or "#000000").lstrip("#")
    if len(v) != 6:
        v = "000000"
    return tuple(int(v[i : i + 2], 16) / 255 for i in (0, 2, 4))


def for_each(files: list[Path], work: Path, fn: Callable[[Path], Path], zip_name: str) -> Result:
    return single_or_zip([fn(f) for f in files], work, zip_name)



def ghostscript(src: Path, dest: Path, *args: str) -> None:
    run(["gs", "-sDEVICE=pdfwrite", "-dNOPAUSE", "-dBATCH", "-dQUIET", "-dSAFER",
         "-dCompatibilityLevel=1.5", *args, f"-sOutputFile={dest}", str(src)])
    # Ghostscript can "succeed" with empty pages (e.g. undecryptable input) — never hand that back.
    try:
        n_in, n_out = fitz.open(src).page_count, fitz.open(dest).page_count
    except Exception as e:  # noqa: BLE001
        raise ToolError("Ghostscript produced an unreadable file.") from e
    if n_out == 0 or n_out != n_in:
        raise ToolError(f"Ghostscript produced {n_out} of {n_in} pages — the PDF may be damaged; try Repair PDF.")


def check_pdf(path: Path, allow_damaged: bool = False) -> None:
    """Reject encrypted or unreadable PDFs up front with a message the user can act on."""
    try:
        doc = fitz.open(path)
    except Exception as e:  # noqa: BLE001
        if allow_damaged:
            return
        raise ToolError(f"{path.name} isn't a readable PDF — it may be damaged. Try Repair PDF first.") from e
    if doc.needs_pass:
        raise ToolError(f"{path.name} is password protected — open it with Unlock PDF first.")
    if doc.page_count == 0 and not allow_damaged:
        raise ToolError(f"{path.name} has no pages.")


def soffice(files: list[Path], work: Path, target: str = "pdf", infilter: str = "") -> list[Path]:
    outdir = work / "out"
    profile = work / "lo-profile"
    outs = []
    for f in files:
        run(["soffice", f"-env:UserInstallation=file://{profile}", "--headless", "--norestore",
             *([f"--infilter={infilter}"] if infilter else []),
             "--convert-to", target, "--outdir", str(outdir), str(f)], timeout=300)
        ext = "." + target.split(":")[0].strip('"')
        p = outdir / (f.stem + ext)
        if not p.exists():
            raise ToolError(f"LibreOffice could not convert {f.name}")
        outs.append(p)
    return outs


def check_public_url(url: str) -> str:
    """Reject non-http(s) URLs and hosts that resolve to private/internal addresses (SSRF guard)."""
    url = (url or "").strip()
    p = urlparse(url)
    if p.scheme not in ("http", "https") or not p.hostname:
        raise ToolError("Enter a full http(s):// URL.")
    if os.environ.get("ALLOW_PRIVATE_URLS") == "1":
        return url
    try:
        infos = socket.getaddrinfo(p.hostname, p.port or (443 if p.scheme == "https" else 80))
    except socket.gaierror as e:
        raise ToolError(f"Can't resolve {p.hostname}") from e
    for info in infos:
        ip = ipaddress.ip_address(info[4][0].split("%")[0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
            raise ToolError("That address points to a private network and is blocked.")
    return url


def num(opts: dict, key: str, default: float = 0.0) -> float:
    try:
        v = opts.get(key)
        return float(v) if v not in (None, "") else default
    except (TypeError, ValueError):
        return default


SIZE_UNITS = {"kb": 1024, "mb": 1024 * 1024}


def target_bytes(opts: dict, key: str = "target", unit_key: str = "unit") -> int:
    v = num(opts, key)
    return int(v * SIZE_UNITS.get(str(opts.get(unit_key, "kb")).lower(), 1024)) if v > 0 else 0


def fmt_size(n: int) -> str:
    return f"{n / 1024 / 1024:.2f} MB" if n >= 1024 * 1024 else f"{n / 1024:.1f} KB"


def shrink_office_media(path: Path, min_bytes: int = 120_000, quality: int = 85) -> None:
    """Re-encode large photographic PNGs inside a DOCX/PPTX/XLSX as JPEG (pdf2docx & co. store photos as PNG)."""
    import io as _io

    from PIL import Image

    with zipfile.ZipFile(path) as zin:
        order = zin.namelist()
        data = {n: zin.read(n) for n in order}
    renamed = {}
    for n in list(data):
        if "/media/" not in n or not n.lower().endswith(".png") or len(data[n]) < min_bytes:
            continue
        try:
            im = Image.open(_io.BytesIO(data[n]))
            if im.mode in ("RGBA", "LA", "P") and "A" in im.convert("RGBA").getbands() and im.convert("RGBA").getchannel("A").getextrema()[0] < 250:
                continue  # real transparency: keep PNG
            b = _io.BytesIO()
            im.convert("RGB").save(b, "JPEG", quality=quality, optimize=True, progressive=True)
        except Exception:  # noqa: BLE001
            continue
        if b.tell() < len(data[n]) * 0.7:
            new = n[:-4] + ".jpeg"
            data[new] = b.getvalue()
            del data[n]
            order[order.index(n)] = new
            renamed[n.rsplit("/", 1)[1]] = new.rsplit("/", 1)[1]
    if not renamed:
        return
    for n in order:
        if n.endswith(".rels") or n.endswith(".xml"):
            txt = data[n].decode("utf-8", errors="ignore")
            hit = False
            for a, b_ in renamed.items():
                if a in txt:
                    txt = txt.replace(f"media/{a}", f"media/{b_}")
                    hit = True
            if hit:
                data[n] = txt.encode("utf-8")
    ct = data["[Content_Types].xml"].decode("utf-8")
    if 'Extension="jpeg"' not in ct:
        ct = re.sub(r"(<Types[^>]*>)", r'\1<Default Extension="jpeg" ContentType="image/jpeg"/>', ct, count=1)
        data["[Content_Types].xml"] = ct.encode("utf-8")
    tmp = path.with_suffix(path.suffix + ".tmp")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
        for n in order:
            zout.writestr(n, data[n])
    tmp.replace(path)


OLE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
MAGIC = {  # extension -> accepted leading bytes
    ".doc": (OLE, b"{\\rtf"), ".xls": (OLE, b"PK\x03\x04"), ".ppt": (OLE,), ".pps": (OLE,),
    ".docx": (b"PK\x03\x04",), ".xlsx": (b"PK\x03\x04",), ".pptx": (b"PK\x03\x04",), ".ppsx": (b"PK\x03\x04",),
    ".odt": (b"PK\x03\x04",), ".ods": (b"PK\x03\x04",), ".odp": (b"PK\x03\x04",), ".epub": (b"PK\x03\x04",),
    ".zip": (b"PK\x03\x04", b"PK\x05\x06"), ".cbz": (b"PK\x03\x04",), ".7z": (b"7z\xbc\xaf\x27\x1c",),
    ".rtf": (b"{\\rtf",), ".gz": (b"\x1f\x8b",), ".tgz": (b"\x1f\x8b",),
}
KIND = {".doc": "Word", ".docx": "Word", ".xls": "Excel", ".xlsx": "Excel", ".ppt": "PowerPoint", ".pptx": "PowerPoint",
        ".pps": "PowerPoint", ".ppsx": "PowerPoint", ".odt": "OpenDocument", ".ods": "OpenDocument", ".odp": "OpenDocument",
        ".epub": "EPUB", ".zip": "ZIP", ".cbz": "comic", ".7z": "7z", ".rtf": "RTF", ".gz": "gzip", ".tgz": "gzip"}


def check_magic(path: Path) -> None:
    ext = path.suffix.lower()
    if ext not in MAGIC:
        return
    with path.open("rb") as fh:
        head = fh.read(16)
    if not any(head.startswith(m) for m in MAGIC[ext]):
        raise ToolError(f"{path.name} isn't a valid {KIND.get(ext, ext[1:].upper())} file (it may be damaged or renamed).")


PARSE_ERRORS = {"BadZipFile", "TTLibError", "UnidentifiedImageError", "FileDataError", "FileConversionException",
                "PdfError", "DecompressionBombError", "Bad7zFile", "ReadError", "ParserError", "XMLSyntaxError",
                "EmptyDataError", "UnicodeDecodeError", "EmptyFileError", "ValueError"}
