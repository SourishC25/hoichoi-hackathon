# Birati — context-aware ad breaks for Bengali drama

**Birati** (Bengali for *pause*) turns a long-form Bengali episode into a safe, ready-to-serve ad plan:
**where** to pause without cutting anyone mid-sentence, **whether** a break is allowed under the pacing
rules, and **which** advertiser fits each moment — never next to a topic that advertiser forbids.

| | |
|---|---|
| **Live app** | https://hoichoi-hackathon-production.up.railway.app |
| **Demo video** | https://drive.google.com/file/d/1iafRTATNVFoolyt8TfDVXlFrnBr6JD9v/view |
| **Static mirror** | https://sourish25-birati.static.hf.space (sample episodes only) |

*hoichoi Hackathon '26 · Problem 1 — Context-Aware Video Segmentation & Intelligent Ad Placement*

---

## What you get

- **An ad plan per episode** — each break explains itself: *why this moment*, *why this advertiser*, and
  *which advertisers were kept out and why*.
- **A playable demo** — the player pauses on the exact cut frame, plays the ad and resumes.
- **An industry-standard schedule file** — IAB **VMAP 1.0** with inline **VAST 3.0**, ready for any ad-capable
  player or ad server.
- **A full report** (JSON) — every moment considered, every score, every safety block, for audit.
- **Advertisers as data** — add a brand (where it wants to appear / must never appear) from the UI; no code changes.

## How it works

```
episode ─► 1. perceive ─► 2. understand ─► 3. where ─► 4. what ─► 5. whether ─► ad plan + VMAP + report
            shot changes    scenes, mood,    silent shot    advertiser   pacing rules,
            speech (VAD)    sensitive topics  change only    fit + 3-layer self-audit
                            (Gemini, video    + AI judges    safety block
                            + Bengali audio)  the cut
```

1. **Perceive** — frame-exact shot changes (ffmpeg `scdet`) and every moment of speech (Silero VAD,
   language-agnostic, so Bengali/English code-switching doesn't matter).
2. **Understand** — Gemini watches *and listens to* the whole episode: story scenes, the dominant activity,
   mood, and sensitive topics — including ones that are only **spoken about** (a death, an illness).
3. **Where** — a break may only land on a shot change inside a speech-free gap, so a mid-sentence cut is
   structurally impossible. The AI then re-watches each candidate with an "AD BREAK" card spliced in at the
   exact frame and judges whether the scene has really ended.
4. **What** — every advertiser is scored against the scene just before the break (dominant activity wins).
   Negative contexts are a **hard, fail-closed block** from three independent layers: scene tags, a lead-in
   review, and an adversarial verifier that looks for reasons *not* to air the ad. A block found once is never
   lifted by a later run.
5. **Whether** — an exact optimiser picks the best breaks under max breaks/hour, minimum gap and ad-load
   budget; weak or risky moments get no break at all. A self-audit then re-checks every guarantee from the
   video itself.

## Why the AI needs a system around it

- **41 % of the model's own scene boundaries fall inside someone's speech.** Used raw, that is a mid-dialogue
  cut almost half the time — Birati snaps each one to a silent shot change or rejects it.
- **Open-source vision/audio alone isn't enough.** An offline engine built on CLIP + CLAP (included,
  `BIRATI_ENGINE=local`) placed ads next to grief or violence in 3 of 8 breaks, because in Bengali drama those
  topics are *said*, not shown. The model reads the story; the system guarantees the safety.

## Architecture

```
frontend/   Next.js (App Router, TypeScript, Tailwind) — built to a static SPA
app/        FastAPI backend: REST API, job queue, and the Python pipeline
```

One container, one URL: a multi-stage Dockerfile builds the UI with Node and serves it from the Python
image (no PyTorch in the server image; speech detection runs on onnxruntime). Deployed on Railway.

## Run locally

```bash
python -m venv .venv
.venv/Scripts/pip install torch --index-url https://download.pytorch.org/whl/cpu
.venv/Scripts/pip install -r requirements.txt
echo GEMINI_API_KEY=<key from aistudio.google.com> > .env    # omit to use the offline engine
(cd frontend && npm ci && npm run build)
.venv/Scripts/python -m uvicorn app.main:app --port 7860      # http://localhost:7860
```

Headless: `python -m app.pipeline.run episode.mp4 --brands data/brands.json` → VMAP + report.

## Repository

```
app/main.py                 API: episodes, uploads (file or Drive link), jobs, re-runs, downloads
app/pipeline/run.py         orchestrator (cached stages), sticky safety verdicts, self-audit, CLI
app/pipeline/signals.py     shot changes, speech detection, loudness
app/pipeline/understand.py  whole-episode scene understanding
app/pipeline/breaks.py      candidate moments + AI cut judgement
app/pipeline/brands.py      advertiser matching, hard blocks, adversarial verifier
app/pipeline/pacing.py      break selection under pacing rules
app/pipeline/manifest.py    VMAP / VAST writer
app/pipeline/gemini.py      model client: rate limiting, free-tier model fall-back
app/pipeline/local_*.py     offline CLIP + CLAP engine
frontend/                   UI: player, decision timeline, ad plan, advertisers & rules
data/brands.json            the synthetic advertiser catalogue
data/example_brand.json     an extra advertiser used to show "add a brand"
data/work/<episode>/        cached pipeline outputs for the sample episodes
scripts/                    batch processing, calibration/evaluation, static-mirror export
```

## Notes

- **No hard-coding.** Nothing in the code references a sample episode, timestamp or brand; the sample plans
  are cached outputs of this pipeline, and any uploaded episode runs through it live.
- **Synthetic brands and creatives.** Only the catalogue's synthetic brands are used; since no ad files were
  supplied, clearly-labelled placeholder spots are generated for every creative.
- **Free tier.** The live app uses Gemini's free tier, which has a daily request limit (resets 12:30 PM IST).
  Episodes under ~15 minutes are the safest to test; the sample episodes always work.
