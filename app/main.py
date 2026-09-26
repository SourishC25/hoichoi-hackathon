"""FastAPI server: episode library, upload + live processing jobs, re-runs with a custom brand
catalogue / pacing rules, VMAP + debug JSON downloads, and the demo player UI."""
from __future__ import annotations

import json
import queue
import re
import threading
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from .pipeline import media, pacing, run

ROOT = run.ROOT
WORK = run.WORK
WEB = run.WEB
UPLOADS = ROOT / "data" / "uploads"
DEFAULT_BRANDS = ROOT / "data" / "brands.json"
UPLOADS.mkdir(parents=True, exist_ok=True)
WORK.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Birati — contextual ad breaks")

JOBS: dict[str, dict] = {}
TRACK: list[dict] = []
_q: "queue.Queue[tuple[str, callable]]" = queue.Queue()


def default_brands() -> list[dict]:
    return json.loads(DEFAULT_BRANDS.read_text(encoding="utf-8"))


def _worker():
    while True:
        job_id, fn = _q.get()
        job = JOBS[job_id]
        job["status"] = "running"
        job["started"] = time.time()
        try:
            res = fn(lambda m: job["log"].append(f"{time.strftime('%H:%M:%S')}  {m}"))
            job["status"] = "done"
            job["variant"] = res.get("variant")
        except Exception as e:  # surface failures to the UI
            job["status"] = "error"
            job["log"].append(f"ERROR: {e}")
        job["finished"] = time.time()


threading.Thread(target=_worker, daemon=True).start()


def _warm_creatives():
    from .pipeline import ads
    try:
        ads.ensure_all(WEB, default_brands())
    except Exception as e:  # never block startup on this
        print("creative warm-up failed:", e)


threading.Thread(target=_warm_creatives, daemon=True).start()


def _submit(video_id: str, kind: str, fn) -> dict:
    jid = uuid.uuid4().hex[:10]
    JOBS[jid] = {"id": jid, "video_id": video_id, "kind": kind, "status": "queued", "log": [], "created": time.time()}
    _q.put((jid, fn))
    return JOBS[jid]


def _safe_id(s: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9_-]+", "_", s).strip("_").lower()
    return s[:48] or "video"


def _source_for(video_id: str) -> Path:
    for base in (ROOT / "data" / "videos", UPLOADS):
        p = base / f"{video_id}.mp4"
        if p.exists():
            return p
    proxy = WORK / video_id / "proxy.mp4"
    if proxy.exists():
        return proxy
    raise HTTPException(404, "unknown video")


def _result_path(video_id: str, variant: str | None) -> Path:
    wd = WORK / video_id
    if variant:
        p = wd / f"result_{_safe_id(variant)}.json"
        if p.exists():
            return p
        raise HTTPException(404, "unknown variant")
    v = run.variant_id(default_brands(), None)
    for p in (wd / f"result_{v}.json", wd / "result.json"):
        if p.exists():
            return p
    # fall back to most recent variant (e.g. uploads processed with a custom catalogue)
    cands = sorted(wd.glob("result_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if cands:
        return cands[0]
    raise HTTPException(404, "not processed yet")


# ---------------- API ----------------

@app.get("/api/videos")
def list_videos():
    out = []
    for wd in sorted(WORK.iterdir()) if WORK.exists() else []:
        if not wd.is_dir():
            continue
        try:
            rp = _result_path(wd.name, None)
            r = json.loads(rp.read_text(encoding="utf-8"))
            out.append({"id": wd.name, "duration": r["video"]["duration"], "summary": r["summary"],
                        "synopsis": r.get("synopsis", ""), "uploaded": (UPLOADS / f"{wd.name}.mp4").exists()})
        except HTTPException:
            pending = [j for j in JOBS.values() if j["video_id"] == wd.name and j["status"] in ("queued", "running")]
            if pending:
                out.append({"id": wd.name, "processing": True, "job": pending[-1]["id"]})
    return out


@app.get("/api/videos/{video_id}/result")
def get_result(video_id: str, variant: str | None = None):
    return FileResponse(_result_path(_safe_id(video_id), variant), media_type="application/json")


@app.get("/api/videos/{video_id}/debug.json")
def download_debug(video_id: str, variant: str | None = None):
    p = _result_path(_safe_id(video_id), variant)
    return FileResponse(p, media_type="application/json", filename=f"{video_id}_debug.json")


@app.get("/api/videos/{video_id}/vmap.xml")
def get_vmap(video_id: str, request: Request, variant: str | None = None, download: int = 0):
    video_id = _safe_id(video_id)
    r = json.loads(_result_path(video_id, variant).read_text(encoding="utf-8"))
    wd = WORK / video_id
    p = wd / f"vmap_{r.get('variant')}.xml"
    if not p.exists():
        p = wd / "vmap.xml"
    base = str(request.base_url).rstrip("/")
    xml = p.read_text(encoding="utf-8").replace("{BASE}", base)
    headers = {"Content-Disposition": f'attachment; filename="{video_id}_vmap.xml"'} if download else {}
    return Response(xml, media_type="application/xml", headers=headers)


@app.get("/api/videos/{video_id}/catalogue")
def get_catalogue(video_id: str, variant: str | None = None):
    r = json.loads(_result_path(_safe_id(video_id), variant).read_text(encoding="utf-8"))
    p = WORK / _safe_id(video_id) / f"catalogue_{r['catalogue_hash']}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default_brands()


@app.get("/media/{video_id}.mp4")
def get_media(video_id: str):
    p = WORK / _safe_id(video_id) / "proxy.mp4"
    if not p.exists():
        raise HTTPException(404)
    return FileResponse(p, media_type="video/mp4")


@app.get("/api/thumb/{video_id}/{t}")
def get_thumb(video_id: str, t: float):
    video_id = _safe_id(video_id)
    proxy = WORK / video_id / "proxy.mp4"
    if not proxy.exists():
        raise HTTPException(404)
    d = WORK / video_id / "thumbs"
    d.mkdir(exist_ok=True)
    return FileResponse(media.thumbnail(proxy, d / f"{t:.2f}.jpg", t), media_type="image/jpeg",
                        headers={"Cache-Control": "public, max-age=86400"})


@app.get("/api/brands")
def get_brands():
    return default_brands()


@app.get("/api/rules")
def get_rules():
    return pacing.DEFAULT_RULES


def _parse_brands(text: str | None) -> list[dict]:
    if not text:
        return default_brands()
    try:
        b = json.loads(text)
    except json.JSONDecodeError as e:
        raise HTTPException(400, f"brand catalogue is not valid JSON: {e}")
    if not isinstance(b, list) or not all(isinstance(x, dict) and "brand_id" in x for x in b):
        raise HTTPException(400, "brand catalogue must be a JSON array of objects with brand_id")
    for x in b:
        x.setdefault("negative_contexts", [])
        x.setdefault("target_contexts", [])
        x.setdefault("creatives", [{"id": f"{x['brand_id']}_20s", "duration_sec": 20,
                                    "language": "bn", "url": f"ads/{x['brand_id']}/{x['brand_id']}_20s.mp4"}])
        for cr in x["creatives"]:
            if not cr.get("url", "").startswith("http"):
                cr["url"] = "ads/" + _safe_id(x["brand_id"]) + "/" + _safe_id(Path(cr.get("url") or cr["id"]).stem) + ".mp4"
    return b


def _parse_rules(text: str | None) -> dict:
    if not text:
        return {}
    r = json.loads(text)
    return {k: type(pacing.DEFAULT_RULES[k])(v) for k, v in r.items() if k in pacing.DEFAULT_RULES}


@app.post("/api/upload")
async def upload(file: UploadFile = File(...), brands: str | None = Form(None), rules: str | None = Form(None)):
    vid = _safe_id(Path(file.filename or "video").stem)
    if (WORK / vid).exists():
        vid = f"{vid}_{uuid.uuid4().hex[:4]}"
    dst = UPLOADS / f"{vid}.mp4"
    with dst.open("wb") as f:
        while chunk := await file.read(1 << 20):
            f.write(chunk)
    bl, rl = _parse_brands(brands), _parse_rules(rules)
    (WORK / vid).mkdir(parents=True, exist_ok=True)
    return _submit(vid, "full", lambda log: run.process(vid, dst, bl, rl, log=log))


def _download_url(url: str, dst: Path, log) -> None:
    """Fetch a public video URL (Google Drive share links supported) with basic SSRF guarding."""
    import ipaddress
    import socket
    import urllib.parse
    import urllib.request

    u = urllib.parse.urlparse(url.strip())
    if u.scheme not in ("http", "https") or not u.hostname:
        raise ValueError("only http(s) URLs are supported")
    for info in socket.getaddrinfo(u.hostname, None):
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            raise ValueError("URL resolves to a private address")
    m = re.search(r"/d/([\w-]{20,})", url) or re.search(r"[?&]id=([\w-]{20,})", url)
    if "drive.google.com" in (u.hostname or "") and m:
        url = f"https://drive.usercontent.google.com/download?id={m.group(1)}&export=download&confirm=t"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 birati"})
    with urllib.request.urlopen(req, timeout=60) as r, dst.open("wb") as f:
        total, last = 0, 0
        while chunk := r.read(1 << 20):
            f.write(chunk)
            total += len(chunk)
            if total > 3 << 30:
                raise ValueError("file larger than 3 GB")
            if total - last > 25 << 20:
                log(f"downloaded {total >> 20} MB")
                last = total
    ctype = media.probe(dst)
    log(f"downloaded {dst.stat().st_size >> 20} MB · {ctype['duration'] / 60:.1f} min video")


@app.post("/api/ingest_url")
async def ingest_url(url: str = Form(...), brands: str | None = Form(None), rules: str | None = Form(None)):
    stem = Path(url.split("?")[0].rstrip("/")).stem
    vid = _safe_id(stem if stem and stem not in ("view", "download", "edit") else "episode")
    if (WORK / vid).exists():
        vid = f"{vid}_{uuid.uuid4().hex[:4]}"
    dst = UPLOADS / f"{vid}.mp4"
    bl, rl = _parse_brands(brands), _parse_rules(rules)
    (WORK / vid).mkdir(parents=True, exist_ok=True)

    def job(log):
        log("A · fetching video from URL")
        _download_url(url, dst, log)
        return run.process(vid, dst, bl, rl, log=log)

    return _submit(vid, "full", job)


@app.post("/api/videos/{video_id}/rerun")
async def rerun(video_id: str, brands: str | None = Form(None), rules: str | None = Form(None),
                full: int = Form(0)):
    vid = _safe_id(video_id)
    src = _source_for(vid)
    bl, rl = _parse_brands(brands), _parse_rules(rules)
    force = set("ABCE") if full else set()
    return _submit(vid, "full" if full else "rerun", lambda log: run.process(vid, src, bl, rl, log=log, force=force))


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    if job_id not in JOBS:
        raise HTTPException(404)
    j = JOBS[job_id]
    return {**j, "queue_position": _q.qsize() if j["status"] == "queued" else 0}


@app.get("/api/track")
def track(request: Request):
    TRACK.append({**dict(request.query_params), "at": time.time()})
    del TRACK[:-500]
    return Response(status_code=204)


@app.get("/api/track/recent")
def track_recent():
    return TRACK[-50:]


@app.get("/api/health")
def health():
    return {"ok": True}


app.mount("/ads", StaticFiles(directory=WEB / "ads", check_dir=False), name="ads")
app.mount("/", StaticFiles(directory=WEB, html=True), name="web")
