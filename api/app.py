"""
FastAPI service + web UI — production hardened.

Modes:
  MULTI_TENANT=0 (on-prem): one implicit tenant, no auth. Unchanged behaviour.
  MULTI_TENANT=1 (SaaS):    per-tenant isolation + API-key auth on every data request.

Endpoints:
  GET  /            -> chat UI
  GET  /models      -> registered models
  GET  /health      -> status (no tenant data)
  POST /ask         -> answer + charts + citations + trace        [auth in MT mode]
  POST /upload      -> ingest a file, re-index (per-tenant)        [auth in MT mode]
  POST /admin/tenants -> create a tenant (returns api key)         [ADMIN_TOKEN]
  GET  /admin/tenants -> list tenants                              [ADMIN_TOKEN]

Security: CORS allowlist, per-tenant/IP rate limiting, upload size cap, admin gate.
"""
from __future__ import annotations

import os

from fastapi import Depends, FastAPI, File, Header, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import config
from config import MODEL_REGISTRY
from core.tenancy import Tenant
from core.tenant_runtime import TenantRuntime
from api import auth
from api.ingest import classify, safe_name

HERE = os.path.dirname(__file__)
s = config.settings
for d in (s.upload_dir, s.docs_dir, s.data_dir):
    os.makedirs(d, exist_ok=True)

app = FastAPI(title="Analytiq", version="1.0.0")

# CORS allowlist (empty = no cross-origin; set CORS_ORIGINS for a hosted frontend)
_origins = [o.strip() for o in s.cors_origins.split(",") if o.strip()]
if _origins:
    app.add_middleware(CORSMiddleware, allow_origins=_origins, allow_methods=["*"],
                       allow_headers=["*"], allow_credentials=True)

_runtime = TenantRuntime()
_ratelimit = auth.RateLimiter(s.rate_limit_per_min)

from api.routes_accounts import router as accounts_router
app.include_router(accounts_router)
from api.workbench_routes import router as workbench_router  # noqa: E402
app.include_router(workbench_router)
from api.dashboard_routes import router as dashboard_router  # noqa: E402
app.include_router(dashboard_router)
from api.billing_routes import router as billing_router  # noqa: E402
app.include_router(billing_router)


# --- models -----------------------------------------------------------------
class AskRequest(BaseModel):
    question: str
    model: str | None = None
    conversation_id: str | None = None


class CreateTenant(BaseModel):
    name: str
    data_source: str = "upload"
    db_url: str = ""
    default_model: str = ""
    enable_uploads: bool = True
    plan: str = "business"                 # company deals default to Business
    invite_code: str = ""                  # "" -> generate one
    llm_base_url: str = ""                 # dedicated vLLM endpoint (optional)
    llm_model_id: str = ""


# --- UI / public ------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
def landing() -> str:
    with open(os.path.join(HERE, "static", "landing.html"), encoding="utf-8") as f:
        return f.read()


@app.get("/app", response_class=HTMLResponse)
def workspace() -> str:
    with open(os.path.join(HERE, "static", "index.html"), encoding="utf-8") as f:
        return f.read()


@app.get("/login", response_class=HTMLResponse)
def login_page() -> str:
    with open(os.path.join(HERE, "static", "login.html"), encoding="utf-8") as f:
        return f.read()


@app.get("/health")
def health():
    return {"status": "ok", "deploy_mode": s.deploy_mode, "multi_tenant": s.multi_tenant,
            "data_source": s.data_source, "default_model": s.default_model}


def _runtime_reachable(base_url: str, timeout: float = 0.25) -> bool:
    """Cheap TCP probe of a local runtime endpoint (keyless models point here)."""
    import socket
    from urllib.parse import urlparse
    try:
        u = urlparse(base_url)
        host = u.hostname or "localhost"
        port = u.port or (443 if u.scheme == "https" else 80)
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception:
        return False


def _model_usable(m) -> bool:
    """True if this registry model has a working backend on THIS deploy, so the
    picker never offers a model that would fail when selected:
      - stub: eval-only, never in the UI picker
      - keyed model (cloud): its api_key_env must be set
      - keyless model (local runtime): that runtime must be reachable
    """
    if m.provider == "stub":
        return False
    if m.api_key_env:
        return bool(os.getenv(m.api_key_env))
    return _runtime_reachable(m.base_url)


def _model_dto(m) -> dict:
    return {"name": m.name, "provider": m.provider, "notes": m.notes,
            "label": m.label or m.name}


def _plan_name_for_request(request: Request) -> str:
    """Plan name of the logged-in user (multi-tenant), else 'free'."""
    user = auth.resolve_user(request)
    if not user:
        return "free"
    t = auth.store().by_id(user.tenant_id)
    return (user.plan or (t.plan if t else "free")) or "free"


@app.get("/models")
def models(request: Request):
    # single-tenant / on-prem: no accounts → all usable models (unchanged)
    if not s.multi_tenant:
        usable = [m for m in MODEL_REGISTRY.values() if _model_usable(m)]
        if not usable:
            usable = ([m for m in MODEL_REGISTRY.values() if m.name == s.default_model]
                      or list(MODEL_REGISTRY.values()))
        return {"default": s.default_model, "models": [_model_dto(m) for m in usable]}
    # multi-tenant: gate by the caller's plan (logged-out → Free set)
    plan_name = _plan_name_for_request(request)
    names = config.models_for_plan(plan_name)
    allowed = [MODEL_REGISTRY[n] for n in names
               if n in MODEL_REGISTRY and _model_usable(MODEL_REGISTRY[n])]
    if not allowed:  # never hand back an empty picker
        allowed = ([MODEL_REGISTRY[s.default_model]] if s.default_model in MODEL_REGISTRY
                   else list(MODEL_REGISTRY.values())[:1])
    default = config.default_model_for_plan(plan_name)
    if default not in {m.name for m in allowed}:
        default = allowed[0].name
    return {"default": default, "models": [_model_dto(m) for m in allowed]}


@app.get("/runtime")
def runtime():
    """Which serving backend is active (ollama demo / analytiq prod / custom)."""
    from core.runtime import active_runtime
    rt = active_runtime()
    return {"name": rt.name, "label": rt.label, "base_url": rt.base_url,
            "managed": rt.managed, "notes": rt.notes}


@app.get("/settings/inference")
def get_inference_settings():
    """Current sampling settings + UI metadata (labels, ranges, explanations)."""
    from dataclasses import asdict
    from core.inference import PARAM_META
    return {"values": asdict(config.inference), "meta": PARAM_META}


class InferenceUpdate(BaseModel):
    temperature: float | None = None
    top_p: float | None = None
    top_k: int | None = None
    max_tokens: int | None = None
    presence_penalty: float | None = None
    frequency_penalty: float | None = None
    repeat_penalty: float | None = None
    seed: int | None = None
    stop: str | None = None


@app.post("/settings/inference")
def set_inference_settings(body: InferenceUpdate,
                           tenant: Tenant | None = Depends(auth.resolve_tenant)):
    """Calibrate sampling settings live (like LM Studio / Open WebUI)."""
    from dataclasses import asdict
    updated = config.update_inference({k: v for k, v in body.model_dump().items() if v is not None})
    return {"ok": True, "values": asdict(updated)}


# --- data endpoints (auth in multi-tenant mode) -----------------------------
def _plan_for(user, tenant: Tenant | None) -> dict:
    name = (user.plan if user and user.plan else "") or (tenant.plan if tenant else "") or "free"
    return {"name": name, **config.plan_of(name)}


def _dedicated_spec(tenant: Tenant | None):
    """A company's own vLLM endpoint (Business plan): one ModelSpec built live."""
    if not (tenant and tenant.llm_base_url):
        return None
    from config import ModelSpec
    return ModelSpec(name=f"{tenant.tenant_id}-dedicated", provider="openai_compatible",
                     model_id=tenant.llm_model_id or "default",
                     base_url=tenant.llm_base_url, api_key_env="")


@app.post("/ask")
def ask(req: AskRequest, request: Request, tenant: Tenant | None = Depends(auth.resolve_tenant)):
    _ratelimit.check(auth.client_key(request, tenant))
    user = auth.resolve_user(request) if config.settings.multi_tenant else None
    plan = _plan_for(user, tenant)

    # plan-gated model choice: reject a disallowed model BEFORE charging credits
    # (server-side enforcement — hiding it in the picker is not enforcement).
    if user and req.model and req.model not in config.models_for_plan(plan["name"]):
        raise HTTPException(403, f"The {plan['label']} plan can't use the model "
                                 f"{req.model!r}. Upgrade for access to more models.")

    # credits: metered per logged-in user; API-key (programmatic) access is
    # governed by the tenant contract + rate limiter instead.
    if user:
        ok, remaining = auth.accounts().spend_credits(user.user_id, 1, plan["credits_month"])
        if not ok:
            raise HTTPException(402, f"Monthly question limit reached on the "
                                     f"{plan['label']} plan. Upgrade to continue.")
    else:
        remaining = None

    # session memory: plan-gated; Free is stateless by design.
    history = []
    conv_id = req.conversation_id
    if user and plan["memory"] and conv_id:
        owner = auth.accounts().conversation_owner(conv_id)
        if not owner or owner[1] != user.user_id:
            raise HTTPException(404, "Chat not found.")
        history = auth.accounts().history_for_model(conv_id)

    ctx = _runtime.get(tenant)
    # model resolution: explicit choice > company dedicated endpoint > tenant default
    spec_override = None
    model = req.model or None
    # logged-in user with no explicit choice → their plan's default model
    # (Free → ministral-8b, not the pricey 120B). Disallowed models already 403'd above.
    if user and not model:
        model = config.default_model_for_plan(plan["name"])
    if plan.get("dedicated_llm"):
        ded = _dedicated_spec(tenant)
        if ded and (not model or model == "dedicated"):
            spec_override, model = ded, None
    if not model and not spec_override and tenant and tenant.default_model:
        model = tenant.default_model

    result = ctx.orchestrator().ask(req.question, model_name=model,
                                    history=history, spec_override=spec_override)

    if user and conv_id:
        auth.accounts().append_message(conv_id, "user", req.question)
        auth.accounts().append_message(conv_id, "assistant", result.get("answer", ""),
                                       charts=result.get("charts", []))
    result["conversation_id"] = conv_id
    result["credits_remaining"] = remaining
    result["tier"] = plan["name"]          # NOTE: result["plan"] is the ROUTER plan (intent/arm)
    return result


class DeckRequest(BaseModel):
    request: str
    model: str | None = None


class SlideItem(BaseModel):
    title: str = ""
    answer: str = ""
    chart: dict | None = None      # neutral-rendered Vega-Lite spec (as shown in chat)
    sql: list[str] = []


class SelectionDeck(BaseModel):
    title: str = "Analytiq deck"
    items: list[SlideItem]


@app.post("/presentation/from_selection")
def presentation_from_selection(body: SelectionDeck, request: Request,
                                tenant: Tenant | None = Depends(auth.resolve_tenant)):
    """Build an editable PPTX from answers/charts the user SELECTED in chat.

    Unlike /presentation (which plans+runs a fresh analysis), this renders exactly
    what's already on screen: each selected item becomes a chart slide with its
    answer as the takeaway, plus the audit appendix with the SQL behind it.
    """
    _ratelimit.check(auth.client_key(request, tenant))
    if not body.items:
        raise HTTPException(400, "Select at least one answer or chart first.")
    user = auth.resolve_user(request) if config.settings.multi_tenant else None
    plan = _plan_for(user, tenant)
    if user and not plan.get("deck_export"):
        raise HTTPException(403, f"Deck export isn't included in the {plan['label']} plan.")
    if user:
        ok, _ = auth.accounts().spend_credits(user.user_id, config.DECK_CREDITS,
                                              plan["credits_month"])
        if not ok:
            raise HTTPException(402, "Not enough credits left this month for a deck export.")
    try:
        from viz.presentation import DeckBuilder
    except Exception:
        raise HTTPException(503, "Deck export needs the full install "
                                 "(python-pptx + vl-convert-python). See requirements.txt.")

    template = None
    if tenant:
        cand = os.path.join(s.tenants_root, tenant.tenant_id, "template.pptx")
        template = cand if os.path.exists(cand) else None
    deck = DeckBuilder(template_path=template)
    deck.title_slide(body.title, "Selected results · generated by Analytiq")
    audit: list[dict] = []
    for it in body.items:
        title = it.title or (it.answer[:60] if it.answer else "Result")
        if it.chart:
            deck.chart_slide(title, it.answer[:300], it.chart)
        else:
            deck.summary_slide(title, [b for b in it.answer.split("\n") if b][:5] or ["—"])
        if it.sql:
            audit.append({"title": title, "sql": "\n".join(it.sql)[:1200]})
    if audit:
        deck.appendix_slide(audit)
    import io as _io
    buf = _io.BytesIO()
    deck.prs.save(buf)
    data = buf.getvalue()
    from fastapi.responses import Response
    n = len(body.items) + 1 + (1 if audit else 0)
    return Response(content=data, media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                    headers={"x-deck-slides": str(n),
                             "content-disposition": "attachment; filename=analytiq-deck.pptx"})


@app.post("/presentation")
def presentation(req: DeckRequest, request: Request,
                 tenant: Tenant | None = Depends(auth.resolve_tenant)):
    """Generate an editable PPTX deck from a high-level request. Returns the file."""
    _ratelimit.check(auth.client_key(request, tenant))
    from fastapi.responses import Response
    from core.deck_planner import generate_presentation
    ctx = _runtime.get(tenant)
    model = req.model or (tenant.default_model if tenant and tenant.default_model else None)
    # per-tenant brand template, if uploaded (tenants/<id>/template.pptx)
    template = None
    if tenant:
        cand = os.path.join(s.tenants_root, tenant.tenant_id, "template.pptx")
        template = cand if os.path.exists(cand) else None
    else:
        cand = os.path.join(s.data_dir, "template.pptx")
        template = cand if os.path.exists(cand) else None
    try:
        pptx_bytes, meta = generate_presentation(req.request, ctx.orchestrator(),
                                                 model_name=model, template_path=template)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Deck generation failed: {e}")
    fname = "analytiq-deck.pptx"
    return Response(content=pptx_bytes,
                    media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                    headers={"Content-Disposition": f'attachment; filename="{fname}"',
                             "X-Deck-Slides": str(meta["slides"])})


class DeckItem(BaseModel):
    question: str = ""
    answer: str = ""
    chart: dict | None = None          # rendered Vega-Lite spec (data inline)
    title: str = ""


class DeckExport(BaseModel):
    title: str = "Analytiq report"
    items: list[DeckItem]


@app.post("/export/deck")
def export_deck(body: DeckExport, request: Request,
                tenant: Tenant | None = Depends(auth.resolve_tenant)):
    """Build an editable PPTX from the answers/charts the user SELECTED in chat.
    Charts are re-rendered deterministically from their real data (vl-convert),
    never image-generated."""
    _ratelimit.check(auth.client_key(request, tenant))
    user = auth.resolve_user(request) if config.settings.multi_tenant else None
    plan = _plan_for(user, tenant)
    if user:
        if not plan["deck_export"]:
            raise HTTPException(402, f"Deck export isn't included in the {plan['label']} plan.")
        ok, _ = auth.accounts().spend_credits(user.user_id, config.DECK_CREDITS,
                                              plan["credits_month"])
        if not ok:
            raise HTTPException(402, "Not enough credits left this month for a deck export.")
    if not body.items:
        raise HTTPException(400, "Select at least one answer to export.")

    deck: list[dict] = [{"type": "title", "title": body.title,
                         "subtitle": "Generated with Analytiq — charts from real data"}]
    appendix = []
    for it in body.items:
        if it.chart:
            deck.append({"type": "chart", "title": it.title or it.question[:70],
                         "takeaway": (it.answer or "")[:300], "chart": it.chart})
        else:
            deck.append({"type": "summary", "title": it.title or it.question[:70],
                         "bullets": [b.strip() for b in (it.answer or "").split("\n") if b.strip()][:6]})
        appendix.append({"question": it.question, "answer": (it.answer or "")[:200]})
    deck.append({"type": "appendix", "items": appendix})

    template = None
    if tenant:
        cand = os.path.join(s.tenants_root, tenant.tenant_id, "template.pptx")
        template = cand if os.path.exists(cand) else None
    try:
        from viz.presentation import build_deck
        pptx_bytes = build_deck(deck, template_path=template)
    except Exception as e:
        raise HTTPException(500, f"Deck build failed: {e}")
    from fastapi.responses import Response as RawResponse
    return RawResponse(content=pptx_bytes,
                       media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                       headers={"Content-Disposition": 'attachment; filename="analytiq-selection.pptx"'})


def _table_details(connector) -> list[dict]:
    """Per-table row count + column names — proves a table is actually queryable."""
    out = []
    for name in connector.schema_by_table().keys():
        cols, rows = [], None
        try:
            cols = list(connector.run_query(f'SELECT * FROM "{name}" LIMIT 0').columns)
        except Exception:
            pass
        try:
            qr = connector.run_query(f'SELECT COUNT(*) AS n FROM "{name}"')
            rows = qr.rows[0]["n"] if qr.rows else None
        except Exception:
            pass
        out.append({"name": name, "rows": rows, "columns": cols})
    return out


@app.get("/tables")
def tables(tenant: Tenant | None = Depends(auth.resolve_tenant)):
    ctx = _runtime.get(tenant)
    details = _table_details(ctx.connector)
    docs = list(getattr(ctx.doc_index, "documents", []) or [])
    return {"tables": [t["name"] for t in details],   # names (backward-compatible)
            "table_details": details,                  # [{name, rows, columns}] — queryable proof
            "documents": docs,                         # [{name, chunks}] — distinct files
            "document_count": len(docs),               # FIX: files, not chunks
            "docs_indexed": ctx.doc_index.count,       # chunks (backward-compatible)
            "embedding_mode": config.settings.embedding_mode}


@app.post("/upload")
async def upload(request: Request, file: UploadFile = File(...),
                 tenant: Tenant | None = Depends(auth.resolve_tenant)):
    _ratelimit.check(auth.client_key(request, tenant))
    uploads_on = s.enable_uploads if tenant is None else tenant.enable_uploads
    if not uploads_on:
        return {"ok": False, "error": "Uploads are disabled for this deployment/tenant."}
    name = safe_name(file.filename or "upload.bin")
    kind = classify(name)
    if kind == "unknown":
        return {"ok": False, "error": f"Unsupported file type: {name}."}
    data = await file.read()
    if len(data) > s.max_upload_mb * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"File exceeds {s.max_upload_mb} MB limit.")
    ctx = _runtime.get(tenant)
    if kind == "structured":
        duck = ctx.upload_duck()
        if duck is None:
            return {"ok": False, "error": "No upload data store configured for this deployment."}
        up_dir = tenant.upload_dir() if tenant else s.upload_dir
        path = os.path.join(up_dir, name)
        with open(path, "wb") as f:
            f.write(data)
        view = duck.register_file(path)
        if view is None:
            return {"ok": False, "error":
                    f"Couldn't find a data table in '{name}'. If it's a multi-sheet "
                    f"workbook, make sure at least one sheet contains a plain table "
                    f"(a header row followed by data rows)."}
        tables = getattr(duck, "last_ingest", None) or [{"view": view, "rows": None, "cols": None}]
        ctx.reindex()
        listing = ", ".join(
            f"'{t['view']}'" + (f" ({t['rows']} rows)" if t.get("rows") is not None else "")
            for t in tables)
        return {"ok": True, "kind": "structured", "table": view, "tables": tables,
                "message": f"'{name}' is now a queryable table{'s' if len(tables) != 1 else ''}: "
                           f"{listing}. Ask a question to query it."}
    else:
        docs_dir = ctx.docs_dir()
        path = os.path.join(docs_dir, name)
        with open(path, "wb") as f:
            f.write(data)
        ctx.reindex()
        note = (" Document Q&A is limited on this deployment (basic keyword search only) — "
                "upload a CSV or Excel file to query data as a table."
                if s.embedding_mode == "test" else
                " To query structured data as a table, upload a CSV or Excel file.")
        return {"ok": True, "kind": "document", "source": name,
                "message": f"'{name}' was indexed as a DOCUMENT, not a queryable table.{note}"}


# --- admin (tenant management; ADMIN_TOKEN gated) ---------------------------
@app.post("/admin/tenants")
def create_tenant(body: CreateTenant, _: None = Depends(auth.require_admin)):
    import secrets as _sec
    t = auth.store().create(
        name=body.name, data_source=body.data_source, db_url=body.db_url,
        default_model=body.default_model, enable_uploads=body.enable_uploads,
        plan=body.plan, invite_code=body.invite_code or ("join-" + _sec.token_hex(4)),
        llm_base_url=body.llm_base_url, llm_model_id=body.llm_model_id,
    )
    return {"tenant_id": t.tenant_id, "name": t.name, "api_key": t.api_key,
            "invite_code": t.invite_code, "plan": t.plan,
            "note": "Share the invite code with the company's employees; "
                    "store the API key for programmatic access."}


@app.get("/admin/tenants")
def list_tenants(_: None = Depends(auth.require_admin)):
    return {"tenants": [{"tenant_id": t.tenant_id, "name": t.name,
                         "data_source": t.data_source} for t in auth.store().all()]}


app.mount("/static", StaticFiles(directory=os.path.join(HERE, "static")), name="static")
