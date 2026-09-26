"use client";
import { AudioLines, Clapperboard, FileVideo, Gauge, Link2, ListChecks, ScanEye, ShieldCheck, UploadCloud } from "lucide-react";
import { useRef, useState } from "react";
import { cx } from "@/lib/format";
import { Button, Modal } from "./ui";

export function UploadDialog({ open, onClose, onSubmit, isStatic }: {
  open: boolean; onClose: () => void; isStatic: boolean;
  onSubmit: (a: { file?: File; url?: string }, progress: (p: number) => void) => Promise<void>;
}) {
  const [file, setFile] = useState<File | undefined>();
  const [url, setUrl] = useState("");
  const [drag, setDrag] = useState(false);
  const [prog, setProg] = useState<number | null>(null);
  const [err, setErr] = useState("");
  const input = useRef<HTMLInputElement>(null);

  const submit = async () => {
    setErr("");
    if (!file && !url.trim()) return setErr("Choose a video file or paste a link.");
    try {
      setProg(0);
      await onSubmit({ file, url: url.trim() || undefined }, setProg);
      setFile(undefined); setUrl(""); setProg(null); onClose();
    } catch (e) {
      setProg(null); setErr(String((e as Error).message || e));
    }
  };

  if (isStatic) {
    return (
      <Modal open={open} onClose={onClose} wide>
        <h3 className="text-xl font-semibold">Process your own episode</h3>
        <p className="mt-2 text-sm text-mist-300">This mirror plays precomputed runs. The live app processes uploads end to end:</p>
        <a href="https://hoichoi-hackathon-production.up.railway.app" className="bg-accent mt-5 inline-flex rounded-full px-5 py-2.5 text-sm font-semibold text-white">Open the live app →</a>
      </Modal>
    );
  }

  return (
    <Modal open={open} onClose={onClose}>
      <h3 className="text-xl font-semibold">Upload an episode</h3>
      <p className="mt-1.5 text-[13px] leading-relaxed text-mist-500">
        Any length of Bengali drama. The full pipeline runs live — camera cuts, speech, scene understanding, cut judgement,
        brand safety, pacing — and you can watch every step.
      </p>
      <button
        onClick={() => input.current?.click()}
        onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
        onDragLeave={() => setDrag(false)}
        onDrop={(e) => { e.preventDefault(); setDrag(false); const f = e.dataTransfer.files[0]; if (f) setFile(f); }}
        className={cx("mt-5 flex w-full flex-col items-center gap-2 rounded-3xl border-2 border-dashed p-8 transition",
          drag ? "border-rose bg-rose/10" : "border-white/15 hover:border-white/30 hover:bg-white/[0.03]")}
      >
        {file ? <FileVideo className="text-coral" size={30} /> : <UploadCloud className="text-mist-500" size={30} />}
        <span className="text-sm font-medium">{file ? file.name : "Drop an MP4 here, or click to browse"}</span>
        {file && <span className="text-xs text-mist-500">{(file.size / 1e6).toFixed(0)} MB</span>}
      </button>
      <input ref={input} type="file" accept="video/mp4,video/*" hidden onChange={(e) => setFile(e.target.files?.[0])} />
      <div className="my-4 flex items-center gap-3 text-[11px] uppercase tracking-wider text-mist-500"><span className="h-px flex-1 bg-white/10" />or paste a public link<span className="h-px flex-1 bg-white/10" /></div>
      <div className="flex items-center gap-2 rounded-2xl bg-ink-950/60 px-4 ring-1 ring-inset ring-white/10 focus-within:ring-rose/50">
        <Link2 size={16} className="text-mist-500" />
        <input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="Google Drive share link or direct .mp4"
          className="h-11 flex-1 bg-transparent font-mono text-[13px] outline-none placeholder:text-mist-500" />
      </div>
      {prog !== null && (
        <div className="mt-5 h-1.5 overflow-hidden rounded-full bg-white/5"><div className="bg-accent h-full transition-all" style={{ width: `${Math.max(4, prog * 100)}%` }} /></div>
      )}
      {err && <p className="mt-3 text-[13px] text-danger">{err}</p>}
      <div className="mt-6 flex justify-end gap-2">
        <Button variant="ghost" onClick={onClose}>Cancel</Button>
        <Button variant="primary" onClick={submit} disabled={prog !== null}>{prog !== null ? "Uploading…" : "Upload & process"}</Button>
      </div>
    </Modal>
  );
}

const STEPS = [
  { icon: Clapperboard, t: "Perception", d: "Frame-exact camera cuts (ffmpeg scdet), speech activity (Silero VAD — language-agnostic), loudness and fades." },
  { icon: ScanEye, t: "Scene understanding", d: "Gemini watches and listens to the whole episode: semantic scenes, dominant activity, mood and every sensitive topic — even ones only talked about." },
  { icon: AudioLines, t: "Where", d: "Boundaries snap to a camera cut inside a speech-free gap — mid-sentence cuts are structurally impossible. Gemini re-watches each cut with an “AD BREAK” card spliced in." },
  { icon: ShieldCheck, t: "What", d: "Every brand is scored for the slot (dominant activity wins). Negative contexts are a hard, fail-closed block from three independent layers incl. an adversarial verifier." },
  { icon: Gauge, t: "Whether", d: "An exact dynamic programme picks the best breaks under max breaks/hour, min gap and the ad-load budget. Weak moments get no break." },
  { icon: ListChecks, t: "Output + audit", d: "IAB VMAP 1.0 with inline VAST 3.0, a debug JSON explaining every decision, and a self-audit that re-checks every guarantee." },
];

export function HowDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  return (
    <Modal open={open} onClose={onClose} wide>
      <h3 className="text-2xl font-semibold">How Birati decides <span className="text-gradient">where, whether & what</span></h3>
      <p className="mt-2 text-sm text-mist-500">The model makes the judgement calls; deterministic signals provide the precision.</p>
      <ol className="relative mt-7 space-y-5 before:absolute before:bottom-3 before:left-[19px] before:top-3 before:w-px before:bg-gradient-to-b before:from-coral before:via-rose before:to-violet">
        {STEPS.map(({ icon: Icon, t, d }, i) => (
          <li key={t} className="relative flex animate-fade-up gap-4" style={{ animationDelay: `${i * 70}ms` }}>
            <span className="glass-strong relative z-10 flex size-10 shrink-0 items-center justify-center rounded-full text-coral"><Icon size={17} /></span>
            <div className="pt-1.5">
              <div className="font-semibold">{t}</div>
              <p className="mt-0.5 text-[13.5px] leading-relaxed text-mist-300">{d}</p>
            </div>
          </li>
        ))}
      </ol>
    </Modal>
  );
}
