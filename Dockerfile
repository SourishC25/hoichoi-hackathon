FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg fonts-dejavu-core libsndfile1 \
    && rm -rf /var/lib/apt/lists/*
RUN useradd -m -u 1000 user
WORKDIR /home/user/app
COPY requirements-server.txt .
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir -r requirements-server.txt
COPY --chown=user . .
USER user
# BIRATI_LOW_MEM: run perception stages sequentially and fewer parallel LLM clips (1 GB RAM hosts)
ENV PYTHONUNBUFFERED=1 BIRATI_LOW_MEM=1 OMP_NUM_THREADS=2
EXPOSE 7860
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-7860}"]
