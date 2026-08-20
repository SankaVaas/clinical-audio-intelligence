/**
 * Reads config from window.__RUNTIME_CONFIG__, injected by env.js
 * (see public/env.template.js, public/env.js, and the Dockerfile
 * entrypoint). Not process.env.REACT_APP_* directly, because those are
 * baked in at build time -- see the comment in env.template.js for why
 * that's the wrong mechanism for a container that's meant to be deployed
 * to multiple environments from one image.
 */
declare global {
  interface Window {
    __RUNTIME_CONFIG__?: {
      API_BASE?: string;
      WS_BASE?: string;
      OIDC_AUTHORITY?: string;
      OIDC_CLIENT_ID?: string;
      OIDC_AUDIENCE?: string;
      DEV_AUTH_BYPASS?: string;
      DEV_USER_ID?: string;
      DEV_TENANT_ID?: string;
      DEV_ROLES?: string;
    };
  }
}

const runtime = typeof window !== "undefined" ? window.__RUNTIME_CONFIG__ : undefined;

// Falls back to localhost dev defaults if env.js failed to load or wasn't
// templated (e.g. a raw `${API_BASE}` left un-substituted) -- fail toward
// something obviously wrong in local dev rather than a silent prod outage.
function readVar(key: keyof NonNullable<typeof runtime>, fallback: string): string {
  const value = runtime?.[key];
  if (!value || value.startsWith("${")) return fallback;
  return value;
}

export const config = {
  apiBase: readVar("API_BASE", "http://localhost:8000"),
  wsBase: readVar("WS_BASE", "ws://localhost:8000"),
  oidcAuthority: readVar("OIDC_AUTHORITY", "https://auth.example.com/"),
  oidcClientId: readVar("OIDC_CLIENT_ID", "clinical-ai-frontend-dev"),
  oidcAudience: readVar("OIDC_AUDIENCE", "clinical-ai-api"),
  // Local-dev only -- see backend/auth/dependencies.py's DEV_AUTH_BYPASS
  // for the server-side half of this. Never set true outside local dev;
  // infra/k8s/base/*-configmap.yaml pin this to "false" for every real
  // deployment target.
  devAuthBypass: readVar("DEV_AUTH_BYPASS", "false") === "true",
  devUserId: readVar("DEV_USER_ID", "dev-clinician"),
  devTenantId: readVar("DEV_TENANT_ID", "dev-tenant"),
  devRoles: readVar("DEV_ROLES", "clinician,reviewer"),
};
