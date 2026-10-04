<div align="center">

# Folio

**A self-hosted document workshop: every document tool in one Docker container.**

Convert anything to Markdown with [Microsoft MarkItDown](https://github.com/microsoft/markitdown).
Edit PDF text in its original font. Resize photos to an exact KB size and aspect ratio.
Compress, convert and secure PDFs, images, audio, video, eBooks and archives.

93 tools · installable mobile app (PWA) · REST API · no files kept

</div>

---

## Contents

- [Why Folio](#why-folio)
- [Quick start](#quick-start)
- [Features](#features)
- [Tool catalogue](#tool-catalogue)
- [How it works](#how-it-works)
- [Configuration](#configuration)
- [REST API](#rest-api)
- [Using it on a phone](#using-it-on-a-phone)
- [Project structure](#project-structure)
- [Development](#development)
- [Adding a tool](#adding-a-tool)
- [Security and privacy](#security-and-privacy)
- [Limitations](#limitations)
- [Troubleshooting](#troubleshooting)
- [Credits and licences](#credits-and-licences)

---

## Why Folio

Online converters such as iLovePDF, iLoveIMG, CloudConvert and photo-to-KB resizers are convenient. They also mean
uploading contracts, IDs and personal photos to someone else's server. Folio brings the same everyday tools onto your
own machine or server:

- **Private by design.** Files are processed inside the container and deleted as soon as the response is sent.
- **One place for everything.** PDF, image, media, Office, eBook, archive and font tools behind one interface and one API.
- **Built for real requirements.** "Under 200 KB", "20–50 KB, 3.5 × 4.5 cm", "9:16 for reels", "fix one typo
  in this PDF without changing the font".
- **Works on phones.** It can be installed as an app, scans with the camera, and accepts files from the phone's share sheet.

## Quick start

**Requirements:** Docker with Compose v2, about 5 GB of free disk space for the image, and 2 GB+ of RAM
(4 GB recommended for OCR, LibreOffice and background removal).

```bash
git clone <your-fork-url> folio
cd folio
docker compose up -d --build
```

Then open:

| URL | What |
|---|---|
| http://localhost:8080 | Web app |
| http://localhost:8080/api/docs | Interactive API documentation (OpenAPI) |
| http://localhost:8080/api/health | Health check |

The first build downloads LibreOffice, Chromium, Tesseract language packs and the background-removal model, so it
takes a while. Later rebuilds only re-copy the application code.

To stop it, or to update after pulling changes:

```bash
docker compose down
```

```bash
docker compose up -d --build
```

## Features

### Markdown, powered by MarkItDown
- PDF, Word, PowerPoint, Excel, HTML, EPUB, ZIP, JSON, images and audio to clean, LLM-ready Markdown.
- Web pages and YouTube links to Markdown.
- Rendered preview, raw view, copy, per-file and combined download.

### PDF editor that keeps the original font
- Tap any line of text to change it. The replacement keeps the font, size, colour and baseline of the original.
- Add text (it picks up the nearest text's font automatically), images, signatures, white-out boxes, highlights and freehand ink.
- Fill PDF forms, then undo, zoom and save.

### Exact sizes and aspect ratios
- **Compress image to KB:** land between a minimum and maximum (e.g. 20–50 KB). Pixels are reduced before quality
  is, so the result stays sharp.
- **Resize image** in px, %, mm, cm or inches with DPI, plus an optional maximum file size.
- **Crop to aspect ratio:** 1:1, 4:5, 9:16, 16:9, passport or custom W:H. Crop around the face, pad, or pad with a blurred background.
- **Photo & signature for forms:** passport, visa and exam-portal presets. Head-and-shoulders framing, exact
  dimensions, KB range, optional AI white background.
- **Compress PDF to size**, **split PDF by size**, **compress video to a target size** (two-pass), and **reframe video**
  to 9:16 / 1:1 / 16:9.

### Previews everywhere
- Every upload is previewed straight away: numbered page thumbnails for PDF, Word, PowerPoint, Excel and eBooks;
  photos with pixel size and ratio; video with resolution and duration; audio; text; archive contents.
- Results are previewed too. Single-file PDF and image results get a **before/after slider** with 2× zoom to check quality.

### App experience
- Mobile-first layout with a bottom tab bar, a camera **Scan** button and full-screen tool views.
- Installable as a PWA, with an offline app shell and Android share-target support.
- "Continue with…" passes a result straight into the next tool (e.g. Merge → Compress → Protect).
- Recently used and most-used tools, plus instant search across all tools (press `/`).

## Tool catalogue

<details open>
<summary><b>Markdown</b> (4)</summary>

| Tool | Description |
|---|---|
| Anything to Markdown | PDF, Word, PowerPoint, Excel, HTML, EPUB, ZIP, JSON, images — all to Markdown |
| PDF to Markdown | Headings, lists and text from PDFs into structured Markdown |
| Office to Markdown | Word, PowerPoint and Excel, with tables kept |
| Web page to Markdown | Articles, Wikipedia, YouTube transcripts |
</details>

<details>
<summary><b>Edit & sign</b> (10)</summary>

| Tool | Description |
|---|---|
| Edit PDF | Change existing text in its original font and size; add text, images and shapes |
| Sign PDF | Draw, type or upload a signature and place it anywhere |
| Fill PDF form | Text fields, check boxes and drop-downs |
| Add watermark | Text or logo, any angle and opacity |
| Add page numbers | Position, format and starting number |
| Header & footer | `{page}`, `{total}`, `{date}`, `{file}` placeholders |
| Crop PDF | Trim margins by a fixed amount |
| Flatten PDF | Burn form fields and annotations into the page |
| Compare PDF | Side-by-side text diff of two versions |
| Edit metadata | Title, author, subject, keywords |
</details>

<details>
<summary><b>Organize PDF</b> (11)</summary>

| Tool | Description |
|---|---|
| Merge PDF | Combine files in a chosen order |
| Split PDF | By ranges, every page, or fixed-size chunks |
| Split PDF by size | Parts that each stay under an MB limit |
| Remove pages / Extract pages | Drop or keep selected pages |
| Reorder pages | Custom order, reverse, odd-then-even |
| Rotate PDF | 90° / 180° / 270°, all or selected pages |
| Pages per sheet (N-up) | 2, 4, 6 or 9 pages on a sheet |
| Alternate & mix | Interleave front and back scans (duplex) |
| Insert blank pages / Remove blank pages | Add pages, or detect and remove empty ones |
</details>

<details>
<summary><b>Optimize PDF</b> (7)</summary>

| Tool | Description |
|---|---|
| Compress PDF | Light (225 dpi), Recommended (150 dpi), Extreme (100 dpi) |
| Compress PDF to size | Exact KB/MB target; text stays legible unless strong loss is allowed |
| Resize PDF pages | A3, A4, A5, B5, Letter, Legal, Tabloid or custom mm; any ratio |
| Repair PDF | pikepdf → MuPDF → Ghostscript recovery chain |
| OCR PDF | Searchable text with OCRmyPDF (7 languages) |
| Grayscale PDF | Remove colour |
| Fast web view | Linearize with qpdf |
</details>

<details>
<summary><b>Convert to PDF</b> (11)</summary>

| Tool | Description |
|---|---|
| Word / PowerPoint / Excel to PDF | LibreOffice rendering |
| Images to PDF | Fit-to-image, A4 or Letter, margins, orientation |
| Scan to PDF | Phone camera; edge detection, perspective fix, clean-up, optional OCR |
| Markdown to PDF · Text to PDF | Typeset A4 documents and monospaced code/logs |
| HTML to PDF · Web page to PDF | Headless Chromium |
| eBook to PDF | EPUB, MOBI, FB2, CBZ, XPS |
| PDF to PDF/A | PDF/A-2b for archiving |
</details>

<details>
<summary><b>Convert from PDF</b> (8)</summary>

| Tool | Description |
|---|---|
| PDF to Word | **Editable text** (pdf2docx) or **Exact layout** (LibreOffice: shapes and charts kept) |
| PDF to PowerPoint | One slide per page; page text in the speaker notes |
| PDF to Excel | Detected tables, one sheet each |
| PDF to JPG / PNG / WebP | 72–300 dpi |
| PDF to Text · PDF to HTML · PDF to SVG | Plain text, a self-contained web page, vector pages |
| Extract images | Embedded pictures at their original resolution |
</details>

<details>
<summary><b>PDF security</b> (4)</summary>

| Tool | Description |
|---|---|
| Protect PDF | AES-256 with print, copy and edit restrictions |
| Unlock PDF | Remove the password from a PDF you own |
| Redact PDF | True removal of words, emails and phone numbers |
| Remove metadata | Author, XMP, JavaScript, embedded files |
</details>

<details>
<summary><b>Image</b> (21)</summary>

| Tool | Description |
|---|---|
| Compress image | Quality slider, optional max dimension; PNG via pngquant |
| Compress image to KB | Min/max KB range with quick presets |
| Resize image | px, %, mm, cm, inch + DPI; fill, fit or stretch; optional max KB |
| Crop to aspect ratio | Face-aware crop, pad or blurred pad |
| Photo & signature for forms | Passport 35×45 mm, US 2×2 in, visa, Canada, exam photo/signature presets, custom |
| Convert image | HEIC, WebP, AVIF, PNG, JPG, GIF, BMP, TIFF, ICO, PDF |
| Remove background | AI cut-out (rembg `isnet-general-use`) to transparent or a colour |
| Blur faces | Blur, pixelate or black box |
| Rotate & flip · Adjust & filters | Any angle, mirror; brightness, contrast, saturation, sharpen, sepia… |
| Watermark image · Meme generator | Text or logo, corner or tiled; top and bottom captions |
| Enlarge image | 1.5×–4× Lanczos with sharpening |
| Remove EXIF & GPS · View file metadata | Lossless strip; full exiftool report |
| Image to text (OCR) | Document, column, screenshot and single-block layouts |
| Image to SVG · SVG to PNG / PDF | Vector tracing (vtracer); cairo rendering |
| Make animated GIF · Photo collage · Web page to image | GIF/WebP animation, grid collage, Chromium screenshot |
</details>

<details>
<summary><b>Audio & video</b> (10)</summary>

| Tool | Description |
|---|---|
| Convert video | MP4, WebM, MOV, MKV, AVI |
| Compress video | Quality level, or an exact target size with two-pass encoding |
| Resize & reframe video | 9:16, 1:1, 4:5, 16:9, 21:9; crop, bars or blurred fill; 360p–4K |
| Trim audio / video | Frame-accurate or instant copy |
| Video to GIF · Video to images | Palette-optimised GIF; frames every N seconds |
| Convert audio · Extract audio | MP3, M4A, WAV, FLAC, OGG, Opus; bitrate, mono, loudness normalisation |
| Mute video · Change speed | No re-encode; 0.5×–4× with natural pitch |
</details>

<details>
<summary><b>Docs, data & files</b> (7)</summary>

| Tool | Description |
|---|---|
| Convert document | DOCX, DOC, ODT, RTF, Markdown, HTML, EPUB, LaTeX, reStructuredText, TXT, PDF |
| Convert spreadsheet & data | XLSX, XLS, ODS, CSV, TSV, JSON, XML, HTML table, Markdown table, PDF |
| Convert presentation | PPTX, PPT, ODP, PDF, PNG slides |
| Create archive · Extract / convert archive | ZIP, 7z (optional password), TAR.GZ |
| Convert font | TTF/OTF ↔ WOFF/WOFF2 |
| eBook to Markdown / EPUB | EPUB, FB2, MOBI to Markdown, text, EPUB, Word |
</details>

## How it works

```
Browser / PWA ──► FastAPI (uvicorn, 2 workers)
                   ├─ /api/tools/{id}   upload → temp dir → tool handler → file / Markdown JSON → temp dir deleted
                   ├─ /api/preview      page thumbnails, image/video/archive previews
                   ├─ /api/editor/*     PDF editor sessions (expire after 3 h)
                   └─ static app        HTML/CSS/JS, service worker, manifest
Engines: PyMuPDF · pikepdf/qpdf · Ghostscript · LibreOffice · OCRmyPDF/Tesseract · ffmpeg · pandoc
         Chromium · cairo · rembg/ONNX · OpenCV · vtracer · pngquant · exiftool · fontTools · py7zr
```

### Editing text in the original font
1. Each span's font, size, colour and baseline are read with `page.get_text("dict")`.
2. The PDF's own embedded font is reused when it contains every character of the new text. Word-exported PDFs
   embed trimmed (subset) fonts without a Unicode map; Folio rebuilds that map from the document's own text with
   fontTools, so the original font stays usable.
3. If characters are missing, Folio uses the same family installed in the container, or a metric-compatible twin via
   fontconfig: Calibri → Carlito, Cambria → Caladea, Arial/Helvetica → Liberation Sans/Nimbus Sans,
   Times → Liberation Serif/Nimbus Roman.
4. The old glyphs are removed with a tight redaction that leaves images and vector graphics untouched, and the new
   text is written on the original baseline. When you save, a note tells you which edits kept the original font.

### Quality safeguards
- **Size targets** reduce pixel dimensions before JPEG quality drops below 50, so results stay sharp, not blocky.
- **PNG compression** uses pngquant with dithering; if quality can't be met, the image stays lossless.
- **PDF compression** never goes below 100 dpi (72 dpi for size targets) unless "Allow strong quality loss" is ticked.
  Ghostscript output is page-count checked, so it can never return blank pages.
- **Input validation:** password-protected or damaged PDFs are rejected with an actionable message; Office, archive
  and eBook files are checked by their file signature; unreadable files return HTTP 422, not a server error.

## Configuration

Set these in `docker-compose.yml`:

| Setting | Default | Purpose |
|---|---|---|
| `ports` | `8080:8000` | Host port for the web app |
| `MAX_UPLOAD_MB` | `500` | Maximum total upload size per request |
| `ALLOW_PRIVATE_URLS` | unset | Set to `1` to let the web-page tools fetch intranet/private addresses |
| `tmpfs /tmp` | `4g` | In-memory scratch space for uploads, results and editor sessions; raise it for very large files |

Previews are limited to files up to 120 MB. Editor sessions are removed 3 hours after their last use.

## REST API

Every tool is available over HTTP. `GET /api/tools` returns each tool's ID, accepted file types and options
(with defaults). Send files as `files` (repeat the field for several files) and options as form fields.

```bash
# Anything to Markdown
curl -F files=@report.pdf http://localhost:8080/api/tools/pdf-to-markdown
```

```bash
# PDF under 200 KB
curl -F files=@big.pdf -F target=200 -F unit=kb http://localhost:8080/api/tools/compress-pdf-to-size -o small.pdf
```

```bash
# Photo between 20 and 50 KB
curl -F files=@me.jpg -F min_size=20 -F max_size=50 -F size_unit=kb http://localhost:8080/api/tools/image-to-size -o me_50kb.jpg
```

```bash
# 9:16 reel with blurred fill
curl -F files=@clip.mov -F aspect=9:16 -F fill=blur -F res=1080 http://localhost:8080/api/tools/resize-video -o reel.mp4
```

```bash
# Merge in order
curl -F files=@a.pdf -F files=@b.pdf http://localhost:8080/api/tools/merge -o merged.pdf
```

**Responses**

| Result | Format |
|---|---|
| A single file | The file, with `Content-Disposition` |
| Several files | A ZIP |
| Markdown / text tools | `{"kind": "markdown", "docs": [{"name", "markdown", "title"}]}` |
| Compare PDF | `{"kind": "html", "html": "…"}` |
| Errors | `422 {"error": "…"}` for bad input; `500` for unexpected failures |

Useful response headers: `X-Original-Size`, `X-Result-Size`, `X-Folio-Note` (URL-encoded explanation) and
`X-Folio-Target-Met` (`1`/`0` for size targets).

**Editor API**

| Call | Purpose |
|---|---|
| `POST /api/editor/open` (`file`, optional `password`) | `{sid, pages: [{w, h, spans, widgets}]}` |
| `GET /api/editor/{sid}/page/{n}.jpg?w=1200` | Page image |
| `GET /api/editor/{sid}/font/{xref}` | Embedded font, used for on-screen editing |
| `POST /api/editor/{sid}/save` | JSON `{"ops": [...]}` with `edit-text`, `add-text`, `image`, `rect`, `highlight`, `line` and `field` operations |
| `DELETE /api/editor/{sid}` | End the session |

**Preview API:** `POST /api/preview` (`file`, optional `first`, `count`, `width`) returns page or frame thumbnails as data URLs.

## Using it on a phone

- Open the site on the phone. On Android/Chrome tap **Install app**; on iOS use **Share → Add to Home Screen**.
- Once installed on Android, Folio appears in the system **share sheet**: share a PDF or photo from any app and
  pick a tool.
- The **Scan** button opens the camera, straightens the page edges and builds a PDF.
- Installing the app and the share sheet need HTTPS (or `localhost`). To use Folio from phones on your network,
  put it behind a TLS reverse proxy such as Caddy, Traefik or nginx. A minimal Caddy example:

```
folio.example.lan {
    reverse_proxy localhost:8080
    request_body {
        max_size 500MB
    }
}
```

## Project structure

```
.
├── Dockerfile              python:3.12-slim-trixie + all engines; bakes in the rembg model
├── docker-compose.yml      port, upload limit, tmpfs scratch space
├── requirements.txt
└── app/
    ├── main.py             FastAPI app: uploads, validation, responses, static files
    ├── registry.py         Tool registry, categories, shared helpers (Ghostscript, LibreOffice,
    │                       size targets, PDF/file validation, SSRF guard, Office media shrinker)
    ├── tools_pdf.py        Markdown (MarkItDown) and all PDF tools
    ├── tools_image.py      Image tools: KB targets, ratios, form photos, AI background removal, OCR
    ├── tools_media.py      Audio and video (ffmpeg)
    ├── tools_files.py      Documents, spreadsheets, presentations, archives, fonts, eBooks
    ├── editor.py           PDF editor API (font-preserving edits, forms, signatures)
    ├── preview.py          Upload/result previews
    └── static/
        ├── index.html      App shell (catalogue, workspace, editor, signature pad)
        ├── styles.css      Design system, responsive/mobile layout, previews
        ├── app.js          Catalogue, routing, tool workspace, previews, PWA
        ├── editor.js       PDF editor front end
        ├── editor.css
        ├── sw.js           Service worker (offline shell, fonts, share target)
        ├── manifest.webmanifest
        └── icons/
```

The front end is plain HTML, CSS and JavaScript, with no build step. Typography uses Fraunces, Figtree and
JetBrains Mono from Google Fonts.

## Development

The app runs only inside the container, because it depends on many system engines. A typical loop:

```bash
docker compose up -d --build
```

```bash
docker logs -f folio
```

For faster front-end iteration, mount the static folder by adding this to the `folio` service in `docker-compose.yml`:

```yaml
    volumes:
      - ./app/static:/srv/app/static:ro
```

Run Python inside the container, e.g. to check that all modules import:

```bash
docker exec folio python -c "import app.main; print(len(app.main.TOOLS), 'tools')"
```

## Adding a tool

Tools are plain functions registered with the `@tool` decorator. The front end builds the options form from the
metadata automatically.

```python
from .registry import PDF, Result, ToolError, out_path, tool, num


@tool(
    id="pdf-stamp", name="Stamp PDF", category="edit", glyph="watermark",
    description="Put a short stamp in the top-right corner of every page.",
    accept=PDF,
    options=[
        {"name": "text", "label": "Stamp text", "type": "text", "default": "APPROVED", "required": True},
        {"name": "size", "label": "Font size", "type": "range", "min": 8, "max": 48, "default": 18},
    ],
)
def pdf_stamp(files, opts, work):
    import pymupdf as fitz

    doc = fitz.open(files[0])
    for page in doc:
        page.insert_text((page.rect.width - 160, 40), opts["text"], fontsize=num(opts, "size", 18), color=(0.8, 0.1, 0.1))
    out = out_path(work, files[0], ".pdf", "stamped")
    doc.save(out)
    return Result("file", out)
```

- **Option types:** `text`, `url`, `password`, `textarea`, `number`, `range`, `color`, `checkbox`, `select`,
  `segmented`, `cards`, `chips`, `grid9` and `file` (a secondary upload, sent as `asset`).
- **Option keys:** `when: {"other_option": "value"}` shows an option conditionally; `sets` on a select or chips option
  fills other fields (presets); `half: true` puts two fields on one row.
- **Errors:** raise `ToolError("message")` for user-facing errors (HTTP 422).
- **Results:** return `Result("file", path)`, `Result("markdown", docs=[...])`, or add `meta={"note": "…"}` to show
  a note with the result.

## Security and privacy

- Uploads and results live in a per-request temp directory on tmpfs and are deleted after the response. Editor
  sessions expire after 3 hours. Logs contain request lines and, for failures, error tracebacks (which can include
  file names) — never file contents.
- The container runs as an unprivileged user (`uid 10001`).
- URL tools refuse loopback, private, link-local and reserved addresses (SSRF guard) unless `ALLOW_PRIVATE_URLS=1`.
- Archive extraction rejects path traversal; uploaded file names are sanitised.
- There is **no built-in authentication**. Do not expose Folio directly to the internet; put it behind a reverse
  proxy with authentication (basic auth, OAuth proxy or VPN) if anyone outside your network can reach it.
- Redaction removes the underlying text, not just draws boxes. Always review redacted output before sharing it.

## Limitations

- **Editing text:**
  - Edited text is written as one run; paragraphs don't reflow.
  - Complex-script shaping (e.g. Devanagari conjuncts) isn't supported.
  - Scanned pages need OCR before their text can be edited.
- **PDF to Word "Editable text"** can drop vector charts; use "Exact layout" for visually faithful output.
- **Enlarge image** uses classical resampling, not AI super-resolution.
- **RAR archives** aren't supported (the decoder isn't free software).
- **MarkItDown extras:**
  - Audio transcription uses an online speech service.
  - Image captioning needs an LLM client, which isn't configured.
- **Third-party assets:** fonts and the Markdown preview library are loaded from Google Fonts and cdnjs (cached by the
  service worker after the first visit).
- **Image size:** about 4.6 GB, mostly LibreOffice, Chromium and the ONNX model.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `failed to connect to the docker API` | Start Docker Desktop / the Docker daemon |
| Upload fails on large files | Raise `MAX_UPLOAD_MB` and the `tmpfs` size; check reverse-proxy body limits |
| "…is password protected" | Run **Unlock PDF** first, or enter the password in the editor |
| "…isn't a readable PDF" | Try **Repair PDF** |
| Size target "not met" note | The target is below what the content allows at legible quality; tick "Allow strong quality loss" or raise the target |
| First background removal is slow | The model warms up in the background after start; later requests take ~1–3 s |
| App doesn't offer to install | Needs HTTPS or `localhost`; see [Using it on a phone](#using-it-on-a-phone) |
| Old UI after an update | Hard-reload once; the service worker updates its cache automatically |

## Credits and licences

Folio stands on these open-source projects:

[MarkItDown](https://github.com/microsoft/markitdown) (MIT) ·
[PyMuPDF](https://github.com/pymupdf/PyMuPDF) (AGPL-3.0 / commercial) ·
[pikepdf](https://github.com/pikepdf/pikepdf) (MPL-2.0) ·
[Ghostscript](https://www.ghostscript.com/) (AGPL-3.0) ·
[qpdf](https://github.com/qpdf/qpdf) (Apache-2.0) ·
[LibreOffice](https://www.libreoffice.org/) (MPL-2.0) ·
[OCRmyPDF](https://github.com/ocrmypdf/OCRmyPDF) (MPL-2.0) ·
[Tesseract](https://github.com/tesseract-ocr/tesseract) (Apache-2.0) ·
[pdf2docx](https://github.com/ArtifexSoftware/pdf2docx) (AGPL-3.0) ·
[FFmpeg](https://ffmpeg.org/) (LGPL/GPL) ·
[pandoc](https://pandoc.org/) (GPL-2.0) ·
[Chromium](https://www.chromium.org/) (BSD) ·
[rembg](https://github.com/danielgatis/rembg) (MIT) ·
[OpenCV](https://opencv.org/) (Apache-2.0) ·
[vtracer](https://github.com/visioncortex/vtracer) (MIT) ·
[pngquant](https://pngquant.org/) (GPL-3.0) ·
[ExifTool](https://exiftool.org/) (Artistic/GPL) ·
[fontTools](https://github.com/fonttools/fonttools) (MIT) ·
[FastAPI](https://fastapi.tiangolo.com/) (MIT).

Several of these components are **AGPL- or GPL-licensed**, including PyMuPDF, Ghostscript, pdf2docx and pngquant.
Running Folio privately is unaffected. If you offer it as a network service to others or redistribute the image,
review those licences' obligations, or arrange commercial licences where available.

Feature research drew on the tool catalogues of iLovePDF, iLoveIMG, CloudConvert and Convertio, and on the
open-source [Stirling-PDF](https://github.com/Stirling-Tools/Stirling-PDF) and
[BentoPDF](https://github.com/alam00000/bentopdf) projects.
