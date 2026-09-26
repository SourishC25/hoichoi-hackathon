"""Stages C+D — WHERE can we cut?

C. Candidate generation: every semantic scene boundary (from the LLM) and every fade-to-black
   is a candidate. Each is snapped to a frame-exact camera cut that sits inside a speech-free gap
   (Silero VAD). If no such cut exists nearby the candidate is rejected — this makes a
   mid-sentence cut structurally impossible, whatever the LLM says.
D. Local judgement: Gemini watches a clip around each surviving cut point at higher frame rate
   and answers as a broadcast standards editor: is dialogue continuing across the cut? is the
   story beat complete? would a viewer find it jarring?"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import gemini, media, signals
from .understand import fmt

SNAP_WINDOW = 6.0      # seconds to search around the LLM boundary for a clean cut
GUARD_BEFORE = 0.45    # no speech allowed this long before the cut
GUARD_AFTER = 0.35     # ...or this long after it
MIN_GAP = 0.8          # minimum speech-free gap containing the cut


def generate(scenes: list[dict], shots: list[float], speech: list[dict], blacks: list[dict],
             loud: dict, duration: float, cfg: dict) -> list[dict]:
    raw = [{"t0": s["start"], "source": "scene_boundary", "scene_after": s["index"]} for s in scenes[1:]]
    for b in blacks:
        if b["end"] - b["start"] >= 0.4:
            raw.append({"t0": (b["start"] + b["end"]) / 2, "source": "fade_to_black", "black": b})
    raw.sort(key=lambda c: c["t0"])

    merged: list[dict] = []
    for c in raw:
        if merged and c["t0"] - merged[-1]["t0"] < 8.0:
            merged[-1]["sources"] = sorted(set(merged[-1]["sources"] + [c["source"]]))
            merged[-1].setdefault("black", c.get("black"))
            continue
        merged.append({**c, "sources": [c["source"]]})

    out = []
    for i, c in enumerate(merged):
        cand = {"id": f"c{i:03d}", "t0": round(c["t0"], 3), "sources": c["sources"], "rejections": []}
        if c["t0"] < cfg["no_break_first_sec"] or c["t0"] > duration - cfg["no_break_last_sec"]:
            cand["rejections"].append("inside protected opening/closing window")
        # options: camera cuts near the boundary (+ the black middle for fades)
        opts = [s for s in shots if abs(s - c["t0"]) <= SNAP_WINDOW]
        if c.get("black"):
            opts.append((c["black"]["start"] + c["black"]["end"]) / 2)
        if not opts:
            opts = [c["t0"]]
        best, best_score = None, -1e9
        for t in opts:
            if signals.speech_overlap(speech, t - GUARD_BEFORE, t + GUARD_AFTER) > 0:
                continue
            g0, g1 = signals.silence_gap(speech, t)
            gap = min(g1, duration) - g0
            if gap < MIN_GAP:
                continue
            score = min(gap, 4.0) - 0.15 * abs(t - c["t0"])
            if score > best_score:
                best, best_score = t, score
        if best is None:
            cand["t"] = cand["t0"]
            cand["rejections"].append("every nearby cut point overlaps speech (mid-dialogue)")
        else:
            cand["t"] = round(best, 3)
        t = cand["t"]
        g0, g1 = signals.silence_gap(speech, t)
        before = [s for s in scenes if s["start"] <= t - 0.01]
        cand["scene_before"] = before[-1]["index"] if before else 0
        cand["scene_after"] = min(cand["scene_before"] + 1, len(scenes) - 1)
        cand["signals"] = {
            "snap_delta": round(t - cand["t0"], 2),
            "silence_before": round(t - g0, 2),
            "silence_after": round(min(g1, duration) - t, 2) if g1 != float("inf") else 99.0,
            "speech_density_10s_before": round(signals.speech_density(speech, t - 10, t), 2),
            "speech_density_10s_after": round(signals.speech_density(speech, t, t + 10), 2),
            "loudness_dip_db": round(signals.loudness_dip(loud, t), 1),
            "fade_to_black": "fade_to_black" in c["sources"],
            "on_camera_cut": any(abs(s - t) < 0.05 for s in shots),
        }
        out.append(cand)
    return out


JUDGE_SCHEMA = {
    "type": "object",
    "properties": {
        "last_line_before_cut": {"type": "string"},
        "first_line_after_cut": {"type": "string"},
        "dialogue_continues_across_cut": {"type": "boolean"},
        "cut_is_mid_sentence": {"type": "boolean"},
        "same_sequence_continues": {"type": "boolean"},
        "music_continues_across_cut": {"type": "boolean"},
        "story_beat_complete": {"type": "number"},
        "jarring": {"type": "number"},
        "suspense_hook": {"type": "number"},
        "natural_break_score": {"type": "number"},
        "reason": {"type": "string"},
    },
    "required": ["last_line_before_cut", "first_line_after_cut", "dialogue_continues_across_cut",
                 "cut_is_mid_sentence", "same_sequence_continues", "music_continues_across_cut", "story_beat_complete", "jarring", "suspense_hook",
                 "natural_break_score", "reason"],
}

PRE, POST = 30.0, 12.0


def judge(cand: dict, proxy: Path, workdir: Path, scenes: list[dict]) -> dict:
    t = cand["t"]
    start = max(0.0, t - PRE)
    clip = media.cut_clip_marked(proxy, workdir / f"clip_{cand['id']}.mp4", start, t, t + POST)
    rel = t - start
    sb, sa = scenes[cand["scene_before"]], scenes[cand["scene_after"]]
    prompt = f"""You are a broadcast standards editor placing a mid-roll ad break in a Bengali drama.
A black card reading "AD BREAK" (at ~{rel:.0f}s into this clip) marks the proposed cut: everything before
the card airs before the commercial, everything after it airs when the programme resumes. The card itself
is not part of the show.
Context — scene before: "{sb['summary']}". Scene after: "{sa['summary']}".

Judge the cut point precisely, listening to the Bengali (and any English) dialogue:
- last_line_before_cut / first_line_after_cut: the spoken line immediately before and after the cut
  (Bengali script, short; "" if none within 5s).
- dialogue_continues_across_cut: true if a conversation/speech is still in progress, a question is
  left unanswered by the same speakers, or a reaction to the last line comes right after.
- cut_is_mid_sentence: true if any sentence (dialogue, narration, song lyric) is split by the card.
  Judge the programme content only; a scene that starts right after the card is fine and expected.
- same_sequence_continues: true if the material after the card continues the same dramatic sequence
  (cross-cutting, a chase, a montage, the same confrontation in the next room, a reaction shot still pending).
- music_continues_across_cut: true if a music cue / song / score is still mid-phrase at the card.
- story_beat_complete 0..1: has the dramatic beat landed so pausing now feels intentional?
- jarring 0..1: how disruptive the interruption would feel to a viewer.
- suspense_hook 0..1: does the moment leave an intriguing question (good for retention after the ad)?
- natural_break_score 0..1 — use the full scale, anchored like this:
    0.90–1.00  act-level ending: fade to black, a major revelation/cliffhanger lands, clear time jump.
    0.70–0.85  clean scene change: conversation concluded, new place or time, no pending reaction.
    0.50–0.65  scene change, but tension/action or music carries straight on, or the beat feels clipped.
    0.20–0.45  inside an ongoing sequence; a reaction or answer is pending.
    0.00–0.20  mid-conversation, mid-action, or mid-song.
  Most boundaries in a drama are NOT act-level; be discriminating.
- reason: one sentence."""
    res = gemini.generate_json([gemini.clip_part(clip, fps=2.0)], prompt, JUDGE_SCHEMA)
    clip.unlink(missing_ok=True)
    return res


def judge_all(cands: list[dict], proxy: Path, workdir: Path, scenes: list[dict], log=print, workers: int = 6) -> None:
    todo = [c for c in cands if not c["rejections"]]
    log(f"local judgement on {len(todo)} / {len(cands)} candidates")

    def one(c):
        try:
            c["judge"] = judge(c, proxy, workdir, scenes)
        except Exception as e:
            c["judge"] = None
            c["rejections"].append(f"judge failed: {e}")
        return c

    with ThreadPoolExecutor(workers) as ex:
        list(ex.map(one, todo))
    failed = [c for c in todo if c.get("judge") is None]
    if failed:  # never cache a half-judged stage
        raise RuntimeError(f"{len(failed)} cut judgements failed: {failed[0]['rejections'][-1]}")
    for c in todo:
        j = c.get("judge")
        if not j:
            continue
        if j["cut_is_mid_sentence"]:
            c["rejections"].append(f"LLM heard a sentence cut: “{j['last_line_before_cut']}”")
        if j["dialogue_continues_across_cut"]:
            c["rejections"].append("LLM: conversation continues across the cut")


def where_score(c: dict) -> float:
    j, s = c.get("judge") or {}, c["signals"]
    if not j:
        return 0.0
    llm = 0.6 * j["natural_break_score"] + 0.25 * j["story_beat_complete"] + 0.15 * (1 - j["jarring"])
    gap = min(1.0, (min(s["silence_before"], 3) + min(s["silence_after"], 3)) / 4)
    dip = min(1.0, s["loudness_dip_db"] / 12)
    quiet = 1 - min(1.0, (s["speech_density_10s_before"] + s["speech_density_10s_after"]) / 1.2)
    score = 0.65 * llm + 0.12 * gap + 0.08 * dip + 0.08 * quiet + 0.07 * (1.0 if s["fade_to_black"] else 0.0)
    score -= 0.08 * bool(j.get("same_sequence_continues")) + 0.05 * bool(j.get("music_continues_across_cut"))
    return round(max(0.0, score), 3)
