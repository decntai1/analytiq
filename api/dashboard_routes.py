"""
Dashboard API — self-contained APIRouter. Integration = two lines in app.py:
    from api.dashboard_routes import router as dashboard_router
    app.include_router(dashboard_router)
Page at GET /dashboard; API under /dashboard/api. Same auth/rate-limit as /upload.
"""
from __future__ import annotations

import os

import config
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel

from api import auth
from core.dashboards import BoardStore
from core.tenancy import Tenant
from core.tenant_runtime import TenantRuntime

router = APIRouter()
_store = BoardStore()
_runtime = TenantRuntime()
_ratelimit = auth.RateLimiter(config.settings.rate_limit_per_min)
_HERE = os.path.dirname(os.path.abspath(__file__))


def _scope(t: Tenant | None) -> str:
    return t.tenant_id if t else "default"


def _gate(request: Request, t: Tenant | None) -> None:
    _ratelimit.check(auth.client_key(request, t))


class NewBoard(BaseModel):
    name: str = "My dashboard"


class NewTile(BaseModel):
    board_id: str | None = None
    title: str = ""
    question: str = ""
    sql: str = ""
    spec: dict | None = None


class EditTile(BaseModel):
    title: str | None = None
    sql: str | None = None


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard_page():
    with open(os.path.join(_HERE, "static", "dashboard.html"), encoding="utf-8") as f:
        return f.read()


@router.get("/dashboard/api/boards")
def boards(request: Request, tenant: Tenant | None = Depends(auth.resolve_tenant)):
    _gate(request, tenant)
    bs = _store.list_boards(_scope(tenant))
    if not bs:
        bs = [{**_store.default_board(_scope(tenant)), "tiles": 0}]
    return {"boards": bs}


@router.post("/dashboard/api/boards")
def create_board(body: NewBoard, request: Request,
                 tenant: Tenant | None = Depends(auth.resolve_tenant)):
    _gate(request, tenant)
    return _store.create_board(_scope(tenant), body.name)


@router.delete("/dashboard/api/boards/{board_id}")
def delete_board(board_id: str, request: Request,
                 tenant: Tenant | None = Depends(auth.resolve_tenant)):
    _gate(request, tenant)
    try:
        _store.delete_board(_scope(tenant), board_id)
    except KeyError:
        raise HTTPException(404, "No such board.")
    return {"ok": True}


@router.get("/dashboard/api/boards/{board_id}/tiles")
def tiles(board_id: str, request: Request,
          tenant: Tenant | None = Depends(auth.resolve_tenant)):
    _gate(request, tenant)
    return {"tiles": _store.list_tiles(_scope(tenant), board_id)}


@router.post("/dashboard/api/tiles")
def add_tile(body: NewTile, request: Request,
             tenant: Tenant | None = Depends(auth.resolve_tenant)):
    """The PIN endpoint — the chat page posts {question, sql, spec} here."""
    _gate(request, tenant)
    try:
        t = _store.add_tile(_scope(tenant), body.board_id, body.title,
                            body.question, body.sql, body.spec)
    except KeyError:
        raise HTTPException(404, "No such board.")
    except ValueError as e:
        raise HTTPException(400, str(e))
    return t


@router.patch("/dashboard/api/tiles/{tile_id}")
def edit_tile(tile_id: str, body: EditTile, request: Request,
              tenant: Tenant | None = Depends(auth.resolve_tenant)):
    _gate(request, tenant)
    try:
        return _store.update_tile(_scope(tenant), tile_id, body.title, body.sql)
    except KeyError:
        raise HTTPException(404, "No such tile.")


@router.delete("/dashboard/api/tiles/{tile_id}")
def delete_tile(tile_id: str, request: Request,
                tenant: Tenant | None = Depends(auth.resolve_tenant)):
    _gate(request, tenant)
    try:
        _store.delete_tile(_scope(tenant), tile_id)
    except KeyError:
        raise HTTPException(404, "No such tile.")
    return {"ok": True}


@router.post("/dashboard/api/tiles/{tile_id}/refresh")
def refresh_tile(tile_id: str, request: Request,
                 tenant: Tenant | None = Depends(auth.resolve_tenant)):
    _gate(request, tenant)
    try:
        return _store.refresh_tile(_scope(tenant), tile_id, _runtime.get(tenant))
    except KeyError:
        raise HTTPException(404, "No such tile.")


@router.get("/dashboard/api/boards/{board_id}/export.pptx")
def export_board(board_id: str, request: Request,
                 tenant: Tenant | None = Depends(auth.resolve_tenant)):
    _gate(request, tenant)
    try:
        data = _store.board_to_deck(_scope(tenant), board_id, _runtime.get(tenant))
    except KeyError:
        raise HTTPException(404, "No such board.")
    except Exception:
        raise HTTPException(503, "Deck export needs python-pptx + vl-convert-python.")
    return Response(content=data,
                    media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                    headers={"content-disposition": "attachment; filename=dashboard.pptx"})
