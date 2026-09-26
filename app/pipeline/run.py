"""Pipeline orchestrator with per-stage caching.

  A  perception   (ffmpeg, PySceneDetect, Silero VAD)            -> perception.json
  B  global scenes (Gemini, full episode)                         -> scenes.json
  C+D candidates + local cut judgement (signals + Gemini clips)   -> candidates.json
  E  brand matching + safety (Gemini, catalogue-dependent)        -> match_<cataloguehash>.json
  F  pacing selection + verification + creative choice            -> result.json (debug) + vmap.xml

Changing the brand catalogue re-runs only E–F; changing pacing rules re-runs only F.
Nothing here knows anything about specific videos or brands.

ENGINE (env BIRATI_ENGINE): "local" (default) = free open-source CLIP + CLAP + Silero on CPU, no API keys;
"gemini" = cloud multimodal LLM (needs GEMINI_API_KEY + credits). Both implement the same stage contracts."""
from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path

from dotenv import load_dotenv

from . import ads, brands as brandlib, breaks, manifest, media, pacing, signals, understand

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / "data" / "work"
WEB = ROOT / "web"

load_dotenv(ROOT / ".env")
# default: Gemini (free tier works) when a key is configured, otherwise the fully offline local engine
LOW_MEM = bool(os.getenv("BIRATI_LOW_MEM"))
LLM_WORKERS = 2 if LOW_MEM else 6
ENGINE = os.getenv("BIRATI_ENGINE", "gemini" if os.getenv("GEMINI_API_KEY") else "local").lower()
if ENGINE == "gemini":
    from . import gemini


def _load(p: Path):
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def _save(p: Path, obj) -> None:
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")


def catalogue_hash(brands: list[dict]) -> str:
    return hashlib.sha1(json.dumps(brands, sort_keys=True).encode()).hexdigest()[:10]


def self_audit(final: list[dict], cands: list[dict], perc: dict, duration: float, rules: dict,
               by_id: dict, scenes: list[dict]) -> list[dict]:
    """Re-check every hard guarantee on the final plan from raw signals (not from LLM output)."""
    checks = []

    def add(name, ok, detail):
        checks.append({"check": name, "pass": bool(ok), "detail": detail})

    speech = perc["speech"]
    worst = max((signals.speech_overlap(speech, b["t"] - breaks.GUARD_BEFORE, b["t"] + breaks.GUARD_AFTER) for b in final), default=0.0)
    add("No speech at any cut point (VAD)", worst == 0, f"max speech overlap in ±guard window: {worst:.2f}s")
    shots = perc["shots"]
    off = [b for b in final if not any(abs(s - b["t"]) < 0.05 for s in shots)
           and not any(x["start"] <= b["t"] <= x["end"] for x in perc["blacks"])]
    add("Every cut on a camera cut or black frame", not off, f"{len(final) - len(off)}/{len(final)} breaks frame-aligned")
    gaps = [b2["t"] - b1["t"] for b1, b2 in zip(final, final[1:])]
    add("Min gap between breaks", all(g >= rules["min_gap_sec"] for g in gaps),
        f"smallest gap {min(gaps):.0f}s (rule ≥ {rules['min_gap_sec']}s)" if gaps else "single break or none")
    allowed = pacing.allowed_breaks(duration, rules)
    add("Max breaks per hour", len(final) <= allowed, f"{len(final)} placed, {allowed} allowed for {duration / 60:.1f} min")
    ad_time = sum(b["creative"]["duration_sec"] for b in final)
    load = 100 * ad_time / (duration + ad_time) if final else 0.0
    add("Ad load within budget", load <= rules["max_ad_load_pct"] + 1e-6, f"{load:.2f}% (max {rules['max_ad_load_pct']}%)")
    add("Protected opening/closing windows", all(rules["no_break_first_sec"] <= b["t"] <= duration - rules["no_break_last_sec"] for b in final),
        f"first {rules['no_break_first_sec']}s / last {rules['no_break_last_sec']}s untouched")
    by_c = {c["id"]: c for c in cands}
    viol = []
    for b in final:
        r = next(x for x in by_c[b["candidate_id"]]["brand_ranking"] if x["brand_id"] == b["brand_id"])
        det = brandlib.deterministic_blocks(by_id[b["brand_id"]], scenes, b["t"])
        if r["blocks"] or det or (r.get("verifier") or {}).get("violation"):
            viol.append(b["brand_id"])
    add("No negative-context brand placed (3 layers re-checked)", not viol, "violations: " + (", ".join(viol) if viol else "none"))
    add("Every placed brand passed the independent verifier",
        all((next(x for x in by_c[b["candidate_id"]]["brand_ranking"] if x["brand_id"] == b["brand_id"]).get("verifier") or {}).get("violation") is False for b in final),
        f"{len(final)} verifier passes")
    return checks


def variant_id(brands: list[dict], rules: dict | None) -> str:
    rules = {**pacing.DEFAULT_RULES, **(rules or {})}
    return hashlib.sha1((catalogue_hash(brands) + json.dumps(rules, sort_keys=True)).encode()).hexdigest()[:10]


def result_variant(brands: list[dict], rules: dict | None) -> str:
    """Result/VMAP file key: catalogue + rules (+ engine, so engines never overwrite each other)."""
    v = variant_id(brands, rules)
    return v if ENGINE == "local" else f"{ENGINE}-{v}"


def process(video_id: str, source: Path, brands: list[dict], rules: dict | None = None,
            log=print, force: set[str] | None = None, work_root: Path | None = None) -> dict:
    rules = {**pacing.DEFAULT_RULES, **(rules or {})}
    force = force or set()
    wd = (work_root or WORK) / video_id
    wd.mkdir(parents=True, exist_ok=True)
    t_start = time.time()
    timings = {}

    # ---- A. perception ----
    proxy = wd / "proxy.mp4"
    pp = wd / "perception.json"
    perc = None if "A" in force else _load(pp)
    if perc is None:
        t = time.time()
        log("A · transcoding web proxy")
        media.make_proxy(source, proxy)
        info = media.probe(proxy)
        log("A · camera cuts (ffmpeg scdet) ‖ speech (Silero VAD) ‖ fades — in parallel")
        from concurrent.futures import ThreadPoolExecutor

        def audio_part():
            wav = media.extract_audio(proxy, wd / "audio.wav")
            return signals.detect_speech(wav), signals.loudness(wav)

        with ThreadPoolExecutor(1 if LOW_MEM else 3) as ex:
            f_shots = ex.submit(signals.detect_shots, proxy)
            f_audio = ex.submit(audio_part)
            f_black = ex.submit(media.black_segments, proxy)
            shots, (speech, loud), blacks = f_shots.result(), f_audio.result(), f_black.result()
        log(f"A · {len(shots)} camera cuts, {len(speech)} speech segments, {len(blacks)} black segments")
        perc = {**info, "shots": shots, "speech": speech, "loudness": loud, "blacks": blacks}
        _save(pp, perc)
        timings["perception"] = round(time.time() - t, 1)
    else:
        media.make_proxy(source, proxy)
    duration = perc["duration"]
    if ENGINE == "local":
        from . import local_engine, local_models
        import numpy as np

        if not (wd / "local_embeds.npz").exists():
            t = time.time()
            log("A · CLIP frame embeddings (1 fps) + CLAP audio embeddings (5 s windows)")
            ft, fe = local_models.embed_frames(proxy, fps=1.0)
            at, ae = local_models.embed_audio(proxy)
            np.savez_compressed(wd / "local_embeds.npz", frame_t=ft, frame_e=fe, audio_t=at, audio_e=ae)
            timings["embeddings"] = round(time.time() - t, 1)
        return _process_local(video_id, wd, proxy, perc, brands, rules, log, timings, t_start)

    # ---- B. global scene understanding ----
    sp = wd / "scenes.json"
    scen = None if "B" in force else _load(sp)
    if scen is None:
        t = time.time()
        log("B · uploading episode to Gemini")
        f = gemini.upload_video(proxy, log=log)
        log("B · Gemini watching full episode → semantic scenes")
        scen = understand.analyse(f, duration, perc["shots"], brands, log=log)
        scen["model"] = gemini.MODEL_GLOBAL
        _save(sp, scen)
        timings["global_scenes"] = round(time.time() - t, 1)
    scenes = scen["scenes"]
    log(f"B · {len(scenes)} scenes")

    # ---- C + D. candidates + local judgement ----
    cp = wd / "candidates.json"
    cands = None if "C" in force else _load(cp)
    rules_c = {k: rules[k] for k in ("no_break_first_sec", "no_break_last_sec")}
    if cands is None or cands.get("rules") != rules_c:
        t = time.time()
        log("C · generating + snapping break candidates")
        lst = breaks.generate(scenes, perc["shots"], perc["speech"], perc["blacks"], perc["loudness"], duration, rules)
        log(f"D · Gemini judging {sum(1 for c in lst if not c['rejections'])} cut points")
        breaks.judge_all(lst, proxy, wd, scenes, log=log, workers=LLM_WORKERS)
        for c in lst:
            c["where_score"] = breaks.where_score(c)
        cands = {"rules": rules_c, "items": lst}
        _save(cp, cands)
        timings["candidates"] = round(time.time() - t, 1)
    items = cands["items"]

    # ---- E. brand matching ----
    ch = catalogue_hash(brands)
    mp = wd / f"match_{ch}.json"
    matched = None if "E" in force else _load(mp)
    if matched is None:
        t = time.time()
        ads.ensure_all(WEB, brands, log=log)
        pool = [json.loads(json.dumps(c)) for c in items if not c["rejections"] and c["where_score"] >= 0.35]
        brandlib.match_all(pool, brands, scenes, proxy, wd, log=log, workers=LLM_WORKERS)
        matched = {"catalogue_hash": ch, "items": {c["id"]: c for c in pool}, "verify": {}}
        _save(mp, matched)
        timings["brand_matching"] = round(time.time() - t, 1)

    models = {"global": scen.get("model"), "local": gemini.MODEL_LOCAL}
    return _finish(video_id, wd, perc, scen, items, matched, mp, brands, rules, log, timings, t_start,
                   lambda c, b: brandlib.verify(c, b, scenes, proxy, wd), models)



def _finish(video_id, wd, perc, scen, items, matched, mp, brands, rules, log, timings, t_start, verify_fn, models):
    """F · pacing selection + independent verification + creative choice + outputs (engine-agnostic)."""
    duration = perc["duration"]
    scenes = scen["scenes"]
    ch = catalogue_hash(brands)
    # ---- F. selection + verification ----
    t = time.time()
    by_id = {b["brand_id"]: b for b in brands}
    merged = []
    for c in items:
        m = matched["items"].get(c["id"])
        merged.append(json.loads(json.dumps(m if m else c)))
    for c in merged:
        c["rejections"] = [x for x in c["rejections"] if not x.startswith("every brand is blocked")]
        if c.get("match"):
            brandlib.rank(c, brands, scenes)
        viable = [r for r in c.get("brand_ranking", []) if not r["blocked"]]
        c["quality"] = round(c["where_score"] + rules["brand_relevance_weight"] * (viable[0]["relevance"] if viable else 0), 3)
        if not c["rejections"] and c["where_score"] < rules["min_break_score"]:
            c["rejections"].append(f"break quality {c['where_score']:.2f} below threshold {rules['min_break_score']}")
        if not c["rejections"] and not viable:
            c["rejections"].append("no brand available after safety blocks")

    budget = pacing.ad_budget(duration, rules)
    final: list[dict] = []
    for _ in range(3):
        eligible = [c for c in merged if not c["rejections"]]
        chosen = pacing.select(eligible, duration, rules)
        final, dropped, remaining, prev_brand = [], False, budget, None
        for i, c in enumerate(chosen):
            viable = [r for r in c["brand_ranking"] if not r["blocked"] and not r.get("verifier_blocked")]
            if len(viable) > 1 and viable[0]["brand_id"] == prev_brand and viable[0]["relevance"] - viable[1]["relevance"] < 0.2:
                viable[0], viable[1] = viable[1], viable[0]
            pick = None
            for r in viable[:2]:
                key = f"{c['id']}:{r['brand_id']}"
                v = matched["verify"].get(key)
                if v is None:
                    log(f"F · verifying {r['brand_id']} at {manifest.ts(c['t'])}")
                    try:
                        v = verify_fn(c, by_id[r["brand_id"]])
                    except Exception as e:
                        v = {"violation": True, "violated_contexts": [], "evidence": f"verifier error (fail-closed): {e}", "confidence": 0, "error": True}
                    if not v.get("error"):
                        matched["verify"][key] = v
                        if mp:
                            _save(mp, matched)
                r["verifier"] = v
                if v["violation"]:
                    r["verifier_blocked"] = True
                    continue
                pick = r
                break
            slots_left = len(chosen) - i
            creative = brandlib.pick_creative(by_id[pick["brand_id"]], remaining / slots_left) if pick else None
            if pick and creative is None:
                crs = sorted(by_id[pick["brand_id"]].get("creatives", []), key=lambda x: x["duration_sec"])
                creative = crs[0] if crs and crs[0]["duration_sec"] <= remaining else None
            if not pick or not creative:
                c["rejections"].append("verifier blocked every viable brand" if not pick else "ad-load budget exhausted")
                dropped = True
                continue
            remaining -= creative["duration_sec"]
            prev_brand = pick["brand_id"]
            j = c.get("judge") or {}
            final.append({
                "candidate_id": c["id"], "t": c["t"], "quality": c["quality"], "where_score": c["where_score"],
                "brand_id": pick["brand_id"], "brand_name": by_id[pick["brand_id"]].get("display_name", pick["brand_id"]),
                "relevance": pick["relevance"], "matched_contexts": pick["matched_contexts"],
                "dominant_activity": c.get("dominant_activity", ""), "creative": creative,
                "reason": f"{j.get('reason', '')} Brand: {pick['rationale']}".strip(),
                "last_line_before_cut": j.get("last_line_before_cut", ""),
                "first_line_after_cut": j.get("first_line_after_cut", ""),
                "blocked_brands": [{"brand_id": r["brand_id"], "why": (r["blocks"] or [{"negative_context": "verifier", "evidence": (r.get("verifier") or {}).get("evidence", "")}])}
                                   for r in c["brand_ranking"] if r["blocked"] or r.get("verifier_blocked")],
            })
        if not dropped:
            break
    chosen_ids = {b["candidate_id"] for b in final}
    for c in merged:
        c["selected"] = c["id"] in chosen_ids
        if not c["selected"] and not c["rejections"]:
            c["rejections"].append("not chosen: pacing rules (min gap / max breaks) favoured a better nearby break")
    timings["selection"] = round(time.time() - t, 1)

    brandlib.annotate_scenes(scenes, brands)
    ad_time = sum(b["creative"]["duration_sec"] for b in final)
    audit = self_audit(final, merged, perc, duration, rules, by_id, scenes)
    result = {
        "video_id": video_id,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "engine": ENGINE,
        "models": models,
        "catalogue_hash": ch,
        "brands": [b["brand_id"] for b in brands],
        "video": {k: perc[k] for k in ("duration", "width", "height", "fps")},
        "rules": rules,
        "summary": {
            "scenes": len(scenes), "camera_cuts": len(perc["shots"]), "candidates": len(merged),
            "breaks": len(final), "ad_seconds": ad_time,
            "ad_load_pct": round(100 * ad_time / (duration + ad_time), 2) if final else 0.0,
            "breaks_per_hour": round(len(final) / (duration / 3600), 2),
            "allowed_breaks": pacing.allowed_breaks(duration, rules),
        },
        "audit": audit,
        "synopsis": scen.get("synopsis", ""),
        "breaks": final,
        "scenes": scenes,
        "candidates": merged,
        "speech": perc["speech"],
        "shots": perc["shots"],
        "blacks": perc["blacks"],
        "timings_sec": {**timings, "total_this_run": round(time.time() - t_start, 1)},
    }
    v = result_variant(brands, rules)
    result["variant"] = v
    _save(wd / f"catalogue_{ch}.json", brands)
    _save(wd / f"result_{v}.json", result)
    (wd / f"vmap_{v}.xml").write_text(manifest.build_vmap(video_id, final), encoding="utf-8")
    log(f"done · {len(final)} breaks, ad load {result['summary']['ad_load_pct']}%")
    return result


def _process_local(video_id, wd, proxy, perc, brands, rules, log, timings, t_start):
    """B–E with the free local engine (seconds per episode once embeddings are cached)."""
    from . import local_engine

    duration = perc["duration"]
    t = time.time()
    scen = local_engine.analyse(wd, duration, perc["shots"], brands, log=log)
    scenes = scen["scenes"]
    lst = breaks.generate(scenes, perc["shots"], perc["speech"], perc["blacks"], perc["loudness"], duration, rules)
    local_engine.judge_all(lst, wd, scenes, log=log)
    for c in lst:
        c["where_score"] = breaks.where_score(c)
    ads.ensure_all(WEB, brands, log=log)
    pool = [json.loads(json.dumps(c)) for c in lst if not c["rejections"] and c["where_score"] >= 0.35]
    local_engine.match_all(pool, brands, scenes, wd, log=log)
    matched = {"catalogue_hash": catalogue_hash(brands), "items": {c["id"]: c for c in pool}, "verify": {}}
    timings["local_understanding"] = round(time.time() - t, 1)
    models = {"vision": "openai/clip-vit-base-patch32", "audio": "laion/clap-htsat-unfused", "speech": "silero-vad"}
    return _finish(video_id, wd, perc, scen, lst, matched, None, brands, rules, log, timings, t_start,
                   lambda c, b: local_engine.verify(c, b, proxy, wd), models)

if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--brands", default=str(ROOT / "data" / "brands.json"))
    ap.add_argument("--force", default="", help="stages to recompute, e.g. BCE")
    a = ap.parse_args()
    src = Path(a.video)
    bl = json.loads(Path(a.brands).read_text(encoding="utf-8"))
    r = process(src.stem, src, bl, force=set(a.force))
    print(json.dumps(r["summary"], indent=1))
    for b in r["breaks"]:
        print(manifest.ts(b["t"]), b["brand_id"], b["creative"]["id"], b["quality"], "|", b["reason"][:140])
