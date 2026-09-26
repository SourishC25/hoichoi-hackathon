# What's on screen — plain-language guide for the demo

Keep this open while recording. Each item says what it is and a one-line way to say it out loud.

## Top bar
- **Birati / বিরতি** — the product name; "birati" means "break/pause" in Bengali.
- **Live** (green) — this page is talking to the real backend; uploads are processed for real.
- **How it works** — a six-step explainer of the pipeline (good to open once, early).
- **Upload episode** — drop any MP4 or paste a Google Drive link to process a new episode.

## Left rail — Episodes
- Each card: episode name, runtime, number of scenes found, number of ad breaks placed.
- **uploaded** tag — an episode a user added (as opposed to the built-in samples).
- **Job console** (appears under the list while processing) — the live log of every pipeline stage; say: "this is the system working in real time, step by step".

## Header of an episode
- **Now analysing** + title + synopsis — the summary is written by the model after watching the whole episode (video and Bengali audio).
- **VMAP** — downloads the industry-standard ad-break manifest (IAB VMAP 1.0 with VAST 3.0 inside) that any ad-capable video player can consume. Say: "this is the file a real player or ad server would take".
- **Debug JSON** — every decision with its evidence: every candidate, why it was kept or rejected, every brand ranking, every safety block. Say: "full audit trail for the ad-ops team".

## The six tiles
- **Runtime** — length of the episode.
- **Semantic scenes** — how many story scenes the model found (a scene = same place, time and storyline; not the same as camera cuts).
- **Camera cuts** — how many shot changes were detected (frame-exact, from the video itself).
- **Breaks placed x / y** — ads placed vs the maximum the pacing rules allow for this runtime.
- **Ad load · max 12 %** — share of total viewing time that is ads (ad ÷ (content + ad)); must stay under the cap.
- **Candidates judged** — how many possible break points were evaluated before choosing.

## Player
- Plays the episode; when it reaches a chosen break it **pauses on the exact frame**, plays the ad, then **resumes from the same frame**.
- **Sponsored · Ad 1 of N** + countdown ring — the ad overlay.
- **"Why Brand X here"** card — the reason in one line: the activity in the scene just before the break and which of the brand's target contexts it matched.
- **Jump to 6 s before a break** list — click any break to watch the cut with 6 seconds of lead-in, so you can hear that nobody is mid-sentence.

## Decision timeline (the coloured strip)
- **Scenes lane** — one block per scene. **Red hatched** blocks contain something at least one brand forbids (grief, violence, hospital…). Hover to read the scene summary.
- **Speech lane** (blue) — every moment someone is talking, found by a speech detector that works in any language.
- **Cuts lane** — every camera cut.
- **Candidates lane** — dots: **green** = chosen ad break, **amber** = a good spot that lost to pacing rules, **red** = rejected (e.g., speech at the cut, or every brand blocked). Hover for the reason.
- **Brand labels** — which brand's ad sits at each break.
- **White line** — the playhead; click anywhere on the strip to jump there.

## Tab: Ad breaks
- **Self-audit — 8/8 checks passed** — after deciding, the system re-checks every hard rule from raw data (no speech at the cut, on a camera cut, min gap, max breaks, ad load, protected opening/closing, no forbidden context, verifier passed). Say: "it double-checks its own guarantees".
- **Break card** (one per ad):
  - Thumbnail + time — the exact cut point; click to watch it.
  - **Brand name**, **creative id · 30s** — which ad file plays and its length.
  - **relevance 90 %** — how well the brand's target contexts match the lead-in scene.
  - **verifier passed** — an independent second model call that tried to find a reason *not* to air this ad, and found none.
  - **Lead-in activity … matched …** — what was happening right before the break and which brand contexts it matched ("dominant scene activity wins").
  - **Five rings** — *Break quality* (overall score), *Natural* (clean scene ending?), *Beat complete* (has the dramatic moment finished?), *Not jarring* (how little it would annoy a viewer), *Suspense hook* (does the moment make you want to come back after the ad?).
  - **Last line before cut / First line after** — the Bengali dialogue on each side of the cut, as heard by the model — proof it isn't mid-sentence.
  - **Speech-free 3.1 s before / 2.4 s after · snapped 0.5 s onto a camera cut · loudness dip 9 dB** — the hard signals: silence around the cut, the cut sits exactly on a shot change, the audio goes quieter (a natural pause).
  - **Reason** — the editor-style explanation in plain words.
  - **Hard-blocked** chips — brands that were *not allowed* here and the forbidden context that blocked them (e.g., "brand_b · eating" means the skincare brand's advertiser excludes eating scenes).
  - **Full brand ranking** — every brand's score for this slot, with evidence for each block.

## Tab: All candidates
- Every possible break point considered: **Time**, **Source** (scene boundary or fade-to-black), **Quality**, **Natural** score, **Speech ±10 s** (how much talking around it), **Decision** (chosen, lost to pacing, or the exact rejection reason). Click a row to preview it.

## Tab: Scenes
- One card per scene: summary, dominant activity, mood with intensity, sensitive-topic tags with confidence, and which brands the scene would block.

## Tab: Brands & pacing
- **Brand catalogue** — the JSON list of synthetic brands: category, *target_contexts* (where they want to appear), *negative_contexts* (where they must never appear), creatives.
- **Add unseen 9th brand** — adds a brand the system has never seen (a tea brand). Say: "no code changes — brands are data".
- **Pacing sliders** — max breaks per hour, minimum gap between breaks, max ad load %, protected opening/closing windows, minimum break quality, how much brand fit influences the choice.
- **Re-run brand matching & pacing** — re-runs only the stages that depend on the catalogue/rules (scene analysis is cached), so it finishes in about a minute.

## Tab: VMAP
- The raw manifest. Point at `timeOffset` (when the break happens), `MediaFile` (the ad video), `Tracking` (events an ad server counts: impression, start, complete).

## Upload dialog
- Drop an MP4 or paste a Google Drive link. Processing takes a few minutes; every step shows in the job console. A file that isn't a video is rejected with a clear message.
