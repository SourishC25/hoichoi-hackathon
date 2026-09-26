"""Pipeline orchestrator with per-stage caching.

  A  perception   (ffmpeg, PySceneDetect, Silero VAD)            -> perception.json
  B  global scenes (Gemini, full episode)                         -> scenes.json
  C+D candidates + local cut judgement (signals + Gemini clips)   -> candidates.json
  E  brand matching + safety (Gemini, catalogue-dependent)        -> match_<cataloguehash>.json
  F  pacing selection + verification + creative choice            -> result.json (debug) + vmap.xml

Changing the brand catalogue re-runs only E–F; changing pacing rules re-runs only F.
Nothing here knows anything about specific videos or brands."""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

from . import ads, brands as brandlib, breaks, gemini, manifest, media, pacing, signals, understand

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / "data" / "work"
WEB = ROOT / "web"


def _load(p: Path):
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def _save(p: Path, obj) -> None:
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")


def catalogue_hash(brands: list[dict]) -> str:
    return hashlib.sha1(json.dumps(brands, sort_keys=True).encode()).hexdigest()[:10]


def variant_id(brands: list[dict], rules: dict | None) -> str:
    rules = {**pacing.DEFAULT_RULES, **(rules or {})}
    return hashlib.sha1((catalogue_hash(brands) + json.dumps(rules, sort_keys=True)).encode()).hexdigest()[:10]


def process(video_id: str, source: Path, brands: list[dict], rules: dict | None = None,
            log=print, force: set[str] | None = None) -> dict:
    rules = {**pacing.DEFAULT_RULES, **(rules or {})}
    force = force or set()
    wd = WORK / video_id
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
        log("A · detecting camera cuts")
        shots = signals.detect_shots(proxy)
        log(f"A · {len(shots)} cuts; running speech detection (Silero VAD)")
        wav = media.extract_audio(proxy, wd / "audio.wav")
        speech = signals.detect_speech(wav)
        loud = signals.loudness(wav)
        log("A · detecting fades to black")
        blacks = media.black_segments(proxy)
        perc = {**info, "shots": shots, "speech": speech, "loudness": loud, "blacks": blacks}
        _save(pp, perc)
        timings["perception"] = round(time.time() - t, 1)
    else:
        media.make_proxy(source, proxy)
    duration = perc["duration"]

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
        breaks.judge_all(lst, proxy, wd, scenes, log=log)
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
        brandlib.match_all(pool, brands, scenes, proxy, wd, log=log)
        matched = {"catalogue_hash": ch, "items": {c["id"]: c for c in pool}, "verify": {}}
        _save(mp, matched)
        timings["brand_matching"] = round(time.time() - t, 1)

    # ---- F. selection + verification ----
    t = time.time()
    by_id = {b["brand_id"]: b for b in brands}
    merged = []
    for c in items:
        m = matched["items"].get(c["id"])
        merged.append(json.loads(json.dumps(m if m else c)))
    for c in merged:
        viable = [r for r in c.get("brand_ranking", []) if not r["blocked"]]
        c["quality"] = round(c["where_score"] + rules["brand_relevance_weight"] * (viable[0]["relevance"] if viable else 0), 3)
        if not c["rejections"] and c["where_score"] < rules["min_break_score"]:
            c["rejections"].append(f"break quality {c['where_score']:.2f} below threshold {rules['min_break_score']}")
        if not c["rejections"] and not viable:
            c["rejections"].append("no brand available after safety blocks")

    budget = pacing.ad_budget(duration, rules)
    final: list[dict] = []
    for _ in range(4):
        eligible = [c for c in merged if not c["rejections"]]
        chosen = pacing.select(eligible, duration, rules)
        final, dropped, remaining, prev_brand = [], False, budget, None
        for i, c in enumerate(chosen):
            viable = [r for r in c["brand_ranking"] if not r["blocked"] and not r.get("verifier_blocked")]
            if len(viable) > 1 and viable[0]["brand_id"] == prev_brand and viable[0]["relevance"] - viable[1]["relevance"] < 0.2:
                viable[0], viable[1] = viable[1], viable[0]
            pick = None
            for r in viable[:4]:
                key = f"{c['id']}:{r['brand_id']}"
                v = matched["verify"].get(key)
                if v is None:
                    log(f"F · verifying {r['brand_id']} at {manifest.ts(c['t'])}")
                    try:
                        v = brandlib.verify(c, by_id[r["brand_id"]], scenes, proxy, wd)
                    except Exception as e:
                        v = {"violation": True, "violated_contexts": [], "evidence": f"verifier error (fail-closed): {e}", "confidence": 0}
                    matched["verify"][key] = v
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
    result = {
        "video_id": video_id,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "models": {"global": scen.get("model"), "local": gemini.MODEL_LOCAL},
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
        "synopsis": scen.get("synopsis", ""),
        "breaks": final,
        "scenes": scenes,
        "candidates": merged,
        "speech": perc["speech"],
        "shots": perc["shots"],
        "blacks": perc["blacks"],
        "timings_sec": {**timings, "total_this_run": round(time.time() - t_start, 1)},
    }
    v = variant_id(brands, rules)
    result["variant"] = v
    _save(wd / f"catalogue_{ch}.json", brands)
    _save(wd / f"result_{v}.json", result)
    (wd / f"vmap_{v}.xml").write_text(manifest.build_vmap(video_id, final), encoding="utf-8")
    log(f"done · {len(final)} breaks, ad load {result['summary']['ad_load_pct']}%")
    return result


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
