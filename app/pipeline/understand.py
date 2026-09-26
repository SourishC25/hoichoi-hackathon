"""Stage B — global semantic understanding of the whole episode with Gemini.

Gemini watches the full video (vision + audio, Bengali dialogue included) and groups
the detected shots into semantically coherent scenes, describing each one: what is
happening, the dominant activity, mood, and any sensitive content. The sensitive
vocabulary is built at runtime from the brand catalogue's negative_contexts, so a
new brand's blocked contexts are watched for with zero code changes."""
from __future__ import annotations

from . import gemini

EXTRA_SENSITIVE = [
    "death", "dead body", "funeral", "grief", "mourning", "crying", "hospital", "illness", "injury",
    "blood", "accident", "violence", "fight", "weapon", "crime", "police arrest", "alcohol",
    "smoking", "drugs", "sexual content", "financial distress", "poverty", "suicide", "bathroom",
    "eating", "religious ritual", "heated argument",
]

SCENE_SCHEMA = {
    "type": "object",
    "properties": {
        "synopsis": {"type": "string"},
        "scenes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "start": {"type": "string", "description": "MM:SS or H:MM:SS"},
                    "end": {"type": "string", "description": "MM:SS or H:MM:SS"},
                    "location": {"type": "string"},
                    "characters": {"type": "array", "items": {"type": "string"}},
                    "summary": {"type": "string"},
                    "dominant_activity": {"type": "string"},
                    "contexts": {"type": "array", "items": {"type": "string"},
                                 "description": "short keywords for activities/objects/settings on screen or discussed"},
                    "mood": {"type": "string"},
                    "emotional_intensity": {"type": "number"},
                    "sensitive": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "topic": {"type": "string"},
                                "evidence": {"type": "string"},
                                "confidence": {"type": "number"},
                            },
                            "required": ["topic", "evidence", "confidence"],
                        },
                    },
                    "ends_with": {"type": "string",
                                  "enum": ["resolved", "cliffhanger", "conversation_continues", "transition", "montage"]},
                },
                "required": ["start", "end", "summary", "dominant_activity", "contexts", "mood",
                             "emotional_intensity", "sensitive", "ends_with"],
            },
        },
    },
    "required": ["synopsis", "scenes"],
}


def fmt(t: float) -> str:
    t = max(0.0, t)
    h, rem = divmod(int(t), 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def parse_ts(s: str) -> float:
    parts = [float(p) for p in str(s).strip().split(":")]
    t = 0.0
    for p in parts:
        t = t * 60 + p
    return t


def sensitive_vocab(brands: list[dict]) -> list[str]:
    seen, vocab = set(), []
    for term in [c for b in brands for c in b.get("negative_contexts", [])] + EXTRA_SENSITIVE:
        if term.lower() not in seen:
            seen.add(term.lower())
            vocab.append(term)
    return vocab


def analyse(video_file, duration: float, shots: list[float], brands: list[dict], log=print) -> dict:
    shot_list = ", ".join(fmt(t) for t in shots)
    vocab = sensitive_vocab(brands)
    prompt = f"""You are a senior story editor at a Bengali OTT platform, preparing this episode for
ad-supported streaming. Watch the ENTIRE video (visuals AND Bengali/English audio). Duration: {fmt(duration)}.

TASK: segment the episode into semantically coherent SCENES — a scene is one continuous dramatic unit
(same place + time + narrative thread). A scene normally spans many shots; typical drama scenes last
30s–5min. Do NOT split a scene at every camera cut, and do NOT merge two scenes just because the same
characters appear. Opening/closing credits and title cards are their own scenes.

Detected camera cuts (scene boundaries almost always coincide with one of these): {shot_list}

For each scene, in chronological order, covering the whole runtime without gaps:
- start/end timestamps (align to the camera cuts above).
- summary: 1–2 sentences in English of what happens (translate the dialogue's meaning).
- dominant_activity: the single main on-screen activity (e.g. "cooking in kitchen", "phone call", "car ride").
- contexts: 3–10 short lowercase keywords of activities, objects, settings visible or discussed.
- mood + emotional_intensity 0..1.
- sensitive: list EVERY sensitive topic present — shown OR clearly discussed in dialogue — using these exact
  labels where they fit: {", ".join(vocab)}. Give evidence and confidence 0..1. Be conservative: grief,
  death or illness that is only talked about still counts. Use an empty list only if truly none.
- ends_with: how the scene ends — resolved | cliffhanger | conversation_continues (dialogue carries straight
  over into the next scene) | transition | montage.
Also give a 2–3 sentence synopsis of the episode."""
    log(f"global analysis: {len(shots)} shots, vocab {len(vocab)} terms")
    out = gemini.generate_json([gemini.file_part(video_file)], prompt, SCENE_SCHEMA,
                               model=gemini.MODEL_GLOBAL, low_res=True)
    scenes = []
    for s in out["scenes"]:
        s["start"], s["end"] = parse_ts(s["start"]), parse_ts(s["end"])
        scenes.append(s)
    scenes.sort(key=lambda s: s["start"])
    out["scenes"] = snap_scenes(scenes, shots, duration)
    out["sensitive_vocab"] = vocab
    return out


def snap_scenes(scenes: list[dict], shots: list[float], duration: float, tol: float = 4.0) -> list[dict]:
    """Snap each LLM scene start to the nearest real shot cut (LLM timestamps are ~1s precise;
    shot cuts are frame precise) and make scenes contiguous."""
    snapped = []
    for i, s in enumerate(scenes):
        t = s["start"]
        if i == 0:
            t = 0.0
        else:
            near = min(shots, key=lambda c: abs(c - t)) if shots else t
            s["snap_delta"] = round(near - t, 2)
            s["llm_start"] = t
            t = near if abs(near - t) <= tol else t
        s["start"] = round(t, 3)
        snapped.append(s)
    # dedupe scenes that snapped onto the same cut
    dedup = []
    for s in snapped:
        if dedup and s["start"] - dedup[-1]["start"] < 3.0:
            dedup[-1]["summary"] += " " + s["summary"]
            dedup[-1]["sensitive"] += s["sensitive"]
            dedup[-1]["contexts"] = list(dict.fromkeys(dedup[-1]["contexts"] + s["contexts"]))
            dedup[-1]["ends_with"] = s["ends_with"]
            continue
        dedup.append(s)
    for i, s in enumerate(dedup):
        s["end"] = dedup[i + 1]["start"] if i + 1 < len(dedup) else round(duration, 3)
        s["index"] = i
    return dedup
