"""Cache CLIP frame + CLAP audio embeddings for every processed sample."""
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.pipeline import local_models as lm  # noqa: E402

WORK = Path(__file__).resolve().parents[1] / "data" / "work"
for wd in sorted(p for p in WORK.iterdir() if (p / "proxy.mp4").exists()):
    out = wd / "local_embeds.npz"
    if out.exists():
        continue
    t = time.time()
    ft, fe = lm.embed_frames(wd / "proxy.mp4", fps=1.0)
    at, ae = lm.embed_audio(wd / "proxy.mp4")
    np.savez_compressed(out, frame_t=ft, frame_e=fe, audio_t=at, audio_e=ae)
    print(f"{wd.name}: {len(ft)} frames, {len(at)} audio windows, {time.time() - t:.0f}s", flush=True)
