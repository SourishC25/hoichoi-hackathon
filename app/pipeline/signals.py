"""Deterministic low-level signals used for *precision*: shot cuts, speech activity,
loudness. The LLM decides *what* a moment means; these decide *exactly where* to cut."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf

from . import media  # noqa: F401  (puts ffmpeg on PATH)


def detect_shots(video: Path) -> list[float]:
    """Shot-cut timestamps (seconds). ffmpeg's scdet on a 256px stream is ~30x faster than
    PySceneDetect with ~93% recall / ~100% precision against it on our samples; falls back to
    PySceneDetect if scdet is unavailable."""
    import re
    import subprocess

    p = subprocess.run(["ffmpeg", "-v", "info", "-i", str(video), "-an", "-vf", "scale=256:-2,scdet=threshold=4.5:sc_pass=1",
                        "-f", "null", "-"], capture_output=True, text=True, encoding="utf-8", errors="replace")
    cuts = sorted(float(m.group(1)) for m in re.finditer(r"lavfi\.scd\.time:\s*([\d.]+)", p.stderr))
    if p.returncode == 0 and cuts:
        out = []
        for c in cuts:
            if c > 0.2 and (not out or c - out[-1] > 0.3):
                out.append(round(c, 3))
        return out
    from scenedetect import AdaptiveDetector, detect

    scenes = detect(str(video), AdaptiveDetector(min_scene_len=8), show_progress=False)
    return [round(s[0].get_seconds(), 3) for s in scenes[1:]]


_vad_session = None


def _silero_onnx_path() -> str:
    import importlib.util

    # locate the model file without importing silero_vad (which would import torch)
    spec = importlib.util.find_spec("silero_vad")
    return str(Path(spec.origin).parent / "data" / "silero_vad.onnx")


def _speech_probs_onnx(audio: np.ndarray, sr: int) -> np.ndarray:
    """Per-window (512 samples @16 kHz) speech probabilities from Silero VAD via onnxruntime —
    no PyTorch needed (keeps the server image ~1.4 GB smaller and idle RAM ~300 MB lower)."""
    global _vad_session
    import onnxruntime as ort

    if _vad_session is None:
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = 1
        opts.inter_op_num_threads = 1
        _vad_session = ort.InferenceSession(_silero_onnx_path(), opts, providers=["CPUExecutionProvider"])
    win, ctx = (512, 64) if sr == 16000 else (256, 32)
    state = np.zeros((2, 1, 128), np.float32)
    context = np.zeros((1, ctx), np.float32)
    sr_in = np.array(sr, dtype=np.int64)
    n = int(np.ceil(len(audio) / win))
    probs = np.zeros(n, np.float32)
    for i in range(n):
        chunk = audio[i * win:(i + 1) * win]
        if len(chunk) < win:
            chunk = np.pad(chunk, (0, win - len(chunk)))
        x = np.concatenate([context, chunk[None, :].astype(np.float32)], axis=1)
        out, state = _vad_session.run(None, {"input": x, "state": state, "sr": sr_in})
        probs[i] = out[0, 0]
        context = x[:, -ctx:]
    return probs


def _segments_from_probs(probs: np.ndarray, n_samples: int, sr: int, threshold: float, min_speech_ms: int,
                         min_silence_ms: int, pad_ms: int) -> list[dict]:
    """Silero's hysteresis segmentation (port of get_speech_timestamps, no max-duration split)."""
    win = 512 if sr == 16000 else 256
    neg = max(threshold - 0.15, 0.01)
    min_speech = sr * min_speech_ms / 1000
    min_silence = sr * min_silence_ms / 1000
    pad = int(sr * pad_ms / 1000)
    triggered, speeches, cur, temp_end = False, [], {}, 0
    for i, p in enumerate(probs):
        t = win * i
        if p >= threshold and temp_end:
            temp_end = 0
        if p >= threshold and not triggered:
            triggered, cur = True, {"start": t}
            continue
        if p < neg and triggered:
            if not temp_end:
                temp_end = t
            if t - temp_end < min_silence:
                continue
            cur["end"] = temp_end
            if cur["end"] - cur["start"] > min_speech:
                speeches.append(cur)
            cur, temp_end, triggered = {}, 0, False
    if cur and n_samples - cur["start"] > min_speech:
        cur["end"] = n_samples
        speeches.append(cur)
    for i, sp in enumerate(speeches):
        if i == 0:
            sp["start"] = max(0, sp["start"] - pad)
        if i != len(speeches) - 1:
            gap = speeches[i + 1]["start"] - sp["end"]
            if gap < 2 * pad:
                sp["end"] += gap // 2
                speeches[i + 1]["start"] = max(0, speeches[i + 1]["start"] - gap // 2)
            else:
                sp["end"] = min(n_samples, sp["end"] + pad)
                speeches[i + 1]["start"] = max(0, speeches[i + 1]["start"] - pad)
        else:
            sp["end"] = min(n_samples, sp["end"] + pad)
    return [{"start": round(sp["start"] / sr, 3), "end": round(sp["end"] / sr, 3)} for sp in speeches]


def detect_speech(wav: Path) -> list[dict]:
    """Silero VAD — language-agnostic, so Bengali/English code-switching is irrelevant.
    Tuned slightly sensitive: a false 'speech' only costs a candidate, a missed one
    risks a mid-dialogue cut."""
    audio, sr = sf.read(str(wav), dtype="float32")
    if audio.ndim > 1:
        audio = audio.mean(1)
    probs = _speech_probs_onnx(audio, sr)
    return _segments_from_probs(probs, len(audio), sr, threshold=0.4, min_speech_ms=150,
                                min_silence_ms=250, pad_ms=120)


def loudness(wav: Path, hop: float = 0.1) -> dict:
    """RMS loudness in dBFS per `hop` seconds."""
    audio, sr = sf.read(str(wav), dtype="float32")
    n = int(sr * hop)
    frames = len(audio) // n
    rms = np.sqrt(np.mean(audio[: frames * n].reshape(frames, n) ** 2, axis=1) + 1e-10)
    db = 20 * np.log10(rms + 1e-10)
    return {"hop": hop, "db": np.round(db, 1).tolist()}


# ---------- queries over signals ----------

def speech_overlap(speech: list[dict], a: float, b: float) -> float:
    return sum(max(0.0, min(b, s["end"]) - max(a, s["start"])) for s in speech)


def silence_gap(speech: list[dict], t: float) -> tuple[float, float]:
    """(gap_start, gap_end) of the non-speech interval containing t; (t, t) if t is in speech."""
    prev_end, nxt_start = 0.0, float("inf")
    for s in speech:
        if s["start"] <= t <= s["end"]:
            return (t, t)
        if s["end"] < t:
            prev_end = max(prev_end, s["end"])
        elif s["start"] > t:
            nxt_start = min(nxt_start, s["start"])
    return (prev_end, nxt_start)


def speech_density(speech: list[dict], a: float, b: float) -> float:
    return speech_overlap(speech, a, b) / max(1e-6, b - a)


def loudness_dip(loud: dict, t: float, win: float = 1.0, ctx: float = 8.0) -> float:
    """How much quieter the moment around t is than its surroundings (dB, >=0)."""
    db, hop = loud["db"], loud["hop"]
    i = lambda x: max(0, min(len(db) - 1, int(x / hop)))
    around = db[i(t - win): i(t + win) + 1] or [0]
    context = db[i(t - ctx): i(t + ctx) + 1] or [0]
    return max(0.0, float(np.median(context) - np.min(around)))
