"""Stage E — WHAT brand belongs in this slot?

The catalogue is data, not code: every brand's category, target_contexts and negative_contexts
are handed to Gemini at runtime, so a 9th unseen brand works with zero code changes.

Safety is layered and fail-closed — negative_contexts are a HARD block:
  1. deterministic block: sensitive topics tagged by the global pass in the surrounding scenes
     (window before + after the break) that match a brand's negative context;
  2. contextual block: Gemini re-watches the lead-in clip and lists violations per brand;
  3. independent adversarial verifier on the final pick (fresh call, only that brand's blocklist,
     instructed to look for reasons NOT to place it). Any doubt -> next brand; none left -> no break.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import gemini, media

SENSITIVE_MIN_CONF = 0.3
LOOKBACK, LOOKAHEAD = 150.0, 30.0

# generic semantic implications between sensitive labels (world knowledge, not per-brand rules)
IMPLIES = {
    "death": ["grief", "funeral"], "dead body": ["grief", "funeral"], "mourning": ["grief", "funeral"],
    "funeral": ["grief"], "suicide": ["grief", "violence"], "blood": ["injury", "violence"],
    "fight": ["violence"], "weapon": ["violence"],
    "medical emergency": ["hospital", "illness"], "hospital": ["illness"],
}


def _norm(s: str) -> str:
    return s.strip().lower()


def window_scenes(scenes: list[dict], t: float) -> list[dict]:
    return [s for s in scenes if s["end"] > t - LOOKBACK and s["start"] < t + LOOKAHEAD]


def scene_hits(scene: dict, negatives: list[str]) -> list[tuple[str, dict]]:
    """(negative_context, sensitive_tag) pairs where a scene's tag matches a blocked context."""
    negs = [_norm(n) for n in negatives]
    hits = []
    for sen in scene.get("sensitive", []):
        if sen.get("confidence", 1) < SENSITIVE_MIN_CONF:
            continue
        topic = _norm(sen["topic"])
        labels = {topic, *IMPLIES.get(topic, [])}
        for n in negs:
            if any(n == l or n in l or l in n for l in labels):
                hits.append((n, sen))
    return hits


def deterministic_blocks(brand: dict, scenes: list[dict], t: float) -> list[dict]:
    return [{"negative_context": n, "source": "global_scene_tags", "scene": s["index"],
             "evidence": f"{sen['topic']}: {sen['evidence']}"}
            for s in window_scenes(scenes, t) for n, sen in scene_hits(s, brand.get("negative_contexts", []))]


def annotate_scenes(scenes: list[dict], brands: list[dict]) -> None:
    """For the UI/debug: which brands each scene would block, and on which context."""
    for s in scenes:
        s["blocks_brands"] = sorted({b["brand_id"] for b in brands if scene_hits(s, b.get("negative_contexts", []))})
        s["blocked_contexts"] = sorted({n for n, _ in scene_hits(s, [n for b in brands for n in b.get("negative_contexts", [])])})


MATCH_SCHEMA = {
    "type": "object",
    "properties": {
        "dominant_activity": {"type": "string"},
        "brands": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "brand_id": {"type": "string"},
                    "violations": {"type": "array", "items": {
                        "type": "object",
                        "properties": {"negative_context": {"type": "string"}, "evidence": {"type": "string"}},
                        "required": ["negative_context", "evidence"]}},
                    "relevance": {"type": "number"},
                    "matched_contexts": {"type": "array", "items": {"type": "string"}},
                    "rationale": {"type": "string"},
                },
                "required": ["brand_id", "violations", "relevance", "matched_contexts", "rationale"],
            },
        },
    },
    "required": ["dominant_activity", "brands"],
}


def _catalogue_text(brands: list[dict]) -> str:
    return "\n".join(
        f"- {b['brand_id']} ({b.get('display_name', '')}; category: {b.get('category', '')})\n"
        f"    target_contexts: {', '.join(b.get('target_contexts', []))}\n"
        f"    negative_contexts: {', '.join(b.get('negative_contexts', []))}"
        for b in brands
    )


def _scene_context(scenes: list[dict], t: float) -> str:
    lines = []
    for s in window_scenes(scenes, t):
        rel = "BEFORE break" if s["start"] < t else "AFTER break"
        sens = "; ".join(f"{x['topic']} ({x['evidence']})" for x in s.get("sensitive", [])) or "none"
        lines.append(f"[{rel}] {s['summary']} | activity: {s['dominant_activity']} | mood: {s['mood']} | sensitive: {sens}")
    return "\n".join(lines)


def match(cand: dict, brands: list[dict], scenes: list[dict], proxy: Path, workdir: Path) -> dict:
    t = cand["t"]
    sb = scenes[cand["scene_before"]]
    start = max(sb["start"], t - 60.0, 0.0)
    clip = media.cut_clip_marked(proxy, workdir / f"match_{cand['id']}.mp4", start, t, t + 12.0)
    prompt = f"""You are an ad-sales planner for a Bengali OTT drama. A black "AD BREAK" card in this clip marks where
the commercial will air: before it is the lead-in scene, after it the first seconds when the show resumes.

Scene context around the break (from the full-episode analysis):
{_scene_context(scenes, t)}

Brand catalogue (synthetic brands):
{_catalogue_text(brands)}

For EVERY brand in the catalogue:
- violations: each of THAT brand's negative_contexts that is present, shown, discussed or strongly implied
  in the lead-in scene, the scene after, or the wider context above (e.g. a food brand after a funeral or a
  death being discussed). Be strict and conservative — if in doubt, list it with your evidence.
- relevance 0..1: how well the brand's target_contexts fit THIS slot. The DOMINANT activity of the lead-in
  scene matters most; a passing background object matters little. 0.8+ only for a direct match.
- matched_contexts: which target_contexts match.
- rationale: one sentence.
Also state the dominant_activity of the lead-in scene."""
    res = gemini.generate_json([gemini.clip_part(clip, fps=1.0)], prompt, MATCH_SCHEMA)
    clip.unlink(missing_ok=True)
    return res


VERIFY_SCHEMA = {
    "type": "object",
    "properties": {
        "violation": {"type": "boolean"},
        "violated_contexts": {"type": "array", "items": {"type": "string"}},
        "evidence": {"type": "string"},
        "confidence": {"type": "number"},
    },
    "required": ["violation", "violated_contexts", "evidence", "confidence"],
}


def verify(cand: dict, brand: dict, scenes: list[dict], proxy: Path, workdir: Path) -> dict:
    """Independent brand-safety check. Wider window, only this brand's blocklist, adversarial framing."""
    t = cand["t"]
    start = max(0.0, t - 90.0)
    clip = media.cut_clip_marked(proxy, workdir / f"verify_{cand['id']}_{brand['brand_id']}.mp4", start, t, t + 20.0)
    prompt = f"""BRAND-SAFETY AUDIT. You are the final reviewer and your job is to find reasons NOT to air this ad.
An ad for "{brand.get('display_name', brand['brand_id'])}" (category: {brand.get('category', '')}) would play where the
black "AD BREAK" card appears in this clip — right after the preceding scene and before the following one.
The advertiser forbids placement adjacent to ANY of: {', '.join(brand.get('negative_contexts', []))}.

Wider episode context:
{_scene_context(scenes, t)}

Watch and listen carefully (Bengali dialogue). violation = true if any forbidden context is shown, discussed,
mourned, or strongly implied in the lead-in or the following scene, or if the emotional tone makes this ad
tasteless there. When unsure, answer true."""
    res = gemini.generate_json([gemini.clip_part(clip, fps=1.0)], prompt, VERIFY_SCHEMA, temperature=0.0)
    clip.unlink(missing_ok=True)
    return res


def match_all(cands: list[dict], brands: list[dict], scenes: list[dict], proxy: Path, workdir: Path,
              log=print, workers: int = 6) -> None:
    log(f"brand matching on {len(cands)} candidates x {len(brands)} brands")

    def one(c):
        try:
            c["match"] = match(c, brands, scenes, proxy, workdir)
        except Exception as e:
            c["match"] = None
            c["rejections"].append(f"brand matching failed: {e}")
        return c

    with ThreadPoolExecutor(workers) as ex:
        list(ex.map(one, cands))
    failed = [c for c in cands if c.get("match") is None]
    if failed:  # never cache a half-matched stage
        raise RuntimeError(f"{len(failed)} brand-matching calls failed: {failed[0]['rejections'][-1]}")


def rank(c: dict, brands: list[dict], scenes: list[dict]) -> None:
    """Combine the cached LLM verdicts with deterministic blocks into a per-slot brand ranking.
    Kept separate from the LLM stage so blocking rules apply without new model calls."""
    by_id = {b["brand_id"]: b for b in brands}
    ranking = []
    llm = {b["brand_id"]: b for b in (c.get("match") or {}).get("brands", [])}
    for bid, brand in by_id.items():
        blocks = deterministic_blocks(brand, scenes, c["t"])
        m = llm.get(bid)
        if m is None:
            blocks.append({"negative_context": "*", "source": "llm", "evidence": "brand missing from LLM answer (fail-closed)"})
        else:
            # fail-closed: any violation the model claims blocks, even if it paraphrased the label
            for v in m["violations"]:
                blocks.append({"negative_context": v["negative_context"], "source": "llm_lead_in", "evidence": v["evidence"]})
        ranking.append({
            "brand_id": bid,
            "relevance": round(float(m["relevance"]), 3) if m else 0.0,
            "matched_contexts": m["matched_contexts"] if m else [],
            "rationale": m["rationale"] if m else "",
            "blocked": bool(blocks),
            "blocks": blocks,
        })
    ranking.sort(key=lambda r: (r["blocked"], -r["relevance"]))
    c["brand_ranking"] = ranking
    c["dominant_activity"] = (c.get("match") or {}).get("dominant_activity", "")
    if c.get("match") and all(r["blocked"] for r in ranking):
        c["rejections"].append("every brand is blocked by negative contexts here")


def pick_creative(brand: dict, max_sec: float) -> dict | None:
    fits = [cr for cr in brand.get("creatives", []) if cr["duration_sec"] <= max_sec + 1e-6]
    return max(fits, key=lambda cr: cr["duration_sec"]) if fits else None
