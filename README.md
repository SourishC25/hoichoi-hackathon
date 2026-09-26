# Birati (বিরতি) — context-aware ad breaks for Bengali drama

> hoichoi Hackathon'26 · Problem 1 — Context-Aware Video Segmentation & Intelligent Ad Placement

**Live demo:** _<add Space URL>_ · **Explainer video:** _<add link>_

Birati ingests a long-form Bengali episode, segments it into semantically coherent scenes, decides
**where** a break is natural, **whether** a break is warranted under pacing rules, and **what** brand
belongs in each slot — then emits an IAB **VMAP 1.0 + inline VAST 3.0** manifest, a **debug JSON** that
explains every decision, and a **player that actually cuts to the ad and resumes** on the exact frame.

## Why it is AI-native (and where it deliberately isn't)

The judgement calls are made by a multimodal LLM (Gemini) that watches and *listens* to the episode;
the precision comes from deterministic signals. Each does what it is best at:

| Question | Decided by | Why |
|---|---|---|
| What is a scene? what's happening? mood? sensitive topics? | **Gemini, full episode (video + Bengali audio)** | Needs story understanding — dialogue about a death is grief even with no funeral on screen |
| Is this cut natural? is dialogue continuing? has the beat landed? | **Gemini, 42 s clip around each cut, 2 fps** | Needs to hear the Bengali conversation and judge dramatic rhythm |
| Which brand fits? which are blocked? | **Gemini, lead-in clip + scene context + catalogue as data** | Dominant activity ≠ background props; generalises to unseen brands |
| Final brand-safety check | **Independent adversarial Gemini call** | Fail-closed second opinion on the chosen brand only |
| Exactly which frame? is anyone speaking? | ffmpeg scdet camera cuts (PySceneDetect fallback) + Silero VAD | Frame-exact and language-agnostic; a mid-sentence cut becomes structurally impossible |
| How many breaks, where, which creative length? | Exact dynamic programme | Hard constraints must be guaranteed, not "usually" respected |

## Pipeline

```
video ─► A. perception ──────────► B. global understanding ─► C. candidates ─► D. local cut judge ─► E. brand match ─► F. pacing + verify ─► VMAP + debug JSON
         ffmpeg proxy               Gemini watches the whole     every scene       Gemini re-watches     Gemini scores all     DP under max/hr,
         ffmpeg scdet cuts          episode → scenes, activity,  boundary & fade   ±30 s around each     brands + violations;  min gap, ad load;
         Silero VAD speech          mood, sensitive topics       snapped to a      cut: dialogue          deterministic tag     adversarial verifier
         loudness, blackdetect      (vocab from catalogue)       silent camera cut continues? beat done?  blocks (fail-closed)  on the final pick
```

Every stage is cached, so **editing the brand catalogue re-runs only E–F** (seconds to a minute), and
editing pacing rules re-runs only F.

### WHERE — no mid-dialogue cuts
1. Candidates = LLM scene boundaries + fades to black.
2. Each is snapped to a **frame-exact camera cut** within ±6 s that sits in a **speech-free gap ≥ 0.8 s**
   with no speech 0.45 s before / 0.35 s after (Silero VAD). No such cut → rejected.
3. Gemini then judges the cut as a broadcast editor (last/first line, dialogue continuing, beat complete,
   jarring, suspense hook). Any "mid-sentence" or "conversation continues" verdict → rejected.

### WHETHER — pacing
Exact DP over candidates maximising total break quality subject to **max breaks/hour**, **min gap**, and
a **max ad-load %** budget (ad / (content + ad)); protected opening/closing windows; minimum quality
threshold — weak episodes get fewer breaks, possibly none. All rules are editable in the UI.

### WHAT — brand matching with hard negative-context blocks
- The catalogue is **data**: category, target and negative contexts are given to Gemini at runtime.
  The sensitive-topic vocabulary for the global pass is also built from the catalogue. **A 9th brand
  works with zero code changes** — try "+ Add an unseen 9th brand" in the UI and re-run.
- A brand is **hard-blocked** if *any* of three independent layers flags one of its negative contexts in
  the window 150 s before → 30 s after the break: (1) global scene tags, (2) the lead-in clip review,
  (3) an adversarial verifier on the final pick ("find reasons NOT to air this; when unsure, say yes").
  Errors fail closed. If every brand is blocked, the break is dropped and pacing re-optimises.
- Among safe brands, **dominant activity of the lead-in scene** drives relevance; consecutive repeats of
  the same brand are avoided when a near-equal alternative exists.

## Outputs
- `GET /api/videos/{id}/vmap.xml` — VMAP 1.0, one `AdBreak` per break with inline VAST 3.0 (MediaFile,
  Impression, start/complete tracking, breakStart/breakEnd) and a `contextual-targeting` extension.
- `GET /api/videos/{id}/debug.json` — scenes, every candidate with signals + LLM verdicts + rejection
  reasons, full per-slot brand ranking with block evidence, verifier results, pacing summary, timings.
- Player — parses the VMAP in the browser, detects the break with `requestVideoFrameCallback`, pauses,
  plays the creative, fires tracking beacons, and resumes from the exact cut frame.

The catalogue references creative files that were not supplied, so Birati renders clearly-labelled
**synthetic placeholder spots** for every creative (including brands added later). Only the synthetic
brand names from the catalogue are used.

## Run locally
```bash
python -m venv .venv && .venv/Scripts/pip install torch --index-url https://download.pytorch.org/whl/cpu
.venv/Scripts/pip install -r requirements.txt
echo GEMINI_API_KEY=... > .env
python -m app.pipeline.run path/to/episode.mp4        # CLI: full pipeline, prints the breaks
uvicorn app.main:app --port 7860                      # web app + API
```
ffmpeg is used from PATH, or downloaded automatically via `static-ffmpeg`.

## No hard-coding
Nothing in the code references a sample video, timestamp or brand. The sample results shipped with the
demo are cached outputs of this pipeline (see `generated_at`, models and timings in each debug JSON);
upload any episode in the UI to run the full pipeline live.

## Repo layout
```
app/pipeline/media.py       ffmpeg helpers (proxy, audio, blackdetect, clips)
app/pipeline/signals.py     camera cuts (scdet), Silero VAD, loudness + queries
app/pipeline/understand.py  B · Gemini full-episode scene segmentation + sensitivity tagging
app/pipeline/breaks.py      C/D · candidate snapping + Gemini cut judgement + where-score
app/pipeline/brands.py      E · catalogue-driven matching, 3-layer hard blocks, verifier
app/pipeline/pacing.py      F · exact DP break selection under pacing rules
app/pipeline/manifest.py    VMAP 1.0 / VAST 3.0 writer
app/pipeline/ads.py         synthetic creative renderer
app/pipeline/run.py         cached orchestrator + CLI
app/main.py                 FastAPI: jobs, uploads, re-runs, downloads
web/                        demo UI (vanilla JS)
```
