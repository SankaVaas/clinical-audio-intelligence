// Rendered from this template by the container entrypoint (envsubst) at
// STARTUP, not by webpack at BUILD time. This is what lets one Docker
// image be deployed to dev/staging/prod without a rebuild per
// environment -- CRA's normal REACT_APP_* env vars are baked into the JS
// bundle at `npm run build` time, which would otherwise force a
// per-environment image.
window.__RUNTIME_CONFIG__ = {
  API_BASE: "${API_BASE}",
  WS_BASE: "${WS_BASE}",
  OIDC_AUTHORITY: "${OIDC_AUTHORITY}",
  OIDC_CLIENT_ID: "${OIDC_CLIENT_ID}",
  OIDC_AUDIENCE: "${OIDC_AUDIENCE}",
};
