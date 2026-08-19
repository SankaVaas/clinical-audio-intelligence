# Frontend — Production Notes

## What changed from the original build
The original frontend assumed a server-owned microphone and a single
global backend session (`POST /session/start`, one shared `WS /ws`). Neither
exists anymore on the backend. This layer replaces:

- Server-side audio capture → **client-side capture**, streamed out.
- No auth → **OIDC login** (`src/auth/AuthProvider.tsx`), matching the
  backend's JWT validation exactly (same custom claim namespace for
  `tenant_id` / `roles`).
- A single global session → **one session per recording**, created by the
  server on WebSocket connect and referenced by `session_id` thereafter.
- Build-time config → **runtime config injection**, so one Docker image
  works across dev/staging/prod (see below).

## Audio capture
`src/audio/AudioStreamer.ts` + `public/audio-processor.js`:
`getUserMedia` → `AudioWorkletNode` → 16-bit PCM at 16kHz, streamed to the
backend as binary WebSocket frames. The worklet does nearest-neighbor
resampling from the browser's native rate (typically 44.1/48kHz) down to
16kHz — adequate for speech, not a production-grade resampler; swap in a
proper polyphase/sinc implementation if transcription accuracy at the
margins matters more than the added complexity.

## Auth flow
`src/auth/AuthProvider.tsx` uses `oidc-client-ts` for a standard
Authorization Code flow against the org's IdP:
1. `login()` redirects to the IdP.
2. IdP redirects back to `/auth/callback` with an auth code.
3. `signinRedirectCallback()` exchanges it for tokens; the access token is
   what's sent as the backend's bearer token and as the WebSocket's
   first-message auth payload.
4. `automaticSilentRenew: true` — works via refresh token if the IdP issues
   one for SPA clients; otherwise falls through to requiring a fresh login
   when the token expires, rather than retrying indefinitely.

Token storage is `sessionStorage` (cleared when the tab closes) — a
standard SPA trade-off, not full in-memory-only storage, since true
in-memory storage breaks silent renewal across a page reload.

## WebSocket protocol (`WS /ws/audio`)
1. Client opens the socket, sends `{"type": "auth", "token": "<JWT>"}` as
   the first message — browsers cannot set an `Authorization` header on a
   WS handshake, so first-message auth is the standard workaround.
2. Server replies `{"type": "session_created", "session_id": "..."}`.
3. Client streams raw PCM binary frames.
4. Server pushes `{"type": "transcript_chunk", ...}` as segments transcribe.
5. Client sends `{"type": "stop"}` or disconnects to end the session.

Close codes `4401` (auth failure) and `4403` (role check failure) are
handled explicitly in `App.tsx` and surfaced to the user, rather than
presenting as a generic connection drop.

## Runtime configuration — read this before deploying
Create React App bakes `REACT_APP_*` variables into the JS bundle at
`npm run build` time. Left as-is, that would require a separate Docker
image per environment just to point at a different API/OIDC URL, which
breaks a "build once, promote the same image" CI/CD model.

Fixed via runtime injection instead:
- `public/env.template.js` — a template with `${VAR}` placeholders.
- `frontend/docker-entrypoint.sh` — runs `envsubst` against real container
  environment variables at **container startup**, writing the result to
  `env.js`, then execs nginx.
- `index.html` loads `env.js` before the app bundle; `src/config.ts` reads
  from `window.__RUNTIME_CONFIG__`.
- `public/env.js` (committed, with dev defaults) is what `npm start` serves
  directly for local development, since CRA's dev server has no envsubst
  step. The container's copy is overwritten at startup, so this file's
  presence in the repo is purely for local dev.

Because the entrypoint needs to *write* `env.js` at startup, but the
container's root filesystem is otherwise read-only
(`infra/k8s/base/frontend.yaml`), an initContainer seeds a writable
`emptyDir` copy of the built static assets rather than relaxing
`readOnlyRootFilesystem` on the main container.

Required environment variables at deploy time (see
`infra/k8s/base/frontend-configmap.yaml`): `API_BASE`, `WS_BASE`,
`OIDC_AUTHORITY`, `OIDC_CLIENT_ID`, `OIDC_AUDIENCE`.

## Local development
```bash
npm install
npm start   # uses public/env.js dev defaults (localhost:8000)
```
Requires a real OIDC test client if you want the login flow to work
end-to-end locally — point `public/env.js` at a dev tenant on the org's IdP,
or a local IdP emulator, rather than a hardcoded backend bypass.

## Known gaps, not addressed in this pass
- No `/auth/callback` route handling beyond the check in `AuthProvider` —
  this is a single-page app with no router; if routing is introduced later,
  make sure `/auth/callback` still resolves to the same component tree.
- No retry/backoff on WebSocket disconnect — a dropped connection mid-session
  ends the session; the user has to press RECORD again. Reasonable for v1,
  worth revisiting if network reliability in the field becomes an issue.
- No resampling quality upgrade (see Audio capture above).
