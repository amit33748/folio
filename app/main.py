from __future__ import annotations

import logging
import os
import re
import shutil
import tempfile
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.background import BackgroundTask
from starlette.datastructures import UploadFile

from . import tools_files, tools_image, tools_media, tools_pdf  # noqa: F401 - registers tools
from .editor import router as editor_router
from .preview import router as preview_router
from .registry import CATEGORIES, PARSE_ERRORS, TOOLS, ToolError, check_magic, check_pdf

log = logging.getLogger("folio")
MAX_MB = int(os.environ.get("MAX_UPLOAD_MB", "200"))
STATIC = Path(__file__).parent / "static"

app = FastAPI(title="Folio", docs_url="/api/docs", openapi_url="/api/openapi.json")
app.include_router(editor_router)
app.include_router(preview_router)


@app.middleware("http")
async def revalidate_static(request: Request, call_next):
    response = await call_next(request)
    if not request.url.path.startswith("/api/"):
        response.headers.setdefault("Cache-Control", "no-cache")
    if request.url.path.endswith(".webmanifest"):
        response.headers["Content-Type"] = "application/manifest+json"
    return response


def safe_name(name: str) -> str:
    name = Path(name or "file").name
    stem, dot, ext = name.rpartition(".")
    stem = re.sub(r"[^\w\-. ]+", "_", stem if dot else name).strip(" .") or "file"
    return f"{stem[:80]}.{ext.lower()}" if dot else stem[:80]


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/tools")
def list_tools():
    return {"categories": CATEGORIES, "tools": [t.meta() for t in TOOLS.values()], "max_upload_mb": MAX_MB}


async def _save(upload: UploadFile, dest: Path, budget: list[int]) -> None:
    with dest.open("wb") as fh:
        while chunk := await upload.read(1 << 20):
            budget[0] += len(chunk)
            if budget[0] > MAX_MB * 1024 * 1024:
                raise ToolError(f"Upload exceeds the {MAX_MB} MB limit.")
            fh.write(chunk)


@app.post("/api/tools/{tool_id}")
async def run_tool(tool_id: str, request: Request):
    tool = TOOLS.get(tool_id)
    if not tool or tool.handler is None:
        raise HTTPException(404, "Unknown tool")

    work = Path(tempfile.mkdtemp(prefix="folio-"))
    (work / "in").mkdir()
    (work / "out").mkdir()
    cleanup = BackgroundTask(shutil.rmtree, work, ignore_errors=True)
    try:
        form = await request.form(max_files=300, max_fields=200)
        files: list[Path] = []
        opts: dict = {}
        budget = [0]
        for key, value in form.multi_items():
            if isinstance(value, UploadFile):
                if not value.filename:
                    continue
                name = safe_name(value.filename)
                if key == "asset":
                    dest = work / "asset" / name
                    dest.parent.mkdir(exist_ok=True)
                    await _save(value, dest, budget)
                    opts["asset"] = dest
                    continue
                if key != "files":
                    continue
                if tool.accept and Path(name).suffix.lower() not in tool.accept:
                    raise ToolError(f"{name}: unsupported file type for {tool.name}")
                dest = work / "in" / f"{len(files):03d}" / name
                dest.parent.mkdir()
                await _save(value, dest, budget)
                files.append(dest)
            elif key != "asset":
                opts[key] = value
        for o in tool.options:  # checkboxes arrive as "true"/"false" strings
            if o["type"] == "checkbox":
                opts[o["name"]] = str(opts.get(o["name"], o["default"])).lower() in {"true", "1", "on"}
        if len(files) < tool.min_files:
            raise ToolError(f"{tool.name} needs at least {tool.min_files} file{'s' if tool.min_files > 1 else ''}.")
        if not tool.multiple and len(files) > 1:
            files = files[:1]
        if tool.id not in ("unlock", "metadata-view"):
            for f in files:
                if f.suffix.lower() == ".pdf":
                    check_pdf(f, allow_damaged=tool.id == "repair")
                else:
                    check_magic(f)

        result = await run_in_threadpool(tool.handler, files, opts, work)
    except ToolError as e:
        shutil.rmtree(work, ignore_errors=True)
        return JSONResponse({"error": str(e).replace(str(work), "")}, status_code=422)
    except Exception as e:  # noqa: BLE001
        shutil.rmtree(work, ignore_errors=True)
        if type(e).__name__ in PARSE_ERRORS:  # unreadable input, not a server fault
            names = ", ".join(f.name for f in files) if "files" in locals() else "the file"
            return JSONResponse({"error": f"Couldn't read {names}: it doesn't look like a valid file of that type."},
                                status_code=422)
        log.exception("tool %s failed", tool_id)
        return JSONResponse({"error": f"Processing failed: {type(e).__name__}: {str(e).replace(str(work), '')}"},
                            status_code=500)

    if result.kind == "markdown":
        shutil.rmtree(work, ignore_errors=True)
        return {"kind": "markdown", "docs": result.docs}
    if result.kind == "html":
        shutil.rmtree(work, ignore_errors=True)
        return {"kind": "html", "html": result.html, "filename": "comparison.html"}

    size_in = result.original_size or sum(f.stat().st_size for f in files)
    headers = {
        "X-Original-Size": str(size_in),
        "X-Result-Size": str(result.path.stat().st_size),
        "Access-Control-Expose-Headers": "X-Original-Size, X-Result-Size, X-Folio-Note, X-Folio-Target-Met, Content-Disposition",
    }
    for k, v in result.meta.items():
        if v != "":
            headers[f"X-Folio-{k.title()}"] = quote(str(v), safe=" ,.:()×–-/%")
    return FileResponse(result.path, filename=result.path.name, headers=headers, background=cleanup)


@app.post("/share-target")
def share_target_fallback():
    # The service worker normally intercepts shares; without it, just open the app.
    return RedirectResponse("/", status_code=303)


app.mount("/", StaticFiles(directory=STATIC, html=True), name="static")
