"""Batch-run the pipeline over every video in data/videos (cached stages are reused)."""
import json
import os
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.pipeline import run  # noqa: E402

brands = json.loads((run.ROOT / "data" / "brands.json").read_text(encoding="utf-8"))
names = sys.argv[1:] or [p.stem for p in sorted((run.ROOT / "data" / "videos").glob("*.mp4"))]
for n in names:
    src = run.ROOT / "data" / "videos" / f"{n}.mp4"
    try:
        r = run.process(n, src, brands, log=lambda m, n=n: print(f"[{n}] {m}", flush=True), force=set(os.getenv("FORCE", "")))
        print(f"[{n}] SUMMARY {json.dumps(r['summary'])}", flush=True)
    except Exception:
        print(f"[{n}] FAILED\n{traceback.format_exc()}", flush=True)
