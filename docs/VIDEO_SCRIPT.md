# Birati — 5-minute explainer video script

Record the screen with **Windows + Alt + R** (Xbox Game Bar) or OBS, with your mic on.
Speak naturally; the lines below are a guide, not something to read word for word.
Keep the browser at full screen with the live demo link open. Target: **4:30–4:50**.

---

## 0:00 – 0:30 · The problem (show the home page)
> "Hi, I'm [your name]. For hoichoi's ad-supported tier, every mid-roll has three decisions:
> **where** to cut without interrupting a sentence, **whether** a break is warranted at all under pacing
> rules, and **what** brand fits — without ever putting a food ad after a funeral.
> I built **Birati** — Bengali for 'pause' — an AI-native system that makes all three decisions."

## 0:30 – 1:20 · How it works (click "How it works", then close it)
> "The design principle: **the LLM makes the judgement calls, deterministic signals provide the
> precision**.
> First, Gemini watches and *listens to* the entire episode — Bengali dialogue included — and groups
> the camera shots into semantically coherent scenes: what's happening, the dominant activity, the mood,
> and every sensitive topic, even ones that are only *talked about*.
> In parallel, frame-exact camera cuts and a language-agnostic voice-activity model tell us exactly when
> someone is speaking. A break can only land on a real camera cut inside a speech-free gap — so a
> mid-sentence cut is structurally impossible, not just unlikely."

## 1:20 – 2:30 · WHERE + the player (open *mohanagar* or *money_honey*)
- Point at the **timeline**: "scenes on top — red ones contain something a brand has blocked; blue is
  speech; green dots are the breaks it chose, amber were good but lost to pacing, red were rejected."
- Hover a **red candidate**: "this one was rejected — every nearby cut overlaps speech."
- Click **"Jump to 6 s before a break"** and let it play:
> "Watch — the scene ends, the dialogue has finished… and it cuts to the ad. The player is reading the
> standard **VMAP** manifest, cutting on the exact frame, firing VAST tracking beacons, and when the ad
> ends it resumes from the exact cut frame."
- Let the ad play ~5 s, then skip ahead to show the resume.

## 2:30 – 3:20 · WHAT + safety (scroll to the break cards)
> "For each slot, Gemini re-watches a clip with an 'AD BREAK' card spliced in at the cut, so it knows
> exactly where the ad sits. It scores every brand — the dominant activity wins — here the lead-in is
> people eating at a restaurant, so the food brand wins…"
- Open **"Full brand ranking for this slot"**:
> "…and negative contexts are a **hard block from three independent layers**: the episode-level
> scene tags, the lead-in clip review, and a separate adversarial verifier that is told to look for
> reasons *not* to air the ad. Any doubt fails closed. Here the skincare brand is blocked because its
> advertiser excluded 'eating'."
- Point at the **Self-audit** card: "and every hard rule is re-checked from raw signals — zero speech at
  every cut, pacing and ad-load respected, no negative-context violations."

## 3:20 – 3:50 · Generalises to an unseen brand (Brands & pacing tab)
- Click **"+ Add an unseen 9th brand"** → **Show run with this catalogue**.
> "The catalogue is data, not code. Here's a ninth brand — a tea brand — added with zero code changes;
> it's scored in every slot and hard-blocked wherever its negative contexts appear."

## 3:50 – 4:20 · Live processing (on your laptop: http://localhost:7860)
- Start the local server beforehand (`.venv\Scripts\python -m uvicorn app.main:app --port 7860`).
- Upload a short clip (5–8 min keeps it within the free Gemini quota) and show the live progress log:
> "Any episode can be processed live — upload a file or paste a Google-Drive link. It runs on the free tier
> of Gemini, with rate-limiting and automatic fall-back between free models."
- Show **VMAP ↓** and **Debug JSON ↓**: "a standard VMAP any player can consume, and a debug JSON that
  explains every single decision."

## 4:20 – 4:40 · Why an LLM is the core (show the README table)
> "I also built a fully offline engine on open-source CLIP and CLAP models and measured it against the
> LLM: it placed ads next to grief or violence three times out of eight, because in these dramas those
> contexts are *spoken*, not shown. That's why the LLM is the core — and the offline engine ships as a
> fallback."

## 4:40 – 4:55 · Close
> "Birati: Gemini for understanding, signals for precision, hard guarantees for safety.
> The code is on GitHub and the demo is live. Thank you!"

---

### Checklist before recording
- [ ] https://sourish25-birati.static.hf.space loads and the sample episodes appear
- [ ] Local server running for the live-processing segment; have a 5–8 min clip ready
- [ ] Play one break end to end once beforehand (so the video is cached)
- [ ] Browser zoom ~90% so the timeline and cards fit
- [ ] Close other tabs / notifications
