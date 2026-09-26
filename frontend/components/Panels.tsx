"use client";
import { CheckCircle2, ChevronDown, Play, Plus, RotateCcw, ShieldCheck, ShieldX, Sparkles, Wand2, XCircle } from "lucide-react";
import { useState } from "react";
import { U } from "@/lib/api";
import { brandColor, cx, fmt, pct } from "@/lib/format";
import type { Brand, Result, Rules } from "@/lib/types";
import { BrandBadge, Button, Chip, ScoreRing, SectionTitle } from "./ui";

/* ---------------- self-audit ---------------- */
export function AuditCard({ r }: { r: Result }) {
  if (!r.audit) return null;
  const ok = r.audit.every((a) => a.pass);
  return (
    <div className="glass mb-6 rounded-3xl p-5">
      <SectionTitle icon={ok ? <ShieldCheck size={16} /> : <ShieldX size={16} />} aside={<Chip tone={ok ? "ok" : "bad"}>{r.audit.filter((a) => a.pass).length}/{r.audit.length} checks passed</Chip>}>
        Self-audit — hard guarantees re-checked from raw signals
      </SectionTitle>
      <div className="grid gap-2.5 sm:grid-cols-2 xl:grid-cols-4">
        {r.audit.map((a) => (
          <div key={a.check} className="flex gap-2.5 rounded-2xl bg-white/[0.03] p-3 ring-1 ring-inset ring-white/5">
            {a.pass ? <CheckCircle2 size={17} className="mt-0.5 shrink-0 text-mint" /> : <XCircle size={17} className="mt-0.5 shrink-0 text-danger" />}
            <div>
              <div className="text-[13px] font-medium leading-snug">{a.check}</div>
              <div className="mt-0.5 text-[11px] text-mist-500">{a.detail}</div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ---------------- break cards ---------------- */
export function BreaksPanel({ r, id, onWatch }: { r: Result; id: string; onWatch: (i: number) => void }) {
  if (!r.breaks.length) {
    return (
      <>
        <AuditCard r={r} />
        <div className="glass rounded-3xl p-6 text-sm text-mist-300">
          No ad breaks were placed.{" "}
          {r.summary.allowed_breaks === 0
            ? `At ${r.rules.max_breaks_per_hour} breaks/hour a ${fmt(r.video.duration, false)} runtime allows none — loosen the pacing rules to test.`
            : "No boundary met the quality and brand-safety bar under these pacing rules — a deliberate outcome, not a failure."}
        </div>
      </>
    );
  }
  return (
    <>
      <AuditCard r={r} />
      <div className="space-y-5">
        {r.breaks.map((b, i) => {
          const c = r.candidates.find((x) => x.id === b.candidate_id);
          const j = c?.judge || {}, s = c?.signals;
          const ranking = c?.brand_ranking || [];
          const blocked = ranking.filter((x) => x.blocked || x.verifier_blocked);
          const verified = ranking.find((x) => x.brand_id === b.brand_id)?.verifier;
          return (
            <article key={b.candidate_id} className="glass group animate-fade-up overflow-hidden rounded-3xl" style={{ animationDelay: `${i * 80}ms` }}>
              <div className="grid gap-0 md:grid-cols-[280px_1fr]">
                <button onClick={() => onWatch(i)} className="relative block aspect-video overflow-hidden md:aspect-auto md:h-full">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src={U.thumb(id, Math.max(0, b.t - 1))} alt="" className="h-full w-full object-cover transition duration-700 group-hover:scale-105" />
                  <div className="absolute inset-0 bg-gradient-to-t from-ink-950 via-ink-950/20 to-transparent" />
                  <span className="absolute inset-0 m-auto flex size-14 items-center justify-center rounded-full bg-white/15 opacity-0 backdrop-blur-md transition group-hover:opacity-100">
                    <Play size={22} className="ml-1 fill-white text-white" />
                  </span>
                  <span className="absolute bottom-3 left-3 font-mono text-lg font-semibold text-white">{fmt(b.t)}</span>
                </button>
                <div className="p-6">
                  <div className="flex flex-wrap items-center gap-2.5">
                    <BrandBadge id={b.brand_id} name={b.brand_name} className="text-lg" />
                    <Chip>{b.creative.id} · {b.creative.duration_sec}s</Chip>
                    <Chip tone="accent">relevance {pct(b.relevance)}%</Chip>
                    {verified && !verified.violation && <Chip tone="ok"><ShieldCheck size={12} /> verifier passed</Chip>}
                  </div>
                  <p className="mt-2 text-[13px] text-mist-500">
                    Lead-in activity <span className="text-mist-100">{b.dominant_activity}</span>
                    {b.matched_contexts?.length ? <> · matched <span className="text-mist-300">{b.matched_contexts.join(", ")}</span></> : null}
                  </p>

                  <div className="mt-5 flex flex-wrap items-center gap-6">
                    <ScoreRing value={b.quality} label="Break quality" size={66} />
                    <ScoreRing value={j.natural_break_score} label="Natural" />
                    <ScoreRing value={j.story_beat_complete} label="Beat complete" />
                    <ScoreRing value={1 - (j.jarring ?? 1)} label="Not jarring" />
                    <ScoreRing value={j.suspense_hook} label="Suspense hook" />
                  </div>

                  {(b.last_line_before_cut || b.first_line_after_cut) && (
                    <div className="mt-5 grid gap-2.5 sm:grid-cols-2">
                      <Line label="Last line before cut" text={b.last_line_before_cut} />
                      <Line label="First line after" text={b.first_line_after_cut} />
                    </div>
                  )}
                  {s && (
                    <p className="mt-4 text-[12px] text-mist-500">
                      Speech-free {s.silence_before >= 99 ? "∞" : s.silence_before + "s"} before / {s.silence_after >= 99 ? "∞" : s.silence_after + "s"} after ·
                      snapped {s.snap_delta}s onto a camera cut · loudness dip {s.loudness_dip_db} dB{s.fade_to_black ? " · fade to black" : ""}
                    </p>
                  )}
                  <p className="mt-3 text-[13.5px] leading-relaxed text-mist-300">{b.reason}</p>

                  {blocked.length > 0 && (
                    <div className="mt-4 flex flex-wrap items-center gap-1.5">
                      <span className="mr-1 text-[11px] font-semibold uppercase tracking-wider text-danger">Hard-blocked</span>
                      {blocked.map((x) => (
                        <Chip key={x.brand_id} tone="bad">
                          {x.brand_id} · {[...new Set(x.blocks.map((y) => y.negative_context))].join(", ") || x.verifier?.violated_contexts?.join(", ") || "verifier"}
                        </Chip>
                      ))}
                    </div>
                  )}
                  <Ranking ranking={ranking} chosen={b.brand_id} />
                </div>
              </div>
            </article>
          );
        })}
      </div>
    </>
  );
}

function Line({ label, text }: { label: string; text?: string }) {
  return (
    <div className="rounded-2xl bg-white/[0.035] px-4 py-3 ring-1 ring-inset ring-white/5">
      <div className="text-[10px] font-semibold uppercase tracking-wider text-mist-500">{label}</div>
      <div className="mt-1 font-bengali text-[15px] text-mist-100">{text || "— (no speech)"}</div>
    </div>
  );
}

function Ranking({ ranking, chosen }: { ranking: NonNullable<Result["candidates"][number]["brand_ranking"]>; chosen: string }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="mt-4">
      <button onClick={() => setOpen(!open)} className="flex items-center gap-1 text-[12px] font-medium text-mist-500 transition hover:text-mist-100">
        <ChevronDown size={14} className={cx("transition", open && "rotate-180")} /> Full brand ranking for this slot
      </button>
      {open && (
        <div className="mt-3 animate-fade-in space-y-2">
          {ranking.map((x) => {
            const isBlocked = x.blocked || x.verifier_blocked;
            return (
              <div key={x.brand_id} className="rounded-2xl bg-white/[0.03] p-3 ring-1 ring-inset ring-white/5">
                <div className="flex items-center gap-3">
                  <BrandBadge id={x.brand_id} className="w-24 text-[13px]" />
                  <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-white/5">
                    <div className="h-full rounded-full" style={{ width: `${pct(x.relevance)}%`, background: isBlocked ? "#ff5c6c66" : brandColor(x.brand_id) }} />
                  </div>
                  <span className="w-10 text-right font-mono text-[12px] text-mist-300">{pct(x.relevance)}%</span>
                  {isBlocked ? <Chip tone="bad">blocked</Chip> : x.brand_id === chosen ? <Chip tone="ok">chosen</Chip> : <Chip>eligible</Chip>}
                </div>
                <p className="mt-1.5 text-[12px] text-mist-500">{x.rationale}</p>
                {x.blocks.map((y, k) => (
                  <p key={k} className="mt-1 text-[12px] text-danger/90">✕ {y.negative_context} — {y.evidence} <span className="text-mist-500">[{y.source}]</span></p>
                ))}
                {x.verifier?.violation && <p className="mt-1 text-[12px] text-danger/90">✕ verifier: {x.verifier.evidence}</p>}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

/* ---------------- tables ---------------- */
export function CandidatesPanel({ r, onSeek }: { r: Result; onSeek: (t: number) => void }) {
  return (
    <div className="glass overflow-hidden rounded-3xl">
      <p className="px-5 pt-5 text-[13px] text-mist-500">Every scene boundary and fade the system considered — and why it was kept or rejected. Click a row to preview.</p>
      <div className="overflow-x-auto p-2">
        <table className="w-full text-left text-[13px]">
          <thead className="text-[10px] uppercase tracking-wider text-mist-500">
            <tr>{["Time", "Source", "Quality", "Natural", "Speech ±10s", "Decision"].map((h) => <th key={h} className="px-3 py-3 font-medium">{h}</th>)}</tr>
          </thead>
          <tbody>
            {r.candidates.map((c) => {
              const s = c.signals;
              return (
                <tr key={c.id} onClick={() => onSeek(c.t - 6)} className="cursor-pointer border-t border-white/5 transition hover:bg-white/[0.04]">
                  <td className="px-3 py-3 font-mono text-mist-100">{fmt(c.t)}</td>
                  <td className="px-3 py-3 text-mist-500">{(c.sources || []).join(", ").replace(/_/g, " ")}</td>
                  <td className="px-3 py-3">{c.quality != null ? <Bar v={c.quality} /> : "—"}</td>
                  <td className="px-3 py-3 font-mono text-mist-300">{c.judge?.natural_break_score != null ? pct(c.judge.natural_break_score) + "%" : "—"}</td>
                  <td className="px-3 py-3 font-mono text-mist-500">{s ? `${pct(s.speech_density_10s_before)}% / ${pct(s.speech_density_10s_after)}%` : "—"}</td>
                  <td className="px-3 py-3">
                    {c.selected ? <Chip tone="ok">Ad break</Chip> : c.rejections.map((x, i) => (
                      <div key={i} className={cx("text-[12px]", x.startsWith("not chosen") ? "text-amber" : "text-danger/90")}>{x}</div>
                    ))}
                    {c.judge?.reason && <div className="mt-1 max-w-xl text-[11.5px] text-mist-500">{c.judge.reason}</div>}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Bar({ v }: { v: number }) {
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-16 overflow-hidden rounded-full bg-white/5"><div className="bg-accent h-full rounded-full" style={{ width: `${pct(v)}%` }} /></div>
      <span className="font-mono text-[12px] text-mist-300">{pct(v)}%</span>
    </div>
  );
}

export function ScenesPanel({ r, onSeek }: { r: Result; onSeek: (t: number) => void }) {
  return (
    <div className="grid gap-3 md:grid-cols-2">
      {r.scenes.map((s) => {
        const blocks = (s.blocked_contexts || []).length > 0;
        return (
          <button key={s.index} onClick={() => onSeek(s.start)}
            className={cx("glass group rounded-3xl p-5 text-left transition hover:-translate-y-0.5 hover:bg-white/[0.06]", blocks && "ring-1 ring-danger/30")}>
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold uppercase tracking-wider text-coral">Scene {s.index + 1}</span>
              <span className="font-mono text-[12px] text-mist-500">{fmt(s.start)} – {fmt(s.end)}</span>
            </div>
            <p className="mt-2 text-[14px] leading-relaxed text-mist-100">{s.summary}</p>
            <div className="mt-3 flex flex-wrap gap-1.5">
              <Chip>{s.dominant_activity}</Chip>
              <Chip>{s.mood} · {pct(s.emotional_intensity)}%</Chip>
              {(s.sensitive || []).map((z) => <Chip key={z.topic} tone={z.confidence >= 0.3 ? "warn" : "neutral"}>{z.topic} {pct(z.confidence)}%</Chip>)}
            </div>
            {blocks && <p className="mt-3 text-[12px] text-danger/90">Blocks {s.blocks_brands?.join(", ")} — {s.blocked_contexts?.join(", ")}</p>}
          </button>
        );
      })}
    </div>
  );
}

/* ---------------- brands & pacing ---------------- */
export const UNSEEN_BRAND: Brand = {
  brand_id: "brand_i", display_name: "Brand I", category: "beverages/tea",
  target_contexts: ["tea", "drinking tea", "cha", "adda", "conversation over tea", "morning", "breakfast", "relaxing at home", "cafe", "guests at home", "restaurant", "office break"],
  negative_contexts: ["funeral", "hospital", "violence", "grief", "illness"],
  creatives: [
    { id: "i_15s_bn", duration_sec: 15, language: "bn", url: "ads/brand_i/i_15s_bn.mp4" },
    { id: "i_20s_bn", duration_sec: 20, language: "bn", url: "ads/brand_i/i_20s_bn.mp4" },
  ],
};

const RULE_LABELS: Record<string, [string, number, number, number]> = {
  max_breaks_per_hour: ["Max breaks / hour", 1, 12, 1],
  min_gap_sec: ["Min gap between breaks (s)", 60, 900, 30],
  max_ad_load_pct: ["Max ad load (%)", 2, 25, 0.5],
  no_break_first_sec: ["No break in first (s)", 0, 600, 10],
  no_break_last_sec: ["No break in last (s)", 0, 600, 10],
  min_break_score: ["Min break quality", 0.2, 0.9, 0.05],
  brand_relevance_weight: ["Brand relevance weight", 0, 0.5, 0.05],
};

export function ConfigPanel({ catalogue, setCatalogue, rules, setRules, defaults, onRun, busy, isStatic }: {
  catalogue: string; setCatalogue: (s: string) => void; rules: Rules; setRules: (r: Rules) => void;
  defaults: Brand[]; onRun: () => void; busy: boolean; isStatic: boolean;
}) {
  const addUnseen = () => {
    try {
      const b = JSON.parse(catalogue) as Brand[];
      if (!b.find((x) => x.brand_id === UNSEEN_BRAND.brand_id)) b.push(UNSEEN_BRAND);
      setCatalogue(JSON.stringify(b, null, 2));
    } catch { setCatalogue(JSON.stringify([...defaults, UNSEEN_BRAND], null, 2)); }
  };
  return (
    <div className="grid gap-5 lg:grid-cols-[1.35fr_1fr]">
      <div className="glass rounded-3xl p-5">
        <SectionTitle icon={<Sparkles size={16} />} aside={
          <div className="flex gap-2">
            <Button size="sm" onClick={addUnseen}><Plus size={14} /> Add unseen 9th brand</Button>
            <Button size="sm" variant="ghost" onClick={() => setCatalogue(JSON.stringify(defaults, null, 2))}><RotateCcw size={14} /> Reset</Button>
          </div>}>
          Brand catalogue
        </SectionTitle>
        <textarea value={catalogue} onChange={(e) => setCatalogue(e.target.value)} spellCheck={false}
          className="h-[460px] w-full resize-y rounded-2xl bg-ink-950/70 p-4 font-mono text-[12px] leading-relaxed text-mist-300 ring-1 ring-inset ring-white/10 outline-none focus:ring-rose/50" />
      </div>
      <div className="glass flex flex-col rounded-3xl p-5">
        <SectionTitle icon={<Wand2 size={16} />}>Pacing rules</SectionTitle>
        <div className="space-y-4">
          {Object.entries(RULE_LABELS).map(([k, [label, min, max, step]]) => (
            <label key={k} className="block">
              <div className="mb-1.5 flex justify-between text-[13px]"><span className="text-mist-300">{label}</span><span className="font-mono text-mist-100">{rules[k]}</span></div>
              <input type="range" min={min} max={max} step={step} value={rules[k] ?? min}
                onChange={(e) => setRules({ ...rules, [k]: Number(e.target.value) })}
                className="w-full accent-[#ff4d8d]" />
            </label>
          ))}
        </div>
        <div className="mt-auto pt-6">
          <Button variant="primary" className="w-full" onClick={onRun} disabled={busy}>
            {busy ? "Re-running…" : isStatic ? "Show run with this catalogue" : "Re-run brand matching & pacing"}
          </Button>
          <p className="mt-3 text-[12px] leading-relaxed text-mist-500">
            {isStatic
              ? "This mirror holds precomputed runs for the default catalogue and the default + unseen Brand I catalogue."
              : "Scene analysis and cut judgement are cached — only catalogue-dependent stages re-run, so a new brand is evaluated in every slot with zero code changes."}
          </p>
        </div>
      </div>
    </div>
  );
}

export function VmapPanel({ xml }: { xml: string }) {
  return (
    <pre className="glass max-h-[640px] overflow-auto rounded-3xl p-5 font-mono text-[12px] leading-relaxed text-mist-300">{xml}</pre>
  );
}
