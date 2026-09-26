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


# Free tier: ~20 requests/day *per model*, so fall through a pool of free Flash models when one is
# exhausted for the day (each has its own quota).
MODEL_POOL = [m.strip() for m in os.getenv(
    "GEMINI_MODEL_POOL",
    "gemini-3.5-flash,gemini-3-flash-preview,"
    "gemini-3.5-flash-lite,gemini-3.1-flash-lite,gemini-flash-lite-latest,gemini-3.8-flash,gemini-3.7-flash,gemini-3.6-flash").split(",") if m.strip()]
_exhausted: set[str] = set()


def _pick(model: str | None, skip: set[str] | None = None) -> str:
    """Preferred model first, then the pool; skips models exhausted for the day or overloaded right now."""
    for m in ([model] if model else []) + MODEL_POOL:
        if m and m not in _exhausted and m not in (skip or ()):
            return m
    raise RuntimeError("Today's free-tier LLM quota is used up (it resets at midnight Pacific time = 12:30 PM IST). "
                       "The sample episodes still work; please try your upload again after the reset.")


# Free-tier friendly: a process-wide request limiter (requests/minute) shared by all threads.
RPM = float(os.getenv("GEMINI_RPM", "8"))
_rl_lock = threading.Lock()
_rl_next = [0.0]
USAGE = {"calls": 0, "input_tokens": 0, "output_tokens": 0}


def _throttle() -> None:
    with _rl_lock:
        now = time.time()
        wait = max(0.0, _rl_next[0] - now)
        _rl_next[0] = max(now, _rl_next[0]) + 60.0 / RPM
    if wait:
        time.sleep(wait)


def _retry_delay(msg: str) -> float:
    import re

    m = re.search(r"retry(?:Delay)?['\"]?\s*[:=]\s*['\"]?(\d+(?:\.\d+)?)s", msg) or re.search(r"retry in (\d+(?:\.\d+)?)", msg, re.I)
    return float(m.group(1)) + 1 if m else 30.0


def generate_json(parts: list, prompt: str, schema: dict, model: str | None = None,
                  low_res: bool = False, retries: int = 6, temperature: float = 0.1) -> dict:
    cfg = types.GenerateContentConfig(
        temperature=temperature,
        response_mime_type="application/json",
        response_json_schema=schema,
    )
    if low_res:
        cfg.media_resolution = types.MediaResolution.MEDIA_RESOLUTION_LOW
    last = None
    use = model or MODEL_POOL[0]
    overloaded: set[str] = set()
    for attempt in range(retries):
        _throttle()
        try:
            use = _pick(model, overloaded)
            resp = client().models.generate_content(model=use, contents=[*parts, prompt], config=cfg)
            um = getattr(resp, "usage_metadata", None)
            USAGE["calls"] += 1
            USAGE["input_tokens"] += getattr(um, "prompt_token_count", 0) or 0
            USAGE["output_tokens"] += (getattr(um, "candidates_token_count", 0) or 0) + (getattr(um, "thoughts_token_count", 0) or 0)
            return json.loads(resp.text)
        except Exception as e:  # rate limits / transient 5xx / truncated JSON
            last = e
            msg = str(e)
            if any(code in msg[:40] for code in ("400", "401", "402", "403")):
                raise RuntimeError(f"Gemini request rejected (not retryable): {msg[:300]}") from e
            if "503" in msg[:40]:  # overloaded model: rotate to the next free model for this call
                overloaded.add(use)
                print(f"[gemini] {use} overloaded, rotating", flush=True)
                if len(overloaded) >= len(MODEL_POOL):
                    overloaded.clear()
                    time.sleep(10 + 5 * attempt)
                continue
            if "429" in msg[:40]:  # free-tier rate limit: wait as instructed, then retry
                if "PerDay" in msg or "per day" in msg.lower():
                    _exhausted.add(use)
                    print(f"[gemini] {use} daily quota reached, falling back to the next free model", flush=True)
                    _pick(None)  # raises if the whole pool is exhausted
                    continue
                delay = _retry_delay(msg)
                print(f"[gemini] rate-limited, waiting {delay:.0f}s", flush=True)
                time.sleep(delay)
                continue
            print(f"[gemini] attempt {attempt + 1} failed: {msg[:200]}", flush=True)
            client(fresh=True)
            time.sleep(min(30, 3 * 2 ** attempt))
    raise RuntimeError(f"Gemini call failed after {retries} attempts: {last}")
