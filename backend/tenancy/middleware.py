"""
Tenant context resolution and enforcement.

Tenant ID comes from the validated JWT (backend/auth/dependencies.py), never
from a client-supplied header or query param -- trusting client input for
tenant scoping is the single most common multi-tenant data-leak bug class.

Deliberately NOT an HTTP middleware: Starlette/FastAPI resolve `Depends()`
inside the route handling that a middleware's `call_next` wraps, so a
middleware can never see a principal that a dependency sets -- it hasn't run
yet at that point. The contextvar is set directly by the auth dependency
(get_current_principal, in backend/auth/dependencies.py) instead, which is
the actual point at which the JWT has been validated and the tenant ID is
known. Each request runs in its own asyncio Task, so contextvar values don't
leak between concurrent requests.
"""
import contextvars
from fastapi import HTTPException, status

current_tenant: contextvars.ContextVar[str] = contextvars.ContextVar("current_tenant")


def require_tenant_match(resource_tenant_id: str):
    """Call at the top of any handler that loads a resource by ID, before
    returning it -- row-level scoping in the query is necessary but a
    second explicit check here is the standard belt-and-suspenders guard
    against an IDOR (one tenant guessing/enumerating another's resource IDs)."""
    if resource_tenant_id != current_tenant.get():
        raise HTTPException(status.HTTP_404_NOT_FOUND)  # 404, not 403 -- don't confirm existence
