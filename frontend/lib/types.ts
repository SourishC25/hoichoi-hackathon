// Shapes of the FastAPI responses (see app/pipeline/run.py). Only fields the UI reads are typed.

export interface Summary {
  scenes: number;
  camera_cuts: number;
  candidates: number;
  breaks: number;
  ad_seconds: number;
  ad_load_pct: number;
  breaks_per_hour: number;
  allowed_breaks: number;
}

export interface VideoItem {
  id: string;
  duration?: number;
  summary?: Summary;
  synopsis?: string;
  uploaded?: boolean;
  processing?: boolean;
  job?: string;
}

export interface Sensitive {
  topic: string;
  evidence: string;
  confidence: number;
}

export interface Scene {
  index: number;
  start: number;
  end: number;
  summary: string;
  dominant_activity: string;
  contexts?: string[];
  mood: string;
  emotional_intensity: number;
  sensitive?: Sensitive[];
  blocks_brands?: string[];
  blocked_contexts?: string[];
}

export interface Judge {
  last_line_before_cut?: string;
  first_line_after_cut?: string;
  natural_break_score?: number;
  story_beat_complete?: number;
  jarring?: number;
  suspense_hook?: number;
  visual_novelty?: number;
  reason?: string;
}

export interface Signals {
  snap_delta: number;
  silence_before: number;
  silence_after: number;
  speech_density_10s_before: number;
  speech_density_10s_after: number;
  loudness_dip_db: number;
  fade_to_black: boolean;
}

export interface Block {
  negative_context: string;
  source: string;
  evidence: string;
}

export interface Verifier {
  violation: boolean;
  violated_contexts?: string[];
  evidence?: string;
}

export interface BrandRank {
  brand_id: string;
  relevance: number;
  matched_contexts: string[];
  rationale: string;
  blocked: boolean;
  blocks: Block[];
  verifier?: Verifier;
  verifier_blocked?: boolean;
}

export interface Candidate {
  id: string;
  t: number;
  sources?: string[];
  quality?: number;
  where_score?: number;
  rejections: string[];
  selected?: boolean;
  judge?: Judge | null;
  signals?: Signals;
  brand_ranking?: BrandRank[];
}

export interface Creative {
  id: string;
  duration_sec: number;
  url: string;
}

export interface Break {
  candidate_id: string;
  t: number;
  quality: number;
  brand_id: string;
  brand_name: string;
  relevance: number;
  matched_contexts: string[];
  dominant_activity: string;
  creative: Creative;
  reason: string;
  last_line_before_cut?: string;
  first_line_after_cut?: string;
}

export interface AuditCheck {
  check: string;
  pass: boolean;
  detail: string;
}

export interface Rules {
  [k: string]: number;
}

export interface Result {
  video_id: string;
  engine?: string;
  variant?: string;
  video: { duration: number; width: number; height: number; fps: number };
  rules: Rules;
  summary: Summary;
  audit?: AuditCheck[];
  synopsis?: string;
  breaks: Break[];
  scenes: Scene[];
  candidates: Candidate[];
  speech: { start: number; end: number }[];
  shots: number[];
}

export interface Brand {
  brand_id: string;
  display_name?: string;
  category?: string;
  target_contexts?: string[];
  negative_contexts?: string[];
  creatives?: { id: string; duration_sec: number; language?: string; url: string }[];
}

export interface Job {
  id: string;
  video_id: string;
  kind: string;
  status: "queued" | "running" | "done" | "error";
  log: string[];
  variant?: string;
}

export interface AdBreak {
  i: number;
  id: string;
  offset: number;
  media: string;
  duration: number;
  title: string;
  impression?: string;
  tracking: Record<string, string>;
  played: boolean;
  meta?: Break;
}
