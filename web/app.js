/* Birati demo UI — library, VMAP-driven player, decision timeline, re-runs. No framework. */
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmt = (t) => { t = Math.max(0, t); const h = Math.floor(t / 3600), m = Math.floor((t % 3600) / 60), s = (t % 60); return (h ? h + ":" + String(m).padStart(2, "0") : m) + ":" + s.toFixed(1).padStart(4, "0"); };
const fmtShort = (t) => fmt(t).replace(/\.\d$/, "");
const pct = (x) => Math.round((x || 0) * 100);

// Same UI, two hosts: the FastAPI server (live processing) or a static export (free hosting).
const STATIC = !!window.BIRATI_STATIC;
const q = (v, extra = "") => (v ? `?variant=${encodeURIComponent(v)}${extra ? "&" + extra : ""}` : extra ? "?" + extra : "");
const U = {
  videos: () => (STATIC ? "api/videos.json" : "/api/videos"),
  result: (id, v) => (STATIC ? `data/${id}/result${v ? "_" + v : ""}.json` : `/api/videos/${id}/result${q(v)}`),
  vmap: (id, v) => (STATIC ? `data/${id}/vmap${v ? "_" + v : ""}.xml` : `/api/videos/${id}/vmap.xml${q(v)}`),
  vmapDownload: (id, v) => (STATIC ? U.vmap(id, v) : `/api/videos/${id}/vmap.xml${q(v, "download=1")}`),
  debug: (id, v) => (STATIC ? U.result(id, v) : `/api/videos/${id}/debug.json${q(v)}`),
  media: (id) => (STATIC ? `media/${id}.mp4` : `/media/${id}.mp4`),
  thumb: (id, t) => (STATIC ? `thumbs/${id}/${t.toFixed(2)}.jpg` : `/api/thumb/${id}/${t.toFixed(2)}`),
  brands: () => (STATIC ? "api/brands.json" : "/api/brands"),
  rules: () => (STATIC ? "api/rules.json" : "/api/rules"),
  catalogue: (id, v) => (STATIC ? `data/${id}/catalogue${v ? "_" + v : ""}.json` : `/api/videos/${id}/catalogue${q(v)}`),
};

const EXAMPLE_BRAND = {
  brand_id: "brand_i", display_name: "Brand I", category: "beverages/tea",
  target_contexts: ["tea", "drinking tea", "cha", "adda", "conversation over tea", "morning", "breakfast", "relaxing at home", "cafe", "guests at home"],
  negative_contexts: ["funeral", "hospital", "violence", "grief", "illness"],
  creatives: [
    { id: "i_15s_bn", duration_sec: 15, language: "bn", url: "ads/brand_i/i_15s_bn.mp4" },
    { id: "i_20s_bn", duration_sec: 20, language: "bn", url: "ads/brand_i/i_20s_bn.mp4" },
  ],
};
const RULE_LABELS = {
  max_breaks_per_hour: "Max breaks / hour", min_gap_sec: "Min gap between breaks (s)", max_ad_load_pct: "Max ad load (%)",
  no_break_first_sec: "No break in first (s)", no_break_last_sec: "No break in last (s)", min_break_score: "Min break quality (0–1)",
  brand_relevance_weight: "Brand relevance weight",
};

const state = { videos: [], id: null, variant: null, result: null, breaks: [], lastT: 0, adPlaying: false, defaultBrands: null, defaultRules: null, jobs: {} };

// ---------------- library ----------------
async function loadLibrary(selectFirst = false) {
  const vids = await (await fetch(U.videos())).json();
  state.videos = vids;
  const lib = $("#library");
  if (!vids.length) { lib.innerHTML = '<div class="muted sm">No processed episodes yet — upload one.</div>'; return; }
  lib.innerHTML = vids.map((v) => v.processing
    ? `<div class="lib-item" data-id="${esc(v.id)}"><div class="t">${esc(v.id.replace(/_/g, " "))}</div><div class="m">processing…</div></div>`
    : `<div class="lib-item ${v.id === state.id ? "active" : ""}" data-id="${esc(v.id)}">
        <div class="t">${esc(v.id.replace(/_/g, " "))}${v.uploaded ? '<span class="tag">uploaded</span>' : ""}</div>
        <div class="m">${fmtShort(v.duration)} · ${v.summary.scenes} scenes · ${v.summary.breaks} breaks</div></div>`).join("");
  $$(".lib-item", lib).forEach((el) => el.onclick = () => { const v = vids.find((x) => x.id === el.dataset.id); if (!v.processing) openEpisode(v.id); });
  if (selectFirst && !state.id) {
    const [hid, hvar] = location.hash.replace(/^#\/?/, "").split("/");
    const pick = vids.find((v) => v.id === hid && !v.processing) || vids.find((v) => !v.processing);
    if (pick) openEpisode(pick.id, hid === pick.id ? hvar : null);
  }
}

async function openEpisode(id, variant = null) {
  const res = await fetch(U.result(id, variant));
  if (!res.ok) { alert("Could not load result"); return; }
  const r = await res.json();
  const sameVideo = state.id === id;
  state.id = id; state.variant = STATIC ? variant : (r.variant || null); state.result = r;
  history.replaceState(null, "", `#/${id}${variant ? "/" + variant : ""}`);
  $$(".lib-item").forEach((el) => el.classList.toggle("active", el.dataset.id === id));
  $("#empty").hidden = true; $("#episode").hidden = false;
  $("#ep-title").textContent = id.replace(/_/g, " ");
  $("#ep-synopsis").textContent = r.synopsis || "";
  $("#dl-vmap").href = U.vmapDownload(id, state.variant);
  $("#dl-debug").href = U.debug(id, state.variant);
  renderKpis(r);
  const content = $("#content");
  if (!sameVideo) { content.src = U.media(id); state.lastT = 0; }
  await loadVmap(U.vmap(id, state.variant));
  renderBreakNav(); renderTimeline(); renderBreaks(); renderCandidates(); renderScenes(); await renderConfig();
}

function renderKpis(r) {
  const s = r.summary;
  const items = [
    [fmtShort(r.video.duration), "Runtime"], [s.scenes, "Semantic scenes"], [s.camera_cuts, "Camera cuts"],
    [`${s.breaks} / ${s.allowed_breaks}`, "Breaks placed / allowed"], [`${s.ad_load_pct}%`, `Ad load (max ${r.rules.max_ad_load_pct}%)`],
    [`${s.candidates}`, "Candidates evaluated"],
  ];
  $("#kpis").innerHTML = items.map(([v, l]) => `<div class="kpi"><div class="v">${esc(v)}</div><div class="l">${esc(l)}</div></div>`).join("");
}

// ---------------- VMAP player ----------------
const VMAP_NS = "http://www.iab.net/videosuite/vmap";
function parseTs(s) { return String(s).split(":").reduce((a, p) => a * 60 + parseFloat(p), 0); }

async function loadVmap(url) {
  const xml = await (await fetch(url)).text();
  $("#vmap-view").textContent = xml;
  const doc = new DOMParser().parseFromString(xml, "application/xml");
  state.breaks = [...doc.getElementsByTagNameNS(VMAP_NS, "AdBreak")].map((b, i) => {
    const ad = b.getElementsByTagName("Ad")[0];
    const trk = {};
    [...b.getElementsByTagName("Tracking"), ...b.getElementsByTagNameNS(VMAP_NS, "Tracking")].forEach((t) => trk[t.getAttribute("event")] = t.textContent.trim());
    return {
      i, id: b.getAttribute("breakId"), offset: parseTs(b.getAttribute("timeOffset")),
      media: ad.getElementsByTagName("MediaFile")[0].textContent.trim(),
      duration: parseTs(ad.getElementsByTagName("Duration")[0].textContent),
      title: ad.getElementsByTagName("AdTitle")[0].textContent,
      impression: ad.getElementsByTagName("Impression")[0]?.textContent.trim(),
      tracking: trk, played: false, meta: state.result.breaks[i],
    };
  });
}

function ping(url) { if (url) fetch(url, { mode: "no-cors", keepalive: true }).catch(() => {}); }

function startAd(b) {
  const content = $("#content"), ad = $("#ad");
  state.adPlaying = true;
  content.pause();
  content.currentTime = b.offset;           // resume from the exact cut frame
  $("#ad-layer").hidden = false;
  $("#ad-label").textContent = `Ad ${b.i + 1} of ${state.breaks.length} · ${b.meta?.brand_name || b.title}`;
  const m = b.meta || {};
  $("#ad-why").innerHTML = `<b>Why ${esc(m.brand_name || "this ad")} here:</b> ${esc(m.dominant_activity || "")} — matched <i>${esc((m.matched_contexts || []).join(", ") || "best available")}</i> · break quality ${pct(m.quality)}%`;
  ad.src = b.media; ad.currentTime = 0;
  ping(b.tracking.breakStart); ping(b.impression);
  ad.play().then(() => ping(b.tracking.start)).catch(() => { ad.controls = true; });
  const tick = () => { if (!state.adPlaying) return; $("#ad-count").textContent = Math.max(0, Math.ceil((ad.duration || b.duration) - ad.currentTime)) + "s"; requestAnimationFrame(tick); };
  tick();
  ad.onended = () => endAd(b);
}

function endAd(b) {
  const content = $("#content"), ad = $("#ad");
  ping(b.tracking.complete); ping(b.tracking.breakEnd);
  b.played = true; state.adPlaying = false;
  ad.pause(); ad.removeAttribute("src"); ad.load(); ad.controls = false;
  $("#ad-layer").hidden = true;
  state.lastT = b.offset;
  content.play();
  renderBreakNav();
}

function checkBreaks(t) {
  if (state.adPlaying) return;
  for (const b of state.breaks) {
    if (!b.played && state.lastT < b.offset && t >= b.offset - 0.02 && t - b.offset < 1.5) { state.lastT = t; startAd(b); return; }
  }
  state.lastT = t;
}

function setupPlayer() {
  const content = $("#content");
  // Frame-accurate detection via requestVideoFrameCallback where the browser composites frames,
  // plus an always-on 40 ms poll (rVFC can stop firing for off-screen/occluded video). Either path
  // triggers at most once per break; startAd() seeks back to the exact cut frame.
  if ("requestVideoFrameCallback" in HTMLVideoElement.prototype) {
    const onFrame = (_, meta) => { checkBreaks(meta.mediaTime); content.requestVideoFrameCallback(onFrame); };
    content.requestVideoFrameCallback(onFrame);
  }
  setInterval(() => { if (!content.paused && !content.seeking) checkBreaks(content.currentTime); }, 40);
  content.addEventListener("seeking", () => { state.lastT = content.currentTime; });
  content.addEventListener("timeupdate", updatePlayhead);
  $("#ad-layer").addEventListener("click", () => { const ad = $("#ad"); if (ad.paused) ad.play(); });
}

function jumpBefore(i, lead = 6) {
  const b = state.breaks[i]; if (!b) return;
  b.played = false;
  const content = $("#content");
  content.currentTime = Math.max(0, b.offset - lead);
  state.lastT = content.currentTime;
  content.play();
  $("#player").scrollIntoView({ behavior: "smooth", block: "center" });
}

function renderBreakNav() {
  const nav = $("#break-nav");
  if (!state.breaks.length) { nav.innerHTML = '<h4>Ad breaks</h4><div class="muted sm">No break met the quality and safety bar under these pacing rules.</div>'; return; }
  nav.innerHTML = "<h4>Jump to 6 s before a break</h4>" + state.breaks.map((b) => `
    <div class="bn-item ${b.played ? "played" : ""}" data-i="${b.i}">
      <img loading="lazy" src="${U.thumb(state.id, Math.max(0, b.offset - 1))}" alt="">
      <div><div class="tt">${fmt(b.offset)}</div><div class="bb">${esc(b.meta?.brand_name || "")}</div>
      <div class="muted sm">${esc(b.meta?.creative?.id || "")} · ${b.duration}s</div></div></div>`).join("");
  $$(".bn-item", nav).forEach((el) => el.onclick = () => jumpBefore(+el.dataset.i));
}

// ---------------- timeline ----------------
function renderTimeline() {
  const r = state.result, D = r.video.duration, W = 1200;
  const lanes = { scenes: [18, 26], speech: [52, 12], cuts: [72, 10], cands: [96, 0] };
  const x = (t) => (t / D) * W;
  let svg = `<svg viewBox="0 0 ${W} 124" preserveAspectRatio="none">`;
  svg += `<text x="0" y="12" fill="#8d96ab" font-size="10">scenes</text><text x="0" y="48" fill="#8d96ab" font-size="10">speech</text>`;
  r.scenes.forEach((s, i) => {
    const sens = (s.blocked_contexts || []).length > 0;
    svg += `<rect data-k="scene" data-i="${i}" x="${x(s.start)}" y="${lanes.scenes[0]}" width="${Math.max(1, x(s.end) - x(s.start) - 1)}" height="${lanes.scenes[1]}" rx="2" fill="${sens ? "var(--sens)" : i % 2 ? "var(--scene-a)" : "var(--scene-b)"}"/>`;
  });
  r.speech.forEach((s) => svg += `<rect x="${x(s.start)}" y="${lanes.speech[0]}" width="${Math.max(0.5, x(s.end) - x(s.start))}" height="${lanes.speech[1]}" fill="var(--speech)" opacity=".75"/>`);
  r.shots.forEach((t) => svg += `<line x1="${x(t)}" x2="${x(t)}" y1="${lanes.cuts[0]}" y2="${lanes.cuts[0] + lanes.cuts[1]}" stroke="#8d96ab" stroke-width=".6" opacity=".7"/>`);
  r.candidates.forEach((c, i) => {
    const col = c.selected ? "var(--ok)" : c.rejections.length && !c.rejections[0].startsWith("not chosen") ? "var(--bad)" : "var(--warn)";
    svg += `<circle data-k="cand" data-i="${i}" cx="${x(c.t)}" cy="${lanes.cands[0]}" r="${c.selected ? 6 : 4}" fill="${col}" stroke="#0d0f14" stroke-width="1.5"/>`;
  });
  r.breaks.forEach((b, i) => {
    svg += `<line x1="${x(b.t)}" x2="${x(b.t)}" y1="10" y2="${lanes.cands[0] - 6}" stroke="var(--ok)" stroke-width="1.5" stroke-dasharray="3 2"/>`;
    svg += `<text x="${Math.min(W - 60, x(b.t) + 4)}" y="118" fill="var(--ok)" font-size="11" font-weight="600">${esc(b.brand_name)}</text>`;
  });
  svg += `<line id="playhead" x1="0" x2="0" y1="0" y2="124" stroke="#fff" stroke-width="1.5"/>`;
  svg += `</svg>`;
  const el = $("#timeline");
  el.innerHTML = svg;
  const svgEl = $("svg", el), tip = $("#tooltip");
  svgEl.addEventListener("mousemove", (e) => {
    const k = e.target.dataset.k, i = +e.target.dataset.i;
    if (!k) { tip.hidden = true; return; }
    tip.innerHTML = k === "scene" ? sceneTip(r.scenes[i]) : candTip(r.candidates[i]);
    const box = el.parentElement.getBoundingClientRect();
    tip.hidden = false;
    tip.style.left = Math.min(box.width - 390, Math.max(0, e.clientX - box.left + 12)) + "px";
    tip.style.top = (e.clientY - box.top + 16) + "px";
  });
  svgEl.addEventListener("mouseleave", () => tip.hidden = true);
  svgEl.addEventListener("click", (e) => {
    const rect = svgEl.getBoundingClientRect();
    const t = ((e.clientX - rect.left) / rect.width) * D;
    const content = $("#content"); content.currentTime = t; state.lastT = t;
  });
}

function sceneTip(s) {
  const sens = (s.sensitive || []).map((z) => `${esc(z.topic)} (${pct(z.confidence)}%)`).join(", ") || "none";
  const blk = (s.blocked_contexts || []).length ? `<br><span style="color:var(--bad)">Blocks ${esc(s.blocks_brands.join(", "))} — ${esc(s.blocked_contexts.join(", "))}</span>` : "";
  return `<b>Scene ${s.index + 1}</b> · ${fmt(s.start)}–${fmt(s.end)}<br>${esc(s.summary)}<br><span class="muted">Activity:</span> ${esc(s.dominant_activity)}<br><span class="muted">Mood:</span> ${esc(s.mood)}<br><span class="muted">Sensitive tags:</span> ${sens}${blk}`;
}
function candTip(c) {
  const j = c.judge || {};
  return `<b>${c.selected ? "AD BREAK" : "Candidate"}</b> ${fmt(c.t)} · quality ${pct(c.quality)}%<br>${esc(j.reason || "")}<br>${c.rejections.map((x) => `<span style="color:var(--bad)">✕ ${esc(x)}</span>`).join("<br>")}`;
}
function updatePlayhead() {
  const ph = $("#playhead"); if (!ph || !state.result) return;
  const x = ($("#content").currentTime / state.result.video.duration) * 1200;
  ph.setAttribute("x1", x); ph.setAttribute("x2", x);
}

// ---------------- tabs ----------------
function bar(label, v) { return `<div class="bar"><div class="l">${esc(label)} · ${pct(v)}%</div><div class="track"><div class="fill" style="width:${pct(v)}%"></div></div></div>`; }

function auditCard(r) {
  if (!r.audit) return "";
  const ok = r.audit.every((a) => a.pass);
  return `<div class="card audit"><h4 style="margin:0 0 8px">${ok ? "✓" : "✕"} Self-audit — hard guarantees re-checked from raw signals</h4>
    <div class="audit-grid">${r.audit.map((a) => `<div class="${a.pass ? "pass" : "fail"}"><b>${a.pass ? "PASS" : "FAIL"}</b> ${esc(a.check)}<div class="muted sm">${esc(a.detail)}</div></div>`).join("")}</div></div>`;
}

function renderBreaks() {
  const r = state.result, el = $("#tab-breaks");
  if (!r.breaks.length) { el.innerHTML = auditCard(r) + '<div class="card muted">No ad breaks were placed. ' + (r.summary.allowed_breaks === 0 ? `At ${r.rules.max_breaks_per_hour} breaks/hour a ${fmtShort(r.video.duration)} runtime allows 0 breaks — loosen the pacing rules in “Brands & pacing” to test.` : 'No boundary met the quality + brand-safety bar under the current pacing rules — a deliberate outcome, not a failure.') + '</div>'; return; }
  el.innerHTML = auditCard(r) + r.breaks.map((b, i) => {
    const c = r.candidates.find((x) => x.id === b.candidate_id) || {};
    const j = c.judge || {}, s = c.signals || {};
    const ranking = (c.brand_ranking || []);
    const blocked = ranking.filter((x) => x.blocked || x.verifier_blocked);
    const verif = ranking.find((x) => x.brand_id === b.brand_id)?.verifier;
    return `<div class="card brk">
      <div><img loading="lazy" src="${U.thumb(state.id, Math.max(0, b.t - 1))}" alt=""><button class="btn sm" style="margin-top:8px;width:100%" onclick="jumpBefore(${i})">▶ Watch this cut</button></div>
      <div>
        <h4><span class="mono">${fmt(b.t)}</span> ${esc(b.brand_name)} <span class="pill">${esc(b.creative.id)} · ${b.creative.duration_sec}s</span>
          <span class="pill ok">quality ${pct(b.quality)}%</span><span class="pill">relevance ${pct(b.relevance)}%</span>
          ${verif ? `<span class="pill ok">✓ safety verifier passed</span>` : ""}</h4>
        <div class="muted sm">Lead-in activity: <b style="color:var(--text)">${esc(b.dominant_activity)}</b> · matched: ${esc((b.matched_contexts || []).join(", ") || "—")}</div>
        ${r.engine === "local"
          ? `<div class="lines"><div><small>speech-free before cut (VAD)</small>${s.silence_before >= 99 ? "no speech" : s.silence_before + " s"}</div><div><small>speech-free after cut (VAD)</small>${s.silence_after >= 99 ? "no speech" : s.silence_after + " s"} · visual change ${pct(j.visual_novelty)}%</div></div>`
          : `<div class="lines"><div><small>last line before cut</small>${esc(b.last_line_before_cut || "— (no speech)")}</div><div><small>first line after</small>${esc(b.first_line_after_cut || "— (no speech)")}</div></div>`}
        <div class="bars">${bar("natural break", j.natural_break_score)}${bar("beat complete", j.story_beat_complete)}${bar("not jarring", 1 - (j.jarring ?? 1))}${bar("suspense hook", j.suspense_hook)}</div>
        <div class="muted sm">Silence around cut: ${s.silence_before}s before / ${s.silence_after}s after · snapped ${s.snap_delta}s to a camera cut · loudness dip ${s.loudness_dip_db} dB${s.fade_to_black ? " · fade to black" : ""}</div>
        <p style="margin:8px 0 0">${esc(b.reason)}</p>
        ${blocked.length ? `<div class="blocked"><b>Hard-blocked here:</b> ${blocked.map((x) => `${esc(x.brand_id)} (${esc([...new Set((x.blocks || []).map((y) => y.negative_context))].join(", ") || "verifier: " + (x.verifier?.violated_contexts || []).join(", "))})`).join(" · ")}</div>` : ""}
        <details><summary>Full brand ranking for this slot</summary>
          <table class="grid"><tr><th>Brand</th><th>Relevance</th><th>Status</th><th>Why</th></tr>
          ${ranking.map((x) => `<tr><td>${esc(x.brand_id)}</td><td>${pct(x.relevance)}%</td><td>${x.blocked || x.verifier_blocked ? '<span class="pill bad">blocked</span>' : x.brand_id === b.brand_id ? '<span class="pill ok">chosen</span>' : '<span class="pill">eligible</span>'}</td>
            <td>${esc(x.rationale)}${(x.blocks || []).map((y) => `<br><span style="color:var(--bad)">✕ ${esc(y.negative_context)} — ${esc(y.evidence)} <span class="muted">[${esc(y.source)}]</span></span>`).join("")}${x.verifier?.violation ? `<br><span style="color:var(--bad)">✕ verifier: ${esc(x.verifier.evidence)}</span>` : ""}</td></tr>`).join("")}
          </table></details>
      </div></div>`;
  }).join("");
}

function renderCandidates() {
  const r = state.result;
  $("#tab-candidates").innerHTML = `<p class="muted sm">Every scene boundary and fade the system considered, and why it was kept or rejected. Click a row to seek.</p>
  <table class="grid"><tr><th>Time</th><th>Source</th><th>Quality</th><th>Natural</th><th>Speech ±10s</th><th>Decision</th></tr>
  ${r.candidates.map((c) => {
    const j = c.judge || {}, s = c.signals || {};
    const dec = c.selected ? '<span class="pill ok">AD BREAK</span>' : c.rejections.map((x) => `<div style="color:${x.startsWith("not chosen") ? "var(--warn)" : "var(--bad)"}">${esc(x)}</div>`).join("");
    return `<tr class="clickable" data-t="${c.t}"><td class="mono">${fmt(c.t)}</td><td>${esc((c.sources || []).join(", "))}</td><td>${c.quality != null ? pct(c.quality) + "%" : "—"}</td><td>${j.natural_break_score != null ? pct(j.natural_break_score) + "%" : "—"}</td><td>${pct(s.speech_density_10s_before)}% / ${pct(s.speech_density_10s_after)}%</td><td>${dec}${j.reason ? `<div class="muted sm">${esc(j.reason)}</div>` : ""}</td></tr>`;
  }).join("")}</table>`;
  $$("#tab-candidates tr.clickable").forEach((tr) => tr.onclick = () => { const c = $("#content"); c.currentTime = Math.max(0, +tr.dataset.t - 6); state.lastT = c.currentTime; c.play(); });
}

function renderScenes() {
  const r = state.result;
  $("#tab-scenes").innerHTML = `<table class="grid"><tr><th>#</th><th>Time</th><th>Summary</th><th>Dominant activity</th><th>Mood</th><th>Sensitive</th><th>Blocks brands</th></tr>
  ${r.scenes.map((s) => `<tr class="clickable" data-t="${s.start}"><td>${s.index + 1}</td><td class="mono">${fmt(s.start)}<br>${fmt(s.end)}</td><td>${esc(s.summary)}<div class="muted sm">${esc((s.contexts || []).join(" · "))}</div></td><td>${esc(s.dominant_activity)}</td><td>${esc(s.mood)} (${pct(s.emotional_intensity)}%)</td>
    <td>${(s.sensitive || []).map((z) => `<span class="pill ${z.confidence >= 0.3 ? "bad" : ""}" title="${esc(z.evidence)}">${esc(z.topic)} ${pct(z.confidence)}%</span>`).join(" ") || '<span class="muted">—</span>'}</td><td>${(s.blocks_brands || []).length ? `<span style="color:var(--bad)">${esc(s.blocks_brands.join(", "))}</span><div class="muted sm">${esc(s.blocked_contexts.join(", "))}</div>` : '<span class="muted">—</span>'}</td></tr>`).join("")}</table>`;
  $$("#tab-scenes tr.clickable").forEach((tr) => tr.onclick = () => { const c = $("#content"); c.currentTime = +tr.dataset.t; state.lastT = c.currentTime; });
}

async function renderConfig() {
  if (!state.defaultBrands) state.defaultBrands = await (await fetch(U.brands())).json();
  if (!state.defaultRules) state.defaultRules = await (await fetch(U.rules())).json();
  const cat = await (await fetch(U.catalogue(state.id, state.variant))).json();
  $("#brands-json").value = JSON.stringify(cat, null, 2);
  const rules = state.result.rules || state.defaultRules;
  $("#rules-form").innerHTML = Object.keys(state.defaultRules).map((k) => `<label for="r-${k}">${esc(RULE_LABELS[k] || k)}</label><input id="r-${k}" name="${k}" type="number" step="any" value="${rules[k] ?? state.defaultRules[k]}">`).join("");
}

function currentRules() { const o = {}; $$("#rules-form input").forEach((i) => o[i.name] = +i.value); return o; }

// ---------------- jobs ----------------
function renderJobs() {
  $("#jobs").innerHTML = Object.values(state.jobs).slice(-3).reverse().map((j) => `
    <div class="job"><div><span class="st ${j.status}">${esc(j.status)}</span> · ${esc(j.kind)} · ${esc(j.video_id)}</div>
    <div class="log">${esc((j.log || []).slice(-12).join("\n"))}</div></div>`).join("");
}

async function pollJob(id, onDone) {
  const j = await (await fetch(`/api/jobs/${id}`)).json();
  state.jobs[id] = j; renderJobs();
  if (j.status === "done") { onDone && onDone(j); return; }
  if (j.status === "error") return;
  setTimeout(() => pollJob(id, onDone), 2000);
}

async function rerun() {
  let brands;
  try { brands = JSON.parse($("#brands-json").value); } catch (e) { alert("Catalogue JSON is invalid: " + e.message); return; }
  if (STATIC) {
    const plus9 = brands.some((b) => b.brand_id === "brand_i");
    const edited = brands.length !== state.defaultBrands.length + (plus9 ? 1 : 0);
    if (edited) alert("This free static demo holds precomputed runs for the default catalogue and the default + unseen Brand I catalogue. For arbitrary catalogues / pacing rules, run Birati locally (see README) — it re-runs in seconds.");
    openEpisode(state.id, plus9 ? "plus9" : null);
    return;
  }
  const fd = new FormData();
  fd.append("brands", JSON.stringify(brands)); fd.append("rules", JSON.stringify(currentRules()));
  const btn = $("#btn-rerun"); btn.disabled = true; btn.textContent = "Re-running…";
  const res = await fetch(`/api/videos/${state.id}/rerun`, { method: "POST", body: fd });
  if (!res.ok) { alert(await res.text()); btn.disabled = false; btn.textContent = "Re-run brand matching & pacing"; return; }
  const job = await res.json();
  const vid = state.id;
  pollJob(job.id, (j) => { btn.disabled = false; btn.textContent = "Re-run brand matching & pacing"; openEpisode(vid, j.variant); });
}

function uploadEpisode(e) {
  e.preventDefault();
  const f = $("#upload-file").files[0], url = $("#upload-url").value.trim();
  if (!f && !url) { alert("Choose a video file or paste a link."); return; }
  const fd = new FormData();
  if ($("#upload-use-cat").checked && $("#brands-json").value) fd.append("brands", $("#brands-json").value);
  const onJob = (job) => { $("#dlg-upload").close(); loadLibrary(); pollJob(job.id, (j) => { loadLibrary(); openEpisode(j.video_id, j.variant); }); };
  if (!f) {
    fd.append("url", url);
    $("#upload-go").disabled = true;
    fetch("/api/ingest_url", { method: "POST", body: fd }).then(async (r) => {
      $("#upload-go").disabled = false;
      if (!r.ok) { alert("Failed: " + await r.text()); return; }
      onJob(await r.json());
    });
    return;
  }
  fd.append("file", f);
  const xhr = new XMLHttpRequest();
  $("#upload-progress").hidden = false; $("#upload-go").disabled = true;
  xhr.upload.onprogress = (ev) => { $("#upload-progress div").style.width = (100 * ev.loaded / ev.total) + "%"; };
  xhr.onload = () => {
    $("#upload-go").disabled = false; $("#upload-progress").hidden = true;
    if (xhr.status !== 200) { alert("Upload failed: " + xhr.responseText); return; }
    onJob(JSON.parse(xhr.responseText));
  };
  xhr.open("POST", "/api/upload"); xhr.send(fd);
}

// ---------------- boot ----------------
function boot() {
  setupPlayer();
  $$(".tab").forEach((t) => t.onclick = () => {
    $$(".tab").forEach((x) => x.classList.toggle("active", x === t));
    $$(".tab-body").forEach((b) => b.hidden = b.id !== "tab-" + t.dataset.tab);
  });
  $("#btn-upload").onclick = () => $(STATIC ? "#dlg-local" : "#dlg-upload").showModal();
  if (STATIC) { $("#btn-upload").textContent = "Process your own episode"; $("#btn-rerun").textContent = "Show run with this catalogue"; }
  $("#btn-how").onclick = () => $("#dlg-how").showModal();
  $("#upload-form").addEventListener("submit", (e) => { if (e.submitter?.value === "cancel") return; uploadEpisode(e); });
  $("#btn-rerun").onclick = rerun;
  $("#btn-add-brand").onclick = () => {
    let b; try { b = JSON.parse($("#brands-json").value); } catch { b = []; }
    if (!b.find((x) => x.brand_id === EXAMPLE_BRAND.brand_id)) b.push(EXAMPLE_BRAND);
    $("#brands-json").value = JSON.stringify(b, null, 2);
  };
  $("#btn-reset-brands").onclick = () => $("#brands-json").value = JSON.stringify(state.defaultBrands, null, 2);
  loadLibrary(true);
}
boot();
