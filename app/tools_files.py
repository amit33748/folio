"""Documents, spreadsheets, presentations, archives and fonts between formats."""
from __future__ import annotations

import shutil
import tarfile
import zipfile
from pathlib import Path

from .registry import (
    OFFICE_PPT, OFFICE_WORD, OFFICE_XLS, Result, ToolError, for_each, out_path, run, single_or_zip, soffice,
    tool, zip_files,
)

LO_DOC_IN = {".doc", ".docx", ".odt", ".rtf", ".wpd", ".wps", ".dot", ".dotx", ".txt", ".pages"}
PANDOC_IN = {".md": "markdown", ".markdown": "markdown", ".html": "html", ".htm": "html", ".epub": "epub",
             ".rst": "rst", ".tex": "latex", ".org": "org", ".ipynb": "ipynb", ".docx": "docx", ".odt": "odt",
             ".textile": "textile", ".adoc": "asciidoc", ".json": "json"}
PANDOC_OUT = {"md": ("gfm", ".md"), "html": ("html5", ".html"), "epub": ("epub3", ".epub"), "rst": ("rst", ".rst"),
              "tex": ("latex", ".tex"), "docx": ("docx", ".docx"), "odt": ("odt", ".odt"), "rtf": ("rtf", ".rtf"),
              "txt": ("plain", ".txt")}
LO_DOC_OUT = {"docx": "docx:MS Word 2007 XML", "odt": "odt", "rtf": "rtf", "doc": "doc:MS Word 97",
              "txt": "txt:Text (encoded):UTF8", "html": "html:XHTML Writer File:UTF8", "pdf": "pdf"}


def pandoc(src: Path, dest: Path, fmt_in: str, fmt_out: str) -> None:
    args = ["pandoc", str(src), "-f", fmt_in, "-t", fmt_out, "-o", str(dest), f"--resource-path={src.parent}"]
    if fmt_out in ("html5", "epub3", "docx", "odt", "rtf", "latex"):
        args.append("--standalone")
    if fmt_out == "gfm":
        args[args.index("gfm")] = "gfm-raw_html"
    if fmt_out == "epub3":
        args += ["--metadata", f"title={src.stem}"]
    run(args, timeout=300)


def lo_convert(f: Path, work: Path, target: str) -> Path:
    out = soffice([f], work, target)[0]
    return out


@tool(
    id="convert-document", name="Convert document", category="files", glyph="word", popular=True,
    description="Word, ODT, RTF, Markdown, HTML, EPUB, LaTeX, TXT — any to any, plus PDF.",
    keywords="docx odt rtf markdown html epub latex pandoc libreoffice md to docx",
    accept=sorted(LO_DOC_IN | set(PANDOC_IN)), multiple=True,
    options=[{"name": "format", "label": "Convert to", "type": "select", "default": "docx",
              "choices": [["docx", "Word (DOCX)"], ["pdf", "PDF"], ["odt", "OpenDocument (ODT)"], ["rtf", "Rich Text (RTF)"],
                          ["doc", "Word 97 (DOC)"], ["md", "Markdown"], ["html", "HTML"], ["epub", "EPUB eBook"],
                          ["txt", "Plain text"], ["rst", "reStructuredText"], ["tex", "LaTeX"]]}],
)
def convert_document(files, opts, work):
    target = opts.get("format", "docx")

    def one(f):
        ext = f.suffix.lower()
        # LibreOffice handles office-to-office and anything to PDF with best fidelity.
        if ext in LO_DOC_IN and target in LO_DOC_OUT and not (ext == ".docx" and target in ("md", "epub", "rst", "tex")):
            return lo_convert(f, work, LO_DOC_OUT[target])
        if target == "pdf":
            if ext in (".md", ".markdown"):
                from .tools_pdf import markdown_to_pdf

                return markdown_to_pdf([f], {}, work).path
            mid = work / f"{f.stem}.mid.docx"
            pandoc(f, mid, PANDOC_IN.get(ext, "markdown"), "docx")
            return lo_convert(mid, work, "pdf").rename(out_path(work, f, ".pdf"))
        src, fin = f, PANDOC_IN.get(ext)
        if fin is None:  # .doc/.rtf/.wpd → docx first
            src, fin = lo_convert(f, work, LO_DOC_OUT["docx"]), "docx"
        if target == "doc":
            mid = work / f"{f.stem}.mid.docx"
            pandoc(src, mid, fin, "docx")
            return lo_convert(mid, work, LO_DOC_OUT["doc"]).rename(out_path(work, f, ".doc"))
        tfmt, text = PANDOC_OUT[target]
        dest = out_path(work, f, text)
        if dest.suffix == ext:
            dest = out_path(work, f, text, "converted")
        pandoc(src, dest, fin, tfmt)
        return dest

    return for_each(files, work, one, f"documents_{target}.zip")


@tool(
    id="convert-spreadsheet", name="Convert spreadsheet & data", category="files", glyph="excel",
    description="XLSX, XLS, ODS, CSV, TSV, JSON, HTML table, Markdown table, XML.",
    keywords="csv to excel xlsx to csv json table data",
    accept=OFFICE_XLS + [".tsv", ".json", ".xml"], multiple=True,
    options=[
        {"name": "format", "label": "Convert to", "type": "select", "default": "xlsx",
         "choices": [["xlsx", "Excel (XLSX)"], ["csv", "CSV"], ["tsv", "TSV"], ["json", "JSON (records)"], ["ods", "OpenDocument (ODS)"],
                     ["html", "HTML table"], ["md", "Markdown table"], ["xml", "XML"], ["pdf", "PDF"]]},
        {"name": "sheet", "label": "Sheet", "type": "text", "default": "", "placeholder": "first sheet",
         "help": "Name or number; leave empty for the first sheet."},
    ],
)
def convert_spreadsheet(files, opts, work):
    import pandas as pd

    target = opts.get("format", "xlsx")

    def read(f: Path) -> "pd.DataFrame":
        ext = f.suffix.lower()
        if ext == ".csv":
            return pd.read_csv(f, sep=None, engine="python")
        if ext == ".tsv":
            return pd.read_csv(f, sep="\t")
        if ext == ".json":
            return pd.read_json(f)
        if ext == ".xml":
            return pd.read_xml(f)
        sheet = (opts.get("sheet") or "").strip()
        sh = int(sheet) - 1 if sheet.isdigit() else (sheet or 0)
        return pd.read_excel(f, sheet_name=sh)

    def one(f):
        if target in ("pdf", "ods") or (target == "xlsx" and f.suffix.lower() in (".xls", ".ods")):
            return lo_convert(f, work, {"pdf": "pdf", "ods": "ods", "xlsx": "xlsx"}[target])
        df = read(f)
        ext = {"md": ".md", "json": ".json"}.get(target, "." + target)
        dest = out_path(work, f, ext)
        if dest.suffix == f.suffix.lower():
            dest = out_path(work, f, ext, "converted")
        if target == "xlsx":
            df.to_excel(dest, index=False)
        elif target == "csv":
            df.to_csv(dest, index=False)
        elif target == "tsv":
            df.to_csv(dest, index=False, sep="\t")
        elif target == "json":
            dest.write_text(df.to_json(orient="records", indent=2, force_ascii=False), encoding="utf-8")
        elif target == "html":
            dest.write_text(df.to_html(index=False), encoding="utf-8")
        elif target == "md":
            dest.write_text(df.to_markdown(index=False), encoding="utf-8")
        elif target == "xml":
            df.columns = [str(c).strip().replace(" ", "_") or f"col{i}" for i, c in enumerate(df.columns)]
            df.to_xml(dest, index=False)
        return dest

    return for_each(files, work, one, f"data_{target}.zip")


@tool(
    id="convert-presentation", name="Convert presentation", category="files", glyph="powerpoint",
    description="PPTX, PPT, ODP and Keynote-exported decks between formats, or to images.",
    accept=OFFICE_PPT + [".key"], multiple=True,
    options=[{"name": "format", "label": "Convert to", "type": "segmented", "default": "pptx",
              "choices": [["pptx", "PPTX"], ["odp", "ODP"], ["pdf", "PDF"], ["png", "PNG slides"]]}],
)
def convert_presentation(files, opts, work):
    target = opts.get("format", "pptx")

    def one(f):
        if target == "png":
            import pymupdf as fitz

            pdf = lo_convert(f, work, "pdf")
            doc = fitz.open(pdf)
            outs = []
            for i, page in enumerate(doc, 1):
                p = work / "out" / f"{f.stem}_slide{i:02d}.png"
                page.get_pixmap(dpi=144).save(p)
                outs.append(p)
            pdf.unlink()
            return zip_files(outs, work / f"{f.stem}_slides.zip") if len(outs) > 1 else outs[0]
        return lo_convert(f, work, target)

    return for_each(files, work, one, f"presentations_{target}.zip")


ARCHIVES = [".zip", ".7z", ".tar", ".gz", ".tgz", ".bz2", ".tbz2", ".xz", ".txz"]


def _safe_extract(f: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    name = f.name.lower()

    def check(member: str) -> None:
        target = (dest / member).resolve()
        if not str(target).startswith(str(dest.resolve())):
            raise ToolError("Archive contains unsafe paths.")

    if name.endswith(".zip"):
        with zipfile.ZipFile(f) as z:
            for m in z.namelist():
                check(m)
            z.extractall(dest)
    elif name.endswith(".7z"):
        import py7zr

        with py7zr.SevenZipFile(f) as z:
            for m in z.getnames():
                check(m)
            z.extractall(dest)
    else:
        with tarfile.open(f) as t:
            t.extractall(dest, filter="data")


@tool(
    id="create-archive", name="Create archive", category="files", glyph="archive",
    description="Bundle any files into ZIP, 7z or TAR.GZ — optionally password-protected 7z.",
    keywords="zip compress folder bundle 7z tar",
    accept=[], multiple=True,
    options=[
        {"name": "format", "label": "Format", "type": "segmented", "default": "zip",
         "choices": [["zip", "ZIP"], ["7z", "7z"], ["tar.gz", "TAR.GZ"]]},
        {"name": "name", "label": "Archive name", "type": "text", "default": "archive"},
        {"name": "password", "label": "Password (7z only)", "type": "password", "default": "", "when": {"format": "7z"}},
    ],
)
def create_archive(files, opts, work):
    name = "".join(c for c in (opts.get("name") or "archive") if c.isalnum() or c in "-_ ").strip() or "archive"
    fmt = opts.get("format", "zip")
    dest = work / "out" / f"{name}.{fmt}"
    if fmt == "zip":
        with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
            for f in files:
                z.write(f, f.name)
    elif fmt == "7z":
        import py7zr

        with py7zr.SevenZipFile(dest, "w", password=opts.get("password") or None) as z:
            if opts.get("password"):
                z.set_encrypted_header(True)
            for f in files:
                z.write(f, f.name)
    else:
        with tarfile.open(dest, "w:gz") as t:
            for f in files:
                t.add(f, f.name)
    return Result("file", dest)


@tool(
    id="convert-archive", name="Extract / convert archive", category="files", glyph="archive",
    description="Open 7z, TAR, GZ, XZ and re-pack as ZIP — or list what's inside.",
    keywords="unzip 7z extract tar gz",
    accept=ARCHIVES,
    options=[{"name": "format", "label": "Output", "type": "segmented", "default": "zip",
              "choices": [["zip", "ZIP"], ["7z", "7z"], ["tar.gz", "TAR.GZ"], ["list", "List contents"]]}],
)
def convert_archive(files, opts, work):
    f = files[0]
    tmp = work / "x"
    _safe_extract(f, tmp)
    items = sorted(p for p in tmp.rglob("*") if p.is_file())
    if not items:
        raise ToolError("The archive is empty.")
    fmt = opts.get("format", "zip")
    stem = f.name.split(".")[0]
    if fmt == "list":
        rows = "\n".join(f"| {p.relative_to(tmp)} | {p.stat().st_size:,} |" for p in items)
        return Result("markdown", docs=[{"name": f"{stem}_contents.md", "title": f.name,
                                         "markdown": f"# {f.name}\n\n{len(items)} files\n\n| File | Bytes |\n|---|---:|\n{rows}"}])
    dest = work / "out" / f"{stem}.{fmt}"
    if fmt == "zip":
        with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
            for p in items:
                z.write(p, p.relative_to(tmp))
    elif fmt == "7z":
        import py7zr

        with py7zr.SevenZipFile(dest, "w") as z:
            for p in items:
                z.write(p, str(p.relative_to(tmp)))
    else:
        with tarfile.open(dest, "w:gz") as t:
            for p in items:
                t.add(p, str(p.relative_to(tmp)))
    return Result("file", dest)


@tool(
    id="convert-font", name="Convert font", category="files", glyph="font",
    description="TTF, OTF, WOFF and WOFF2 for web and desktop use.",
    keywords="webfont woff2 ttf otf",
    accept=[".ttf", ".otf", ".woff", ".woff2"], multiple=True,
    options=[{"name": "format", "label": "Convert to", "type": "segmented", "default": "woff2",
              "choices": [["woff2", "WOFF2"], ["woff", "WOFF"], ["ttf", "TTF / OTF"]]}],
)
def convert_font(files, opts, work):
    from fontTools.ttLib import TTFont

    target = opts.get("format", "woff2")

    def one(f):
        font = TTFont(f)
        if target == "ttf":
            font.flavor = None
            ext = ".otf" if "CFF " in font or "CFF2" in font else ".ttf"
        else:
            font.flavor = target
            ext = "." + target
        dest = out_path(work, f, ext)
        if dest.suffix == f.suffix.lower():
            dest = out_path(work, f, ext, "converted")
        font.save(dest)
        return dest

    return for_each(files, work, one, "fonts.zip")


@tool(
    id="ebook-convert", name="eBook to Markdown / EPUB", category="files", glyph="book",
    description="Turn EPUB, FB2 or MOBI books into Markdown, plain text or a clean EPUB.",
    keywords="epub mobi fb2 kindle book",
    accept=[".epub", ".fb2", ".mobi"], multiple=True,
    options=[{"name": "format", "label": "Convert to", "type": "segmented", "default": "md",
              "choices": [["md", "Markdown"], ["txt", "Text"], ["epub", "EPUB"], ["docx", "Word"]]}],
)
def ebook_convert(files, opts, work):
    import pymupdf as fitz

    target = opts.get("format", "md")

    def one(f):
        if f.suffix.lower() == ".epub" and target == "md":
            from .tools_pdf import markitdown

            dest = out_path(work, f, ".md")
            dest.write_text(markitdown().convert(str(f)).markdown or "", encoding="utf-8")
            return dest
        if f.suffix.lower() == ".epub" and target in ("txt", "docx"):
            tfmt, ext = PANDOC_OUT[target] if target != "docx" else ("docx", ".docx")
            dest = out_path(work, f, ext)
            pandoc(f, dest, "epub", tfmt)
            return dest
        # MOBI / FB2: render to HTML via MuPDF, then pandoc
        doc = fitz.open(f)
        html_text = "".join(p.get_text("xhtml") for p in doc)
        mid = work / f"{f.stem}.html"
        mid.write_text(f"<html><head><title>{f.stem}</title></head><body>{html_text}</body></html>", encoding="utf-8")
        tfmt, ext = {"md": ("gfm", ".md"), "txt": ("plain", ".txt"), "epub": ("epub3", ".epub"), "docx": ("docx", ".docx")}[target]
        dest = out_path(work, f, ext)
        if dest.suffix == f.suffix.lower():
            dest = out_path(work, f, ext, "converted")
        pandoc(mid, dest, "html", tfmt)
        return dest

    return for_each(files, work, one, "ebooks.zip")
