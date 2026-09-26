# ---- 1. build the Next.js frontend to a static SPA (frontend/out) ----
FROM node:22-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---- 2. FastAPI backend + pipeline, serving the built frontend ----
FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg fonts-dejavu-core libsndfile1     && rm -rf /var/lib/apt/lists/*
RUN useradd -m -u 1000 user
WORKDIR /home/user/app
COPY requirements-server.txt .
# silero-vad is installed without its torch dependency: only its bundled ONNX model is used
RUN pip install --no-cache-dir -r requirements-server.txt     && pip install --no-cache-dir --no-deps silero-vad
COPY --chown=user . .
COPY --from=web --chown=user /web/out ./frontend/out
# render the synthetic ad creatives at build time so the first viewer after a cold start never waits
RUN python -c "import json; from pathlib import Path; from app.pipeline import ads; ads.ensure_all(Path('web'), json.load(open('data/brands.json', encoding='utf-8')) + [json.load(open('data/example_brand.json', encoding='utf-8'))])"     && mkdir -p data/uploads && chown -R user:user web data frontend/out && chmod -R u+rwX web data frontend/out
USER user
# BIRATI_LOW_MEM: run perception stages sequentially and fewer parallel LLM clips (1 GB RAM hosts)
ENV PYTHONUNBUFFERED=1 BIRATI_LOW_MEM=1
EXPOSE 7860
# behind a TLS-terminating proxy (Railway, HF): trust X-Forwarded-Proto so generated URLs are https
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-7860} --proxy-headers --forwarded-allow-ips='*'"]
