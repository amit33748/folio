FROM python:3.12-slim-trixie

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HOME=/tmp \
    U2NET_HOME=/opt/u2net \
    MAX_UPLOAD_MB=500

# Engines: Ghostscript + qpdf (PDF), LibreOffice (office), Tesseract/OCRmyPDF (OCR, PDF/A), ffmpeg (audio/video),
# Chromium (web page -> PDF/image, HTML -> PDF), pandoc (document formats), cairo (SVG), exiftool (metadata),
# fontconfig + metric-compatible fonts so edited PDF text keeps its look (Arial/Times/Courier/Calibri/Cambria).
RUN apt-get update && apt-get install -y --no-install-recommends \
        ghostscript qpdf pngquant unpaper \
        tesseract-ocr tesseract-ocr-eng tesseract-ocr-deu tesseract-ocr-fra tesseract-ocr-spa \
        tesseract-ocr-ita tesseract-ocr-por tesseract-ocr-hin \
        libreoffice-writer-nogui libreoffice-calc-nogui libreoffice-impress-nogui \
        ffmpeg exiftool pandoc chromium libcairo2 fontconfig \
        fonts-dejavu fonts-liberation fonts-liberation2 fonts-noto-core fonts-crosextra-carlito fonts-crosextra-caladea \
        libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv
COPY requirements.txt .
RUN pip install -r requirements.txt

# Bake the background-removal model into the image (no download at runtime).
RUN python -c "from rembg import new_session; new_session('isnet-general-use')" && chmod -R a+rX /opt/u2net

COPY app ./app

RUN useradd --system --uid 10001 folio
USER folio

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/api/health')"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2", "--timeout-keep-alive", "300"]
