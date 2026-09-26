"""Run the local engine on every sample and score its placements against the Gemini teacher labels.

teacher-judged violation = a placed brand whose negative_contexts the teacher (which understood the
Bengali dialogue) tagged in any scene within the brand-safety window around the break.
usage: python scripts/evaluate_local.py [--vis 2.0 --aud 2.5]"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.pipeline import brands as brandlib, local_engine as le, run  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--vis", type=float)
ap.add_argument("--aud", type=float)
ap.add_argument("--brands", default=str(run.ROOT / "data" / "brands.json"))
a = ap.parse_args()
if a.vis or a.aud:
    cal = le.calib()
    cal["vis_thr"] = a.vis or cal["vis_thr"]
    cal["aud_thr"] = a.aud or cal["aud_thr"]
    le.CALIB_PATH.write_text(json.dumps(cal, indent=1), encoding="utf-8")

brands = json.loads(Path(a.brands).read_text(encoding="utf-8"))
by_id = {b["brand_id"]: b for b in brands}
report, total_v, total_b = {}, 0, 0
for wd in sorted(p for p in run.WORK.iterdir() if (p / "local_embeds.npz").exists()):
    r = run.process(wd.name, wd / "proxy.mp4", brands, log=lambda m: None)
    teacher = json.loads((wd / "scenes.json").read_text(encoding="utf-8"))["scenes"] if (wd / "scenes.json").exists() else []
    viol = []
    for b in r["breaks"]:
        hits = brandlib.deterministic_blocks(by_id[b["brand_id"]], teacher, b["t"]) if teacher else []
        if hits:
            viol.append({"t": b["t"], "brand": b["brand_id"], "teacher": sorted({h["negative_context"] for h in hits})})
    total_v += len(viol)
    total_b += len(r["breaks"])
    report[wd.name] = {"breaks": [(round(b["t"]), b["brand_id"], b["dominant_activity"]) for b in r["breaks"]],
                       "allowed": r["summary"]["allowed_breaks"], "teacher_violations": viol,
                       "audit_pass": all(x["pass"] for x in r["audit"])}
    print(wd.name, json.dumps(report[wd.name], ensure_ascii=False))
print(f"TOTAL breaks={total_b} teacher-judged violations={total_v}")
(run.ROOT / "data" / "evaluation_report.json").write_text(json.dumps({"breaks": total_b, "teacher_violations": total_v, "episodes": report}, indent=1), encoding="utf-8")
