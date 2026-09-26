"use client";
import { Download, FileJson, Film, Info, Loader2, Play, Radio, Sparkles, Upload } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, detectRuntime, isStatic as staticMode, loadVmap, U } from "@/lib/api";
import { brandColor, cx, fmt, title } from "@/lib/format";
import { planSummary, stageLabel } from "@/lib/plain";
import type { AdBreak, Brand, Job, Result, Rules, VideoItem } from "@/lib/types";
import { HowDialog, UploadDialog } from "./Dialogs";
import { BreaksPanel, CandidatesPanel, ConfigPanel, ScenesPanel, VmapPanel } from "./Panels";
import Player, { type PlayerHandle } from "./Player";
import Timeline from "./Timeline";
import { Button, Chip } from "./ui";

const TABS = [["breaks", "Ad plan"], ["candidates", "Every moment considered"], ["scenes", "Scenes"], ["config", "Advertisers & rules"], ["vmap", "Schedule file"]] as const;
type Tab = (typeof TABS)[number][0];

export default function App() {
  const [ready, setReady] = useState(false);
  const [failed, setFailed] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [isStatic, setStatic] = useState(false);
  const [videos, setVideos] = useState<VideoItem[]>([]);
  const [id, setId] = useState<string | null>(null);
  const [variant, setVariant] = useState<string | null>(null);
  const [r, setR] = useState<Result | null>(null);
  const [xml, setXml] = useState("");
  const [breaks, setBreaks] = useState<AdBreak[]>([]);
  const [played, setPlayed] = useState<boolean[]>([]);
  const [time, setTime] = useState(0);
  const [tab, setTab] = useState<Tab>("breaks");
  const [defaults, setDefaults] = useState<Brand[]>([]);
  const [example, setExample] = useState<Brand | null>(null);
  const [catalogue, setCatalogue] = useState("");
  const [rules, setRules] = useState<Rules>({});
  const [jobs, setJobs] = useState<Job[]>([]);
  const [busy, setBusy] = useState(false);
  const [upOpen, setUpOpen] = useState(false);
  const [howOpen, setHowOpen] = useState(false);
  const player = useRef<PlayerHandle>(null);
  const stage = useRef<HTMLDivElement>(null);

  const loadLibrary = useCallback(async () => {
    const v = await api.videos();
    setVideos(v);
    return v;
  }, []);

  const open = useCallback(async (vid: string, v: string | null = null) => {
    const res = await api.result(vid, v);
    const { xml, breaks } = await loadVmap(U.vmap(vid, staticMode() ? v : res.variant ?? v));
    setId(vid);
    setVariant(staticMode() ? v : res.variant ?? null);
    setR(res);
    setXml(xml);
    setBreaks(breaks.map((b) => ({ ...b, meta: res.breaks[b.i] })));
    setPlayed(breaks.map(() => false));
    setRules(res.rules);
    try { setCatalogue(JSON.stringify(await api.catalogue(vid, staticMode() ? v : res.variant), null, 2)); } catch { /* keep */ }
    history.replaceState(null, "", `#/${vid}${v ? "/" + v : ""}`);
  }, []);

  useEffect(() => {
    (async () => {
      try {
        setFailed(null);
        setStatic(await detectRuntime());
        const [v, b, ex] = await Promise.all([loadLibrary(), api.brands(), api.exampleBrand()]);
        setDefaults(b);
        setExample(ex);
        setCatalogue(JSON.stringify(b, null, 2));
        const [hid, hvar] = location.hash.replace(/^#\/?/, "").split("/");
        const pick = v.find((x) => x.id === hid && !x.processing) || v.find((x) => !x.processing);
        if (!pick) throw new Error("No processed episodes yet.");
        await open(pick.id, hid === pick.id ? hvar || null : null);
        setReady(true);
      } catch (e) {
        setFailed(String((e as Error).message || e));
      }
    })();
  }, [loadLibrary, open, attempt]);

  useEffect(() => {
    if (id) document.title = `${title(id)} · Birati`;
  }, [id]);

  const watch = (i: number) => {
    player.current?.jumpBefore(i);
    stage.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  };
  const seek = (t: number) => {
    player.current?.seek(t, true);
    stage.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  const track = useCallback((job: Job, onDone: (j: Job) => void) => {
    setJobs((js) => [job, ...js.filter((x) => x.id !== job.id)].slice(0, 3));
    const poll = async () => {
      const j = await api.job(job.id);
      setJobs((js) => js.map((x) => (x.id === j.id ? j : x)));
      if (j.status === "done") return onDone(j);
      if (j.status !== "error") setTimeout(poll, 2000);
    };
    poll();
  }, []);

  const rerun = async () => {
    let brands: Brand[];
    try { brands = JSON.parse(catalogue); } catch (e) { alert("Catalogue JSON is invalid: " + (e as Error).message); return; }
    if (!id) return;
    if (isStatic) {
      const plus9 = !!example && brands.some((b) => b.brand_id === example.brand_id);
      await open(id, plus9 ? "plus9" : null).catch(() => alert("No precomputed run for this catalogue on the mirror — use the live app."));
      return;
    }
    setBusy(true);
    try {
      const job = await api.rerun(id, brands, rules);
      track(job, async (j) => { setBusy(false); await open(id, j.variant); });
    } catch (e) { setBusy(false); alert(String(e)); }
  };

  const submitUpload = async ({ file, url }: { file?: File; url?: string }, progress: (p: number) => void) => {
    const job = file ? await api.upload(file, undefined, progress) : await api.ingestUrl(url!);
    await loadLibrary();
    track(job, async (j) => { await loadLibrary(); await open(j.video_id, j.variant); });
  };

  if (failed) return <Unavailable message={failed} onRetry={() => setAttempt((a) => a + 1)} />;
  if (!ready || !r || !id) return <Splash />;
  const names: Record<string, string> = {};
  try { for (const b of JSON.parse(catalogue) as Brand[]) names[b.brand_id] = b.display_name || b.brand_id; } catch { /* fall back to ids */ }
  const s = r.summary;
  const stats: [string, string][] = [
    [fmt(r.video.duration, false), "Runtime"], [String(s.scenes), "Story scenes"], [String(s.camera_cuts), "Shot changes"],
    [`${s.breaks} of ${s.allowed_breaks}`, "Ad breaks placed"], [`${s.ad_load_pct}%`, `Ad time · max ${r.rules.max_ad_load_pct}%`], [String(s.candidates), "Moments considered"],
  ];

  return (
    <div className="mx-auto max-w-[1600px] px-4 pb-24 sm:px-6">
      {/* header */}
      <header className="sticky top-0 z-40 -mx-4 mb-6 px-4 pt-4 sm:-mx-6 sm:px-6">
        <div className="glass-strong flex items-center justify-between gap-4 rounded-full py-2 pl-2.5 pr-2.5 shadow-2xl">
          <div className="flex items-center gap-3">
            <span className="bg-accent flex size-10 items-center justify-center rounded-full font-bengali text-lg font-bold text-white shadow-[0_0_24px_rgb(255_77_141/0.6)]">বি</span>
            <div className="leading-tight">
              <div className="flex items-baseline gap-2 text-[17px] font-semibold tracking-tight">Birati <span className="font-bengali text-gradient text-base">বিরতি</span></div>
              <div className="hidden text-[11px] text-mist-500 sm:block">AI-native ad-break placement for Bengali drama</div>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {isStatic ? <Chip tone="warn">Static mirror</Chip> : <Chip tone="ok"><Radio size={11} /> Live</Chip>}
            <Button variant="ghost" size="sm" onClick={() => setHowOpen(true)}><Info size={15} /> <span className="hidden sm:inline">How it works</span></Button>
            <Button variant="primary" size="sm" onClick={() => setUpOpen(true)}><Upload size={15} /> <span className="hidden sm:inline">Add an episode</span></Button>
          </div>
        </div>
      </header>

      <div className="grid gap-6 lg:grid-cols-[260px_1fr]">
        {/* episode rail */}
        <aside className="lg:sticky lg:top-24 lg:h-[calc(100vh-7rem)] lg:overflow-y-auto">
          <div className="mb-3 px-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-mist-500">Episodes</div>
          <div className="flex gap-3 overflow-x-auto pb-2 lg:flex-col lg:overflow-visible">
            {videos.map((v) => (
              <EpisodeCard key={v.id} v={v} active={v.id === id} onClick={() => !v.processing && open(v.id)} />
            ))}
          </div>
          {jobs.length > 0 && <Jobs jobs={jobs} />}
        </aside>

        <main className="min-w-0">
          {/* hero */}
          <section className="animate-fade-up">
            <div className="flex flex-wrap items-end justify-between gap-4">
              <div className="max-w-3xl">
                <div className="mb-2 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.2em] text-coral"><Film size={13} /> Ad plan{variant === "plus9" && " · with the sample brand"}</div>
                <h1 className="text-4xl font-semibold tracking-tight sm:text-5xl">{title(id)}</h1>
                {r.synopsis && <p className="mt-3 text-[15px] leading-relaxed text-mist-300">{r.synopsis}</p>}
                <p className="mt-3 inline-flex items-center gap-2 rounded-full bg-mint/10 px-3.5 py-1.5 text-[13px] font-medium text-mint ring-1 ring-inset ring-mint/25">{planSummary(r)}</p>
              </div>
              <div className="flex gap-2">
                <a href={U.vmapDownload(id, variant)} target="_blank" className="glass inline-flex h-9 items-center gap-2 rounded-full px-4 text-xs font-medium transition hover:bg-white/10"><Download size={14} /> Ad schedule <span className="text-mist-500">(for your player)</span></a>
                <a href={U.debug(id, variant)} target="_blank" className="glass inline-flex h-9 items-center gap-2 rounded-full px-4 text-xs font-medium transition hover:bg-white/10"><FileJson size={14} /> Full report</a>
              </div>
            </div>
            <div className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-6">
              {stats.map(([v, l], i) => (
                <div key={l} className="glass animate-fade-up rounded-2xl px-4 py-3.5" style={{ animationDelay: `${80 + i * 50}ms` }}>
                  <div className="text-2xl font-semibold tracking-tight">{v}</div>
                  <div className="mt-0.5 text-[11px] font-medium uppercase tracking-wider text-mist-500">{l}</div>
                </div>
              ))}
            </div>
          </section>

          {/* player + break navigator */}
          <section ref={stage} className="mt-6 grid scroll-mt-28 gap-5 xl:grid-cols-[1fr_300px]">
            <Player ref={player} src={U.media(id)} breaks={breaks} onTime={setTime} onPlayed={setPlayed} />
            <div className="glass rounded-3xl p-4">
              <div className="mb-3 px-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-mist-500">Watch a break (starts 6 s before)</div>
              {breaks.length === 0 && <p className="px-1 text-[13px] text-mist-500">No moment met the safety and quality bar.</p>}
              <div className="space-y-2.5">
                {breaks.map((b) => (
                  <button key={b.id} onClick={() => watch(b.i)}
                    className={cx("group flex w-full items-center gap-3 rounded-2xl p-2 text-left transition hover:bg-white/[0.06]", played[b.i] && "opacity-60")}>
                    <span className="relative h-14 w-24 shrink-0 overflow-hidden rounded-xl">
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img src={U.thumb(id, Math.max(0, b.offset - 1))} alt="" className="h-full w-full object-cover transition duration-500 group-hover:scale-110" />
                      <span className="absolute inset-0 flex items-center justify-center bg-black/30 opacity-0 transition group-hover:opacity-100"><Play size={16} className="fill-white text-white" /></span>
                    </span>
                    <span className="min-w-0">
                      <span className="block font-mono text-[12px] text-mist-500">{fmt(b.offset)}</span>
                      <span className="block truncate text-sm font-semibold" style={{ color: brandColor(b.meta?.brand_id || "x", 78) }}>{b.meta?.brand_name}</span>
                      <span className="block text-[11px] text-mist-500">{b.meta?.creative.id} · {b.duration}s</span>
                    </span>
                  </button>
                ))}
              </div>
            </div>
          </section>

          <section className="mt-6"><Timeline r={r} time={time} onSeek={seek} /></section>

          {/* tabs */}
          <nav className="glass mt-8 inline-flex max-w-full gap-1 overflow-x-auto rounded-full p-1">
            {TABS.map(([k, l]) => (
              <button key={k} onClick={() => setTab(k)}
                className={cx("relative whitespace-nowrap rounded-full px-4 py-2 text-[13px] font-medium transition-all duration-300",
                  tab === k ? "bg-accent text-white shadow-[0_8px_24px_-8px_rgb(255_77_141/0.8)]" : "text-mist-500 hover:text-mist-100")}>
                {l}
              </button>
            ))}
          </nav>
          <section className="mt-5 animate-fade-in" key={tab}>
            {tab === "breaks" && <BreaksPanel r={r} id={id} onWatch={watch} names={names} />}
            {tab === "candidates" && <CandidatesPanel r={r} onSeek={seek} />}
            {tab === "scenes" && <ScenesPanel r={r} onSeek={seek} names={names} />}
            {tab === "config" && <ConfigPanel catalogue={catalogue} setCatalogue={setCatalogue} rules={rules} setRules={setRules} defaults={defaults} example={example} onRun={rerun} busy={busy} isStatic={isStatic} />}
            {tab === "vmap" && <VmapPanel xml={xml} href={U.vmapDownload(id, variant)} />}
          </section>
        </main>
      </div>

      <UploadDialog open={upOpen} onClose={() => setUpOpen(false)} onSubmit={submitUpload} isStatic={isStatic} />
      <HowDialog open={howOpen} onClose={() => setHowOpen(false)} />
    </div>
  );
}

function EpisodeCard({ v, active, onClick }: { v: VideoItem; active: boolean; onClick: () => void }) {
  return (
    <button onClick={onClick}
      className={cx("group relative w-56 shrink-0 overflow-hidden rounded-2xl p-3.5 text-left transition-all duration-300 lg:w-full",
        active ? "glass ring-1 ring-rose/50 shadow-[0_12px_40px_-16px_rgb(255_77_141/0.7)]" : "hover:bg-white/[0.05]")}>
      {active && <span className="bg-accent absolute inset-y-3 left-0 w-1 rounded-r-full" />}
      <div className="flex items-center justify-between gap-2">
        <span className={cx("truncate text-[14px] font-semibold", active ? "text-white" : "text-mist-300 group-hover:text-mist-100")}>{title(v.id)}</span>
        {v.uploaded && <Chip tone="accent">uploaded</Chip>}
      </div>
      <div className="mt-1 flex items-center gap-1.5 text-[11.5px] text-mist-500">
        {v.processing ? <><Loader2 size={12} className="animate-spin text-coral" /> processing…</>
          : <>{fmt(v.duration || 0, false)} · {v.summary?.scenes} scenes · <span className="text-mint">{v.summary?.breaks} breaks</span></>}
      </div>
    </button>
  );
}

function Jobs({ jobs }: { jobs: Job[] }) {
  return (
    <div className="mt-5 space-y-3">
      {jobs.map((j) => (
        <div key={j.id} className="glass animate-fade-up rounded-2xl p-3.5">
          <div className="flex items-center justify-between text-[12px]">
            <span className="flex items-center gap-1.5 font-semibold">
              {j.status === "running" || j.status === "queued" ? <Loader2 size={13} className="animate-spin text-coral" /> : <Sparkles size={13} className={j.status === "done" ? "text-mint" : "text-danger"} />}
              {title(j.video_id)}
            </span>
            <Chip tone={j.status === "done" ? "ok" : j.status === "error" ? "bad" : "warn"}>{j.status}</Chip>
          </div>
          <ol className="mt-2 space-y-1 text-[11.5px]">
            {[...new Set((j.log || []).map(stageLabel))].slice(-6).map((l, i, arr) => (
              <li key={i} className={cx("flex items-start gap-1.5", i === arr.length - 1 && j.status === "running" ? "text-coral" : "text-mist-500")}>
                <span>{i === arr.length - 1 && j.status === "running" ? "›" : "✓"}</span><span>{l}</span>
              </li>
            ))}
            {!(j.log || []).length && <li className="text-mist-500">Waiting in queue…</li>}
          </ol>
        </div>
      ))}
    </div>
  );
}

function Unavailable({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-4 px-6 text-center">
      <span className="bg-accent flex size-14 items-center justify-center rounded-full font-bengali text-2xl font-bold text-white">বি</span>
      <h1 className="text-xl font-semibold">The ad-planning service is waking up</h1>
      <p className="max-w-md text-sm text-mist-500">We couldn&apos;t reach it just now ({message}). This usually clears in a few seconds.</p>
      <Button variant="primary" onClick={onRetry}>Try again</Button>
    </div>
  );
}

function Splash() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-5">
      <span className="bg-accent flex size-16 animate-pulse items-center justify-center rounded-full font-bengali text-3xl font-bold text-white shadow-[0_0_60px_rgb(255_77_141/0.7)]">বি</span>
      <div className="skeleton h-2 w-48 rounded-full" />
    </div>
  );
}
