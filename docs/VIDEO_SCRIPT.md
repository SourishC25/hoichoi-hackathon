# Birati — 5-minute demo: flow + script

**URL:** https://hoichoi-hackathon-production.up.railway.app · record with **Win + Alt + R** · target **4:45**
**Upload file ready:** `data\videos\money_honey.mp4` (22 min, not in the demo list → a genuinely live run)

> Order matters: do the *sample-brand update* **before** starting the upload — jobs run one at a time,
> so an update queued behind a 5-minute upload would make you wait on camera.

---

## 0:00 – 0:25 · Hook (home page, Feluda open)
> "Hi, I'm [your name]. On an ad-supported OTT tier every mid-roll is three decisions: **where** to pause
> without cutting someone mid-sentence, **whether** a break is allowed under the pacing rules, and **what**
> advertiser belongs there — without ever putting a food ad after a funeral. This is **Birati** — Bengali for
> 'pause' — and it makes all three decisions from the video itself."

## 0:25 – 1:00 · Safety over inventory (Feluda)
- Point at the green line: **"1 ad break placed in 26 minutes … 2 allowed by the pacing rules."**
- Point at the **timeline** → the two **red-hatched** scenes.
> "The rules allowed two breaks, it placed one. These hatched scenes are the retired judge talking about
> death sentences and his guilt — any break near them would put an advertiser next to a topic it forbids,
> so Birati chose *not* to sell that slot. Choosing nothing over a risky placement is deliberate."
- Hover a red dot on the Candidates lane: "and every rejected moment says why."

## 1:00 – 1:30 · A new advertiser, zero code (Advertisers & rules)
- Open **Advertisers & rules** → show a brand card (**Wants / Never near**).
> "Each advertiser is just data — where it wants to appear, where it must never appear."
- Click **Add a sample brand (beverages/tea)** → **Update the ad plan** → watch the sidebar job finish.
> "I've added a brand the system has never seen. No code change — it's scored in every moment of the
> episode, and kept out wherever its forbidden topics appear."

## 1:30 – 1:50 · Start the live run (Add an episode)
- **Add an episode** → drop `money_honey.mp4` → **Upload & process**.
> "Now a fresh episode, live. Watch the sidebar — it's watching the video, understanding the story,
> finding safe moments, matching advertisers and running safety checks. It takes a few minutes, so while
> it works, let me show a finished one."

## 1:50 – 3:20 · The ad plan (open Mandaar)
- **Ad plan** tab → **Safety checks — 8 of 8 passed**.
> "After deciding, it re-checks every guarantee from the video itself: nobody speaking at any cut, every cut
> on a shot change, gaps, breaks per hour, ad time, the opening and ending untouched, and no advertiser next
> to a forbidden topic."
- First break card — read the three rows:
> "**Why this moment** — the scene has ended and nobody speaks around the cut. **Why this advertiser** — the
> scene just before is *[read the activity on screen]*, which matches this brand's *[read the matched words]*.
> **Kept out here** — these brands weren't allowed, and here's the topic that blocked each one."
- If the card shows **Last words before the cut** in Bengali: "those are the actual last words before the pause."
  If it says *nobody speaking*: "and here nobody is speaking at all around the cut."
- Click **▶ Watch this break**:
> "It plays up to the cut … pauses on that exact frame … plays the ad … and resumes exactly where it left off."
- (Optional) **Show the numbers behind this decision** — one sentence: "the scores are here for anyone who wants them."

## 3:20 – 3:50 · "Isn't this just an AI prompt?"
> "Two numbers. Forty-one percent of the model's own scene boundaries fall *inside* someone's speech — used
> raw, that's a mid-sentence cut almost half the time; Birati snaps each one to a silent shot change or
> rejects it. And I built a fully open-source version with vision and audio models — it placed ads next to
> grief or violence three times in eight, because in Bengali drama those topics are *spoken*, not shown. The
> model reads the story; the system around it guarantees the safety."

## 3:50 – 4:30 · Live result + hand-off (back to Money Honey when the job says Done)
- Open the new episode → green summary line + its break cards (and play one if there's time).
- Open **Schedule file**:
> "This is the hand-off: the industry-standard ad schedule a real video player or ad server reads — when to
> pause, which ad file, and which events to report back. And **Full report** is the audit trail: every
> moment considered and why."
- *If the upload is still running:* show the sidebar steps and say "it finishes in a minute — the plan
  lands here exactly like the ones you've seen."
- *If it shows the daily-quota message:* "it's on a free AI tier and today's quota is used up; it resets
  tomorrow" — then stay on Mandaar.

## 4:30 – 4:50 · Close
> "Birati: an AI that understands the story, signals that guarantee the cut, and safety rules that can't be
> bent. The code is on GitHub and the app is live. Thank you."

---

### Before you press record
- [ ] Hard-refresh the page (Ctrl + Shift + R) and open **Feluda**
- [ ] `money_honey.mp4` ready in File Explorer
- [ ] Browser zoom ~90 %, other tabs and notifications closed
- [ ] Keep the Birati tab in front while the upload runs
