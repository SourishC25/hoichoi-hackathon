"use client";
import { useRef, useState, type ReactNode } from "react";
import { brandColor, cx, fmt, pct } from "@/lib/format";
import type { Candidate, Result, Scene } from "@/lib/types";

type Tip = { x: number; y: number; body: ReactNode } | null;

export default function Timeline({ r, time, onSeek }: { r: Result; time: number; onSeek: (t: number) => void }) {
  const D = r.video.duration;
  const wrap = useRef<HTMLDivElement>(null);
  const [tip, setTip] = useState<Tip>(null);
  const L = (t: number) => `${(t / D) * 100}%`;

  const show = (e: React.MouseEvent, body: ReactNode) => {
    const b = wrap.current!.getBoundingClientRect();
    setTip({ x: Math.min(b.width - 330, Math.max(0, e.clientX - b.left + 14)), y: e.clientY - b.top + 18, body });
  };
  const LABEL = 96; // w-24 lane-label column
  const seek = (e: React.MouseEvent) => {
    const b = e.currentTarget.getBoundingClientRect();
    const x = e.clientX - b.left - LABEL;
    if (x >= 0) onSeek((x / (b.width - LABEL)) * D);
  };

  const legend = [
    ["bg-violet/60", "Scene"],
    ["bg-[repeating-linear-gradient(135deg,#ff5c6c66_0_4px,#ff5c6c22_4px_8px)]", "Blocks a brand"],
    ["bg-sky", "Speech"],
    ["bg-mist-500", "Camera cut"],
    ["bg-mint", "Ad break"],
    ["bg-amber", "Eligible"],
    ["bg-danger", "Rejected"],
  ];

  return (
    <div ref={wrap} className="glass relative rounded-3xl p-5" onMouseLeave={() => setTip(null)}>
      <div className="mb-4 flex flex-wrap items-center gap-x-4 gap-y-1.5 text-[11px] text-mist-500">
        <span className="mr-2 text-xs font-semibold uppercase tracking-[0.16em] text-mist-300">Decision timeline</span>
        {legend.map(([c, l]) => (
          <span key={l} className="flex items-center gap-1.5"><i className={cx("inline-block h-2.5 w-2.5 rounded-sm", c)} />{l}</span>
        ))}
      </div>

      <div className="relative cursor-crosshair select-none" onClick={seek}>
        <Lane label="Scenes" h="h-8">
          {r.scenes.map((s) => (
            <SceneBar key={s.index} s={s} left={L(s.start)} width={`calc(${L(s.end - s.start)} - 2px)`} onHover={(e) => show(e, <SceneTip s={s} />)} />
          ))}
        </Lane>
        <Lane label="Speech" h="h-4">
          {r.speech.map((s, i) => (
            <span key={i} className="absolute inset-y-0 rounded-[2px] bg-sky/70" style={{ left: L(s.start), width: `max(1px, ${L(s.end - s.start)})` }} />
          ))}
        </Lane>
        <Lane label="Cuts" h="h-3">
          {r.shots.map((t, i) => <span key={i} className="absolute inset-y-0 w-px bg-mist-500/50" style={{ left: L(t) }} />)}
        </Lane>
        <Lane label="Candidates" h="h-6">
          {r.candidates.map((c) => <CandDot key={c.id} c={c} left={L(c.t)} onHover={(e) => show(e, <CandTip c={c} />)} />)}
        </Lane>
        <div className="relative ml-24 h-7">
          {r.breaks.map((b) => (
            <span key={b.candidate_id} className="absolute top-0 -translate-x-1/2 whitespace-nowrap rounded-full px-2 py-0.5 text-[10px] font-semibold text-ink-950"
              style={{ left: L(b.t), background: brandColor(b.brand_id), boxShadow: `0 0 16px ${brandColor(b.brand_id)}` }}>
              {b.brand_name}
            </span>
          ))}
        </div>
        {/* break guides + playhead */}
        <div className="pointer-events-none absolute inset-y-0 left-24 right-0">
          {r.breaks.map((b) => (
            <span key={b.candidate_id} className="absolute inset-y-0 w-px bg-gradient-to-b from-mint/0 via-mint/70 to-mint/0" style={{ left: L(b.t) }} />
          ))}
          <span className="absolute inset-y-0 w-0.5 rounded bg-white shadow-[0_0_12px_rgb(255_255_255/0.9)] transition-[left] duration-200" style={{ left: L(time) }} />
        </div>
      </div>

      {tip && (
        <div className="glass-strong pointer-events-none absolute z-20 w-80 animate-fade-in rounded-2xl p-3.5 text-xs leading-relaxed shadow-2xl" style={{ left: tip.x, top: tip.y }}>
          {tip.body}
        </div>
      )}
    </div>
  );
}

function Lane({ label, h, children }: { label: string; h: string; children: ReactNode }) {
  return (
    <div className="mb-2 flex items-center">
      <span className="w-24 shrink-0 text-[10px] font-medium uppercase tracking-wider text-mist-500">{label}</span>
      <div className={cx("relative flex-1 overflow-hidden rounded-md bg-white/[0.03]", h)}>{children}</div>
    </div>
  );
}

function SceneBar({ s, left, width, onHover }: { s: Scene; left: string; width: string; onHover: (e: React.MouseEvent) => void }) {
  const blocks = (s.blocked_contexts || []).length > 0;
  return (
    <span
      onMouseMove={onHover}
      className={cx(
        "absolute inset-y-0.5 rounded-md transition-all duration-200 hover:inset-y-0 hover:brightness-150",
        blocks ? "bg-[repeating-linear-gradient(135deg,#ff5c6c55_0_5px,#ff5c6c1a_5px_10px)] ring-1 ring-inset ring-danger/40"
          : s.index % 2 ? "bg-violet/35" : "bg-violet/55",
      )}
      style={{ left, width }}
    />
  );
}

function CandDot({ c, left, onHover }: { c: Candidate; left: string; onHover: (e: React.MouseEvent) => void }) {
  const lost = !c.selected && c.rejections.length > 0 && c.rejections[0].startsWith("not chosen");
  const tone = c.selected ? "bg-mint animate-pulse-ring" : lost ? "bg-amber" : "bg-danger/80";
  return (
    <span onMouseMove={onHover}
      className={cx("absolute top-1/2 -translate-x-1/2 -translate-y-1/2 rounded-full ring-2 ring-ink-900 transition-transform hover:scale-150", tone, c.selected ? "size-3.5" : "size-2.5")}
      style={{ left }} />
  );
}

function SceneTip({ s }: { s: Scene }) {
  return (
    <>
      <div className="mb-1 flex items-center justify-between"><b className="text-coral">Scene {s.index + 1}</b><span className="font-mono text-mist-500">{fmt(s.start)}–{fmt(s.end)}</span></div>
      <p className="text-mist-100">{s.summary}</p>
      <p className="mt-1.5 text-mist-500">Activity: <span className="text-mist-300">{s.dominant_activity}</span> · Mood: <span className="text-mist-300">{s.mood}</span></p>
      {(s.blocked_contexts || []).length > 0 && (
        <p className="mt-1.5 text-danger">Blocks {s.blocks_brands?.join(", ")} — {s.blocked_contexts?.join(", ")}</p>
      )}
    </>
  );
}

function CandTip({ c }: { c: Candidate }) {
  return (
    <>
      <div className="mb-1 flex items-center justify-between">
        <b className={c.selected ? "text-mint" : "text-mist-100"}>{c.selected ? "Ad break" : "Candidate"}</b>
        <span className="font-mono text-mist-500">{fmt(c.t)} · q {pct(c.quality)}%</span>
      </div>
      {c.judge?.reason && <p className="text-mist-300">{c.judge.reason}</p>}
      {c.rejections.map((x, i) => (
        <p key={i} className={cx("mt-1", x.startsWith("not chosen") ? "text-amber" : "text-danger")}>✕ {x}</p>
      ))}
    </>
  );
}
