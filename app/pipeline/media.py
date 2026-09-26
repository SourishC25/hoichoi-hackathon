"""ffmpeg / ffprobe helpers: probing, proxy transcode, audio extraction, black-frame
detection and clip cutting."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path


def _ensure_ffmpeg() -> None:
    if shutil.which("ffmpeg") and shutil.which("ffprobe"):
        return
    import static_ffmpeg  # downloads a static build on first use

    static_ffmpeg.add_paths()


_ensure_ffmpeg()


def run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", check=True)


def probe(path: Path) -> dict:
    out = run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)]).stdout
    info = json.loads(out)
    v = next((s for s in info["streams"] if s["codec_type"] == "video"), {})
    num, _, den = (v.get("avg_frame_rate") or "25/1").partition("/")
    return {
        "duration": float(info["format"]["duration"]),
        "width": v.get("width"),
        "height": v.get("height"),
        "fps": float(num) / float(den or 1) if float(den or 1) else 25.0,
    }


def make_proxy(src: Path, dst: Path, height: int = 480) -> Path:
    """Web/LLM friendly H.264 proxy with fast-start so it streams with range requests."""
    if dst.exists():
        return dst
    tmp = dst.with_suffix(".tmp.mp4")
    run([
        "ffmpeg", "-y", "-v", "error", "-i", str(src),
        "-vf", f"scale=-2:{height}", "-c:v", "libx264", "-preset", "veryfast", "-crf", "27",
        "-c:a", "aac", "-b:a", "96k", "-ac", "2", "-movflags", "+faststart", str(tmp),
    ])
    tmp.replace(dst)
    return dst


def extract_audio(src: Path, dst: Path, sr: int = 16000) -> Path:
    if not dst.exists():
        run(["ffmpeg", "-y", "-v", "error", "-i", str(src), "-vn", "-ac", "1", "-ar", str(sr), "-c:a", "pcm_s16le", str(dst)])
    return dst


def black_segments(src: Path, min_dur: float = 0.25) -> list[dict]:
    """Fade-to-black / black frames — strong natural-break cues in TV drama."""
    p = subprocess.run(
        ["ffmpeg", "-v", "info", "-i", str(src), "-vf", f"blackdetect=d={min_dur}:pix_th=0.10", "-an", "-f", "null", "-"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    segs = []
    for m in re.finditer(r"black_start:([\d.]+)\s+black_end:([\d.]+)", p.stderr):
        segs.append({"start": float(m.group(1)), "end": float(m.group(2))})
    return segs


def cut_clip(src: Path, dst: Path, start: float, end: float, height: int = 360) -> Path:
    """Re-encoded (frame-accurate) short clip for local LLM judgement."""
    start = max(0.0, start)
    run([
        "ffmpeg", "-y", "-v", "error", "-ss", f"{start:.3f}", "-i", str(src), "-t", f"{end - start:.3f}",
        "-vf", f"scale=-2:{height}", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "30",
        "-c:a", "aac", "-b:a", "64k", "-ac", "1", str(dst),
    ])
    return dst


def cut_clip_marked(src: Path, dst: Path, start: float, cut: float, end: float, height: int = 360,
                    card_sec: float = 1.5, label: str = "AD BREAK") -> Path:
    """Clip [start, end] with a black 'AD BREAK' card spliced in at `cut`. Showing the model the
    break *in the video itself* removes any ambiguity about where the cut sits (LLM timestamp
    perception on short clips is only ~1 s accurate)."""
    start = max(0.0, start)
    rel = cut - start
    w = int(round(height * 16 / 9 / 2) * 2)
    norm_v = f"scale={w}:{height}:force_original_aspect_ratio=decrease,pad={w}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=25,format=yuv420p"
    norm_a = "aformat=sample_rates=22050:channel_layouts=mono"
    font = next((f for f in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "C:/Windows/Fonts/arialbd.ttf") if Path(f).exists()), None)
    ff = f"fontfile='{font.replace(':', chr(92) + ':')}':" if font else ""
    fc = (
        f"[0:v]{norm_v},split[va][vb];[va]trim=0:{rel:.3f},setpts=PTS-STARTPTS[v1];"
        f"[vb]trim={rel:.3f},setpts=PTS-STARTPTS[v2];"
        f"[0:a]{norm_a},asplit[aa][ab];[aa]atrim=0:{rel:.3f},asetpts=PTS-STARTPTS[a1];"
        f"[ab]atrim={rel:.3f},asetpts=PTS-STARTPTS[a2];"
        f"[1:v]{norm_v},drawtext={ff}text='{label}':fontsize=48:fontcolor=yellow:x=(w-tw)/2:y=(h-th)/2[card];"
        f"[2:a]{norm_a}[ca];"
        f"[v1][a1][card][ca][v2][a2]concat=n=3:v=1:a=1[v][a]"
    )
    run([
        "ffmpeg", "-y", "-v", "error", "-ss", f"{start:.3f}", "-t", f"{end - start:.3f}", "-i", str(src),
        "-f", "lavfi", "-t", f"{card_sec}", "-i", f"color=c=black:s={w}x{height}:r=25",
        "-f", "lavfi", "-t", f"{card_sec}", "-i", "anullsrc=r=22050:cl=mono",
        "-filter_complex", fc, "-map", "[v]", "-map", "[a]",
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "30", "-c:a", "aac", "-b:a", "48k", str(dst),
    ])
    return dst


def thumbnail(src: Path, dst: Path, t: float, height: int = 180) -> Path:
    if not dst.exists():
        run(["ffmpeg", "-y", "-v", "error", "-ss", f"{max(0.0, t):.3f}", "-i", str(src), "-frames:v", "1",
             "-vf", f"scale=-2:{height}", "-q:v", "4", str(dst)])
    return dst
