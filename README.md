# Birati (বিরতি) — context-aware ad breaks for Bengali drama

> hoichoi Hackathon'26 · Problem 1 — Context-Aware Video Segmentation & Intelligent Ad Placement

**Live demo:** https://sourish25-birati.static.hf.space · **Explainer video:** _<add link>_

Birati ingests a long-form Bengali episode, segments it into semantically coherent scenes, decides
**where** a break is natural, **whether** a break is warranted under pacing rules, and **what** brand
belongs in each slot — then emits an IAB **VMAP 1.0 + inline VAST 3.0** manifest, a **debug JSON** that
explains every decision, and a **player that actually cuts to the ad and resumes** on the exact frame.

## Design principle: the model makes the judgement calls, signals provide the precision

| Question | Decided by | Why |
|---|---|---|
| What is a scene? what's happening? mood? sensitive topics? | **Gemini, whole episode (video + Bengali audio)** | needs story understanding — a death that is only *talked about* is still grief |
| Is this cut natural? is dialogue continuing? has the beat landed? | **Gemini, 42 s clip with an "AD BREAK" card spliced in at the cut** | the card removes any ambiguity about where the cut sits |
| Which brand fits? which are blocked? | **Gemini, lead-in clip + scene context + catalogue as data** | dominant activity ≠ background props; generalises to unseen brands |
| Final brand-safety check | **independent adversarial Gemini call** ("find reasons NOT to air this") | fail-closed second opinion on the chosen brand |
| Exactly which frame? is anyone speaking? | ffmpeg `scdet` camera cuts + **Silero VAD** | frame-exact, language-agnostic: a mid-sentence cut is structurally impossible |
| How many breaks, where, which creative length? | exact dynamic programme | hard constraints must be guaranteed, not "usually" respected |

### Why an LLM is the core — measured, not assumed
We also built a fully offline engine on free open-weights models (**CLIP** for frames, **CLAP** for the
soundtrack, Silero VAD) with per-concept z-score standardisation against a reference bank of real drama
footage, calibrated against the LLM's labels (`scripts/calibrate_local.py`, `scripts/evaluate_local.py`).
Scoring the local engine's placements against the LLM's scene labels on the six sample episodes
(teacher-judged violation = a placed brand whose negative context the LLM tagged near the break):

| Local CLIP + CLAP setting | Breaks placed | Teacher-judged violations |
|---|---|---|
| moderate thresholds | 8 | 3 |
| looser thresholds | 12 | 5 |
| strict enough to be "safe" | 0–1 | 0 (but useless) |

(The LLM pipeline itself places 11 breaks on these episodes and passes all three independent block layers,
including the separate adversarial verifier; it is the reference here, so it is not scored against itself.)

Every local miss was **spoken** context (a death, a fight, a guest describing trauma) that no vision/audio
embedding can hear; free CPU Bengali ASR (Whisper-small, wav2vec2-bn) was not reliable on drama audio.
So the LLM is the core, and the local engine ships as an offline mode (`BIRATI_ENGINE=local`).

**Runs on the Gemini free tier.** A process-wide rate limiter, low media resolution for clip calls,
at most two verifier attempts per break, and automatic fall-through across free Flash models when one hits
its daily quota keep a new episode within free limits (~25 calls). Every stage is cached, so re-running
with a new brand catalogue re-uses the scene analysis.

## Pipeline

```
video ─► A. perception ──────► B. scenes (Gemini) ─► C. candidates ─► D. cut judge ─► E. brand match ─► F. pacing + verify ─► VMAP + debug JSON
          proxy, scdet cuts,     whole episode:        scene bounds +    Gemini on a     Gemini scores      exact DP under max/hr,
          Silero VAD, loudness,  scenes, activity,     fades, snapped    marked clip:    every brand +      min gap, ad load;
          blackdetect            mood, sensitive tags  to a silent cut   dialogue? beat? violations         adversarial verifier
```

### WHERE — no mid-dialogue cuts
1. Candidates = LLM scene boundaries (snapped to real camera cuts) + fades to black.
2. Each is snapped to a **frame-exact camera cut** within ±6 s inside a **speech-free gap ≥ 0.8 s** with no
   speech 0.45 s before / 0.35 s after (Silero VAD). No such cut → rejected.
3. Gemini re-watches 30 s before → 12 s after with an **"AD BREAK" card spliced into the video at the cut**
   and answers as a broadcast editor (last/first line in Bengali, dialogue continuing, same sequence
   continuing, music carrying over, beat complete, jarring, suspense hook, anchored 0–1 rubric).

### WHETHER — pacing
Exact DP maximising total break quality subject to **max breaks/hour**, **min gap**, **max ad-load %**
(ad / (content + ad)), protected opening/closing windows and a minimum quality threshold — weak episodes
get fewer breaks, possibly none. All rules are editable.

### WHAT — brand matching with hard negative-context blocks
- The catalogue is **data**: category, target and negative contexts are given to the model at runtime; the
  sensitive-topic vocabulary for the scene pass is built from it too. **A 9th unseen brand works with zero
  code changes** (the demo includes a default + "Brand I" (tea) run for comparison).
- A brand is **hard-blocked** if *any* of three independent layers flags one of its negative contexts
  around the break (150 s before → 30 s after): (1) scene tags, (2) the lead-in clip review, (3) an
  adversarial verifier on the final pick. Errors fail closed. If every brand is blocked the break is dropped
  and pacing re-optimises.
- Among safe brands, the lead-in's **dominant activity** drives relevance; back-to-back repeats of a brand
  are avoided when a near-equal alternative exists.

### Self-audit
Every result re-checks the hard guarantees from raw signals — zero speech at each cut, frame alignment,
min gap, max breaks, ad load, protected windows, no negative-context brand, verifier passed — shown in the
UI and stored in the debug JSON. All six sample episodes pass every check.

## Outputs
- **VMAP 1.0** with one `AdBreak` per break and inline **VAST 3.0** (MediaFile, Impression, start/complete
  tracking, breakStart/breakEnd) plus a `contextual-targeting` extension explaining the choice.
- **Debug JSON** — scenes, every candidate with signals + verdicts + rejection reasons, per-slot brand
  ranking with block evidence, verifier results, pacing summary, self-audit.
- **Player** — parses the VMAP in the browser, detects the break (requestVideoFrameCallback + 40 ms poll),
  pauses, plays the creative, fires tracking beacons and resumes from the exact cut frame.

The catalogue references creative files that were not supplied, so Birati renders clearly-labelled
**synthetic placeholder spots** for every creative (including brands added later). Only the synthetic brand
names from the catalogue are used.

## Run it
The public demo is a free static export of the processed sample episodes. To process your own episodes
(upload, Google-Drive link, live progress, catalogue/pacing re-runs):
```bash
python -m venv .venv
.venv/Scripts/pip install torch --index-url https://download.pytorch.org/whl/cpu
.venv/Scripts/pip install -r requirements.txt
echo GEMINI_API_KEY=<free key from aistudio.google.com> > .env      # omit to use the offline local engine
.venv/Scripts/python -m uvicorn app.main:app --port 7860             # web app on http://localhost:7860
.venv/Scripts/python -m app.pipeline.run episode.mp4 --brands data/brands_plus_unseen.json   # headless
```

## No hard-coding
Nothing in the code references a sample video, timestamp or brand. The sample results are cached outputs of
this pipeline (see `generated_at`, `engine`, `models` and timings in each debug JSON).

## Repo layout
```
app/pipeline/run.py           orchestrator (cached stages, engine switch), self-audit, CLI
app/pipeline/signals.py       camera cuts (scdet), Silero VAD, loudness
app/pipeline/understand.py    B · Gemini whole-episode scene segmentation + sensitivity tagging
app/pipeline/breaks.py        C/D · candidate snapping + marked-clip cut judgement + where-score
app/pipeline/brands.py        E · catalogue-driven matching, hard blocks, adversarial verifier
app/pipeline/gemini.py        free-tier client: rate limiter, model pool fall-through, JSON schema output
app/pipeline/pacing.py        exact DP break selection under pacing rules
app/pipeline/manifest.py      VMAP 1.0 / VAST 3.0 writer
app/pipeline/ads.py           synthetic creative renderer
app/pipeline/local_*.py       offline CLIP + CLAP engine (BIRATI_ENGINE=local)
app/main.py                   FastAPI: jobs, uploads, Drive-link ingest, re-runs, downloads
scripts/                      batch processing, calibration/evaluation, static export + deploy
web/                          demo UI (vanilla JS; same UI serves live and static modes)
```
