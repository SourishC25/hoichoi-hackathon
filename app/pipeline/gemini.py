"""Thin Gemini wrapper: file upload, inline clips, JSON-schema output, retries."""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

# Global pass needs long-video reasoning; local passes need speed + many parallel calls.
MODEL_GLOBAL = os.getenv("GEMINI_MODEL_GLOBAL", "gemini-3.5-flash")
MODEL_LOCAL = os.getenv("GEMINI_MODEL_LOCAL", "gemini-3.5-flash")

_local = threading.local()


def client(fresh: bool = False) -> genai.Client:
    """One client per thread (the SDK's HTTP client is not safe to share across a thread pool)."""
    if fresh or getattr(_local, "client", None) is None:
        key = os.getenv("GEMINI_API_KEY")
        if not key:
            raise RuntimeError("GEMINI_API_KEY is not set")
        _local.client = genai.Client(api_key=key)
    return _local.client


def upload_video(path: Path, log=print):
    f = client().files.upload(file=str(path), config={"mime_type": "video/mp4"})
    while f.state and f.state.name == "PROCESSING":
        time.sleep(3)
        f = client().files.get(name=f.name)
    if f.state and f.state.name == "FAILED":
        raise RuntimeError(f"Gemini file processing failed for {path.name}")
    log(f"uploaded {path.name} -> {f.name}")
    return f


def file_part(f, fps: float | None = None, low_res: bool = False) -> types.Part:
    part = types.Part(file_data=types.FileData(file_uri=f.uri, mime_type="video/mp4"))
    if fps:
        part.video_metadata = types.VideoMetadata(fps=fps)
    return part


def clip_part(path: Path, fps: float = 2.0) -> types.Part:
    return types.Part(
        inline_data=types.Blob(data=path.read_bytes(), mime_type="video/mp4"),
        video_metadata=types.VideoMetadata(fps=fps),
    )


def generate_json(parts: list, prompt: str, schema: dict, model: str | None = None,
                  low_res: bool = False, retries: int = 4, temperature: float = 0.1) -> dict:
    cfg = types.GenerateContentConfig(
        temperature=temperature,
        response_mime_type="application/json",
        response_json_schema=schema,
    )
    if low_res:
        cfg.media_resolution = types.MediaResolution.MEDIA_RESOLUTION_LOW
    last = None
    for attempt in range(retries):
        try:
            resp = client().models.generate_content(
                model=model or MODEL_LOCAL, contents=[*parts, prompt], config=cfg
            )
            return json.loads(resp.text)
        except Exception as e:  # rate limits / transient 5xx / truncated JSON
            last = e
            print(f"[gemini] attempt {attempt + 1} failed: {str(e)[:200]}", flush=True)
            client(fresh=True)
            time.sleep(min(30, 3 * 2 ** attempt))
    raise RuntimeError(f"Gemini call failed after {retries} attempts: {last}")
