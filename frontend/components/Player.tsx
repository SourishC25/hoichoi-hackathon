"use client";
import { Sparkles, Volume2 } from "lucide-react";
import { useEffect, useImperativeHandle, useRef, useState, type Ref } from "react";
import { ping } from "@/lib/api";
import { brandColor, pct } from "@/lib/format";
import type { AdBreak } from "@/lib/types";

export interface PlayerHandle {
  jumpBefore: (i: number, lead?: number) => void;
  seek: (t: number, play?: boolean) => void;
}

interface Props {
  src: string;
  breaks: AdBreak[];
  onTime?: (t: number) => void;
  onPlayed?: (played: boolean[]) => void;
  ref?: Ref<PlayerHandle>;
}

export default function Player({ src, breaks, onTime, onPlayed, ref }: Props) {
  const content = useRef<HTMLVideoElement>(null);
  const ad = useRef<HTMLVideoElement>(null);
  const lastT = useRef(0);
  const playing = useRef(false);
  const brk = useRef<AdBreak[]>(breaks);
  const [active, setActive] = useState<AdBreak | null>(null);
  const [left, setLeft] = useState(0);
  const [progress, setProgress] = useState(0);

  useEffect(() => {
    brk.current = breaks.map((b) => ({ ...b, played: false }));
    lastT.current = content.current?.currentTime ?? 0;
  }, [breaks]);

  const report = () => onPlayed?.(brk.current.map((b) => b.played));

  const endAd = (b: AdBreak) => {
    const c = content.current!, a = ad.current!;
    ping(b.tracking.complete);
    ping(b.tracking.breakEnd);
    b.played = true;
    playing.current = false;
    a.pause();
    a.removeAttribute("src");
    a.load();
    setActive(null);
    lastT.current = b.offset;
    c.play().catch(() => {});
    report();
  };

  const startAd = (b: AdBreak) => {
    const c = content.current!, a = ad.current!;
    playing.current = true;
    c.pause();
    c.currentTime = b.offset; // resume from the exact cut frame
    setActive(b);
    a.src = b.media;
    a.currentTime = 0;
    a.muted = c.muted;
    ping(b.tracking.breakStart);
    ping(b.impression);
    a.play().then(() => ping(b.tracking.start)).catch(() => (a.controls = true));
    a.onended = () => endAd(b);
  };

  const check = (t: number) => {
    if (playing.current) return;
    for (const b of brk.current) {
      if (!b.played && lastT.current < b.offset && t >= b.offset - 0.02 && t - b.offset < 1.5) {
        lastT.current = t;
        startAd(b);
        return;
      }
    }
    lastT.current = t;
  };

  useEffect(() => {
    const c = content.current!;
    let alive = true;
    // frame-accurate where frames are composited, plus an always-on poll (rVFC can stall off-screen)
    const onFrame = (_: number, meta: VideoFrameCallbackMetadata) => {
      if (!alive) return;
      check(meta.mediaTime);
      c.requestVideoFrameCallback(onFrame);
    };
    if ("requestVideoFrameCallback" in c) c.requestVideoFrameCallback(onFrame);
    const poll = setInterval(() => !c.paused && !c.seeking && check(c.currentTime), 40);
    const seeking = () => (lastT.current = c.currentTime);
    const tu = () => onTime?.(c.currentTime);
    c.addEventListener("seeking", seeking);
    c.addEventListener("timeupdate", tu);
    return () => {
      alive = false;
      clearInterval(poll);
      c.removeEventListener("seeking", seeking);
      c.removeEventListener("timeupdate", tu);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!active) return;
    const a = ad.current!;
    let raf = 0;
    const tick = () => {
      const d = a.duration || active.duration;
      setLeft(Math.max(0, Math.ceil(d - a.currentTime)));
      setProgress(Math.min(1, a.currentTime / (d || 1)));
      raf = requestAnimationFrame(tick);
    };
    tick();
    return () => cancelAnimationFrame(raf);
  }, [active]);

  useImperativeHandle(ref, () => ({
    jumpBefore(i, lead = 6) {
      const b = brk.current[i];
      if (!b) return;
      b.played = false;
      const c = content.current!;
      c.currentTime = Math.max(0, b.offset - lead);
      lastT.current = c.currentTime;
      c.play().catch(() => {});
      report();
    },
    seek(t, play = false) {
      const c = content.current!;
      c.currentTime = Math.max(0, t);
      lastT.current = c.currentTime;
      if (play) c.play().catch(() => {});
    },
  }));

  const m = active?.meta;
  const R = 17, C = 2 * Math.PI * R;
  return (
    <div className="ring-glow relative aspect-video w-full overflow-hidden rounded-3xl bg-black">
      <video ref={content} src={src} controls playsInline preload="metadata" className="h-full w-full" />
      <div className={`absolute inset-0 bg-black transition-opacity duration-500 ${active ? "opacity-100" : "pointer-events-none opacity-0"}`}>
        <video ref={ad} playsInline className="h-full w-full" onClick={() => ad.current?.paused && ad.current.play()} />
        {active && (
          <>
            <div className="absolute left-4 top-4 flex animate-fade-up items-center gap-2.5 rounded-full bg-black/55 py-1.5 pl-1.5 pr-4 backdrop-blur-md">
              <svg width={40} height={40} className="-rotate-90">
                <circle cx={20} cy={20} r={R} fill="none" stroke="rgb(255 255 255 / 0.15)" strokeWidth={3} />
                <circle cx={20} cy={20} r={R} fill="none" stroke="#fbbf24" strokeWidth={3} strokeLinecap="round" strokeDasharray={C} strokeDashoffset={C * progress} />
                <text x="50%" y="50%" dominantBaseline="central" textAnchor="middle" transform="rotate(90 20 20)" className="fill-white text-[11px] font-bold">{left}</text>
              </svg>
              <div className="leading-tight">
                <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-amber">Sponsored · Ad {active.i + 1} of {brk.current.length}</div>
                <div className="text-sm font-semibold text-white" style={{ textShadow: `0 0 18px ${brandColor(m?.brand_id || "x")}` }}>{m?.brand_name || active.title}</div>
              </div>
            </div>
            <div className="absolute inset-x-4 bottom-4 flex animate-fade-up items-start gap-3 rounded-2xl bg-black/60 p-3.5 text-[13px] text-mist-100 backdrop-blur-md [animation-delay:250ms]">
              <Sparkles size={16} className="mt-0.5 shrink-0 text-coral" />
              <p>
                <b className="text-white">Why {m?.brand_name || "this ad"} here:</b> lead-in scene is <i>{m?.dominant_activity}</i>
                {m?.matched_contexts?.length ? <> — matches <i>{m.matched_contexts.join(", ")}</i></> : null}. Break quality {pct(m?.quality)}%, brand-safety verified.
              </p>
              <Volume2 size={15} className="ml-auto mt-0.5 shrink-0 text-mist-500" />
            </div>
          </>
        )}
      </div>
    </div>
  );
}
