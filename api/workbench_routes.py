"""
Workbench API — self-contained APIRouter. Integration = two lines in app.py:
    from api.workbench_routes import router as workbench_router
    app.include_router(workbench_router)
Serves the standalone page at GET /workbench and the API under /workbench/api.
Same auth + rate-limit conventions as /upload; sessions are tenant-scoped.
"""
from __future__ import annotations

import os

import config
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

from api import auth
from core.tenancy import Tenant
from core.tenant_runtime import TenantRuntime
from core.workbench import SessionStore

router = APIRouter()
_store = SessionStore()
_runtime = TenantRuntime()
_ratelimit = auth.RateLimiter(config.settings.rate_limit_per_min)
_HERE = os.path.dirname(os.path.abspath(__file__))


def _scope(tenant: Tenant | None) -> str:
    return tenant.tenant_id if tenant else "default"


def _gate(request: Request, tenant: Tenant | None) -> None:
    _ratelimit.check(auth.client_key(request, tenant))


class CreateSession(BaseModel):
    view: str


class OpsBody(BaseModel):
    ops: list[dict]


class ProposeBody(BaseModel):
    instruction: str = ""
    model: str | None = None


@router.get("/workbench", response_class=HTMLResponse)
def workbench_page():
    with open(os.path.join(_HERE, "static", "workbench.html"), encoding="utf-8") as f:
        return f.read()


@router.get("/workbench/api/sessions")
def list_sessions(request: Request, tenant: Tenant | None = Depends(auth.resolve_tenant)):
    _gate(request, tenant)
    return {"sessions": _store.list(_scope(tenant))}


@router.post("/workbench/api/sessions")
def create_session(body: CreateSession, request: Request,
                   tenant: Tenant | None = Depends(auth.resolve_tenant)):
    _gate(request, tenant)
    ctx = _runtime.get(tenant)
    if body.view not in ctx.connector.schema_by_table():
        raise HTTPException(404, f"No such table {body.view!r}.")
    try:
        ses = _store.create_from_view(_scope(tenant), body.view, ctx)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"sid": ses.sid, "source_view": body.view, "rows": ses.row_count(),
            "source_file": ses.meta.get("source_file"),
            "source_sha256": ses.meta.get("source_sha256")}


def _get(tenant: Tenant | None, sid: str):
    try:
        return _store.get(_scope(tenant), sid)
    except (KeyError, ValueError):
        raise HTTPException(404, "No such workbench session.")


@router.get("/workbench/api/sessions/{sid}/profile")
def profile(sid: str, request: Request, tenant: Tenant | None = Depends(auth.resolve_tenant)):
    _gate(request, tenant)
    ses = _get(tenant, sid)
    return {"profile": ses.profile(), "recipe": ses.meta.get("recipe", [])}


@router.post("/workbench/api/sessions/{sid}/propose")
def propose(sid: str, body: ProposeBody, request: Request,
            tenant: Tenant | None = Depends(auth.resolve_tenant)):
    _gate(request, tenant)
    return _get(tenant, sid).propose(body.instruction, body.model)


@router.post("/workbench/api/sessions/{sid}/preview")
def preview(sid: str, body: OpsBody, request: Request,
            tenant: Tenant | None = Depends(auth.resolve_tenant)):
    _gate(request, tenant)
    return _get(tenant, sid).preview(body.ops)


@router.post("/workbench/api/sessions/{sid}/apply")
def apply(sid: str, body: OpsBody, request: Request,
          tenant: Tenant | None = Depends(auth.resolve_tenant)):
    _gate(request, tenant)
    return _get(tenant, sid).apply(body.ops)


@router.post("/workbench/api/sessions/{sid}/reset")
def reset(sid: str, request: Request, tenant: Tenant | None = Depends(auth.resolve_tenant)):
    _gate(request, tenant)
    return _get(tenant, sid).reset()


@router.get("/workbench/api/sessions/{sid}/download")
def download(sid: str, request: Request, tenant: Tenant | None = Depends(auth.resolve_tenant)):
    _gate(request, tenant)
    ses = _get(tenant, sid)
    path = ses.export_csv()
    name = (ses.meta.get("source_view") or "cleaned") + "_cleaned.csv"
    return FileResponse(path, media_type="text/csv", filename=name)


@router.delete("/workbench/api/sessions/{sid}")
def delete(sid: str, request: Request, tenant: Tenant | None = Depends(auth.resolve_tenant)):
    _gate(request, tenant)
    _get(tenant, sid)  # 404 if unknown
    _store.delete(_scope(tenant), sid)
    return {"ok": True}


class SaveRecipe(BaseModel):
    sid: str
    name: str = "My recipe"


class ApplyRecipe(BaseModel):
    recipe_id: str


@router.get("/workbench/api/recipes")
def recipes(request: Request, tenant: Tenant | None = Depends(auth.resolve_tenant)):
    _gate(request, tenant)
    return {"recipes": _store.list_recipes(_scope(tenant))}


@router.post("/workbench/api/recipes")
def save_recipe(body: SaveRecipe, request: Request,
                tenant: Tenant | None = Depends(auth.resolve_tenant)):
    _gate(request, tenant)
    try:
        return _store.save_recipe(_scope(tenant), body.sid, body.name)
    except KeyError:
        raise HTTPException(404, "No such session.")
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/workbench/api/sessions/{sid}/apply_recipe")
def apply_recipe(sid: str, body: ApplyRecipe, request: Request,
                 tenant: Tenant | None = Depends(auth.resolve_tenant)):
    _gate(request, tenant)
    try:
        return _store.apply_recipe(_scope(tenant), sid, body.recipe_id)
    except KeyError:
        raise HTTPException(404, "No such session or recipe.")
