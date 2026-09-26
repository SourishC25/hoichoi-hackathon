"use client";
import { X } from "lucide-react";
import { useEffect, type ButtonHTMLAttributes, type ReactNode } from "react";
import { brandColor, cx, pct } from "@/lib/format";

type BtnProps = ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "ghost" | "soft"; size?: "sm" | "md" };

export function Button({ variant = "soft", size = "md", className, children, ...rest }: BtnProps) {
  return (
    <button
      {...rest}
      className={cx(
        "inline-flex items-center justify-center gap-2 rounded-full font-medium transition-all duration-300 disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-rose",
        size === "sm" ? "h-8 px-3.5 text-xs" : "h-10 px-5 text-sm",
        variant === "primary" && "bg-accent text-white shadow-[0_10px_30px_-10px_rgb(255_77_141/0.8)] hover:shadow-[0_14px_40px_-10px_rgb(255_77_141/0.95)] hover:brightness-110 active:scale-[0.98]",
        variant === "soft" && "glass text-mist-100 hover:bg-white/10",
        variant === "ghost" && "text-mist-300 hover:bg-white/5 hover:text-mist-100",
        className,
      )}
    >
      {children}
    </button>
  );
}

export function Chip({ children, tone = "neutral", className }: { children: ReactNode; tone?: "neutral" | "ok" | "bad" | "warn" | "accent"; className?: string }) {
  return (
    <span
      className={cx(
        "inline-flex items-center gap-1 whitespace-nowrap rounded-full px-2.5 py-0.5 text-[11px] font-medium ring-1 ring-inset",
        tone === "neutral" && "bg-white/5 text-mist-300 ring-white/10",
        tone === "ok" && "bg-mint/10 text-mint ring-mint/25",
        tone === "bad" && "bg-danger/10 text-danger ring-danger/25",
        tone === "warn" && "bg-amber/10 text-amber ring-amber/25",
        tone === "accent" && "bg-rose/10 text-coral ring-rose/30",
        className,
      )}
    >
      {children}
    </span>
  );
}

export function BrandBadge({ id, name, className }: { id: string; name?: string; className?: string }) {
  return (
    <span className={cx("inline-flex items-center gap-1.5 font-semibold", className)}>
      <span className="size-2.5 rounded-full" style={{ background: brandColor(id), boxShadow: `0 0 12px ${brandColor(id)}` }} />
      {name || id}
    </span>
  );
}

export function ScoreRing({ value, label, size = 58, color = "url(#ring-grad)" }: { value?: number; label: string; size?: number; color?: string }) {
  const v = Math.max(0, Math.min(1, value ?? 0));
  const r = size / 2 - 5;
  const c = 2 * Math.PI * r;
  return (
    <div className="flex flex-col items-center gap-1.5">
      <svg width={size} height={size} className="-rotate-90">
        <defs>
          <linearGradient id="ring-grad" x1="0" x2="1">
            <stop offset="0%" stopColor="#ff7a8a" />
            <stop offset="100%" stopColor="#8b5cf6" />
          </linearGradient>
        </defs>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="rgb(255 255 255 / 0.08)" strokeWidth={5} />
        <circle
          cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth={5} strokeLinecap="round"
          strokeDasharray={c} strokeDashoffset={c * (1 - v)} style={{ transition: "stroke-dashoffset 1s cubic-bezier(.22,1,.36,1)" }}
        />
        <text x="50%" y="50%" dominantBaseline="central" textAnchor="middle" transform={`rotate(90 ${size / 2} ${size / 2})`}
          className="fill-mist-100 text-[13px] font-semibold">{pct(v)}</text>
      </svg>
      <span className="text-center text-[10px] font-medium uppercase tracking-wider text-mist-500">{label}</span>
    </div>
  );
}

export function Modal({ open, onClose, children, wide }: { open: boolean; onClose: () => void; children: ReactNode; wide?: boolean }) {
  useEffect(() => {
    if (!open) return;
    const k = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" role="dialog" aria-modal>
      <div className="absolute inset-0 animate-fade-in bg-ink-950/70 backdrop-blur-sm" onClick={onClose} />
      <div className={cx("glass-strong relative max-h-[88vh] w-full animate-fade-up overflow-y-auto rounded-3xl p-7 shadow-2xl", wide ? "max-w-3xl" : "max-w-lg")}>
        <button onClick={onClose} className="absolute right-5 top-5 rounded-full p-1.5 text-mist-500 transition hover:bg-white/10 hover:text-mist-100" aria-label="Close">
          <X size={18} />
        </button>
        {children}
      </div>
    </div>
  );
}

export function SectionTitle({ icon, children, aside }: { icon?: ReactNode; children: ReactNode; aside?: ReactNode }) {
  return (
    <div className="mb-4 flex items-center justify-between gap-3">
      <h3 className="flex items-center gap-2 text-sm font-semibold tracking-wide text-mist-100">
        {icon && <span className="text-coral">{icon}</span>}
        {children}
      </h3>
      {aside}
    </div>
  );
}
