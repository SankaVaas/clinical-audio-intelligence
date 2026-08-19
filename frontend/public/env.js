// Local-development default. `npm start` serves files under public/
// directly with no envsubst step, so this file must exist with sane
// dev-mode defaults. In the container, docker-entrypoint.sh overwrites
// this exact file at startup from env.template.js + real environment
// variables -- see frontend/Dockerfile.
window.__RUNTIME_CONFIG__ = {
  API_BASE: "http://localhost:8000",
  WS_BASE: "ws://localhost:8000",
  OIDC_AUTHORITY: "https://auth.example.com/",
  OIDC_CLIENT_ID: "clinical-ai-frontend-dev",
  OIDC_AUDIENCE: "clinical-ai-api",
};
