# Cadence — Web App (SaaS)

A multi-tenant web app where people sign up and turn raw footage into premium vertical
video. Next.js 16 (App Router) + Supabase (auth / Postgres / storage) + the Python
render worker that runs the tested `cadence` engine.

```
 Browser (Next.js, Tailwind)
   signup/login ─┐
   studio: upload/record · brand · Module-D customize · generate · poll · download
                 │  supabase-js (RLS-scoped)            POST /api/render (quota gate)
                 ▼                                        │
            Supabase  ◀──── auth · Postgres · Storage ───┘
   (render_jobs queue)        ▲
                 ▲            │ claim_next_render_job (FOR UPDATE SKIP LOCKED)
                 └──── Python worker ──── analyze · clean (ASR) · synthesize · render (FFmpeg)
```

## Verified
- **Backend smoke** (`worker/scripts/smoke_backend.py`): user → upload → job → worker → 1080×1920 output. ✅
- **Browser E2E** (`web/e2e/smoke.mjs`, Playwright): signup → project → upload → generate → result. ✅
- **Cross-tenant isolation** (`worker/scripts/test_rls.py`): user B cannot read/write/download user A's data. ✅ 6/6
- Server-side **monthly render quota** enforced in `/api/render` (never trusts the client).

## Run it locally (3 terminals)

**Prereqs:** Docker running, Python venv at repo root with the engine installed
(`pip install -e ./engine` + `pip install supabase faster-whisper`), Node 20+.

```bash
# 1) Backend — local Supabase (from repo root). Keys are already wired into
#    web/.env.local and worker/.env for the standard local stack.
npx supabase start

# 2) Render worker (repo root, venv active)
python worker/cadence_worker.py          # loads faster-whisper, polls the queue

# 3) Web app
cd web && npm run dev                     # http://localhost:3000
```

Open http://localhost:3000 → **Start free** → create a project → upload a reference +
record/upload a clip → **Generate**. The worker renders it and the result streams back.

Useful: Supabase Studio at http://localhost:54323 · stop with `npx supabase stop`.

## Auth notes
- **Email + password** works fully out of the box (local email confirmation is disabled).
- **Google sign-in** is wired (`auth-form.tsx` → `/auth/callback`) but needs real Google
  OAuth credentials configured under `[auth.external.google]` in `supabase/config.toml`
  (and in the Supabase dashboard when deployed).

## Deploying
- **Frontend** → Vercel (`web/`). Set `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`.
- **Supabase** → a hosted project; `supabase db push` applies `supabase/migrations`.
- **Worker** → containerize with `worker/Dockerfile` (Python + FFmpeg) and run on Fly.io /
  Render / Cloud Run / a VPS — anywhere that can run FFmpeg (not Vercel/serverless).
