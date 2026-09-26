"""Export the processed sample episodes + UI as a static site (free hosting, e.g. a static HF Space).

usage: python scripts/export_static.py [--space user/name] [--out dist]
Publishes, per episode, the default-catalogue run and the default + unseen 'Brand I' run."""
import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.pipeline import ads, media, pacing, run  # noqa: E402

ROOT = run.ROOT
ap = argparse.ArgumentParser()
ap.add_argument("--space", default="")
ap.add_argument("--out", default=str(ROOT / "dist"))
a = ap.parse_args()
out = Path(a.out)
if out.exists():
    shutil.rmtree(out)
(out / "api").mkdir(parents=True)

base = ""
if a.space:
    user, name = a.space.split("/")
    base = f"https://{user.lower()}-{name.lower().replace('_', '-')}.static.hf.space"

default = json.loads((ROOT / "data" / "brands.json").read_text(encoding="utf-8"))
plus9 = json.loads((ROOT / "data" / "brands_plus_unseen.json").read_text(encoding="utf-8"))
variants = {"": run.result_variant(default, None), "plus9": run.result_variant(plus9, None)}
ads.ensure_all(run.WEB, plus9)

videos = []
for wd in sorted(p for p in run.WORK.iterdir() if p.is_dir()):
    rp = wd / f"result_{variants['']}.json"
    if not rp.exists() or not (wd / "proxy.mp4").exists():
        continue
    vid = wd.name
    d = out / "data" / vid
    d.mkdir(parents=True)
    (out / "thumbs" / vid).mkdir(parents=True)
    for suffix, v in variants.items():
        rpath = wd / f"result_{v}.json"
        if not rpath.exists():
            continue
        tag = f"_{suffix}" if suffix else ""
        r = json.loads(rpath.read_text(encoding="utf-8"))
        (d / f"result{tag}.json").write_text(json.dumps(r, ensure_ascii=False), encoding="utf-8")
        xml = (wd / f"vmap_{v}.xml").read_text(encoding="utf-8").replace("{BASE}", base or ".")
        (d / f"vmap{tag}.xml").write_text(xml, encoding="utf-8")
        shutil.copy(wd / f"catalogue_{r['catalogue_hash']}.json", d / f"catalogue{tag}.json")
        for b in r["breaks"]:
            t = max(0.0, b["t"] - 1)
            media.thumbnail(wd / "proxy.mp4", out / "thumbs" / vid / f"{t:.2f}.jpg", t)
        if not suffix:
            videos.append({"id": vid, "duration": r["video"]["duration"], "summary": r["summary"],
                           "synopsis": r.get("synopsis", ""), "uploaded": False})
    (out / "media").mkdir(exist_ok=True)
    shutil.copy(wd / "proxy.mp4", out / "media" / f"{vid}.mp4")
    print("exported", vid)

(out / "api" / "videos.json").write_text(json.dumps(videos), encoding="utf-8")
(out / "api" / "brands.json").write_text(json.dumps(default, ensure_ascii=False), encoding="utf-8")
(out / "api" / "rules.json").write_text(json.dumps(pacing.DEFAULT_RULES), encoding="utf-8")
# UI: the Next.js static build (frontend/out), flagged as a static mirror via runtime.json
front = ROOT / "frontend" / "out"
if not (front / "index.html").exists():
    subprocess.run("npm run build", cwd=ROOT / "frontend", shell=True, check=True)
shutil.copytree(front, out, dirs_exist_ok=True)
(out / "runtime.json").write_text(json.dumps({"static": True}), encoding="utf-8")
shutil.copytree(run.WEB / "ads", out / "ads")
cal = ROOT / "data" / "calibration_report.json"
if cal.exists():
    shutil.copy(cal, out / "api" / "calibration_report.json")
readme = ROOT / "README.md"
body = readme.read_text(encoding="utf-8") if readme.exists() else ""
(out / "README.md").write_text("""---
title: Birati - Contextual Ad Breaks
emoji: 🎬
colorFrom: pink
colorTo: indigo
sdk: static
app_file: index.html
pinned: false
short_description: AI ad-break placement for Bengali drama (free, local models)
---
""" + body, encoding="utf-8")
print(f"static site in {out} ({len(videos)} episodes)" + (f" · base {base}" if base else ""))
