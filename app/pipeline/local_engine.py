"""Local, free, open-source decision engine (CLIP + CLAP + Silero VAD on CPU).

Implements the same stage contracts as the Gemini engine, so pacing, manifests, player and
self-audit are shared:
  analyse()    B · semantic scene segmentation + zero-shot tagging (activity, mood, sensitive topics)
  judge_all()  D · is this cut natural?     (visual novelty, silence, loudness dip, fades, music carry-over)
  match_all()  E · which brand fits? which are blocked?  (catalogue text scored against lead-in media)
  verify()     F · independent dense re-check of the final pick (2 fps, stricter thresholds, fail-closed)

Every concept is plain text from the catalogue (target_contexts / negative_contexts), embedded by
CLIP/CLAP at runtime — an unseen 9th brand is scored with zero code changes. Thresholds are
calibrated against Gemini labels from development runs (see scripts/calibrate_local.py)."""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

from . import local_models as lm
from .understand import fmt

GENERIC_VIS = [
    "people talking in a room", "a close-up of a person's face", "a city street", "an office",
    "a living room at home", "the inside of a car", "text or credits on a dark screen", "a landscape",
    "a crowd of people", "a bedroom", "a corridor", "a dark night scene", "two people having a conversation",
    "a group of people standing", "a shop", "an outdoor scene in daylight",
]
# acoustic evidence for abstract contexts (world knowledge; unknown contexts fall back to "the sound of X")
AUDIO_CUES = {
    "grief": ["people crying", "sobbing and weeping", "mournful sad music"],
    "funeral": ["mourning and wailing", "funeral prayer chanting", "people crying"],
    "violence": ["people fighting and screaming", "gunshots", "punching and a violent fight"],
    "accident": ["a car crash", "an ambulance siren", "breaking glass and screeching tyres"],
    "hospital": ["a hospital heart monitor beeping", "an ambulance siren"],
    "medical emergency": ["an ambulance siren", "a heart monitor beeping", "someone gasping for breath"],
    "illness": ["coughing", "someone groaning in pain"],
    "injury": ["someone screaming in pain", "someone groaning in pain"],
    "eating": ["people eating and chewing", "cutlery and plates clinking"],
    "cooking": ["food sizzling in a frying pan", "cooking sounds in a kitchen"],
    "frying": ["food sizzling in a frying pan"],
    "phone": ["a phone ringing"], "calling": ["a phone ringing"],
    "car": ["a car engine running"], "driving": ["a car engine and road noise"],
    "traffic": ["street traffic and car horns"], "shower": ["a shower running water"],
    "party": ["a party with cheering and music"], "wedding": ["wedding shehnai music and celebration"],
}
MOODS = {"tense": "tense suspenseful music", "sad": "sad emotional music", "happy": "happy upbeat music",
         "calm": "calm soft music", "conversational": "people talking calmly", "quiet": "near silence"}

CALIB_PATH = Path(__file__).resolve().parents[2] / "data" / "calibration.json"
REF_PATH = Path(__file__).resolve().parents[2] / "data" / "reference_bank.npz"
# thresholds are in z-units: how unusual this match is versus typical Bengali-drama footage
DEFAULT_CALIB = {"scene_tau": 0.14, "vis_thr": 2.5, "aud_thr": 3.0, "rel_mid": 1.5, "rel_width": 0.7, "per_term": {}}
_ref = None


def ref_bank():
    """Reference frames/audio windows sampled from real episodes. Any concept's baseline (mean/std
    similarity) is computed on this bank at runtime, so an unseen brand's words are standardised
    exactly like the known ones."""
    global _ref
    if _ref is None:
        z = np.load(REF_PATH)
        _ref = (z["frame_e"], z["audio_e"])
    return _ref


def calib() -> dict:
    try:
        return {**DEFAULT_CALIB, **json.loads(CALIB_PATH.read_text(encoding="utf-8"))}
    except Exception:
        return dict(DEFAULT_CALIB)


# ---------------- zero-shot scoring ----------------


_zstats: dict = {}


def _stats(key, ref: np.ndarray, sim_fn):
    if key not in _zstats:
        r = sim_fn(ref)
        _zstats[key] = (r.mean(0), r.std(0) + 1e-6)
    return _zstats[key]


def vis_z(frame_e: np.ndarray, concepts: list[str]) -> np.ndarray:
    """CLIP similarity of each frame to each concept, standardised per concept on the reference
    bank (z-score). Removes CLIP's per-word bias (e.g. every TV frame looks a bit like 'video call')."""
    if len(frame_e) == 0:
        return np.zeros((0, len(concepts)))
    C = lm.concept_bank(concepts, lm.VIS_TEMPLATES, lm.clip_text)
    mu, sd = _stats(("v", tuple(concepts)), ref_bank()[0], lambda r: r @ C.T)
    return (frame_e @ C.T - mu) / sd


def aud_z(audio_e: np.ndarray, concepts: list[str]) -> np.ndarray:
    """Same for the soundtrack with CLAP. Concepts with known acoustic signatures use them
    (grief -> crying/sobbing); others fall back to their own words."""
    if len(audio_e) == 0:
        return np.zeros((0, len(concepts)))
    out = np.zeros((len(audio_e), len(concepts)))
    for j, c in enumerate(concepts):
        cues = AUDIO_CUES.get(c.lower(), [c])
        E = lm.concept_bank(cues, lm.AUD_TEMPLATES, lm.clap_text)
        mu, sd = _stats(("a", tuple(cues)), ref_bank()[1], lambda r, E=E: (r @ E.T).max(1))
        out[:, j] = ((audio_e @ E.T).max(1) - mu) / sd
    return out


def has_audio_cue(term: str) -> bool:
    return term.lower() in AUDIO_CUES


def rel01(z, cal: dict):
    """Map a z-score to a 0..1 relevance for display/ranking."""
    return 1 / (1 + np.exp(-(np.asarray(z) - cal["rel_mid"]) / cal["rel_width"]))


def topq(p: np.ndarray, frac: float = 0.2, min_n: int = 2) -> np.ndarray:
    """Mean of the top-q values per column — robust to a single noisy frame, sensitive to a
    short but real event inside a long window."""
    if len(p) == 0:
        return np.zeros(p.shape[1] if p.ndim == 2 else 0)
    q = max(min_n, int(math.ceil(frac * len(p))))
    q = min(q, len(p))
    return np.sort(p, axis=0)[-q:].mean(0)


class Episode:
    """Cached embeddings for one episode plus windowed queries."""

    def __init__(self, wd: Path):
        z = np.load(wd / "local_embeds.npz")
        self.ft, self.fe, self.at, self.ae = z["frame_t"], z["frame_e"], z["audio_t"], z["audio_e"]
        self.cal = calib()

    def fidx(self, a: float, b: float) -> np.ndarray:
        return np.where((self.ft >= a) & (self.ft < b))[0]

    def aidx(self, a: float, b: float) -> np.ndarray:
        return np.where((self.at + lm.AUDIO_WIN / 2 > a) & (self.at - lm.AUDIO_WIN / 2 < b))[0]

    def mean_emb(self, a: float, b: float) -> np.ndarray | None:
        i = self.fidx(a, b)
        if len(i) == 0:
            if len(self.ft) == 0:
                return None
            i = np.array([int(np.argmin(np.abs(self.ft - (a + b) / 2)))])
        v = self.fe[i].mean(0)
        return v / (np.linalg.norm(v) + 1e-8)

    def thr(self, term: str, kind: str) -> float:
        pt = self.cal.get("per_term", {}).get(term.lower(), {})
        return float(pt.get(kind, self.cal["vis_thr" if kind == "vis" else "aud_thr"]))

    def sensitive_in(self, a: float, b: float, terms: list[str], strict: float = 1.0, frac: float = 0.2) -> list[dict]:
        """Sensitive terms whose visual or acoustic evidence in [a, b) clears its threshold × strict."""
        fi, ai = self.fidx(a, b), self.aidx(a, b)
        if not terms:
            return []
        zv_all = vis_z(self.fe[fi], terms) if len(fi) else np.zeros((0, len(terms)))
        pv = topq(zv_all, frac) if len(fi) else np.full(len(terms), -9.0)
        pa = topq(aud_z(self.ae[ai], terms), frac, 1) if len(ai) else np.full(len(terms), -9.0)
        out = []
        for j, term in enumerate(terms):
            tv, ta = self.thr(term, "vis") * strict, self.thr(term, "aud") * strict
            aud_hit = has_audio_cue(term) and pa[j] >= ta
            if pv[j] >= tv or aud_hit:
                peak = self.ft[fi][int(np.argmax(zv_all[:, j]))] if len(fi) else a
                conf = float(np.clip(0.5 + 0.1 * max(pv[j] - tv, (pa[j] - ta) if has_audio_cue(term) else -9), 0.3, 1.0))
                src = "CLIP visual" if pv[j] >= tv else "CLAP audio"
                out.append({"topic": term, "confidence": round(conf, 3),
                            "evidence": f"{src}: visual z={pv[j]:.1f} (thr {tv:.1f}), audio z={pa[j]:.1f} (thr {ta:.1f}), peak ~{fmt(float(peak))}",
                            "vis": round(float(pv[j]), 3), "aud": round(float(pa[j]), 3)})
        return out


def sensitive_terms(brands: list[dict]) -> list[str]:
    """Only the catalogue's own negative contexts: zero-shot scores for extra, unused labels only
    add noise (and the implication rules would turn that noise into blocks)."""
    seen, out = set(), []
    for t in [n for b in brands for n in b.get("negative_contexts", [])]:
        if t.lower() not in seen:
            seen.add(t.lower())
            out.append(t)
    return out


def activity_terms(brands: list[dict]) -> list[str]:
    seen, out = set(), []
    for t in [c for b in brands for c in b.get("target_contexts", [])]:
        if t.lower() not in seen:
            seen.add(t.lower())
            out.append(t)
    return out


# ---------------- B · scenes ----------------

def shot_novelty(ep: Episode, shots: list[float], duration: float, lookback: float = 60.0, max_prev: int = 8) -> list[dict]:
    """For each shot: 1 − max similarity to the shots in the preceding minute. Shot/reverse-shot
    dialogue keeps novelty low (the angle was seen seconds ago); a new place/time spikes it."""
    bounds = [0.0] + list(shots) + [duration]
    embs = [ep.mean_emb(a, max(b, a + 0.5)) for a, b in zip(bounds[:-1], bounds[1:])]
    out = []
    for j in range(len(embs)):
        a = bounds[j]
        prev = [k for k in range(j - 1, -1, -1) if bounds[k] >= a - lookback][:max_prev]
        if embs[j] is None or not prev:
            nov = 1.0 if j else 0.0
        else:
            nov = 1.0 - max(float(embs[j] @ embs[k]) for k in prev if embs[k] is not None)
        out.append({"start": a, "end": bounds[j + 1], "novelty": round(nov, 4)})
    return out


def segment(ep: Episode, shots: list[float], duration: float, tau: float, min_len: float = 20.0) -> list[tuple[float, float, float]]:
    sh = shot_novelty(ep, shots, duration)
    starts = [(s["start"], s["novelty"]) for s in sh if s["start"] == 0.0 or s["novelty"] >= tau]
    # merge too-short scenes: drop the weaker of the two boundaries around a short scene
    changed = True
    while changed and len(starts) > 1:
        changed = False
        for i in range(len(starts)):
            end = starts[i + 1][0] if i + 1 < len(starts) else duration
            if end - starts[i][0] < min_len:
                if i == 0:
                    del starts[1]
                elif i + 1 < len(starts) and starts[i + 1][1] < starts[i][1]:
                    del starts[i + 1]
                else:
                    del starts[i]
                changed = True
                break
    return [(a, starts[i + 1][0] if i + 1 < len(starts) else duration, nov) for i, (a, nov) in enumerate(starts)]


def analyse(wd: Path, duration: float, shots: list[float], brands: list[dict], log=print) -> dict:
    ep = Episode(wd)
    cal = ep.cal
    spans = segment(ep, shots, duration, cal["scene_tau"])
    acts = activity_terms(brands)
    sens = sensitive_terms(brands)
    moods = list(MOODS.values())
    labels = acts + GENERIC_VIS
    scenes = []
    for i, (a, b, nov) in enumerate(spans):
        fi, ai = ep.fidx(a, b), ep.aidx(a, b)
        pl = topq(vis_z(ep.fe[fi], labels)) if len(fi) else np.zeros(len(labels))
        order = np.argsort(-pl)
        dominant = labels[int(order[0])] if len(fi) else "unknown"
        contexts = [labels[k] for k in order[:8] if pl[k] >= 1.0][:6] or [dominant]
        if len(ai):
            pm = aud_z(ep.ae[ai], moods).mean(0)
            mood = list(MOODS)[int(np.argmax(pm))]
            intensity = float(np.clip(0.5 + 0.2 * (pm[0] + 0.5 * pm[1]), 0, 1))
        else:
            mood, intensity = "quiet", 0.0
        sensitive = ep.sensitive_in(a, b, sens)
        s_txt = f"; flagged: {', '.join(x['topic'] for x in sensitive)}" if sensitive else ""
        scenes.append({
            "index": i, "start": round(a, 3), "end": round(b, 3), "boundary_novelty": round(nov, 3),
            "summary": f"{dominant} (z={pl[order[0]]:.1f}) — also {', '.join(c for c in contexts[1:4]) or 'n/a'}; audio mood {mood}{s_txt}",
            "dominant_activity": dominant, "contexts": contexts, "mood": mood,
            "emotional_intensity": round(intensity, 3), "sensitive": sensitive, "ends_with": "transition",
        })
    log(f"B · local: {len(scenes)} scenes from {len(shots)} cuts (τ={cal['scene_tau']})")
    top = {}
    for s in scenes:
        top[s["dominant_activity"]] = top.get(s["dominant_activity"], 0) + (s["end"] - s["start"])
    main = ", ".join(k for k, _ in sorted(top.items(), key=lambda kv: -kv[1])[:3])
    flagged = sorted({x["topic"] for s in scenes for x in s["sensitive"]})
    synopsis = (f"{len(scenes)} scenes over {fmt(duration)}. Most screen time: {main}. "
                f"Brand-safety flags: {', '.join(flagged) if flagged else 'none'}. "
                f"(Local engine: CLIP + CLAP zero-shot on 1 fps frames and 5 s audio windows.)")
    return {"synopsis": synopsis, "scenes": scenes, "sensitive_vocab": sens, "engine": "local"}


# ---------------- D · cut judgement ----------------

def judge_all(cands: list[dict], ep_dir: Path, scenes: list[dict], log=print) -> None:
    ep = Episode(ep_dir)
    cal = ep.cal
    todo = [c for c in cands if not c["rejections"]]
    log(f"D · local cut judgement on {len(todo)} / {len(cands)} candidates")
    for c in todo:
        t, s = c["t"], c["signals"]
        before, after = ep.mean_emb(t - 6, t), ep.mean_emb(t, t + 6)
        nov = 1.0 - float(before @ after) if before is not None and after is not None else 0.0
        vchange = float(np.clip((nov - 0.04) / 0.22, 0, 1))
        ab, aa = ep.aidx(t - 5, t - 0.1), ep.aidx(t + 0.1, t + 5)
        mus = lambda idx: float(aud_z(ep.ae[idx], ["background music"]).mean()) if len(idx) else -9.0
        tense = float(rel01(aud_z(ep.ae[ab], [MOODS["tense"]]).mean(), cal)) if len(ab) else 0.0
        mb, ma = mus(ab), mus(aa)
        gap = min(1.0, (min(s["silence_before"], 3) + min(s["silence_after"], 3)) / 4)
        quiet = 1 - min(1.0, (s["speech_density_10s_before"] + s["speech_density_10s_after"]) / 1.2)
        dip = min(1.0, s["loudness_dip_db"] / 12)
        music_carry = mb > 1.0 and ma > 1.0
        natural = 0.35 * vchange + 0.25 * gap + 0.15 * quiet + 0.10 * dip + 0.15 * (1.0 if s["fade_to_black"] else 0.0)
        natural = float(np.clip(natural - (0.08 if music_carry else 0.0) + (0.1 if vchange > 0.8 and gap > 0.6 else 0.0), 0, 1))
        dialogue = s["speech_density_10s_before"] > 0.45 and s["speech_density_10s_after"] > 0.45 and (s["silence_before"] + s["silence_after"]) < 2.0
        c["judge"] = {
            "last_line_before_cut": "", "first_line_after_cut": "",
            "dialogue_continues_across_cut": bool(dialogue), "cut_is_mid_sentence": False,
            "same_sequence_continues": bool(vchange < 0.2), "music_continues_across_cut": bool(music_carry),
            "story_beat_complete": round(float(0.5 * min(1.0, s["silence_before"] / 3) + 0.5 * vchange), 3),
            "jarring": round(1 - natural, 3), "suspense_hook": round(tense, 3), "natural_break_score": round(natural, 3),
            "visual_novelty": round(nov, 3),
            "reason": (f"Visual change across the cut {nov:.2f} (CLIP), {s['silence_before']:.1f}s silence before / "
                       f"{s['silence_after']:.1f}s after (VAD), speech density {pct(s['speech_density_10s_before'])}/"
                       f"{pct(s['speech_density_10s_after'])}, loudness dip {s['loudness_dip_db']} dB"
                       + (", music carries over" if music_carry else "") + (", fade to black" if s["fade_to_black"] else "") + "."),
        }
        if dialogue:
            c["rejections"].append("speech on both sides with <2 s combined gap: conversation likely continues")


def pct(x: float) -> str:
    return f"{round(100 * x)}%"


# ---------------- E · brand matching ----------------

def match_all(cands: list[dict], brands: list[dict], scenes: list[dict], ep_dir: Path, log=print) -> None:
    ep = Episode(ep_dir)
    log(f"E · local brand matching on {len(cands)} candidates x {len(brands)} brands")
    for c in cands:
        t = c["t"]
        sb = scenes[c["scene_before"]]
        lead = ep.fidx(max(sb["start"], t - 60.0), t)
        after = ep.fidx(t, t + 12.0)
        out = []
        for b in brands:
            tc = b.get("target_contexts", []) or [b.get("category", b["brand_id"])]
            pv = topq(vis_z(ep.fe[lead], tc)) if len(lead) else np.zeros(len(tc))
            pa = topq(vis_z(ep.fe[after], tc)) if len(after) else np.zeros(len(tc))
            score = rel01(0.8 * pv + 0.2 * pa, ep.cal)
            k = int(np.argmax(score))
            matched = [tc[j] for j in np.argsort(-score)[:3] if score[j] >= max(0.3, 0.7 * score[k])]
            viol = ep.sensitive_in(t - 60.0, t + 12.0, b.get("negative_contexts", []), strict=0.9)
            out.append({
                "brand_id": b["brand_id"], "relevance": round(float(score[k]), 3), "matched_contexts": matched,
                "violations": [{"negative_context": v["topic"], "evidence": v["evidence"]} for v in viol],
                "rationale": f"Lead-in best matches “{tc[k]}” (CLIP z={pv[k]:.1f} before / {pa[k]:.1f} after the cut)",
            })
        c["match"] = {"dominant_activity": sb["dominant_activity"], "brands": out}


# ---------------- F · independent verifier ----------------

_dense_cache: dict = {}


def verify(cand: dict, brand: dict, proxy: Path, ep_dir: Path) -> dict:
    """Dense, stricter re-check on fresh 2 fps frames over a wider window (t−90 s … t+20 s)."""
    ep = Episode(ep_dir)
    t = cand["t"]
    negs = brand.get("negative_contexts", [])
    key = (str(proxy), round(t, 3))
    if key not in _dense_cache:  # same frames for every brand tried at this slot
        _dense_cache[key] = lm.embed_frames(proxy, fps=2.0, start=max(0.0, t - 90.0), end=t + 20.0)
    ft, fe = _dense_cache[key]
    dense = Episode.__new__(Episode)
    dense.ft, dense.fe, dense.at, dense.ae, dense.cal = ft, fe, ep.at, ep.ae, ep.cal
    hits = dense.sensitive_in(t - 90.0, t + 20.0, negs, strict=0.8, frac=0.05)
    return {
        "violation": bool(hits), "violated_contexts": [h["topic"] for h in hits],
        "evidence": "; ".join(f"{h['topic']}: {h['evidence']}" for h in hits) or
                    f"No forbidden context above 0.8× threshold in {len(ft)} frames at 2 fps (t−90 s…t+20 s) or the soundtrack.",
        "confidence": round(max([h["confidence"] for h in hits], default=0.9), 3),
    }
