"""
JWT-based auth. Tokens are issued by the org's IdP (Auth0/Okta/Cognito, OIDC)
and validated here via JWKS -- the backend never issues or stores credentials.
"""
import os
import time
import logging
from functools import lru_cache

import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError

from backend.tenancy.middleware import current_tenant

bearer_scheme = HTTPBearer()

# --------------------------------------------------------------------------
# Local-dev auth bypass. Lets the app run without a real IdP for local
# development / docker-compose -- setting up a full OIDC provider just to
# click through the UI is friction nobody should have to pay for local dev.
#
# Hard-gated: refuses to even start if somehow enabled with
# ENVIRONMENT=production, rather than silently ignoring the misconfiguration.
# This check runs at import time, not on first request, so a misconfigured
# deploy fails at pod startup (visible immediately in rollout status) rather
# than passing health checks and only failing when someone notices auth is
# wide open.
# --------------------------------------------------------------------------
DEV_AUTH_BYPASS = os.getenv("DEV_AUTH_BYPASS", "false").lower() == "true"
ENVIRONMENT = os.getenv("ENVIRONMENT", "production")

if DEV_AUTH_BYPASS and ENVIRONMENT == "production":
    raise RuntimeError(
        "DEV_AUTH_BYPASS=true with ENVIRONMENT=production -- refusing to start. "
        "This combination would disable authentication in production."
    )

if DEV_AUTH_BYPASS:
    logging.getLogger(__name__).warning(
        "DEV_AUTH_BYPASS is enabled -- authentication is DISABLED. "
        "This build must never be deployed outside local development."
    )
    OIDC_ISSUER = os.getenv("OIDC_ISSUER", "")
    OIDC_AUDIENCE = os.getenv("OIDC_AUDIENCE", "")
else:
    OIDC_ISSUER = os.environ["OIDC_ISSUER"]        # e.g. https://auth.example.com/
    OIDC_AUDIENCE = os.environ["OIDC_AUDIENCE"]    # e.g. clinical-ai-api


@lru_cache(maxsize=1)
def _jwks():
    resp = httpx.get(f"{OIDC_ISSUER}.well-known/jwks.json", timeout=5)
    resp.raise_for_status()
    return resp.json()


class Principal:
    def __init__(self, claims: dict):
        self.user_id: str = claims["sub"]
        self.tenant_id: str = claims["https://clinical-ai/tenant_id"]
        self.roles: list[str] = claims.get("https://clinical-ai/roles", [])
        self.claims = claims

    def require_role(self, role: str):
        if role not in self.roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"requires role: {role}")


async def decode_token(token: str) -> Principal:
    """Core validation logic, usable outside the HTTP Depends() flow --
    specifically for WebSocket auth, since a browser cannot set an
    Authorization header on a WS handshake. get_current_principal (below)
    wraps this for regular HTTP routes; WebSocket routes call this directly
    against a token sent as the connection's first message."""
    if DEV_AUTH_BYPASS:
        # Any non-empty token is accepted; identity comes from env vars,
        # not from the token contents, since there's no real IdP issuing
        # it. The frontend's dev-mode AuthProvider sends a fixed
        # placeholder token to satisfy HTTPBearer's "header must be
        # present" check -- see frontend/src/auth/AuthProvider.tsx.
        if not token:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing token")
        principal = Principal({
            "sub": os.getenv("DEV_USER_ID", "dev-clinician"),
            "https://clinical-ai/tenant_id": os.getenv("DEV_TENANT_ID", "dev-tenant"),
            "https://clinical-ai/roles": os.getenv("DEV_ROLES", "clinician,reviewer").split(","),
        })
        current_tenant.set(principal.tenant_id)
        return principal

    try:
        claims = jwt.decode(
            token,
            _jwks(),
            algorithms=["RS256"],
            audience=OIDC_AUDIENCE,
            issuer=OIDC_ISSUER,
            options={"require": ["exp", "sub", "iss", "aud"]},
        )
    except JWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid or expired token")

    if claims.get("exp", 0) < time.time():
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "token expired")

    principal = Principal(claims)

    # Set here, not in middleware: this is the earliest point the tenant ID
    # is known from a validated token. Every downstream call in this
    # request's task (audit writes, RLS-scoped queries, cost tracking) reads
    # this same contextvar rather than having tenant_id threaded through
    # every function signature by hand.
    current_tenant.set(principal.tenant_id)

    return principal


async def get_current_principal(
    creds: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> Principal:
    return await decode_token(creds.credentials)


def require_role(role: str):
    async def _dep(principal: Principal = Depends(get_current_principal)) -> Principal:
        principal.require_role(role)
        return principal
    return _dep


# Usage in main.py:
#   @app.post("/sessions/{id}/finalize")
#   async def finalize(id: str, principal: Principal = Depends(require_role("clinician"))):
#       ...
