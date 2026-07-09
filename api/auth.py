"""
Auth + safety middleware helpers.

- resolve_tenant(): in multi-tenant mode, require a valid API key (Authorization:
  Bearer <key> or X-API-Key) and return the Tenant; in single-tenant mode return None
  (the implicit default tenant) with no auth.
- require_admin(): gate tenant-management endpoints behind ADMIN_TOKEN.
- RateLimiter: simple in-memory sliding-window per key. For multi-process/scale, swap
  for Redis — same check() interface.
"""
from __future__ import annotations

import time
from collections import defaultdict, deque

from fastapi import Header, HTTPException, Request

import config
from core.tenancy import Tenant, TenantStore

# single shared store (created lazily so single-tenant mode never touches disk)
_store: TenantStore | None = None


def store() -> TenantStore:
    global _store
    if _store is None:
        _store = TenantStore()
    return _store


def _extract_key(authorization: str | None, x_api_key: str | None) -> str:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return (x_api_key or "").strip()


_accounts = None


def accounts():
    global _accounts
    if _accounts is None:
        from core.accounts import AccountStore
        _accounts = AccountStore()
    return _accounts


def resolve_user(request: Request):
    """The logged-in User from the session cookie, or None."""
    return accounts().user_by_session(request.cookies.get("aq_session", ""))


def resolve_tenant(
    request: Request,
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None),
) -> Tenant | None:
    """Returns the authenticated Tenant (multi-tenant) or None (single-tenant).
    Credentials accepted, in order: user session cookie -> tenant API key."""
    if not config.settings.multi_tenant:
        return None
    user = resolve_user(request)
    if user:
        tenant = store().by_id(user.tenant_id)
        if tenant:
            return tenant
        raise HTTPException(status_code=401, detail="Your workspace no longer exists.")
    key = _extract_key(authorization, x_api_key)
    if not key:
        raise HTTPException(status_code=401, detail="Sign in or provide an API key.")
    tenant = store().by_key(key)
    if not tenant:
        raise HTTPException(status_code=401, detail="Invalid API key.")
    return tenant


def require_admin(x_admin_token: str | None = Header(default=None)) -> None:
    expected = config.settings.admin_token
    if not expected:
        raise HTTPException(status_code=403, detail="Admin API disabled (no ADMIN_TOKEN set).")
    if (x_admin_token or "") != expected:
        raise HTTPException(status_code=403, detail="Bad admin token.")


class RateLimiter:
    def __init__(self, per_min: int) -> None:
        self.per_min = per_min
        self._hits: dict[str, deque] = defaultdict(deque)

    def check(self, key: str) -> None:
        if self.per_min <= 0:
            return
        now = time.time()
        q = self._hits[key]
        while q and now - q[0] > 60:
            q.popleft()
        if len(q) >= self.per_min:
            raise HTTPException(status_code=429, detail="Rate limit exceeded.")
        q.append(now)


def client_key(request: Request, tenant: Tenant | None) -> str:
    if tenant:
        return f"t:{tenant.tenant_id}"
    return f"ip:{request.client.host if request.client else 'unknown'}"
