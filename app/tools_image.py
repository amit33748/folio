"""Image tools: exact-size compression, resizing by px/mm/cm/in, aspect-ratio crops, form photos, AI touches."""
from __future__ import annotations

import io
import subprocess
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps

from .registry import (
    IMAGES, Result, ToolError, check_public_url, fmt_size, for_each, hex_color, num, out_path, run,
    single_or_zip, target_bytes, tool, zip_files,
)

try:  # HEIC / HEIF (iPhone photos)
    from pillow_heif import register_heif_opener

    register_heif_opener()
except Exception:  # noqa: BLE001
    pass

Image.MAX_IMAGE_PIXELS = 200_000_000
IMG_IN = IMAGES + [".svg", ".ico", ".psd", ".jfif"]

FORMATS = {  # key: (PIL format, extension, supports alpha)
    "jpg": ("JPEG", ".jpg", False), "png": ("PNG", ".png", True), "webp": ("WEBP", ".webp", True),
    "avif": ("AVIF", ".avif", True), "gif": ("GIF", ".gif", True), "bmp": ("BMP", ".bmp", False),
    "tiff": ("TIFF", ".tiff", True), "ico": ("ICO", ".ico", True), "pdf": ("PDF", ".pdf", False),
    "heic": ("HEIF", ".heic", True),
}
FORMAT_CHOICES = [["same", "Keep format"], ["jpg", "JPG"], ["png", "PNG"], ["webp", "WebP"], ["avif", "AVIF"]]
MM_PER_IN = 25.4


def load_image(path: Path) -> Image.Image:
    if path.suffix.lower() == ".svg":
        import cairosvg

        return Image.open(io.BytesIO(cairosvg.svg2png(url=str(path), output_width=2000)))
    try:
        im = Image.open(path)
        im.load()
        return im
    except Exception as e:  # noqa: BLE001
        raise ToolError(f"Can't read image {path.name}") from e


def oriented(path: Path) -> Image.Image:
    return ImageOps.exif_transpose(load_image(path))


def flatten(im: Image.Image, bg=(255, 255, 255)) -> Image.Image:
    if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
        im = im.convert("RGBA")
        base = Image.new("RGB", im.size, bg)
        base.paste(im, mask=im.getchannel("A"))
        return base
    return im.convert("RGB")


def fmt_for(path: Path, choice: str) -> str:
    if choice and choice != "same":
        return choice
    ext = path.suffix.lower().lstrip(".")
    return {"jpeg": "jpg", "jfif": "jpg", "tif": "tiff", "heif": "jpg", "heic": "jpg", "svg": "png",
            "psd": "png"}.get(ext, ext if ext in FORMATS else "jpg")


def encode(im: Image.Image, fmt: str, quality: int = 88, dpi: tuple | None = None) -> bytes:
    pil, _, alpha = FORMATS[fmt]
    if not alpha or fmt == "jpg":
        im = flatten(im)
    elif fmt == "gif":
        im = im.convert("RGBA") if im.mode in ("RGBA", "LA", "P") else im.convert("RGB")
    elif im.mode not in ("RGB", "RGBA", "L", "LA"):
        im = im.convert("RGBA")
    kw: dict = {}
    if fmt == "jpg":
        kw = {"quality": quality, "optimize": True, "progressive": True, "subsampling": 2 if quality < 90 else 0}
    elif fmt in ("webp", "avif", "heic"):
        kw = {"quality": quality}
    elif fmt == "png":
        kw = {"optimize": True}
    elif fmt == "ico":
        kw = {"sizes": [(s, s) for s in (16, 32, 48, 64, 128, 256) if s <= max(im.size)] or [(16, 16)]}
    elif fmt == "tiff":
        kw = {"compression": "tiff_lzw"}
    if dpi and fmt in ("jpg", "png", "tiff"):
        kw["dpi"] = dpi
    b = io.BytesIO()
    try:
        im.save(b, pil, **kw)
    except (KeyError, OSError) as e:
        raise ToolError(f"{fmt.upper()} output is not supported here") from e
    return b.getvalue()


def pngquant(im: Image.Image, qmin: int, qmax: int) -> bytes | None:
    """Palette-reduce with pngquant (dithered, perceptual). None if the quality floor can't be met."""
    src = io.BytesIO()
    im.convert("RGBA" if im.mode in ("RGBA", "LA", "P") else "RGB").save(src, "PNG")
    try:
        proc = subprocess.run(["pngquant", f"--quality={max(0, qmin)}-{min(100, qmax)}", "--speed", "3", "--strip", "-"],
                              input=src.getvalue(), capture_output=True, timeout=120)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return proc.stdout if proc.returncode == 0 and proc.stdout else None


SCALES = [1, 0.9, 0.8, 0.7, 0.6, 0.5, 0.42, 0.35, 0.3, 0.25, 0.2, 0.16, 0.12, 0.1, 0.08, 0.06]


def _fit_quality(im, fmt, max_b, lo, hi, dpi):
    """Highest quality in [lo, hi] whose encoding fits max_b, or None."""
    best = None
    while lo <= hi:
        q = (lo + hi) // 2
        d = encode(im, fmt, q, dpi)
        if len(d) <= max_b:
            best, lo = d, q + 1
        else:
            hi = q - 1
    return best


def encode_sized(im: Image.Image, fmt: str, max_b: int = 0, min_b: int = 0, quality: int = 88,
                 dpi: tuple | None = None, allow_resize: bool = True) -> tuple[bytes, dict]:
    """Encode so the file lands within [min_b, max_b] bytes.

    Visual quality first: JPEG/WebP quality never drops below 50 while there is room to shrink the pixel
    dimensions instead (a smaller clean image beats a full-size blocky one). Only if even a tiny image
    can't fit does quality go lower. PNG uses pngquant, then shrinks.
    """
    lossy = fmt in ("jpg", "webp", "avif", "heic")
    data = encode(im, fmt, quality, dpi)
    info: dict = {}
    if max_b and len(data) > max_b:
        scales = SCALES if allow_resize else [1]
        done = None
        for k in scales:
            work = im if k == 1 else im.resize((max(16, round(im.width * k)), max(16, round(im.height * k))), Image.LANCZOS)
            if lossy:
                done = _fit_quality(work, fmt, max_b, 50, min(quality, 92), dpi)
            else:
                d = encode(work, fmt, quality, dpi)
                if len(d) > max_b and fmt == "png":
                    d = pngquant(work, 40, 90) or d
                done = d if len(d) <= max_b else None
            if done is not None:
                if k != 1:
                    info["resized"] = f"{work.width}×{work.height}"
                break
        if done is None:  # last resort: lower quality on the smallest candidate
            work = im if not allow_resize else im.resize((max(16, round(im.width * scales[-1])), max(16, round(im.height * scales[-1]))), Image.LANCZOS)
            if lossy:
                done = _fit_quality(work, fmt, max_b, 10, 49, dpi) or encode(work, fmt, 10, dpi)
            else:
                done = pngquant(work, 0, 60) or encode(work, fmt, quality, dpi)
            info["low-quality"] = "1"
        data = done
    if min_b and len(data) < min_b and lossy:
        for q in (90, 94, 97, 100):
            d = encode(im, fmt, q, dpi)
            if len(d) >= min_b and (not max_b or len(d) <= max_b):
                data = d
                break
            if not max_b or len(d) <= max_b:
                data = d
        if len(data) < min_b:  # pad with a JPEG/EXIF-safe comment block to satisfy portal minimums
            if fmt == "jpg":
                pad = min_b - len(data) + 16
                chunks = b""
                while pad > 0:
                    n = min(pad, 65000)
                    chunks += b"\xff\xfe" + (n + 2).to_bytes(2, "big") + b" " * n
                    pad -= n + 4
                data = data[:2] + chunks + data[2:]
                info["padded"] = "1"
    info["size"] = len(data)
    return data, info


def size_opts(default_max: float | str = "", unit: str = "kb", show_min: bool = True) -> list[dict]:
    mx = {"name": "max_size", "label": "Max file size", "type": "number", "min": 0, "default": default_max,
          "half": True, "placeholder": "no limit"}
    un = {"name": "size_unit", "label": "Unit", "type": "segmented", "default": unit, "half": not show_min,
          "choices": [["kb", "KB"], ["mb", "MB"]]}
    if not show_min:
        return [mx, un]
    mn = {"name": "min_size", "label": "Min file size", "type": "number", "min": 0, "default": "", "half": True,
          "placeholder": "optional"}
    return [mn, mx, un]


def limits(opts: dict) -> tuple[int, int]:
    mx = target_bytes(opts, "max_size", "size_unit")
    mn = target_bytes(opts, "min_size", "size_unit")
    if mx and mn and mn > mx:
        raise ToolError("Minimum size is larger than the maximum.")
    return mx, mn


def write(work: Path, src: Path, data: bytes, fmt: str, tag: str = "") -> Path:
    p = out_path(work, src, FORMATS[fmt][1], tag)
    p.write_bytes(data)
    return p


# --------------------------------------------------------------------------- #
# Dimensions & ratios
# --------------------------------------------------------------------------- #

UNITS = [["px", "px"], ["percent", "%"], ["mm", "mm"], ["cm", "cm"], ["in", "inch"]]


def to_px(v: float, unit: str, dpi: float, base: int) -> int:
    if unit == "percent":
        return round(base * v / 100)
    if unit == "mm":
        return round(v / MM_PER_IN * dpi)
    if unit == "cm":
        return round(v * 10 / MM_PER_IN * dpi)
    if unit == "in":
        return round(v * dpi)
    return round(v)


def parse_ratio(s: str) -> float | None:
    s = (s or "").replace("x", ":").replace("×", ":").replace("/", ":").strip()
    if not s or s == "free":
        return None
    try:
        a, b = (float(x) for x in s.split(":"))
        return a / b if a > 0 and b > 0 else None
    except ValueError as e:
        raise ToolError(f"Ratio '{s}' should look like 16:9") from e


@lru_cache(maxsize=1)
def _face_cascade():
    import cv2

    return cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")


def faces(im: Image.Image) -> list[tuple[int, int, int, int]]:
    import cv2
    import numpy as np

    g = np.array(im.convert("L"))
    k = 1000 / max(g.shape)
    small = cv2.resize(g, None, fx=k, fy=k) if k < 1 else g
    k = min(k, 1)
    found = _face_cascade().detectMultiScale(small, scaleFactor=1.1, minNeighbors=5, minSize=(24, 24))
    return [(int(x / k), int(y / k), int(w / k), int(h / k)) for (x, y, w, h) in found]


def crop_to_ratio(im: Image.Image, ratio: float, anchor: str = "center") -> Image.Image:
    W, H = im.size
    if W / H > ratio:
        nw, nh = round(H * ratio), H
    else:
        nw, nh = W, round(W / ratio)
    cx, cy = W / 2, H / 2
    if anchor == "face":
        fs = faces(im)
        if fs:
            x, y, w, h = max(fs, key=lambda f: f[2] * f[3])
            cx, cy = x + w / 2, y + h * 0.65  # leave room for shoulders
        else:
            anchor = "top" if H > W else "center"
    if anchor == "top":
        cy = nh / 2
    elif anchor == "bottom":
        cy = H - nh / 2
    elif anchor == "left":
        cx = nw / 2
    elif anchor == "right":
        cx = W - nw / 2
    left = int(min(max(cx - nw / 2, 0), W - nw))
    top = int(min(max(cy - nh / 2, 0), H - nh))
    return im.crop((left, top, left + nw, top + nh))


def frame_portrait(im: Image.Image, ratio: float, head_share: float = 0.70) -> Image.Image:
    """Head-and-shoulders framing used by passport/visa rules: head (chin to crown) ≈ 70% of the photo height,
    face centred horizontally, clear space above the hair. When the original has too little room around the head,
    the canvas is extended with the photo's own background colour instead of cutting the hair."""
    import numpy as np

    fs = faces(im)
    if not fs:
        return crop_to_ratio(im, ratio, "top" if im.height > im.width else "center")
    W, H = im.size
    x, y, w, h = max(fs, key=lambda f: f[2] * f[3])
    head = h * 1.5  # Haar box spans brows→chin; hair and crown add ~50%
    ch = head / head_share
    cw = ch * ratio
    cx = x + w / 2
    crown = y - h * 0.5
    left, top = cx - cw / 2, crown - (ch - head) * 0.38
    pl, pt_, pr, pb = max(0, -left), max(0, -top), max(0, left + cw - W), max(0, top + ch - H)
    if pl or pt_ or pr or pb:
        rgb_im = im.convert("RGB")
        strip = np.array(rgb_im.crop((0, 0, W, max(4, H // 30)))).reshape(-1, 3)
        fill = tuple(int(v) for v in np.median(strip, axis=0))
        canvas = Image.new("RGB", (round(W + pl + pr), round(H + pt_ + pb)), fill)
        canvas.paste(rgb_im, (round(pl), round(pt_)))
        im, left, top = canvas, left + pl, top + pt_
    return im.crop((round(left), round(top), round(left + cw), round(top + ch)))


def pad_to_ratio(im: Image.Image, ratio: float, color) -> Image.Image:
    W, H = im.size
    if W / H > ratio:
        nw, nh = W, round(W / ratio)
    else:
        nw, nh = round(H * ratio), H
    mode = "RGBA" if color is None else "RGB"
    base = Image.new(mode, (nw, nh), (0, 0, 0, 0) if color is None else color)
    src = im.convert("RGBA")
    base.paste(src, ((nw - W) // 2, (nh - H) // 2), src)
    return base


def rgb(value: str):
    return tuple(int(c * 255) for c in hex_color(value))


def fit_box(im: Image.Image, w: int, h: int, mode: str, bg, anchor: str = "center") -> Image.Image:
    if mode == "stretch":
        return im.resize((w, h), Image.LANCZOS)
    if mode == "fill":
        return crop_to_ratio(im, w / h, anchor).resize((w, h), Image.LANCZOS)
    t = im.copy()
    t.thumbnail((w, h), Image.LANCZOS)
    if t.size != (w, h) and w >= t.width and h >= t.height:
        t = t.resize((min(w, round(t.width * min(w / t.width, h / t.height))),
                      min(h, round(t.height * min(w / t.width, h / t.height)))), Image.LANCZOS)
    base = Image.new("RGBA" if bg is None else "RGB", (w, h), (0, 0, 0, 0) if bg is None else bg)
    src = t.convert("RGBA")
    base.paste(src, ((w - t.width) // 2, (h - t.height) // 2), src)
    return base


# --------------------------------------------------------------------------- #
# Compression
# --------------------------------------------------------------------------- #


@tool(
    id="compress-image", name="Compress image", category="image", glyph="compress",
    description="Shrink JPG, PNG, WebP and HEIC photos with a quality you control.",
    keywords="reduce optimize smaller jpeg png",
    accept=IMG_IN, multiple=True,
    options=[
        {"name": "quality", "label": "Quality", "type": "range", "min": 10, "max": 95, "default": 72},
        {"name": "format", "label": "Output", "type": "segmented", "default": "same", "choices": FORMAT_CHOICES[:4]},
        {"name": "max_dim", "label": "Longest side (px)", "type": "number", "min": 0, "default": "", "placeholder": "keep"},
        {"name": "strip", "label": "Remove EXIF / GPS metadata", "type": "checkbox", "default": True},
    ],
)
def compress_image(files, opts, work):
    q = int(num(opts, "quality", 72))
    md = int(num(opts, "max_dim"))
    total = sum(f.stat().st_size for f in files)

    def one(f):
        im = oriented(f)
        if md:
            im.thumbnail((md, md), Image.LANCZOS)
        fmt = fmt_for(f, opts.get("format"))
        data = encode(im, fmt, q)
        if fmt == "png":  # palette reduction only when pngquant can keep the requested quality
            pq = pngquant(im, max(0, q - 25), min(100, q + 10))
            if pq and len(pq) < len(data):
                data = pq
        if len(data) >= f.stat().st_size and fmt_for(f, "same") == fmt:
            data = f.read_bytes()
        return write(work, f, data, fmt, "compressed")

    res = for_each(files, work, one, "compressed_images.zip")
    res.original_size = total
    return res


@tool(
    id="image-to-size", name="Compress image to KB", category="image", glyph="target", popular=True,
    description="Land between an exact min and max — 20–50 KB, under 100 KB, under 1 MB…",
    keywords="kb mb exact size limit form upload resize photo 20kb 50kb 100kb",
    accept=IMG_IN, multiple=True,
    options=[
        {"name": "preset", "label": "Quick pick", "type": "chips", "default": "",
         "choices": [["10-20", "10–20 KB"], ["20-50", "20–50 KB"], ["50", "≤ 50 KB"], ["100", "≤ 100 KB"],
                     ["200", "≤ 200 KB"], ["500", "≤ 500 KB"], ["1024", "≤ 1 MB"], ["2048", "≤ 2 MB"]],
         "sets": {"10-20": {"min_size": 10, "max_size": 20, "size_unit": "kb"},
                  "20-50": {"min_size": 20, "max_size": 50, "size_unit": "kb"},
                  "50": {"min_size": "", "max_size": 50, "size_unit": "kb"},
                  "100": {"min_size": "", "max_size": 100, "size_unit": "kb"},
                  "200": {"min_size": "", "max_size": 200, "size_unit": "kb"},
                  "500": {"min_size": "", "max_size": 500, "size_unit": "kb"},
                  "1024": {"min_size": "", "max_size": 1, "size_unit": "mb"},
                  "2048": {"min_size": "", "max_size": 2, "size_unit": "mb"}}},
        *size_opts(default_max=100),
        {"name": "format", "label": "Output", "type": "segmented", "default": "jpg",
         "choices": [["jpg", "JPG"], ["webp", "WebP"], ["png", "PNG"]]},
        {"name": "keep_dims", "label": "Never change pixel dimensions", "type": "checkbox", "default": False,
         "help": "Only quality is lowered; the target may be missed for very large images."},
    ],
)
def image_to_size(files, opts, work):
    mx, mn = limits(opts)
    if not mx and not mn:
        raise ToolError("Set a maximum or minimum size.")
    fmt = opts.get("format") if opts.get("format") in ("jpg", "webp", "png") else "jpg"
    notes, resized = [], []

    def one(f):
        im = oriented(f)
        data, info = encode_sized(im, fmt, mx, mn, 92, allow_resize=not opts.get("keep_dims"))
        if mx and len(data) > mx or mn and len(data) < mn:
            notes.append(f"{f.name}: {fmt_size(len(data))}")
        if info.get("resized"):
            resized.append(f"{f.name} → {info['resized']} px")
        return write(work, f, data, fmt, "sized")

    res = for_each(files, work, one, "sized_images.zip")
    res.original_size = sum(f.stat().st_size for f in files)
    msg = []
    if notes:
        msg.append("Couldn't fully reach the range: " + ", ".join(notes))
    if resized:
        msg.append("Pixel size reduced to keep it sharp: " + ", ".join(resized))
    res.meta = {"target-met": "0" if notes else "1", "note": ". ".join(msg)}
    return res


# --------------------------------------------------------------------------- #
# Resize / crop / ratio
# --------------------------------------------------------------------------- #

RATIOS = [["free", "Free"], ["1:1", "1:1 Square"], ["4:5", "4:5 Portrait post"], ["9:16", "9:16 Story / Reel"],
          ["16:9", "16:9 Widescreen"], ["4:3", "4:3"], ["3:4", "3:4"], ["3:2", "3:2 Photo"], ["2:3", "2:3"],
          ["35:45", "35:45 Passport"], ["21:9", "21:9 Cinema"], ["3:1", "3:1 Banner"], ["custom", "Custom W:H"]]


@tool(
    id="resize-image", name="Resize image", category="image", glyph="ratio", popular=True,
    description="Exact width × height in px, %, mm, cm or inches — with optional max KB.",
    keywords="dimension pixel cm mm inch dpi scale width height aspect ratio",
    accept=IMG_IN, multiple=True,
    options=[
        {"name": "unit", "label": "Units", "type": "segmented", "default": "px", "choices": UNITS},
        {"name": "width", "label": "Width", "type": "number", "min": 0, "default": 1080, "half": True, "placeholder": "auto"},
        {"name": "height", "label": "Height", "type": "number", "min": 0, "default": "", "half": True, "placeholder": "auto"},
        {"name": "dpi", "label": "DPI (for mm / cm / inch)", "type": "number", "min": 30, "max": 1200, "default": 300,
         "when": {"unit": ["mm", "cm", "in"]}},
        {"name": "mode", "label": "When both sides are set", "type": "segmented", "default": "fill",
         "choices": [["fill", "Crop to fill"], ["fit", "Fit + pad"], ["stretch", "Stretch"]]},
        {"name": "bg", "label": "Pad colour", "type": "color", "default": "#ffffff", "when": {"mode": "fit"}},
        {"name": "format", "label": "Output", "type": "segmented", "default": "same", "choices": FORMAT_CHOICES[:4]},
        *size_opts(show_min=False),
    ],
)
def resize_image(files, opts, work):
    unit = opts.get("unit", "px")
    dpi = num(opts, "dpi", 300) if unit in ("mm", "cm", "in") else 0
    mx, _ = limits(opts)

    def one(f):
        im = oriented(f)
        W, H = im.size
        w = to_px(num(opts, "width"), unit, dpi, W) if num(opts, "width") else 0
        h = to_px(num(opts, "height"), unit, dpi, H) if num(opts, "height") else 0
        if not w and not h:
            raise ToolError("Enter a width or a height.")
        if w and not h:
            h = round(H * w / W)
        elif h and not w:
            w = round(W * h / H)
        if w > 20000 or h > 20000:
            raise ToolError("That's larger than 20 000 px.")
        im2 = fit_box(im, max(1, w), max(1, h), opts.get("mode", "fill"), rgb(opts.get("bg", "#ffffff")))
        fmt = fmt_for(f, opts.get("format"))
        data, _ = encode_sized(im2, fmt, mx, 0, 90, (dpi, dpi) if dpi else None, allow_resize=False)
        return write(work, f, data, fmt, f"{w}x{h}")

    return for_each(files, work, one, "resized_images.zip")


@tool(
    id="crop-ratio", name="Crop to aspect ratio", category="image", glyph="crop",
    description="1:1, 4:5, 9:16, 16:9, passport or any W:H — crop or pad, face-aware.",
    keywords="aspect ratio square instagram story reel youtube thumbnail height width",
    accept=IMG_IN, multiple=True,
    options=[
        {"name": "ratio", "label": "Ratio", "type": "select", "default": "1:1", "choices": RATIOS[1:]},
        {"name": "custom", "label": "Custom ratio (W:H)", "type": "text", "default": "5:7", "when": {"ratio": "custom"}},
        {"name": "mode", "label": "Method", "type": "segmented", "default": "crop",
         "choices": [["crop", "Crop"], ["pad", "Pad"], ["blur", "Blurred pad"]]},
        {"name": "anchor", "label": "Keep", "type": "segmented", "default": "face", "when": {"mode": "crop"},
         "choices": [["face", "Face"], ["center", "Centre"], ["top", "Top"], ["bottom", "Bottom"]]},
        {"name": "bg", "label": "Pad colour", "type": "color", "default": "#ffffff", "when": {"mode": "pad"}},
        {"name": "width", "label": "Final width (px)", "type": "number", "min": 0, "default": "", "placeholder": "keep"},
        {"name": "format", "label": "Output", "type": "segmented", "default": "same", "choices": FORMAT_CHOICES[:4]},
    ],
)
def crop_ratio(files, opts, work):
    ratio = parse_ratio(opts.get("custom") if opts.get("ratio") == "custom" else opts.get("ratio"))
    if not ratio:
        raise ToolError("Pick a ratio.")
    mode = opts.get("mode", "crop")

    def one(f):
        im = oriented(f)
        if mode == "crop":
            out = crop_to_ratio(im, ratio, opts.get("anchor", "center"))
        elif mode == "pad":
            out = pad_to_ratio(im, ratio, rgb(opts.get("bg")))
        else:
            W, H = im.size
            nw, nh = (W, round(W / ratio)) if W / H > ratio else (round(H * ratio), H)
            bg = crop_to_ratio(im.convert("RGB"), ratio).resize((nw, nh)).filter(ImageFilter.GaussianBlur(max(nw, nh) / 30))
            bg = ImageEnhance.Brightness(bg).enhance(0.85)
            src = im.convert("RGBA")
            bg.paste(src, ((nw - W) // 2, (nh - H) // 2), src)
            out = bg
        tw = int(num(opts, "width"))
        if tw:
            out = out.resize((tw, round(tw / ratio)), Image.LANCZOS)
        fmt = fmt_for(f, opts.get("format"))
        return write(work, f, encode(out, fmt, 90), fmt, (opts.get("ratio") or "").replace(":", "x"))

    return for_each(files, work, one, "cropped_images.zip")


# Form photo presets: width, height, unit, dpi, min KB, max KB, background
FORM_PRESETS = {
    "passport-35x45": (35, 45, "mm", 300, 0, 0),
    "us-2x2": (2, 2, "in", 300, 0, 240),
    "visa-33x48": (33, 48, "mm", 300, 0, 0),
    "canada-50x70": (50, 70, "mm", 300, 0, 0),
    "exam-photo": (200, 230, "px", 200, 20, 50),
    "exam-sign": (140, 60, "px", 200, 10, 20),
    "photo-3.5x4.5-kb": (3.5, 4.5, "cm", 200, 20, 50),
    "sign-4x2-kb": (4, 2, "cm", 200, 10, 20),
    "thumb-1x1": (600, 600, "px", 300, 0, 100),
}


@tool(
    id="form-photo", name="Photo & signature for forms", category="image", glyph="id", popular=True,
    description="Passport, visa and exam-portal specs in one step: exact size, ratio, KB range and white background.",
    keywords="passport visa id photo signature exam govt application 35x45 2x2 kb upload",
    accept=IMG_IN, capture=True,
    options=[
        {"name": "preset", "label": "Specification", "type": "select", "default": "passport-35x45",
         "choices": [["passport-35x45", "Passport 35 × 45 mm (UK, EU, India…)"], ["us-2x2", "US passport / visa 2 × 2 in, ≤ 240 KB"],
                     ["visa-33x48", "Visa 33 × 48 mm"], ["canada-50x70", "Canada 50 × 70 mm"],
                     ["exam-photo", "Exam photo 200 × 230 px, 20–50 KB"], ["exam-sign", "Exam signature 140 × 60 px, 10–20 KB"],
                     ["photo-3.5x4.5-kb", "Photo 3.5 × 4.5 cm, 20–50 KB"], ["sign-4x2-kb", "Signature 4 × 2 cm, 10–20 KB"],
                     ["thumb-1x1", "Profile 600 × 600 px, ≤ 100 KB"], ["custom", "Custom…"]],
         "sets": {k: {"width": v[0], "height": v[1], "unit": v[2], "dpi": v[3], "min_size": v[4] or "", "max_size": v[5] or "",
                      "size_unit": "kb"} for k, v in FORM_PRESETS.items()}},
        {"name": "unit", "label": "Units", "type": "segmented", "default": "mm",
         "choices": [["px", "px"], ["mm", "mm"], ["cm", "cm"], ["in", "inch"]]},
        {"name": "width", "label": "Width", "type": "number", "min": 1, "default": 35, "half": True},
        {"name": "height", "label": "Height", "type": "number", "min": 1, "default": 45, "half": True},
        {"name": "dpi", "label": "DPI", "type": "number", "min": 72, "max": 1200, "default": 300},
        *size_opts(default_max=""),
        {"name": "subject", "label": "Subject", "type": "segmented", "default": "face",
         "choices": [["face", "Face photo"], ["signature", "Signature"]]},
        {"name": "framing", "label": "Framing", "type": "segmented", "default": "passport", "when": {"subject": "face"},
         "choices": [["passport", "Head & shoulders"], ["full", "Whole photo"]]},
        {"name": "whiten", "label": "Replace background with white (AI)", "type": "checkbox", "default": False,
         "when": {"subject": "face"}},
        {"name": "clean", "label": "Clean up paper (pure white, dark ink)", "type": "checkbox", "default": True,
         "when": {"subject": "signature"}},
    ],
)
def form_photo(files, opts, work):
    f = files[0]
    unit = opts.get("unit", "mm")
    dpi = num(opts, "dpi", 300)
    im = oriented(f)
    w = to_px(num(opts, "width"), unit, dpi, im.width)
    h = to_px(num(opts, "height"), unit, dpi, im.height)
    if w < 10 or h < 10:
        raise ToolError("Width and height are required.")
    if opts.get("subject") == "signature":
        if opts.get("clean"):
            g = ImageOps.autocontrast(im.convert("L"), cutoff=2)
            g = g.point(lambda p: 255 if p > 170 else int(p * 0.6))
            im = g.convert("RGB")
        bbox = ImageOps.invert(im.convert("L")).point(lambda p: 255 if p > 40 else 0).getbbox()
        if bbox:
            pad = int(max(bbox[2] - bbox[0], bbox[3] - bbox[1]) * 0.06)
            im = im.crop((max(0, bbox[0] - pad), max(0, bbox[1] - pad), min(im.width, bbox[2] + pad), min(im.height, bbox[3] + pad)))
        out = fit_box(im, w, h, "fit", (255, 255, 255))
    else:
        framed = frame_portrait(im, w / h) if opts.get("framing", "passport") == "passport" else crop_to_ratio(im, w / h, "face")
        if opts.get("whiten"):  # after framing: same composition, and the cut-out runs on fewer pixels
            framed = remove_bg_image(framed, (255, 255, 255))
        out = framed.resize((w, h), Image.LANCZOS)
    mx, mn = limits(opts)
    data, info = encode_sized(out, "jpg", mx, mn, 95, (dpi, dpi), allow_resize=False)
    dest = work / "out" / f"{f.stem}_{w}x{h}.jpg"
    dest.write_bytes(data)
    met = (not mx or len(data) <= mx) and (not mn or len(data) >= mn)
    note = f"{w} × {h} px at {int(dpi)} dpi · {fmt_size(len(data))}"
    return Result("file", dest, original_size=f.stat().st_size, meta={"target-met": "1" if met else "0", "note": note})


# --------------------------------------------------------------------------- #
# Convert / transform
# --------------------------------------------------------------------------- #


@tool(
    id="convert-image", name="Convert image", category="image", glyph="convert", popular=True,
    description="HEIC, WebP, AVIF, PNG, JPG, GIF, BMP, TIFF, SVG, ICO — any to any.",
    keywords="heic to jpg webp to png avif ico favicon svg format",
    accept=IMG_IN, multiple=True,
    options=[
        {"name": "format", "label": "Convert to", "type": "select", "default": "jpg",
         "choices": [["jpg", "JPG"], ["png", "PNG"], ["webp", "WebP"], ["avif", "AVIF"], ["gif", "GIF"], ["bmp", "BMP"],
                     ["tiff", "TIFF"], ["ico", "ICO (favicon)"], ["heic", "HEIC"], ["pdf", "PDF"]]},
        {"name": "quality", "label": "Quality", "type": "range", "min": 30, "max": 100, "default": 90,
         "when": {"format": ["jpg", "webp", "avif", "heic"]}},
        {"name": "bg", "label": "Background for transparency", "type": "color", "default": "#ffffff",
         "when": {"format": ["jpg", "bmp", "pdf"]}},
    ],
)
def convert_image(files, opts, work):
    fmt = opts.get("format", "jpg")
    if fmt not in FORMATS:
        raise ToolError("Unknown format.")
    q = int(num(opts, "quality", 90))

    def one(f):
        im = oriented(f)
        if not FORMATS[fmt][2]:
            im = flatten(im, rgb(opts.get("bg", "#ffffff")))
        if fmt == "ico":
            im.thumbnail((256, 256))
        return write(work, f, encode(im, fmt, q), fmt)

    return for_each(files, work, one, f"converted_{fmt}.zip")


@tool(
    id="rotate-image", name="Rotate & flip image", category="image", glyph="rotate",
    description="Turn by any angle, mirror horizontally or vertically, or auto-fix EXIF orientation.",
    accept=IMG_IN, multiple=True,
    options=[
        {"name": "angle", "label": "Rotate", "type": "segmented", "default": "90",
         "choices": [["0", "0°"], ["90", "90° ↻"], ["180", "180°"], ["270", "90° ↺"], ["custom", "Custom"]]},
        {"name": "custom", "label": "Angle (°, clockwise)", "type": "number", "default": 15, "when": {"angle": "custom"}},
        {"name": "flip", "label": "Mirror", "type": "segmented", "default": "none",
         "choices": [["none", "None"], ["h", "Horizontal"], ["v", "Vertical"]]},
    ],
)
def rotate_image(files, opts, work):
    ang = num(opts, "custom") if opts.get("angle") == "custom" else num(opts, "angle")

    def one(f):
        im = oriented(f)
        if ang % 360:
            fill = (255, 255, 255, 0) if im.mode in ("RGBA", "LA", "P") else (255, 255, 255)
            im = im.rotate(-ang, expand=True, resample=Image.BICUBIC, fillcolor=fill)
        if opts.get("flip") == "h":
            im = ImageOps.mirror(im)
        elif opts.get("flip") == "v":
            im = ImageOps.flip(im)
        fmt = fmt_for(f, "same")
        return write(work, f, encode(im, fmt, 92), fmt, "rotated")

    return for_each(files, work, one, "rotated_images.zip")


@tool(
    id="image-filters", name="Adjust & filters", category="image", glyph="sliders",
    description="Brightness, contrast, saturation, sharpen, blur, grayscale, sepia or invert.",
    keywords="edit photo enhance black white",
    accept=IMG_IN, multiple=True,
    options=[
        {"name": "brightness", "label": "Brightness", "type": "range", "min": 20, "max": 200, "default": 100, "unit": "%"},
        {"name": "contrast", "label": "Contrast", "type": "range", "min": 20, "max": 200, "default": 100, "unit": "%"},
        {"name": "saturation", "label": "Saturation", "type": "range", "min": 0, "max": 200, "default": 100, "unit": "%"},
        {"name": "sharpen", "label": "Sharpen", "type": "range", "min": 0, "max": 300, "default": 0, "unit": "%"},
        {"name": "blur", "label": "Blur", "type": "range", "min": 0, "max": 30, "default": 0, "unit": "px"},
        {"name": "effect", "label": "Effect", "type": "segmented", "default": "none",
         "choices": [["none", "None"], ["gray", "B&W"], ["sepia", "Sepia"], ["invert", "Invert"]]},
    ],
)
def image_filters(files, opts, work):
    def one(f):
        im = oriented(f)
        alpha = im.getchannel("A") if im.mode == "RGBA" else None
        im = im.convert("RGB")
        im = ImageEnhance.Brightness(im).enhance(num(opts, "brightness", 100) / 100)
        im = ImageEnhance.Contrast(im).enhance(num(opts, "contrast", 100) / 100)
        im = ImageEnhance.Color(im).enhance(num(opts, "saturation", 100) / 100)
        if num(opts, "sharpen"):
            im = im.filter(ImageFilter.UnsharpMask(2, int(num(opts, "sharpen")), 2))
        if num(opts, "blur"):
            im = im.filter(ImageFilter.GaussianBlur(num(opts, "blur")))
        eff = opts.get("effect")
        if eff == "gray":
            im = im.convert("L").convert("RGB")
        elif eff == "sepia":
            g = im.convert("L")
            im = ImageOps.colorize(g, (40, 26, 13), (255, 240, 205))
        elif eff == "invert":
            im = ImageOps.invert(im)
        if alpha is not None:
            im.putalpha(alpha)
        fmt = fmt_for(f, "same")
        return write(work, f, encode(im, fmt, 92), fmt, "edited")

    return for_each(files, work, one, "edited_images.zip")


def _font(size: int, bold: bool = True):
    name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    try:
        return ImageFont.truetype(f"/usr/share/fonts/truetype/dejavu/{name}", size)
    except OSError:
        return ImageFont.load_default()


POS9 = [["tl", "↖"], ["tc", "↑"], ["tr", "↗"], ["ml", "←"], ["c", "•"], ["mr", "→"], ["bl", "↙"], ["bc", "↓"], ["br", "↘"], ["tile", "Tile"]]


def _place(W, H, w, h, pos, m):
    col = {"l": m, "c": (W - w) // 2, "r": W - w - m}
    row = {"t": m, "m": (H - h) // 2, "b": H - h - m}
    if pos == "c":
        return (W - w) // 2, (H - h) // 2
    return col[pos[1] if pos[1] in col else "c"], row[pos[0]]


@tool(
    id="watermark-image", name="Watermark image", category="image", glyph="watermark",
    description="Stamp text or your logo on photos — corner, centre or tiled.",
    keywords="copyright logo brand",
    accept=IMG_IN, multiple=True,
    options=[
        {"name": "kind", "label": "Watermark", "type": "segmented", "default": "text", "choices": [["text", "Text"], ["image", "Logo"]]},
        {"name": "text", "label": "Text", "type": "text", "default": "© Folio", "when": {"kind": "text"}},
        {"name": "asset", "label": "Logo image", "type": "file", "accept": "image/*", "when": {"kind": "image"}},
        {"name": "color", "label": "Colour", "type": "color", "default": "#ffffff", "when": {"kind": "text"}},
        {"name": "size", "label": "Size", "type": "range", "min": 2, "max": 60, "default": 6, "unit": "%"},
        {"name": "opacity", "label": "Opacity", "type": "range", "min": 5, "max": 100, "default": 55, "unit": "%"},
        {"name": "position", "label": "Position", "type": "grid9", "default": "br", "choices": POS9},
    ],
)
def watermark_image(files, opts, work):
    op = num(opts, "opacity", 55) / 100
    frac = num(opts, "size", 6) / 100
    logo = None
    if opts.get("kind") == "image":
        if not opts.get("asset"):
            raise ToolError("Choose a logo image.")
        logo = Image.open(opts["asset"]).convert("RGBA")

    def one(f):
        im = oriented(f).convert("RGBA")
        W, H = im.size
        if logo is not None:
            lw = max(8, int(W * frac * 3))
            mark = logo.resize((lw, max(1, int(lw * logo.height / logo.width))), Image.LANCZOS)
        else:
            fs = max(8, int(min(W, H) * frac))
            font = _font(fs)
            tb = ImageDraw.Draw(im).textbbox((0, 0), opts.get("text") or "", font=font, stroke_width=max(1, fs // 18))
            mark = Image.new("RGBA", (tb[2] - tb[0] + 4, tb[3] - tb[1] + 4), (0, 0, 0, 0))
            col = rgb(opts.get("color", "#ffffff"))
            stroke = (0, 0, 0) if sum(col) > 380 else (255, 255, 255)
            ImageDraw.Draw(mark).text((2 - tb[0], 2 - tb[1]), opts.get("text") or "", font=font, fill=col + (255,),
                                      stroke_width=max(1, fs // 18), stroke_fill=stroke + (160,))
        a = mark.getchannel("A").point(lambda v: int(v * op))
        mark.putalpha(a)
        layer = Image.new("RGBA", im.size, (0, 0, 0, 0))
        pos = opts.get("position", "br")
        if pos == "tile":
            sx, sy = mark.width * 2, mark.height * 3
            for y in range(-mark.height, H, sy):
                for x in range(-mark.width + (y // sy % 2) * mark.width, W, sx):
                    layer.paste(mark, (x, y), mark)
        else:
            layer.paste(mark, _place(W, H, mark.width, mark.height, pos, int(min(W, H) * 0.03)), mark)
        out = Image.alpha_composite(im, layer)
        fmt = fmt_for(f, "same")
        return write(work, f, encode(out, fmt, 92), fmt, "wm")

    return for_each(files, work, one, "watermarked_images.zip")


@tool(
    id="meme", name="Meme generator", category="image", glyph="smile",
    description="Classic top and bottom captions in bold outlined type.",
    accept=IMG_IN,
    options=[
        {"name": "top", "label": "Top text", "type": "text", "default": "WHEN THE PDF"},
        {"name": "bottom", "label": "Bottom text", "type": "text", "default": "IS FINALLY UNDER 200 KB"},
        {"name": "size", "label": "Text size", "type": "range", "min": 4, "max": 20, "default": 10, "unit": "%"},
    ],
)
def meme(files, opts, work):
    im = oriented(files[0]).convert("RGB")
    W, H = im.size
    d = ImageDraw.Draw(im)

    def draw(text, top):
        text = (text or "").upper().strip()
        if not text:
            return
        fs = int(H * num(opts, "size", 10) / 100)
        font = _font(fs)
        while fs > 10 and d.textlength(text, font=font) > W * 0.94:
            fs -= 2
            font = _font(fs)
        tw = d.textlength(text, font=font)
        y = int(H * 0.03) if top else H - fs - int(H * 0.05)
        d.text(((W - tw) / 2, y), text, font=font, fill="white", stroke_width=max(2, fs // 14), stroke_fill="black")

    draw(opts.get("top"), True)
    draw(opts.get("bottom"), False)
    return Result("file", write(work, files[0], encode(im, "jpg", 92), "jpg", "meme"))


@tool(
    id="blur-face", name="Blur faces", category="image", glyph="face",
    description="Automatically find faces and blur or pixelate them for privacy.",
    keywords="anonymize privacy pixelate",
    accept=IMG_IN, multiple=True,
    options=[{"name": "style", "label": "Style", "type": "segmented", "default": "blur",
              "choices": [["blur", "Blur"], ["pixel", "Pixelate"], ["box", "Black box"]]}],
)
def blur_face(files, opts, work):
    found_any = False

    def one(f):
        nonlocal found_any
        im = oriented(f).convert("RGB")
        for (x, y, w, h) in faces(im):
            found_any = True
            pad = int(w * 0.15)
            box = (max(0, x - pad), max(0, y - pad), min(im.width, x + w + pad), min(im.height, y + h + pad))
            region = im.crop(box)
            style = opts.get("style", "blur")
            if style == "pixel":
                small = region.resize((max(1, region.width // 14), max(1, region.height // 14)), Image.NEAREST)
                region = small.resize(region.size, Image.NEAREST)
            elif style == "box":
                region = Image.new("RGB", region.size, (0, 0, 0))
            else:
                region = region.filter(ImageFilter.GaussianBlur(max(6, region.width // 7)))
            mask = Image.new("L", region.size, 0)
            ImageDraw.Draw(mask).ellipse((0, 0, *region.size), fill=255) if style == "blur" else mask.paste(255)
            im.paste(region, box[:2], mask)
        fmt = fmt_for(f, "same")
        return write(work, f, encode(im, fmt, 92), fmt, "blurred")

    res = for_each(files, work, one, "blurred_images.zip")
    if not found_any:
        raise ToolError("No faces were detected.")
    return res


_rembg_session = None


def remove_bg_image(im: Image.Image, bg=None) -> Image.Image:
    global _rembg_session
    try:
        from rembg import new_session, remove
    except ImportError as e:
        raise ToolError("Background removal engine is not installed.") from e
    if _rembg_session is None:
        _rembg_session = new_session("isnet-general-use")
    cut = remove(im.convert("RGB"), session=_rembg_session, post_process_mask=True)
    if bg is None:
        return cut
    base = Image.new("RGB", cut.size, bg)
    base.paste(cut, mask=cut.getchannel("A"))
    return base


@tool(
    id="remove-bg", name="Remove background", category="image", glyph="cutout", popular=True,
    description="AI cut-out of people, products and pets — transparent PNG or any colour.",
    keywords="transparent cutout ai product photo",
    accept=IMG_IN, multiple=True,
    options=[
        {"name": "bg", "label": "New background", "type": "segmented", "default": "transparent",
         "choices": [["transparent", "Transparent"], ["white", "White"], ["color", "Colour"]]},
        {"name": "color", "label": "Colour", "type": "color", "default": "#d8401f", "when": {"bg": "color"}},
        {"name": "trim", "label": "Trim empty edges", "type": "checkbox", "default": False},
    ],
)
def remove_bg(files, opts, work):
    def one(f):
        im = oriented(f)
        im.thumbnail((3000, 3000))
        choice = opts.get("bg", "transparent")
        cut = remove_bg_image(im, None)
        if opts.get("trim"):
            bb = cut.getchannel("A").getbbox()
            if bb:
                cut = cut.crop(bb)
        if choice == "transparent":
            return write(work, f, encode(cut, "png"), "png", "nobg")
        col = (255, 255, 255) if choice == "white" else rgb(opts.get("color"))
        base = Image.new("RGB", cut.size, col)
        base.paste(cut, mask=cut.getchannel("A"))
        return write(work, f, encode(base, "jpg", 92), "jpg", "nobg")

    return for_each(files, work, one, "cutouts.zip")


@tool(
    id="upscale-image", name="Enlarge image", category="image", glyph="expand",
    description="Scale up 2×–4× with Lanczos resampling and detail sharpening.",
    keywords="upscale bigger resolution increase",
    accept=IMG_IN, multiple=True,
    options=[{"name": "factor", "label": "Scale", "type": "segmented", "default": "2",
              "choices": [["1.5", "1.5×"], ["2", "2×"], ["3", "3×"], ["4", "4×"]]},
             {"name": "sharpen", "label": "Detail boost", "type": "range", "min": 0, "max": 200, "default": 80, "unit": "%"}],
)
def upscale_image(files, opts, work):
    k = num(opts, "factor", 2)

    def one(f):
        im = oriented(f)
        if im.width * k * im.height * k > 120_000_000:
            raise ToolError("Result would be too large.")
        big = im.resize((int(im.width * k), int(im.height * k)), Image.LANCZOS)
        if num(opts, "sharpen"):
            alpha = big.getchannel("A") if big.mode == "RGBA" else None
            big = big.convert("RGB").filter(ImageFilter.UnsharpMask(radius=1.6 * k, percent=int(num(opts, "sharpen")), threshold=2))
            if alpha is not None:
                big.putalpha(alpha)
        fmt = fmt_for(f, "same")
        return write(work, f, encode(big, fmt, 93), fmt, f"{k:g}x")

    return for_each(files, work, one, "enlarged.zip")


@tool(
    id="strip-exif", name="Remove EXIF & GPS", category="image", glyph="sanitize",
    description="Delete camera, location and date metadata before sharing photos.",
    keywords="privacy metadata location",
    accept=IMG_IN, multiple=True,
)
def strip_exif(files, opts, work):
    def one(f):
        dest = out_path(work, f, f.suffix.lower(), "clean")
        if f.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".heic", ".heif", ".avif", ".gif"):
            # lossless: pixels untouched; orientation is baked in only when the EXIF tag says the image is rotated
            im = Image.open(f)
            if im.getexif().get(0x0112, 1) not in (1, None):
                fmt = fmt_for(f, "same")
                return write(work, f, encode(oriented(f), fmt, 95), fmt, "clean")
            proc = subprocess.run(["exiftool", "-all=", "-o", str(dest), str(f)], capture_output=True, text=True, timeout=120)
            if proc.returncode == 0 and dest.exists():
                return dest
        fmt = fmt_for(f, "same")
        return write(work, f, encode(oriented(f), fmt, 95), fmt, "clean")

    return for_each(files, work, one, "clean_images.zip")


@tool(
    id="metadata-view", name="View file metadata", category="image", glyph="info",
    description="See every EXIF, GPS, camera and document property of a photo, video or PDF.",
    keywords="exif inspect camera gps info properties",
    accept=IMG_IN + [".pdf", ".mp4", ".mov", ".mp3", ".docx", ".m4a", ".wav"], multiple=True,
)
def metadata_view(files, opts, work):
    docs = []
    for f in files:
        proc = subprocess.run(["exiftool", "-G1", "-s", "-a", "-api", "largefilesupport=1", str(f)],
                              capture_output=True, text=True, timeout=60)
        rows = []
        for line in proc.stdout.splitlines():
            if ":" not in line:
                continue
            k, v = line.split(":", 1)
            k = k.strip()
            if "Directory" in k or "FileName" in k or "FilePermissions" in k:
                continue
            rows.append(f"| {k} | {v.strip().replace('|', '/')[:200]} |")
        md = f"# {f.name}\n\n| Tag | Value |\n|---|---|\n" + "\n".join(rows)
        docs.append({"name": f.stem + "_metadata.md", "markdown": md, "title": f.name})
    return Result("markdown", docs=docs)


@tool(
    id="make-gif", name="Make animated GIF", category="image", glyph="film",
    description="Turn a sequence of images into a looping GIF or animated WebP.",
    accept=IMG_IN, multiple=True, min_files=2, reorder=True,
    options=[
        {"name": "delay", "label": "Frame delay", "type": "range", "min": 40, "max": 2000, "default": 500, "unit": " ms"},
        {"name": "width", "label": "Width (px)", "type": "number", "min": 16, "max": 2000, "default": 480},
        {"name": "format", "label": "Format", "type": "segmented", "default": "gif", "choices": [["gif", "GIF"], ["webp", "WebP"]]},
    ],
)
def make_gif(files, opts, work):
    w = int(num(opts, "width", 480))
    frames = []
    first = oriented(files[0])
    h = round(w * first.height / first.width)
    for f in files:
        frames.append(fit_box(oriented(f), w, h, "fit", (255, 255, 255)).convert("RGB"))
    fmt = "webp" if opts.get("format") == "webp" else "gif"
    dest = work / "out" / f"animation.{fmt}"
    kw = {"save_all": True, "append_images": frames[1:], "duration": int(num(opts, "delay", 500)), "loop": 0}
    if fmt == "gif":
        frames = [fr.quantize(256, method=Image.Quantize.MEDIANCUT) for fr in frames]
        kw["append_images"] = frames[1:]
        kw["optimize"] = True
    frames[0].save(dest, "GIF" if fmt == "gif" else "WEBP", **kw)
    return Result("file", dest)


@tool(
    id="image-to-text", name="Image to text (OCR)", category="image", glyph="ocr", capture=True,
    description="Read printed text from photos and screenshots — copy it as Markdown.",
    keywords="ocr extract text read scan screenshot",
    accept=IMG_IN, multiple=True,
    options=[{"name": "lang", "label": "Language", "type": "select", "default": "eng",
              "choices": [["eng", "English"], ["deu", "German"], ["fra", "French"], ["spa", "Spanish"], ["ita", "Italian"],
                          ["por", "Portuguese"], ["hin", "Hindi"], ["eng+hin", "English + Hindi"]]},
             {"name": "layout", "label": "Layout", "type": "segmented", "default": "4",
              "choices": [["4", "Document"], ["3", "Columns"], ["11", "Screenshot / sparse"], ["6", "Single block"]]}],
)
def image_to_text(files, opts, work):
    lang = opts.get("lang") if opts.get("lang") in {"eng", "deu", "fra", "spa", "ita", "por", "hin", "eng+hin"} else "eng"
    docs = []
    for f in files:
        im = oriented(f).convert("L")
        tmp = work / f"{f.stem}.ocr.png"
        im.save(tmp)
        psm = opts.get("layout") if opts.get("layout") in ("3", "4", "6", "11") else "4"
        proc = subprocess.run(["tesseract", str(tmp), "stdout", "-l", lang, "--psm", psm, "-c", "preserve_interword_spaces=1"],
                              capture_output=True, text=True, timeout=300)
        if proc.returncode != 0:
            raise ToolError("OCR failed: " + (proc.stderr.strip().splitlines() or ["unknown"])[-1])
        text = "\n".join(line.rstrip() for line in proc.stdout.splitlines())
        docs.append({"name": f.stem + ".md", "markdown": text.strip(), "title": f.name})
    return Result("markdown", docs=docs)


@tool(
    id="vectorize", name="Image to SVG", category="image", glyph="vector",
    description="Trace logos, icons and drawings into scalable vector SVG.",
    keywords="trace vector logo svg",
    accept=[".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"],
    options=[{"name": "mode", "label": "Colours", "type": "segmented", "default": "color",
              "choices": [["color", "Full colour"], ["binary", "Black & white"]]},
             {"name": "detail", "label": "Detail", "type": "range", "min": 1, "max": 10, "default": 7}],
)
def vectorize(files, opts, work):
    try:
        import vtracer
    except ImportError as e:
        raise ToolError("Vector tracing engine is not installed.") from e
    f = files[0]
    im = oriented(f)
    im.thumbnail((1600, 1600))
    tmp = work / "trace.png"
    im.convert("RGBA").save(tmp)
    dest = out_path(work, f, ".svg")
    d = int(num(opts, "detail", 7))
    vtracer.convert_image_to_svg_py(str(tmp), str(dest), colormode=opts.get("mode", "color"), hierarchical="stacked",
                                    filter_speckle=max(1, 11 - d), color_precision=min(8, max(3, d)), layer_difference=max(4, 30 - d * 3),
                                    mode="spline", corner_threshold=60, length_threshold=4.0, splice_threshold=45,
                                    path_precision=3)
    return Result("file", dest)


@tool(
    id="url-to-image", name="Web page to image", category="image", glyph="globe",
    description="Screenshot any public web page at desktop or phone width.",
    keywords="screenshot website capture html",
    accept=[], min_files=0,
    options=[
        {"name": "url", "label": "URL", "type": "url", "placeholder": "https://", "required": True, "default": ""},
        {"name": "device", "label": "Viewport", "type": "segmented", "default": "desktop",
         "choices": [["desktop", "Desktop 1440"], ["tablet", "Tablet 820"], ["phone", "Phone 390"]]},
        {"name": "height", "label": "Capture height (px)", "type": "number", "min": 400, "max": 12000, "default": 1600},
        {"name": "format", "label": "Format", "type": "segmented", "default": "png", "choices": [["png", "PNG"], ["jpg", "JPG"], ["webp", "WebP"]]},
    ],
)
def url_to_image(files, opts, work):
    from .tools_pdf import chromium

    url = check_public_url(opts.get("url"))
    w = {"desktop": 1440, "tablet": 820, "phone": 390}.get(opts.get("device"), 1440)
    h = int(min(12000, max(400, num(opts, "height", 2400))))
    tmp = work / "shot.png"
    extra = ["--user-agent=Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148"] if w == 390 else []
    chromium([*extra, f"--window-size={w},{h}", f"--screenshot={tmp}", "--force-device-scale-factor=1", url], work)
    if not tmp.exists():
        raise ToolError("The page could not be captured.")
    im = Image.open(tmp)
    fmt = opts.get("format") if opts.get("format") in ("png", "jpg", "webp") else "png"
    dest = work / "out" / f"screenshot.{fmt}"
    dest.write_bytes(encode(im, fmt, 90))
    return Result("file", dest)


@tool(
    id="collage", name="Photo collage", category="image", glyph="grid",
    description="Arrange several photos into a neat grid with spacing and background.",
    accept=IMG_IN, multiple=True, min_files=2, reorder=True,
    options=[
        {"name": "cols", "label": "Columns", "type": "segmented", "default": "2",
         "choices": [["1", "1"], ["2", "2"], ["3", "3"], ["4", "4"]]},
        {"name": "ratio", "label": "Cell ratio", "type": "segmented", "default": "1:1",
         "choices": [["1:1", "1:1"], ["4:5", "4:5"], ["3:2", "3:2"], ["16:9", "16:9"]]},
        {"name": "gap", "label": "Spacing", "type": "range", "min": 0, "max": 60, "default": 12, "unit": "px"},
        {"name": "bg", "label": "Background", "type": "color", "default": "#ffffff"},
        {"name": "width", "label": "Total width (px)", "type": "number", "min": 300, "max": 6000, "default": 1600},
    ],
)
def collage(files, opts, work):
    cols = int(num(opts, "cols", 2))
    gap = int(num(opts, "gap", 12))
    W = int(num(opts, "width", 1600))
    ratio = parse_ratio(opts.get("ratio", "1:1")) or 1
    cw = (W - gap * (cols + 1)) // cols
    ch = round(cw / ratio)
    rows = -(-len(files) // cols)
    H = rows * ch + gap * (rows + 1)
    canvas = Image.new("RGB", (W, H), rgb(opts.get("bg", "#ffffff")))
    for i, f in enumerate(files):
        tile = crop_to_ratio(oriented(f).convert("RGB"), ratio, "face").resize((cw, ch), Image.LANCZOS)
        r, c = divmod(i, cols)
        canvas.paste(tile, (gap + c * (cw + gap), gap + r * (ch + gap)))
    dest = work / "out" / "collage.jpg"
    dest.write_bytes(encode(canvas, "jpg", 90))
    return Result("file", dest)


@tool(
    id="svg-convert", name="SVG to PNG / PDF", category="image", glyph="vector",
    description="Render vector SVG to crisp PNG at any width, or to PDF.",
    accept=[".svg"], multiple=True,
    options=[{"name": "format", "label": "Format", "type": "segmented", "default": "png",
              "choices": [["png", "PNG"], ["pdf", "PDF"], ["jpg", "JPG"]]},
             {"name": "width", "label": "Width (px)", "type": "number", "min": 16, "max": 10000, "default": 2048,
              "when": {"format": ["png", "jpg"]}}],
)
def svg_convert(files, opts, work):
    import cairosvg

    fmt = opts.get("format", "png")

    def one(f):
        if fmt == "pdf":
            dest = out_path(work, f, ".pdf")
            cairosvg.svg2pdf(url=str(f), write_to=str(dest))
            return dest
        png = cairosvg.svg2png(url=str(f), output_width=int(num(opts, "width", 2048)))
        im = Image.open(io.BytesIO(png))
        return write(work, f, encode(im, "jpg" if fmt == "jpg" else "png", 92), "jpg" if fmt == "jpg" else "png")

    return for_each(files, work, one, "svg_renders.zip")


def _warm_rembg():
    try:
        remove_bg_image(Image.new("RGB", (64, 64), "white"))
    except Exception:  # noqa: BLE001
        pass


import threading as _threading  # noqa: E402

_threading.Thread(target=_warm_rembg, daemon=True).start()
