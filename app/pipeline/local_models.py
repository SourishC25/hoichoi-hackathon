"""Free, local, open-weights foundation models (CPU):
  - CLIP  (openai/clip-vit-base-patch32)  — zero-shot visual understanding of frames
  - CLAP  (laion/clap-htsat-unfused)      — zero-shot understanding of the soundtrack
Both map media and natural-language text into a shared embedding space, so any context string
from the brand catalogue (including an unseen brand's) can be scored with zero code changes."""
from __future__ import annotations

import subprocess
import threading
from pathlib import Path

import numpy as np

from . import media  # noqa: F401  (ffmpeg on PATH)

CLIP_ID = "openai/clip-vit-base-patch32"
CLAP_ID = "laion/clap-htsat-unfused"
FRAME = 224
AUDIO_SR = 48000
AUDIO_WIN = 5.0

_lock = threading.Lock()
_models: dict = {}


def _as_tensor(o):
    import torch

    if torch.is_tensor(o):
        return o
    for attr in ("image_embeds", "text_embeds", "audio_embeds", "pooler_output"):
        v = getattr(o, attr, None)
        if v is not None:
            return v
    raise TypeError(f"unexpected model output {type(o)}")


def _norm(x: np.ndarray) -> np.ndarray:
    return x / (np.linalg.norm(x, axis=-1, keepdims=True) + 1e-8)


def clip():
    with _lock:
        if "clip" not in _models:
            from transformers import CLIPModel, CLIPProcessor

            _models["clip"] = (CLIPModel.from_pretrained(CLIP_ID).eval(), CLIPProcessor.from_pretrained(CLIP_ID))
    return _models["clip"]


def clap():
    with _lock:
        if "clap" not in _models:
            from transformers import ClapModel, ClapProcessor

            _models["clap"] = (ClapModel.from_pretrained(CLAP_ID).eval(), ClapProcessor.from_pretrained(CLAP_ID))
    return _models["clap"]


# ---------------- media → embeddings ----------------

def frames(video: Path, fps: float = 1.0, start: float | None = None, end: float | None = None):
    """Yield (t, HxWx3 uint8) frames sampled at `fps`, streamed from ffmpeg."""
    cmd = ["ffmpeg", "-v", "error"]
    if start is not None:
        cmd += ["-ss", f"{max(0.0, start):.3f}"]
    cmd += ["-i", str(video)]
    if end is not None:
        cmd += ["-t", f"{end - max(0.0, start or 0.0):.3f}"]
    cmd += ["-vf", f"fps={fps},scale={FRAME}:{FRAME}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    n = FRAME * FRAME * 3
    i = 0
    t0 = max(0.0, start or 0.0)
    try:
        while True:
            buf = p.stdout.read(n)
            if len(buf) < n:
                break
            yield t0 + i / fps, np.frombuffer(buf, np.uint8).reshape(FRAME, FRAME, 3)
            i += 1
    finally:
        p.stdout.close()
        p.wait()


def embed_frames(video: Path, fps: float = 1.0, start: float | None = None, end: float | None = None,
                 batch: int = 64) -> tuple[np.ndarray, np.ndarray]:
    import torch
    from PIL import Image

    model, proc = clip()
    ts, embs, buf, bt = [], [], [], []

    def flush():
        with torch.no_grad():
            e = _as_tensor(model.get_image_features(**proc(images=buf, return_tensors="pt"))).numpy()
        embs.append(_norm(e))
        ts.extend(bt)
        buf.clear()
        bt.clear()

    for t, f in frames(video, fps, start, end):
        buf.append(Image.fromarray(f))
        bt.append(t)
        if len(buf) == batch:
            flush()
    if buf:
        flush()
    if not embs:
        return np.zeros((0,)), np.zeros((0, 512), np.float32)
    return np.array(ts, np.float32), np.concatenate(embs).astype(np.float32)


def embed_audio(video: Path, batch: int = 16) -> tuple[np.ndarray, np.ndarray]:
    """CLAP embeddings of consecutive 5 s windows; returns (window centre times, embeddings)."""
    import torch

    model, proc = clap()
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-i", str(video), "-vn", "-ac", "1", "-ar", str(AUDIO_SR),
                          "-f", "f32le", "-"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    n = int(AUDIO_SR * AUDIO_WIN) * 4
    ts, embs, buf, bt, i = [], [], [], [], 0

    def flush():
        with torch.no_grad():
            e = _as_tensor(model.get_audio_features(**proc(audio=buf, sampling_rate=AUDIO_SR, return_tensors="pt"))).numpy()
        embs.append(_norm(e))
        ts.extend(bt)
        buf.clear()
        bt.clear()

    try:
        while True:
            raw = p.stdout.read(n)
            if len(raw) < n // 4:
                break
            buf.append(np.frombuffer(raw, np.float32).copy())
            bt.append(i * AUDIO_WIN + AUDIO_WIN / 2)
            i += 1
            if len(buf) == batch:
                flush()
        if buf:
            flush()
    finally:
        p.stdout.close()
        p.wait()
    return np.array(ts, np.float32), (np.concatenate(embs).astype(np.float32) if embs else np.zeros((0, 512), np.float32))


# ---------------- text → embeddings ----------------

_text_cache: dict = {}
VIS_TEMPLATES = ["a photo of {}.", "a still from an Indian TV drama showing {}.", "a scene of {}."]
AUD_TEMPLATES = ["the sound of {}.", "{}"]


def clip_text(prompts: list[str]) -> np.ndarray:
    import torch

    key = ("clip", tuple(prompts))
    if key not in _text_cache:
        model, proc = clip()
        with torch.no_grad():
            e = _as_tensor(model.get_text_features(**proc(text=prompts, return_tensors="pt", padding=True))).numpy()
        _text_cache[key] = _norm(e)
    return _text_cache[key]


def clap_text(prompts: list[str]) -> np.ndarray:
    import torch

    key = ("clap", tuple(prompts))
    if key not in _text_cache:
        model, proc = clap()
        with torch.no_grad():
            e = _as_tensor(model.get_text_features(**proc(text=prompts, return_tensors="pt", padding=True))).numpy()
        _text_cache[key] = _norm(e)
    return _text_cache[key]


def concept_bank(concepts: list[str], templates: list[str], encoder) -> np.ndarray:
    """One embedding per concept: mean over prompt templates (prompt ensembling)."""
    prompts = [tpl.format(c) for c in concepts for tpl in templates]
    e = encoder(prompts).reshape(len(concepts), len(templates), -1).mean(1)
    return _norm(e)
