export const fmt = (t: number, decimals = true) => {
  t = Math.max(0, t || 0);
  const h = Math.floor(t / 3600);
  const m = Math.floor((t % 3600) / 60);
  const s = t % 60;
  const ss = decimals ? s.toFixed(1).padStart(4, "0") : String(Math.floor(s)).padStart(2, "0");
  return (h ? `${h}:${String(m).padStart(2, "0")}` : String(m)) + ":" + ss;
};

export const pct = (x?: number | null) => Math.round((x || 0) * 100);

export const title = (id: string) => id.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());

export const cx = (...c: (string | false | null | undefined)[]) => c.filter(Boolean).join(" ");

// deterministic, pleasant brand hues so every brand keeps its colour everywhere in the UI
export const brandHue = (id: string) => {
  let h = 0;
  for (const ch of id) h = (h * 31 + ch.charCodeAt(0)) % 360;
  return h;
};
export const brandColor = (id: string, l = 68) => `hsl(${brandHue(id)} 85% ${l}%)`;
