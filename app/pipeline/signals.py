"""Deterministic low-level signals used for *precision*: shot cuts, speech activity,
loudness. The LLM decides *what* a moment means; these decide *exactly where* to cut."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf


def detect_shots(video: Path) -> list[float]:
    """Returns shot-cut timestamps (seconds), excluding 0."""
    from scenedetect import AdaptiveDetector, detect

    scenes = detect(str(video), AdaptiveDetector(min_scene_len=8), show_progress=False)
    return [round(s[0].get_seconds(), 3) for s in scenes[1:]]


_vad_model = None


def detect_speech(wav: Path) -> list[dict]:
    """Silero VAD — language-agnostic, so Bengali/English code-switching is irrelevant.
    Tuned slightly sensitive: a false 'speech' only costs a candidate, a missed one
    risks a mid-dialogue cut."""
    global _vad_model
    from silero_vad import get_speech_timestamps, load_silero_vad
    import torch

    if _vad_model is None:
        _vad_model = load_silero_vad()
    audio, sr = sf.read(str(wav), dtype="float32")
    ts = get_speech_timestamps(
        torch.from_numpy(audio), _vad_model, sampling_rate=sr, threshold=0.4,
        min_speech_duration_ms=150, min_silence_duration_ms=250, speech_pad_ms=120, return_seconds=True,
    )
    return [{"start": round(float(t["start"]), 3), "end": round(float(t["end"]), 3)} for t in ts]


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
