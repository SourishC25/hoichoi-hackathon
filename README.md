# Birati (বিরতি) — context-aware ad breaks for Bengali drama

> hoichoi Hackathon'26 · Problem 1 — Context-Aware Video Segmentation & Intelligent Ad Placement

**Live demo:** _<add Space URL>_ · **Explainer video:** _<add link>_

Birati ingests a long-form Bengali episode, segments it into semantically coherent scenes, decides
**where** a break is natural, **whether** a break is warranted under pacing rules, and **what** brand
belongs in each slot — then emits an IAB **VMAP 1.0 + inline VAST 3.0** manifest, a **debug JSON** that
explains every decision, and a **player that actually cuts to the ad and resumes** on the exact frame.

**It runs entirely on free, open-weights foundation models on a laptop CPU — no API keys, no cost.**

## The AI core — and why each model is there

| Question | Model (open weights, local CPU) | How |
|---|---|---|
| What is on screen? eating, kitchen, funeral, hospital, car, phone… | **CLIP** `openai/clip-vit-base-patch32` | zero-shot: every frame (1 fps) and every catalogue phrase share one embedding space |
| What is in the soundtrack? crying, screaming, gunshots, sirens, sad/tense music | **CLAP** `laion/clap-htsat-unfused` | zero-shot on 5 s audio windows |
| Where are the semantic scenes? | CLIP shot embeddings | a new scene starts when a shot looks unlike everything in the previous minute (shot/reverse-shot dialogue stays one scene) |
| Is anyone speaking at this instant? | **Silero VAD** | language-agnostic, so Bengali/English code-switching is irrelevant |
| Exactly which frame? | ffmpeg `scdet` camera cuts, `blackdetect` fades | frame-exact |

**Open-vocabulary by construction.** Brands are *data*: every `target_contexts` / `negative_contexts`
phrase is embedded at runtime and scored against the episode. A 9th, unseen brand is handled with
**zero code changes** — its words are standardised against a reference bank of real drama footage exactly
like the known brands' words (per-concept z-scores remove CLIP's word biases).

**Calibrated, not guessed.** During development a large multimodal LLM (Gemini) labelled the sample
episodes' scenes and sensitive topics. Those labels are the *teacher*: `scripts/calibrate_local.py` tunes
the local engine's scene threshold and safety thresholds against them (recall-weighted: a missed funeral
disqualifies, a false alarm only costs one ad slot) and reports **leave-one-episode-out** scores in
`data/calibration_report.json`. The runtime never calls a paid API. (A `BIRATI_ENGINE=gemini` mode still
exists for anyone with credits; both engines implement the same stage contracts.)

## Pipeline

```
video ─► A. perception ─► B. scenes ─► C. candidates ─► D. cut judge ─► E. brand match ─► F. pacing + verify ─► VMAP + debug JSON
          proxy, scdet      CLIP shot     scene bounds +   CLIP visual      CLIP vs every      exact DP under
          cuts, Silero      novelty →     fades, snapped   change, VAD      brand phrase;      max/hr, min gap,
          VAD, loudness,    scenes; CLIP  to a silent      silence, CLAP    3-layer hard       ad load; dense
          blackdetect,      +CLAP tags    camera cut       music carry,     negative blocks    2 fps verifier on
          CLIP+CLAP embeds  per scene                      loudness dip                        the final pick
```

### WHERE — no mid-dialogue cuts
1. Candidates = semantic scene boundaries + fades to black.
2. Each is snapped to a **frame-exact camera cut** within ±6 s that sits in a **speech-free gap ≥ 0.8 s**
   with no speech 0.45 s before / 0.35 s after (Silero VAD). No such cut → rejected. A mid-sentence cut
   is structurally impossible.
3. Cut quality: CLIP visual change across the cut, silence on both sides, speech density, loudness dip,
   fade-to-black, and whether music carries over (CLAP). Speech on both sides with < 2 s combined gap →
   "conversation continues" → rejected.

### WHETHER — pacing
Exact dynamic programme over candidates maximising total break quality subject to **max breaks/hour**,
**min gap**, **max ad-load %** (ad / (content + ad)), protected opening/closing windows and a minimum
quality threshold — weak episodes get fewer breaks, possibly none. All rules are editable.

### WHAT — brand matching with hard negative-context blocks
- Relevance = how strongly the **lead-in scene's frames** match each brand's `target_contexts`
  (the dominant on-screen activity wins; the lead-in is weighted 80 %, the first seconds after 20 %).
- A brand is **hard-blocked** if *any* of three independent layers finds one of its `negative_contexts`
  around the break: (1) scene-level tags for every scene within 150 s before → 30 s after,
  (2) a lead-in window check (t−60 s … t+12 s) at a slightly stricter threshold, (3) an **independent
  verifier** on the final pick that re-extracts frames at 2 fps over t−90 s … t+20 s and uses stricter
  thresholds still. Fail-closed; if every brand is blocked the break is dropped and pacing re-optimises.
- Consecutive repeats of the same brand are avoided when a near-equal alternative exists.

### Self-audit
Every result re-checks the hard guarantees from raw signals — zero speech at each cut, frame alignment,
min gap, max breaks, ad load, protected windows, no negative-context brand placed, verifier passed —
shown in the UI and stored in the debug JSON.

## Outputs
- **VMAP 1.0** with one `AdBreak` per break and inline **VAST 3.0** (MediaFile, Impression, start/complete
  tracking, breakStart/breakEnd) plus a `contextual-targeting` extension explaining the choice.
- **Debug JSON** — scenes with tags and evidence, every candidate with signals + verdicts + rejection
  reasons, per-slot brand ranking with block evidence, verifier results, pacing summary, self-audit.
- **Player** — parses the VMAP in the browser, detects the break with `requestVideoFrameCallback`, pauses,
  plays the creative, fires tracking beacons and resumes from the exact cut frame.

The catalogue references creative files that were not supplied, so Birati renders clearly-labelled
**synthetic placeholder spots** for every creative (including brands added later). Only the synthetic
brand names from the catalogue are used.

## Run it (free, offline after the first model download)
```bash
python -m venv .venv
.venv/Scripts/pip install torch --index-url https://download.pytorch.org/whl/cpu
.venv/Scripts/pip install -r requirements.txt
.venv/Scripts/python -m uvicorn app.main:app --port 7860          # web app: upload, live progress, re-runs
.venv/Scripts/python -m app.pipeline.run episode.mp4 --brands data/brands_plus_unseen.json   # headless
```
A 25-minute episode takes a few minutes on a laptop CPU (CLIP/CLAP embeddings ≈ 100 s, the rest seconds).
The public demo is a static export (`scripts/export_static.py`) of the sample episodes, with the default
catalogue and the default + unseen "Brand I" catalogue.

## No hard-coding
Nothing in the code references a sample video, timestamp or brand. Sample results are cached outputs of
this pipeline (see `generated_at`, `engine`, `models` and timings in each debug JSON).

## Repo layout
```
app/pipeline/local_models.py  CLIP + CLAP loading, streamed frame/audio embedding, prompt ensembling
app/pipeline/local_engine.py  B–F local engine: scenes, tags, cut judge, brand match, dense verifier
app/pipeline/signals.py       camera cuts (scdet), Silero VAD, loudness
app/pipeline/breaks.py        candidate generation + snapping to silent camera cuts, where-score
app/pipeline/brands.py        per-slot ranking, deterministic blocks, creative choice
app/pipeline/pacing.py        exact DP break selection under pacing rules
app/pipeline/manifest.py      VMAP 1.0 / VAST 3.0 writer
app/pipeline/run.py           orchestrator + CLI + self-audit
app/pipeline/understand.py, gemini.py   optional cloud engine (BIRATI_ENGINE=gemini)
app/main.py                   FastAPI: jobs, uploads, Drive-link ingest, re-runs, downloads
scripts/calibrate_local.py    teacher→student calibration + leave-one-episode-out report
scripts/export_static.py      static site export for free hosting
web/                          demo UI (vanilla JS)
```
