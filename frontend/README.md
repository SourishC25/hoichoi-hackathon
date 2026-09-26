# Birati — frontend

Next.js (App Router, TypeScript, Tailwind) single-page app, built as a static export and served by the
FastAPI backend in `../app` (one container, one URL). The same build also runs as a static mirror.

```bash
npm ci
npm run build        # → out/, picked up automatically by the backend
```

- `lib/api.ts` — typed API client; `/runtime.json` tells the UI whether it is on the live backend or the static mirror
- `lib/plain.ts` — turns backend scores and logs into plain-language explanations
- `components/Player.tsx` — reads the VMAP, cuts to the ad on the exact frame and resumes
- `components/Timeline.tsx`, `components/Panels.tsx`, `components/Dialogs.tsx` — decision timeline, ad plan, advertisers & rules, upload
