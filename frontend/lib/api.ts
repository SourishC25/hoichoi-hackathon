// One UI, two hosts: the FastAPI backend (live processing) or a static export (free mirror).
// The host announces itself through /runtime.json.
import type { AdBreak, Brand, Job, Result, Rules, VideoItem } from "./types";

let STATIC = false;
export const isStatic = () => STATIC;

export async function detectRuntime(): Promise<boolean> {
  try {
    const r = await fetch("runtime.json", { cache: "no-store" });
    if (r.ok) STATIC = !!(await r.json()).static;
  } catch {
    STATIC = false;
  }
  return STATIC;
}

const q = (v?: string | null, extra = "") =>
  v ? `?variant=${encodeURIComponent(v)}${extra ? "&" + extra : ""}` : extra ? "?" + extra : "";

export const U = {
  videos: () => (STATIC ? "api/videos.json" : "/api/videos"),
  result: (id: string, v?: string | null) =>
    STATIC ? `data/${id}/result${v ? "_" + v : ""}.json` : `/api/videos/${id}/result${q(v)}`,
  vmap: (id: string, v?: string | null) =>
    STATIC ? `data/${id}/vmap${v ? "_" + v : ""}.xml` : `/api/videos/${id}/vmap.xml${q(v)}`,
  vmapDownload: (id: string, v?: string | null) =>
    STATIC ? U.vmap(id, v) : `/api/videos/${id}/vmap.xml${q(v, "download=1")}`,
  debug: (id: string, v?: string | null) => (STATIC ? U.result(id, v) : `/api/videos/${id}/debug.json${q(v)}`),
  media: (id: string) => (STATIC ? `media/${id}.mp4` : `/media/${id}.mp4`),
  thumb: (id: string, t: number) =>
    STATIC ? `thumbs/${id}/${t.toFixed(2)}.jpg` : `/api/thumb/${id}/${t.toFixed(2)}`,
  brands: () => (STATIC ? "api/brands.json" : "/api/brands"),
  rules: () => (STATIC ? "api/rules.json" : "/api/rules"),
  catalogue: (id: string, v?: string | null) =>
    STATIC ? `data/${id}/catalogue${v ? "_" + v : ""}.json` : `/api/videos/${id}/catalogue${q(v)}`,
};

async function json<T>(url: string): Promise<T> {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${r.status} ${url}`);
  return r.json() as Promise<T>;
}

export const api = {
  videos: () => json<VideoItem[]>(U.videos()),
  result: (id: string, v?: string | null) => json<Result>(U.result(id, v)),
  brands: () => json<Brand[]>(U.brands()),
  rules: () => json<Rules>(U.rules()),
  catalogue: (id: string, v?: string | null) => json<Brand[]>(U.catalogue(id, v)),
  job: (id: string) => json<Job>(`/api/jobs/${id}`),
  async rerun(id: string, brands: Brand[], rules: Rules): Promise<Job> {
    const fd = new FormData();
    fd.append("brands", JSON.stringify(brands));
    fd.append("rules", JSON.stringify(rules));
    const r = await fetch(`/api/videos/${id}/rerun`, { method: "POST", body: fd });
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  },
  async ingestUrl(url: string, brands?: string): Promise<Job> {
    const fd = new FormData();
    fd.append("url", url);
    if (brands) fd.append("brands", brands);
    const r = await fetch("/api/ingest_url", { method: "POST", body: fd });
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  },
  upload(file: File, brands: string | undefined, onProgress: (p: number) => void): Promise<Job> {
    return new Promise((resolve, reject) => {
      const fd = new FormData();
      fd.append("file", file);
      if (brands) fd.append("brands", brands);
      const xhr = new XMLHttpRequest();
      xhr.upload.onprogress = (e) => e.lengthComputable && onProgress(e.loaded / e.total);
      xhr.onload = () => (xhr.status === 200 ? resolve(JSON.parse(xhr.responseText)) : reject(new Error(xhr.responseText)));
      xhr.onerror = () => reject(new Error("network error"));
      xhr.open("POST", "/api/upload");
      xhr.send(fd);
    });
  },
};

// ---------- VMAP (IAB VMAP 1.0 with inline VAST 3.0) ----------
const VMAP_NS = "http://www.iab.net/videosuite/vmap";
const parseTs = (s: string) => String(s).split(":").reduce((a, p) => a * 60 + parseFloat(p), 0);

export async function loadVmap(url: string): Promise<{ xml: string; breaks: AdBreak[] }> {
  const xml = await (await fetch(url)).text();
  const doc = new DOMParser().parseFromString(xml, "application/xml");
  const breaks = [...doc.getElementsByTagNameNS(VMAP_NS, "AdBreak")].map((b, i) => {
    const ad = b.getElementsByTagName("Ad")[0];
    const tracking: Record<string, string> = {};
    [...b.getElementsByTagName("Tracking"), ...b.getElementsByTagNameNS(VMAP_NS, "Tracking")].forEach(
      (t) => (tracking[t.getAttribute("event") || ""] = (t.textContent || "").trim()),
    );
    return {
      i,
      id: b.getAttribute("breakId") || `break-${i + 1}`,
      offset: parseTs(b.getAttribute("timeOffset") || "0"),
      media: (ad.getElementsByTagName("MediaFile")[0].textContent || "").trim(),
      duration: parseTs(ad.getElementsByTagName("Duration")[0].textContent || "0"),
      title: ad.getElementsByTagName("AdTitle")[0]?.textContent || "",
      impression: ad.getElementsByTagName("Impression")[0]?.textContent?.trim(),
      tracking,
      played: false,
    } as AdBreak;
  });
  return { xml, breaks };
}

export const ping = (url?: string) => {
  if (url) fetch(url, { mode: "no-cors", keepalive: true }).catch(() => {});
};
