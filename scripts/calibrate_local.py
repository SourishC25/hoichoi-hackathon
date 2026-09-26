"""Calibrate the free local engine against Gemini labels from development runs (teacher → student).

1. Reference bank: random frames + audio windows from the sample episodes (unsupervised; gives each
   concept's baseline so scores become z-scores).
2. Scene threshold τ: grid-search boundary F1 vs Gemini scene starts (±4 s tolerance).
3. Sensitive-topic thresholds (z-units): recall-weighted (F2) — a missed funeral is a disqualifier,
   a false alarm only costs one ad slot. Global thresholds + per-term overrides with enough positives.
Reports leave-one-episode-out (LOEO) scores so the numbers reflect unseen episodes."""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.pipeline import local_engine as le  # noqa: E402
from app.pipeline.brands import IMPLIES  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "data" / "work"
rng = np.random.default_rng(0)
eps = [d for d in sorted(WORK.iterdir()) if (d / "local_embeds.npz").exists() and (d / "scenes.json").exists()]
print("episodes:", [e.name for e in eps])

# ---- 1. reference bank ----
F, A = [], []
for d in eps:
    z = np.load(d / "local_embeds.npz")
    fe, ae = z["frame_e"], z["audio_e"]
    F.append(fe[rng.choice(len(fe), min(700, len(fe)), replace=False)])
    A.append(ae[rng.choice(len(ae), min(250, len(ae)), replace=False)])
np.savez_compressed(le.REF_PATH, frame_e=np.concatenate(F), audio_e=np.concatenate(A))
le._ref = None
le._zstats.clear()
print("reference bank:", sum(len(x) for x in F), "frames,", sum(len(x) for x in A), "audio windows")

brands = json.loads((ROOT / "data" / "brands.json").read_text(encoding="utf-8"))
terms = le.sensitive_terms(brands)
cue_terms = [t for t in terms if le.has_audio_cue(t)]


def gem(d):
    return json.loads((d / "scenes.json").read_text(encoding="utf-8"))["scenes"]


def perc(d):
    return json.loads((d / "perception.json").read_text(encoding="utf-8"))


# ---- 2. scene threshold ----
def boundary_f1(tau, ds):
    tp = fp = fn = 0
    for d in ds:
        p = perc(d)
        ep = le.Episode(d)
        pred = [a for a, _, _ in le.segment(ep, p["shots"], p["duration"], tau)][1:]
        gold = [s["start"] for s in gem(d)][1:]
        used = set()
        for g in gold:
            m = [i for i, x in enumerate(pred) if abs(x - g) <= 4.0 and i not in used]
            if m:
                used.add(m[0])
                tp += 1
            else:
                fn += 1
        fp += len(pred) - len(used)
    pr, rc = tp / max(1, tp + fp), tp / max(1, tp + fn)
    return 2 * pr * rc / max(1e-9, pr + rc), pr, rc


grid = [0.06, 0.08, 0.10, 0.12, 0.14, 0.16, 0.18, 0.20, 0.23, 0.26]
res = {t: boundary_f1(t, eps) for t in grid}
tau = max(res, key=lambda t: res[t][0])
loeo_scene = [boundary_f1(max(grid, key=lambda t: boundary_f1(t, [e for e in eps if e != d])[0]), [d]) for d in eps]
print(f"scene τ={tau}: F1={res[tau][0]:.2f} P={res[tau][1]:.2f} R={res[tau][2]:.2f} | LOEO F1={np.mean([x[0] for x in loeo_scene]):.2f}")

# ---- 3. sensitive thresholds (on Gemini scene spans) ----
rows = []  # (episode, term, vis_z, aud_z, label)
for d in eps:
    ep = le.Episode(d)
    for s in gem(d):
        fi, ai = ep.fidx(s["start"], s["end"]), ep.aidx(s["start"], s["end"])
        zv = le.topq(le.vis_z(ep.fe[fi], terms)) if len(fi) else np.full(len(terms), -9.0)
        za = le.topq(le.aud_z(ep.ae[ai], terms), 0.2, 1) if len(ai) else np.full(len(terms), -9.0)
        tags = set()
        for x in s.get("sensitive", []):
            if x.get("confidence", 0) >= 0.5:
                t0 = x["topic"].strip().lower()
                tags |= {t0, *IMPLIES.get(t0, [])}
        for j, t in enumerate(terms):
            rows.append((d.name, t.lower(), float(zv[j]), float(za[j]), t.lower() in tags))


def evaluate(rs, tv, ta, per=None):
    tp = fp = fn = tn = 0
    for _, t, zv, za, y in rs:
        o = (per or {}).get(t, {})
        hit = zv >= o.get("vis", tv) or (t in [c.lower() for c in cue_terms] and za >= o.get("aud", ta))
        tp += hit and y
        fp += hit and not y
        fn += (not hit) and y
        tn += (not hit) and (not y)
    pr, rc = tp / max(1, tp + fp), tp / max(1, tp + fn)
    f2 = 5 * pr * rc / max(1e-9, 4 * pr + rc)
    return {"f2": f2, "precision": pr, "recall": rc, "flag_rate": (tp + fp) / max(1, len(rs)), "positives": tp + fn}


def fit(rs):
    best = None
    for tv in np.arange(1.0, 4.01, 0.25):
        for ta in np.arange(1.5, 5.01, 0.5):
            m = evaluate(rs, tv, ta)
            if best is None or m["f2"] > best[0]["f2"]:
                best = (m, float(tv), float(ta))
    m, tv, ta = best
    per = {}
    for t in {r[1] for r in rs}:
        sub = [r for r in rs if r[1] == t]
        if sum(r[4] for r in sub) >= 3:
            cand = []
            for v in np.arange(1.0, 4.51, 0.25):
                mm = evaluate(sub, v, ta)
                if mm["recall"] >= 0.8:
                    cand.append((mm["precision"], float(v)))
            if cand:
                per[t] = {"vis": max(cand)[1]}
    return tv, ta, per


tv, ta, per = fit(rows)
overall = evaluate(rows, tv, ta, per)
print(f"sensitive: vis_thr={tv} aud_thr={ta} per-term={per}")
print("in-sample:", {k: round(v, 3) for k, v in overall.items()})
loeo = []
for d in eps:
    tr = [r for r in rows if r[0] != d.name]
    te = [r for r in rows if r[0] == d.name]
    a, b, c = fit(tr)
    loeo.append(evaluate(te, a, b, c))
loeo_sum = {k: round(float(np.mean([x[k] for x in loeo if x["positives"] or k in ("flag_rate",)])), 3) for k in ("precision", "recall", "f2", "flag_rate")}
print("LOEO (held-out episode):", loeo_sum)

per_term_report = {}
for t in sorted({r[1] for r in rows}):
    sub = [r for r in rows if r[1] == t]
    m = evaluate(sub, tv, ta, per)
    if m["positives"]:
        per_term_report[t] = {k: round(v, 3) for k, v in m.items()}

cal = {"scene_tau": tau, "vis_thr": tv, "aud_thr": ta, "rel_mid": 1.5, "rel_width": 0.7, "per_term": per}
le.CALIB_PATH.write_text(json.dumps(cal, indent=1), encoding="utf-8")
report = {
    "teacher": "Gemini scene labels from development runs", "episodes": [e.name for e in eps],
    "scene_boundaries": {"tau": tau, "f1": round(res[tau][0], 3), "precision": round(res[tau][1], 3),
                         "recall": round(res[tau][2], 3), "loeo_f1": round(float(np.mean([x[0] for x in loeo_scene])), 3)},
    "sensitive_in_sample": {k: round(v, 3) for k, v in overall.items()},
    "sensitive_loeo": loeo_sum, "per_term": per_term_report,
}
(ROOT / "data" / "calibration_report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
print("saved calibration.json + calibration_report.json")
