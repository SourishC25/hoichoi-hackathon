// Plain-language presentation helpers: the backend logs and scores are technical; the UI is not.
import type { Break, Candidate, Result } from "./types";

/** Map a pipeline log line to what a non-technical user should read. */
export function stageLabel(line: string): string {
  const m = line.replace(/^\d{2}:\d{2}:\d{2}\s+/, "");
  if (/^A · fetch/i.test(m)) return "Fetching the video";
  if (/^A · /.test(m)) return "Watching the video — finding shot changes and speech";
  if (/^B · /.test(m) || /^global analysis/.test(m) || /^uploaded/.test(m)) return "Understanding the story — scenes, mood, sensitive topics";
  if (/^C · |^D · |^local judgement/.test(m)) return "Finding safe moments to pause";
  if (/^creatives ready/.test(m)) return "Preparing the advertisers' creatives";
  if (/^E · |^brand matching/.test(m)) return "Matching advertisers to each moment";
  if (/^F · /.test(m)) return "Independent safety verification";
  if (/^done/.test(m)) return "Done — ad plan ready";
  if (/^ERROR/.test(m)) return m.replace(/^ERROR:\s*/, "Problem: ");
  return m;
}

export function planSummary(r: Result): string {
  const s = r.summary;
  const mins = Math.round(r.video.duration / 60);
  if (!s.breaks) return `No ad break placed in this ${mins}-minute episode — nothing met the safety and quality bar.`;
  return `${s.breaks} ad break${s.breaks > 1 ? "s" : ""} placed in ${mins} minutes — ${s.ad_seconds} s of ads (${s.ad_load_pct} % of viewing time), ${s.allowed_breaks} allowed by the pacing rules.`;
}

/** Display name for a brand id, from the catalogue in use (falls back to the id). */
export const brandName = (id: string, names: Record<string, string>) => names[id] || id;

/** Three plain lines per break: why this moment, why this brand, who was kept out. */
export function explainBreak(b: Break, c: Candidate | undefined, names: Record<string, string>) {
  const j = c?.judge || {};
  const s = c?.signals;
  const why = j.reason?.split(" Brand:")[0]?.trim() || "A clean scene change with nobody speaking across the cut.";
  const silence = s ? `Nobody speaks for ${s.silence_before >= 99 ? "a long time" : s.silence_before + " s"} before and ${s.silence_after >= 99 ? "a long time" : s.silence_after + " s"} after the cut.` : "";
  const brandWhy = `The scene just before is ${b.dominant_activity || "a neutral moment"}${b.matched_contexts?.length ? `, which matches this advertiser's "${b.matched_contexts.slice(0, 3).join('", "')}"` : ""}.`;
  const kept = (c?.brand_ranking || [])
    .filter((x) => x.blocked || x.verifier_blocked)
    .map((x) => {
      const ctx = [...new Set(x.blocks.map((y) => y.negative_context))].concat(x.verifier?.violated_contexts || []);
      return `${brandName(x.brand_id, names)} — ${ctx[0] ? `"${ctx[0]}" appears nearby` : "safety check failed"}`;
    });
  return { why: `${why} ${silence}`.trim(), brandWhy, kept };
}

export const RULE_HELP: Record<string, string> = {
  max_breaks_per_hour: "How many ad breaks an hour of content may have",
  min_gap_sec: "Minimum time between two ad breaks",
  max_ad_load_pct: "Maximum share of viewing time that can be ads",
  no_break_first_sec: "Never interrupt the opening",
  no_break_last_sec: "Never interrupt the ending",
  min_break_score: "How natural a moment must be before an ad is allowed there",
  brand_relevance_weight: "How much a strong advertiser fit can tip the choice of moment",
};
