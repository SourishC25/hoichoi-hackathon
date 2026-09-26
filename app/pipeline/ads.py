"""Synthetic ad creatives. The catalogue references creative files that are not supplied, so we
render a clearly-labelled placeholder spot for any creative that is missing — including creatives
of brands added later — so every manifest is playable end to end."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

from . import media

FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
]


def _font() -> str:
    for f in FONT_CANDIDATES:
        if os.path.exists(f):
            return f.replace("\\", "/").replace(":", r"\:")
    return ""


def _esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace(":", r"\:").replace("'", "\u2019").replace("%", r"\%").replace(",", r"\,")


def _color(brand_id: str) -> tuple[str, str]:
    h = hashlib.md5(brand_id.encode()).hexdigest()
    return f"0x{h[:6]}", f"0x{h[6:12]}"


def ensure_creative(web_root: Path, brand: dict, creative: dict) -> Path | None:
    url = creative.get("url", "")
    if url.startswith("http"):
        return None
    path = web_root / url
    if path.exists():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    d = float(creative["duration_sec"])
    c1, c2 = _color(brand["brand_id"])
    font = _font()
    ff = f"fontfile='{font}':" if font else ""
    name, cat = _esc(brand.get("display_name", brand["brand_id"])), _esc(brand.get("category", ""))
    vf = ",".join([
        f"drawbox=x=0:y=ih*0.62:w=iw:h=ih*0.38:color={c2}@0.85:t=fill",
        f"drawtext={ff}text='{name}':fontsize=64:fontcolor=white:x=(w-tw)/2:y=h*0.25",
        f"drawtext={ff}text='{cat}':fontsize=28:fontcolor=white@0.9:x=(w-tw)/2:y=h*0.25+80",
        f"drawtext={ff}text='SYNTHETIC AD  ·  {_esc(creative['id'])}':fontsize=22:fontcolor=white:x=(w-tw)/2:y=h*0.70",
        f"drawtext={ff}text='Ad · %{{eif\\:{d}-t\\:d}}s':fontsize=26:fontcolor=white:x=w-tw-24:y=h-50",
    ])
    tmp = path.with_suffix(".tmp.mp4")
    media.run([
        "ffmpeg", "-y", "-v", "error",
        "-f", "lavfi", "-i", f"color=c={c1}:s=854x480:r=25:d={d}",
        "-f", "lavfi", "-i", f"sine=frequency=220:sample_rate=44100:duration={d}",
        "-vf", vf, "-af", "volume=0.04", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "64k", "-shortest", "-movflags", "+faststart", str(tmp),
    ])
    tmp.replace(path)
    return path


def ensure_all(web_root: Path, brands: list[dict], log=print) -> None:
    for b in brands:
        for cr in b.get("creatives", []):
            if ensure_creative(web_root, b, cr):
                pass
    log(f"creatives ready for {len(brands)} brands")
