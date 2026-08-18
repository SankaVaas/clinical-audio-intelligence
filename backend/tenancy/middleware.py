"""
Tenant context resolution and enforcement.

Tenant ID comes from the validated JWT (backend/auth/dependencies.py), never
from a client-supplied header or query param -- trusting client input for
tenant scoping is the single most common multi-tenant data-leak bug class.
"""
import contextvars
from fastapi import Request, HTTPException, status

current_tenant: contextvars.ContextVar[str] = contextvars.ContextVar("current_tenant")


async def tenant_context_middleware(request: Request, call_next):
    principal = getattr(request.state, "principal", None)  # set by auth dependency upstream
    if principal is None and request.url.path not in ("/health", "/metrics"):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED)

    token = None
    if principal:
        token = current_tenant.set(principal.tenant_id)
    try:
        response = await call_next(request)
    finally:
        if token:
            current_tenant.reset(token)
    return response


def require_tenant_match(resource_tenant_id: str):
    """Call at the top of any handler that loads a resource by ID, before
    returning it -- row-level scoping in the query is necessary but a
    second explicit check here is the standard belt-and-suspenders guard
    against an IDOR (one tenant guessing/enumerating another's resource IDs)."""
    if resource_tenant_id != current_tenant.get():
        raise HTTPException(status.HTTP_404_NOT_FOUND)  # 404, not 403 -- don't confirm existence
