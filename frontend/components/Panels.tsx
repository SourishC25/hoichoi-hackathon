"use client";
import { CheckCircle2, ChevronDown, Download, Play, Plus, RotateCcw, ShieldCheck, ShieldX, Sparkles, Wand2, XCircle } from "lucide-react";
import { useState } from "react";
import { U } from "@/lib/api";
import { brandColor, cx, fmt, pct } from "@/lib/format";
import { brandName, explainBreak, RULE_HELP } from "@/lib/plain";
import type { Brand, BrandRank, Result, Rules } from "@/lib/types";
import { BrandBadge, Button, Chip, ScoreRing, SectionTitle } from "./ui";

const PLAIN_CHECK: Record<string, string> = {
  "No speech at any cut point (VAD)": "Nobody is speaking at any cut",
  "Every cut on a camera cut or black frame": "Every cut sits on a shot change",
  "Min gap between breaks": "Breaks are far enough apart",
  "Max breaks per hour": "Not too many breaks per hour",
  "Ad load within budget": "Ad time within the allowed share",
  "Protected opening/closing windows": "Opening and ending left untouched",
  "No negative-context brand placed (3 layers re-checked)": "No advertiser next to a topic it forbids",
  "Every placed brand passed the independent verifier": "Every ad passed the independent safety check",
};

/* ---------------- safety checks ---------------- */
export function AuditCard({ r }: { r: Result }) {
  if (!r.audit) return null;
  const ok = r.audit.every((a) => a.pass);
  return (
    <div className="glass mb-6 rounded-3xl p-5">
      <SectionTitle icon={ok ? <ShieldCheck size={16} /> : <ShieldX size={16} />} aside={<Chip tone={ok ? "ok" : "bad"}>{r.audit.filter((a) => a.pass).length} of {r.audit.length} passed</Chip>}>
        Safety checks — re-verified from the video itself after deciding
      </SectionTitle>
      <div className="grid gap-2.5 sm:grid-cols-2 xl:grid-cols-4">
        {r.audit.map((a) => (
          <div key={a.check} className="flex gap-2.5 rounded-2xl bg-white/[0.03] p-3 ring-1 ring-inset ring-white/5">
            {a.pass ? <CheckCircle2 size={17} className="mt-0.5 shrink-0 text-mint" /> : <XCircle size={17} className="mt-0.5 shrink-0 text-danger" />}
            <div>
              <div className="text-[13px] font-medium leading-snug">{PLAIN_CHECK[a.check] || a.check}</div>
              <div className="mt-0.5 text-[11px] text-mist-500">{a.detail}</div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ---------------- the ad plan ---------------- */
export function BreaksPanel({ r, id, onWatch, names }: { r: Result; id: string; onWatch: (i: number) => void; names: Record<string, string> }) {
  if (!r.breaks.length) {
    return (
      <>
        <AuditCard r={r} />
        <div className="glass rounded-3xl p-6 text-sm text-mist-300">
          No ad break was placed.{" "}
          {r.summary.allowed_breaks === 0
            ? `At ${r.rules.max_breaks_per_hour} breaks per hour, a ${fmt(r.video.duration, false)} episode allows none — relax the rules under Advertisers & rules to test.`
            : "No moment met both the quality bar and the safety rules. Choosing nothing over a risky placement is deliberate."}
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
          const ex = explainBreak(b, c, names);
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
                  <span className="absolute bottom-3 right-3 rounded-full bg-black/50 px-2.5 py-1 text-[11px] font-medium text-white backdrop-blur">▶ Watch this break</span>
                </button>
                <div className="p-6">
                  <div className="flex flex-wrap items-center gap-2.5">
                    <span className="text-[11px] font-semibold uppercase tracking-[0.18em] text-mist-500">Ad break {i + 1} · {fmt(b.t, false)}</span>
                    <Chip tone="accent">fit {pct(b.relevance)}%</Chip>
                    <Chip tone="ok"><ShieldCheck size={12} /> safety verified</Chip>
                  </div>
                  <h3 className="mt-2 flex items-center gap-2 text-xl font-semibold"><BrandBadge id={b.brand_id} name={b.brand_name} /> <span className="text-sm font-normal text-mist-500">· {b.creative.duration_sec}-second ad</span></h3>

                  <dl className="mt-4 space-y-3 text-[13.5px] leading-relaxed">
                    <Row k="Why this moment">{ex.why}</Row>
                    <Row k="Why this advertiser">{ex.brandWhy}</Row>
                    <Row k="Kept out here">
                      {ex.kept.length ? (
                        <span className="flex flex-wrap gap-1.5">{ex.kept.map((t) => <Chip key={t} tone="bad">{t}</Chip>)}</span>
                      ) : <span className="text-mist-500">No advertiser was blocked at this moment.</span>}
                    </Row>
                  </dl>

                  {(b.last_line_before_cut || b.first_line_after_cut) && (
                    <div className="mt-4 grid gap-2.5 sm:grid-cols-2">
                      <Line label="Last words before the cut" text={b.last_line_before_cut} />
                      <Line label="First words after the ad" text={b.first_line_after_cut} />
                    </div>
                  )}

                  <Details c={c} b={b} />
                </div>
              </div>
            </article>
          );
        })}
      </div>
    </>
  );
}

function Row({ k, children }: { k: string; children: React.ReactNode }) {
  return (
    <div className="grid gap-1 sm:grid-cols-[150px_1fr]">
      <dt className="text-[11px] font-semibold uppercase tracking-wider text-mist-500 sm:pt-0.5">{k}</dt>
      <dd className="text-mist-100">{children}</dd>
    </div>
  );
}

function Line({ label, text }: { label: string; text?: string }) {
  return (
    <div className="rounded-2xl bg-white/[0.035] px-4 py-3 ring-1 ring-inset ring-white/5">
      <div className="text-[10px] font-semibold uppercase tracking-wider text-mist-500">{label}</div>
      <div className="mt-1 font-bengali text-[15px] text-mist-100">{text || "— (nobody speaking)"}</div>
    </div>
  );
}

function Details({ c, b }: { c?: Result["candidates"][number]; b: Result["breaks"][number] }) {
  const [open, setOpen] = useState(false);
  const j = c?.judge || {}, s = c?.signals;
  return (
    <div className="mt-4">
      <button onClick={() => setOpen(!open)} className="flex items-center gap-1 text-[12px] font-medium text-mist-500 transition hover:text-mist-100">
        <ChevronDown size={14} className={cx("transition", open && "rotate-180")} /> {open ? "Hide" : "Show"} the numbers behind this decision
      </button>
      {open && (
        <div className="mt-4 animate-fade-in">
          <div className="flex flex-wrap items-center gap-6">
            <ScoreRing value={b.quality} label="Break quality" size={66} />
            <ScoreRing value={j.natural_break_score} label="Natural pause" />
            <ScoreRing value={j.story_beat_complete} label="Moment finished" />
            <ScoreRing value={1 - (j.jarring ?? 1)} label="Not jarring" />
            <ScoreRing value={j.suspense_hook} label="Come-back hook" />
          </div>
          {s && (
            <p className="mt-4 text-[12px] text-mist-500">
              Silence {s.silence_before >= 99 ? "∞" : s.silence_before + " s"} before / {s.silence_after >= 99 ? "∞" : s.silence_after + " s"} after · cut moved {s.snap_delta} s onto the nearest shot change · audio dips {s.loudness_dip_db} dB{s.fade_to_black ? " · fade to black" : ""}
            </p>
          )}
          {c?.brand_ranking && <Ranking ranking={c.brand_ranking} chosen={b.brand_id} />}
        </div>
      )}
    </div>
  );
}

function Ranking({ ranking, chosen }: { ranking: BrandRank[]; chosen: string }) {
  return (
    <div className="mt-4 space-y-2">
      <div className="text-[11px] font-semibold uppercase tracking-wider text-mist-500">How every advertiser scored for this moment</div>
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
              <p key={k} className="mt-1 text-[12px] text-danger/90">✕ {y.negative_context} — {y.evidence} <span className="text-mist-500">[{y.source.replace(/_/g, " ")}]</span></p>
            ))}
            {x.verifier?.violation && <p className="mt-1 text-[12px] text-danger/90">✕ safety check: {x.verifier.evidence}</p>}
          </div>
        );
      })}
    </div>
  );
}

/* ---------------- every moment considered ---------------- */
export function CandidatesPanel({ r, onSeek }: { r: Result; onSeek: (t: number) => void }) {
  return (
    <div className="glass overflow-hidden rounded-3xl">
      <p className="px-5 pt-5 text-[13px] text-mist-500">Every scene change and fade the system considered, and what happened to it. Click a row to watch that moment.</p>
      <div className="overflow-x-auto p-2">
        <table className="w-full text-left text-[13px]">
          <thead className="text-[10px] uppercase tracking-wider text-mist-500">
            <tr>{["Time", "Kind", "Quality", "Natural pause", "Talking around it", "Outcome"].map((h) => <th key={h} className="px-3 py-3 font-medium">{h}</th>)}</tr>
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
                      <div key={i} className={cx("text-[12px]", x.startsWith("not chosen") ? "text-amber" : "text-danger/90")}>{plainRejection(x)}</div>
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

function plainRejection(x: string): string {
  if (x.startsWith("not chosen")) return "Good moment, but a better one nearby won under the pacing rules";
  if (x.includes("overlaps speech")) return "Someone is speaking here — no clean cut nearby";
  if (x.includes("protected")) return "Inside the protected opening or ending";
  if (x.startsWith("every brand is blocked")) return "Every advertiser is kept out by a nearby topic";
  if (x.includes("below threshold")) return "Not a natural enough pause";
  if (x.includes("conversation")) return "The conversation continues across this cut";
  if (x.includes("sentence")) return "Would cut a sentence in half";
  if (x.includes("verifier")) return "Failed the independent safety check";
  return x;
}

function Bar({ v }: { v: number }) {
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-16 overflow-hidden rounded-full bg-white/5"><div className="bg-accent h-full rounded-full" style={{ width: `${pct(v)}%` }} /></div>
      <span className="font-mono text-[12px] text-mist-300">{pct(v)}%</span>
    </div>
  );
}

export function ScenesPanel({ r, onSeek, names }: { r: Result; onSeek: (t: number) => void; names: Record<string, string> }) {
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
              <Chip>{s.mood}</Chip>
              {(s.sensitive || []).filter((z) => z.confidence >= 0.3).map((z) => <Chip key={z.topic} tone="warn">{z.topic}</Chip>)}
            </div>
            {blocks && <p className="mt-3 text-[12px] text-danger/90">Keeps out {s.blocks_brands?.map((b) => brandName(b, names)).join(", ")} — {s.blocked_contexts?.join(", ")}</p>}
          </button>
        );
      })}
    </div>
  );
}

/* ---------------- advertisers & rules ---------------- */
const RULE_LABELS: Record<string, [string, number, number, number]> = {
  max_breaks_per_hour: ["Ad breaks per hour (max)", 1, 12, 1],
  min_gap_sec: ["Minimum gap between breaks (seconds)", 60, 900, 30],
  max_ad_load_pct: ["Ad time as % of viewing (max)", 2, 25, 0.5],
  no_break_first_sec: ["Protect the opening (seconds)", 0, 600, 10],
  no_break_last_sec: ["Protect the ending (seconds)", 0, 600, 10],
  min_break_score: ["Minimum naturalness of a pause", 0.2, 0.9, 0.05],
  brand_relevance_weight: ["Weight of advertiser fit", 0, 0.5, 0.05],
};

const slug = (s: string) => s.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "") || "brand";
const list = (s: string) => s.split(/[,;\n]/).map((x) => x.trim()).filter(Boolean);

export function ConfigPanel({ catalogue, setCatalogue, rules, setRules, defaults, example, onRun, busy, isStatic }: {
  catalogue: string; setCatalogue: (s: string) => void; rules: Rules; setRules: (r: Rules) => void;
  defaults: Brand[]; example: Brand | null; onRun: () => void; busy: boolean; isStatic: boolean;
}) {
  const [adv, setAdv] = useState(false);
  const [form, setForm] = useState({ name: "", category: "", targets: "", negatives: "", seconds: 20 });
  let brands: Brand[] = [];
  try { brands = JSON.parse(catalogue); } catch { /* shown in advanced */ }

  const write = (b: Brand[]) => setCatalogue(JSON.stringify(b, null, 2));
  const addExample = () => example && write(brands.find((x) => x.brand_id === example.brand_id) ? brands : [...brands, example]);
  const addBrand = () => {
    if (!form.name.trim()) return alert("Give the advertiser a name.");
    const id = slug(form.name);
    if (brands.some((b) => b.brand_id === id)) return alert("An advertiser with that name already exists.");
    write([...brands, {
      brand_id: id, display_name: form.name.trim(), category: form.category.trim(),
      target_contexts: list(form.targets), negative_contexts: list(form.negatives),
      creatives: [{ id: `${id}_${form.seconds}s`, duration_sec: Number(form.seconds), language: "bn", url: `ads/${id}/${id}_${form.seconds}s.mp4` }],
    }]);
    setForm({ name: "", category: "", targets: "", negatives: "", seconds: 20 });
  };
  const remove = (id: string) => write(brands.filter((b) => b.brand_id !== id));

  return (
    <div className="grid gap-5 lg:grid-cols-[1.35fr_1fr]">
      <div className="space-y-5">
        <div className="glass rounded-3xl p-5">
          <SectionTitle icon={<Sparkles size={16} />} aside={example && <Button size="sm" onClick={addExample}><Plus size={14} /> Add a sample brand ({example.category || example.display_name})</Button>}>
            Advertisers in this run
          </SectionTitle>
          <div className="grid gap-2 sm:grid-cols-2">
            {brands.map((b) => (
              <div key={b.brand_id} className="rounded-2xl bg-white/[0.03] p-3.5 ring-1 ring-inset ring-white/5">
                <div className="flex items-center justify-between gap-2">
                  <BrandBadge id={b.brand_id} name={b.display_name || b.brand_id} className="text-[14px]" />
                  <button onClick={() => remove(b.brand_id)} className="text-[11px] text-mist-500 hover:text-danger">remove</button>
                </div>
                <div className="mt-0.5 text-[11px] text-mist-500">{b.category}</div>
                <p className="mt-2 text-[12px] text-mist-300"><span className="text-mint">Wants:</span> {(b.target_contexts || []).slice(0, 5).join(", ")}{(b.target_contexts || []).length > 5 ? "…" : ""}</p>
                <p className="mt-1 text-[12px] text-mist-300"><span className="text-danger">Never near:</span> {(b.negative_contexts || []).join(", ")}</p>
              </div>
            ))}
          </div>
        </div>

        <div className="glass rounded-3xl p-5">
          <SectionTitle icon={<Plus size={16} />}>Add an advertiser</SectionTitle>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Brand name" value={form.name} onChange={(v) => setForm({ ...form, name: v })} placeholder="e.g. Brand J" />
            <Field label="Category" value={form.category} onChange={(v) => setForm({ ...form, category: v })} placeholder="e.g. snacks / biscuits" />
            <Field label="Wants to appear near (comma-separated)" value={form.targets} onChange={(v) => setForm({ ...form, targets: v })} placeholder="tea, snacks, evening at home, guests" full />
            <Field label="Must never appear near (comma-separated)" value={form.negatives} onChange={(v) => setForm({ ...form, negatives: v })} placeholder="funeral, hospital, violence, grief" full />
            <label className="block text-[12px] text-mist-500">Ad length
              <select value={form.seconds} onChange={(e) => setForm({ ...form, seconds: Number(e.target.value) })} className="mt-1 block h-10 w-full rounded-xl bg-ink-950/70 px-3 text-sm text-mist-100 ring-1 ring-inset ring-white/10">
                {[15, 20, 30].map((s) => <option key={s} value={s}>{s} seconds</option>)}
              </select>
            </label>
          </div>
          <div className="mt-4 flex items-center justify-between gap-3">
            <p className="text-[11.5px] text-mist-500">A placeholder ad is generated automatically (no real creatives were supplied).</p>
            <Button onClick={addBrand}><Plus size={14} /> Add</Button>
          </div>
        </div>

        <div className="glass rounded-3xl p-5">
          <button onClick={() => setAdv(!adv)} className="flex items-center gap-1 text-[12px] font-medium text-mist-500 hover:text-mist-100">
            <ChevronDown size={14} className={cx("transition", adv && "rotate-180")} /> Advanced: edit the raw catalogue (JSON)
          </button>
          {adv && (
            <>
              <textarea value={catalogue} onChange={(e) => setCatalogue(e.target.value)} spellCheck={false}
                className="mt-3 h-[360px] w-full resize-y rounded-2xl bg-ink-950/70 p-4 font-mono text-[12px] leading-relaxed text-mist-300 ring-1 ring-inset ring-white/10 outline-none focus:ring-rose/50" />
              <Button size="sm" variant="ghost" className="mt-2" onClick={() => setCatalogue(JSON.stringify(defaults, null, 2))}><RotateCcw size={14} /> Reset to default catalogue</Button>
            </>
          )}
        </div>
      </div>

      <div className="glass flex flex-col rounded-3xl p-5">
        <SectionTitle icon={<Wand2 size={16} />}>Pacing rules</SectionTitle>
        <div className="space-y-4">
          {Object.entries(RULE_LABELS).map(([k, [label, min, max, step]]) => (
            <label key={k} className="block">
              <div className="mb-1 flex justify-between text-[13px]"><span className="text-mist-100">{label}</span><span className="font-mono text-mist-300">{rules[k]}</span></div>
              <div className="mb-1.5 text-[11px] text-mist-500">{RULE_HELP[k]}</div>
              <input type="range" min={min} max={max} step={step} value={rules[k] ?? min}
                onChange={(e) => setRules({ ...rules, [k]: Number(e.target.value) })} className="w-full accent-[#ff4d8d]" />
            </label>
          ))}
        </div>
        <div className="mt-auto pt-6">
          <Button variant="primary" className="w-full" onClick={onRun} disabled={busy}>
            {busy ? "Updating the ad plan…" : isStatic ? "Show the plan for this catalogue" : "Update the ad plan"}
          </Button>
          <p className="mt-3 text-[12px] leading-relaxed text-mist-500">
            {isStatic
              ? "This mirror holds precomputed plans for the default catalogue and for the default catalogue plus the sample brand."
              : "The episode is already understood — only advertiser matching and pacing re-run, so this takes about a minute."}
          </p>
        </div>
      </div>
    </div>
  );
}

function Field({ label, value, onChange, placeholder, full }: { label: string; value: string; onChange: (v: string) => void; placeholder?: string; full?: boolean }) {
  return (
    <label className={cx("block text-[12px] text-mist-500", full && "sm:col-span-2")}>{label}
      <input value={value} onChange={(e) => onChange(e.target.value)} placeholder={placeholder}
        className="mt-1 block h-10 w-full rounded-xl bg-ink-950/70 px-3 text-sm text-mist-100 ring-1 ring-inset ring-white/10 outline-none placeholder:text-mist-500/70 focus:ring-rose/50" />
    </label>
  );
}

/* ---------------- the schedule file ---------------- */
export function VmapPanel({ xml, href }: { xml: string; href: string }) {
  return (
    <div className="glass rounded-3xl p-5">
      <SectionTitle icon={<Download size={16} />} aside={<a href={href} target="_blank" className="bg-accent inline-flex h-8 items-center gap-1.5 rounded-full px-3.5 text-xs font-semibold text-white"><Download size={13} /> Download</a>}>
        The ad schedule file (VMAP)
      </SectionTitle>
      <p className="mb-4 text-[13px] leading-relaxed text-mist-300">
        This is the hand-off to a real video player or ad server. It is the industry-standard format (IAB VMAP 1.0 with VAST 3.0 inside):
        for each break it says <b>when</b> to pause (<code>timeOffset</code>), <b>which ad file</b> to play (<code>MediaFile</code>) and
        <b> which events to report</b> back (<code>Tracking</code>: impression, start, complete). The player on this page reads exactly this file.
      </p>
      <pre className="max-h-[560px] overflow-auto rounded-2xl bg-ink-950/60 p-4 font-mono text-[12px] leading-relaxed text-mist-300">{xml}</pre>
    </div>
  );
}
