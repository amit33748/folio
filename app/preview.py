"""Thumbnails for anything a user drops in: PDF/Office/eBook pages, HEIC/TIFF/PSD/SVG images, video frames,
archive listings. Browsers preview JPG/PNG/WebP/GIF/video/audio/text themselves; this covers the rest."""
from __future__ import annotations

import base64
import io
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

import pymupdf as fitz
from fastapi import APIRouter, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from starlette.datastructures import UploadFile

router = APIRouter()
MAX_PREVIEW_MB = 120
OFFICE = {".doc", ".docx", ".odt", ".rtf", ".ppt", ".pptx", ".pps", ".ppsx", ".odp", ".xls", ".xlsx", ".ods", ".wpd",
          ".key", ".pages", ".dotx"}
MUPDF = {".pdf", ".epub", ".mobi", ".fb2", ".cbz", ".xps", ".oxps"}
IMAGES = {".heic", ".heif", ".avif", ".tif", ".tiff", ".psd", ".bmp", ".ico", ".svg", ".jpg", ".jpeg", ".png", ".webp", ".gif", ".jfif"}
VIDEO = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v", ".wmv", ".flv", ".3gp", ".mpeg", ".mpg", ".ts"}


def _jpeg_url(data: bytes) -> str:
    return "data:image/jpeg;base64," + base64.b64encode(data).decode()


def _pdf_pages(doc: fitz.Document, first: int, count: int, width: int) -> list[str]:
    out = []
    for i in range(first, min(doc.page_count, first + count)):
        page = doc[i]
        z = width / max(1, page.rect.width)
        pix = page.get_pixmap(matrix=fitz.Matrix(z, z), alpha=False)
        out.append(_jpeg_url(pix.tobytes("jpg", jpg_quality=78)))
    return out


def build(path: Path, work: Path, first: int, count: int, width: int, password: str = "") -> dict:
    ext = path.suffix.lower()
    if ext in OFFICE:
        run = subprocess.run(["soffice", f"-env:UserInstallation=file://{work / 'lo'}", "--headless", "--norestore",
                              "--convert-to", "pdf", "--outdir", str(work), str(path)], capture_output=True, timeout=180)
        pdf = work / (path.stem + ".pdf")
        if run.returncode or not pdf.exists():
            return {"kind": "none", "error": "Preview not available"}
        doc = fitz.open(pdf)
        return {"kind": "pages", "page_count": doc.page_count, "first": first, "pages": _pdf_pages(doc, first, count, width),
                "w": doc[0].rect.width, "h": doc[0].rect.height}
    if ext in MUPDF:
        doc = fitz.open(path)
        if doc.needs_pass and not doc.authenticate(password):
            return {"kind": "locked", "page_count": doc.page_count}
        if doc.is_reflowable:
            doc.layout(width=420, height=595, fontsize=11)
        meta = {}
        if ext == ".pdf":
            meta = {"title": (doc.metadata or {}).get("title") or "", "fonts": len({f[3] for p in doc for f in p.get_fonts()}),
                    "images": sum(len(p.get_images()) for p in doc), "text": any(p.get_text().strip() for p in doc.pages(0, min(3, doc.page_count)))}
        return {"kind": "pages", "page_count": doc.page_count, "first": first, "pages": _pdf_pages(doc, first, count, width),
                "w": doc[0].rect.width, "h": doc[0].rect.height, "meta": meta}
    if ext in IMAGES:
        from PIL import Image, ImageOps

        from .tools_image import load_image

        im = ImageOps.exif_transpose(load_image(path))
        w, h = im.size
        im.thumbnail((width * 2, width * 2))
        b = io.BytesIO()
        base = Image.new("RGB", im.size, (255, 255, 255))
        rgba = im.convert("RGBA")
        base.paste(rgba, mask=rgba.getchannel("A"))
        base.save(b, "JPEG", quality=82)
        return {"kind": "image", "pages": [_jpeg_url(b.getvalue())], "w": w, "h": h, "mode": im.mode}
    if ext in VIDEO:
        frame = work / "f.jpg"
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-ss", "1", "-i", str(path), "-frames:v", "1",
                        "-vf", f"scale={width * 2}:-2", str(frame)], capture_output=True, timeout=60)
        if not frame.exists():
            subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(path), "-frames:v", "1",
                            "-vf", f"scale={width * 2}:-2", str(frame)], capture_output=True, timeout=60)
        probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height:format=duration",
                                "-of", "default=nw=1", str(path)], capture_output=True, text=True, timeout=30).stdout
        info = dict(line.split("=", 1) for line in probe.splitlines() if "=" in line)
        return {"kind": "video", "pages": [_jpeg_url(frame.read_bytes())] if frame.exists() else [],
                "w": int(info.get("width", 0) or 0), "h": int(info.get("height", 0) or 0),
                "duration": float(info.get("duration", 0) or 0)}
    if ext == ".zip":
        with zipfile.ZipFile(path) as z:
            items = [(i.filename, i.file_size) for i in z.infolist() if not i.is_dir()]
        return {"kind": "list", "items": items[:200], "count": len(items)}
    return {"kind": "none"}


@router.post("/api/preview")
async def preview(request: Request):
    form = await request.form()
    up = form.get("file")
    if not isinstance(up, UploadFile) or not up.filename:
        return JSONResponse({"error": "No file"}, status_code=422)
    first = max(0, int(form.get("first") or 0))
    count = max(1, min(60, int(form.get("count") or 12)))
    width = max(80, min(1400, int(form.get("width") or 300)))
    work = Path(tempfile.mkdtemp(prefix="folio-pv-"))
    try:
        path = work / Path(up.filename).name.replace("/", "_")
        size = 0
        with path.open("wb") as fh:
            while chunk := await up.read(1 << 20):
                size += len(chunk)
                if size > MAX_PREVIEW_MB * 1024 * 1024:
                    return {"kind": "none", "error": "Too large to preview"}
                fh.write(chunk)
        try:
            return await run_in_threadpool(build, path, work, first, count, width, str(form.get("password") or ""))
        except Exception as e:  # noqa: BLE001 - previews are best effort
            return {"kind": "none", "error": f"Preview not available ({type(e).__name__})"}
    finally:
        shutil.rmtree(work, ignore_errors=True)
