# Running Locally

## Fastest path: docker compose

```bash
docker compose up --build
```

Then open **http://localhost:3000**. No IdP or manual Postgres setup
required — this uses `DEV_AUTH_BYPASS` (see "How auth works locally" below)
and auto-provisions the database on first run.

What's running:
| Service | Port | What |
|---|---|---|
| `frontend` | 3000 → 8080 | React app, served by nginx |
| `backend` | 8000 | FastAPI + Whisper |
| `postgres` | 5432 | Audit log + tenant budgets |

First startup will take a few minutes — the backend downloads the Whisper
model on first load (`WHISPER_MODEL=base` by default; override with
`WHISPER_MODEL=tiny docker compose up --build` for a faster first run while
iterating).

To get real clinical analysis output (not just transcription), export an
OpenRouter API key before starting:
```bash
OPENROUTER_API_KEY=sk-... docker compose up --build
```
Without one, `/analyze` still runs end-to-end but returns empty
entities/SOAP fields — the LLM call fails gracefully rather than crashing
(see `backend/nlp/extractor.py`).

To reset the database (e.g. after changing schema files):
```bash
docker compose down -v   # -v drops the postgres volume
```

## How auth works locally

There's no real IdP wired up for local dev — standing one up just to click
through the UI is unnecessary friction. Instead, `docker-compose.yml` sets
`DEV_AUTH_BYPASS=true` on both services:

- **Backend** (`backend/auth/dependencies.py`): skips real JWT validation
  and constructs a `Principal` directly from `DEV_USER_ID` /
  `DEV_TENANT_ID` / `DEV_ROLES` env vars.
- **Frontend** (`frontend/src/auth/AuthProvider.tsx`): skips the OIDC
  redirect entirely and provides a fixed principal + placeholder token.

This is **hard-gated**: the backend refuses to even start if
`DEV_AUTH_BYPASS=true` and `ENVIRONMENT=production` are set together —
verified, not just asserted; see the test below. Every real deployment
manifest (`infra/k8s/base/backend-configmap.yaml`,
`infra/k8s/base/frontend-configmap.yaml`) pins this to `"false"`.

```bash
# Confirms the guard actually works, not just documented intent:
ENVIRONMENT=production DEV_AUTH_BYPASS=true python -c "import backend.main"
# -> RuntimeError: DEV_AUTH_BYPASS=true with ENVIRONMENT=production -- refusing to start.
```

## Running without Docker (faster iteration)

**Backend:**
```bash
# Run from the repo root (prod/), not from inside backend/ -- the app uses
# absolute imports like `backend.audio.session`, which requires `backend`
# to be an importable package with the repo root on PYTHONPATH. Same
# reason the Dockerfile's WORKDIR is /app with backend/ copied underneath
# it, not flattened.
python -m venv venv && source venv/bin/activate
pip install -r backend/requirements.txt --break-system-packages

# Point at a Postgres instance -- either the compose one:
#   docker compose up postgres
# or your own local instance with infra/local-dev/postgres-init/*.sql applied.
export DATABASE_URL="postgresql://app_runtime:dev_only_not_a_real_secret@localhost:5432/clinical_ai"
export ENVIRONMENT=development
export DEV_AUTH_BYPASS=true
export DEV_USER_ID=dev-clinician
export DEV_TENANT_ID=dev-tenant
export DEV_ROLES="clinician,reviewer"
export ALLOWED_ORIGINS="http://localhost:3000"
export OPENROUTER_API_KEY=sk-...   # optional, see note above

python -m uvicorn backend.main:app --reload --port 8000
```

**Frontend:**
```bash
cd frontend
npm install
npm start
```
`npm start` reads `public/env.js`, which already has `DEV_AUTH_BYPASS: "true"`
and points at `localhost:8000` by default — no extra setup needed.

## Testing with a real IdP instead of the bypass

Set `DEV_AUTH_BYPASS=false` (or unset it) on both services, then:
- Backend: set `OIDC_ISSUER`, `OIDC_AUDIENCE` to your IdP's values.
- Frontend: set `OIDC_AUTHORITY`, `OIDC_CLIENT_ID`, `OIDC_AUDIENCE` in
  `public/env.js` (or the container's env vars).
- Configure your IdP client to issue custom claims
  `https://clinical-ai/tenant_id` and `https://clinical-ai/roles` — both
  sides of the app expect this exact claim namespace
  (`backend/auth/dependencies.py`'s `Principal`,
  `frontend/src/auth/AuthProvider.tsx`'s `principalFromUser`).
- Register `http://localhost:3000/auth/callback` as an allowed redirect URI.

## What's not exercised by any of this yet
This gets you a running, clickable system on one machine — it does **not**
exercise the Kubernetes layer, the API Gateway, secrets management, or
multi-pod session behavior. See `docs/ARCHITECTURE.md` for what's still
outstanding before this is deployable for real.
