"""
Forecast API — self-contained APIRouter. Integration = two lines in app.py:
    from api.forecast_routes import router as forecast_router
    app.include_router(forecast_router)

Two endpoints, same auth + rate-limit conventions as /upload:
  GET  /forecast/columns?table=T  -> forecastable columns (date-typed + numeric),
                                     so the data-drawer form can pre-filter.
  POST /forecast                  -> deterministic forecast + rendered chart.

NO LLM anywhere on this path: it calls core/forecast.py (a fixed statistical
function) and renders through the existing neutral chart pipeline. Honest
refusals surface as 422 (ForecastError), never a 500. Forecasting is not an
LLM question, so it consumes no question credits.
"""
from __future__ import annotations

import datetime
from decimal import Decimal

import config
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from api import auth
from core.forecast import ForecastError, forecast
from core.tenancy import Tenant
from core.tenant_runtime import TenantRuntime
from viz.render_vegalite import to_vegalite

router = APIRouter()
_runtime = TenantRuntime()
_ratelimit = auth.RateLimiter(config.settings.rate_limit_per_min)

_DATE_FORMATS = ("%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y", "%d/%m/%Y",
                 "%Y-%m-%d %H:%M:%S", "%Y-%m", "%Y")


def _gate(request: Request, tenant: Tenant | None) -> None:
    _ratelimit.check(auth.client_key(request, tenant))


def _q(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _is_number(v) -> bool:
    return isinstance(v, (int, float, Decimal)) and not isinstance(v, bool)


def _date_parse_frac(vals: list[str]) -> float:
    ok = 0
    for v in vals:
        s = v.strip()
        parsed = False
        try:
            datetime.datetime.fromisoformat(s)
            parsed = True
        except ValueError:
            for fmt in _DATE_FORMATS:
                try:
                    datetime.datetime.strptime(s, fmt)
                    parsed = True
                    break
                except ValueError:
                    continue
        ok += parsed
    return ok / len(vals) if vals else 0.0


def _forecastable(connector, table: str) -> dict:
    """Classify a table's columns into time candidates (date/timestamp-typed, or
    text that parses as dates) and numeric candidates, from a bounded sample."""
    res = connector.run_query(f"SELECT * FROM {_q(table)} LIMIT 200")
    time_cols, value_cols = [], []
    for c in res.columns:
        vals = [r[c] for r in res.rows if r.get(c) is not None][:100]
        if not vals:
            continue
        if all(_is_number(v) for v in vals):
            value_cols.append(c)
        elif all(isinstance(v, (datetime.date, datetime.datetime)) for v in vals):
            time_cols.append(c)
        elif all(isinstance(v, str) for v in vals) and _date_parse_frac(vals) >= 0.8:
            time_cols.append(c)
    return {"time_candidates": time_cols, "value_candidates": value_cols}


class ForecastBody(BaseModel):
    table: str
    time_col: str
    value_col: str
    horizon: int = 6
    period: str = "auto"
    method: str = "auto"
    agg: str = "sum"
    ci: float | None = None


@router.get("/forecast/columns")
def forecast_columns(request: Request, table: str = Query(...),
                     tenant: Tenant | None = Depends(auth.resolve_tenant)):
    _gate(request, tenant)
    ctx = _runtime.get(tenant)
    if table not in ctx.connector.schema_by_table():
        raise HTTPException(404, f"No such table {table!r}.")
    try:
        cands = _forecastable(ctx.connector, table)
    except Exception:
        cands = {"time_candidates": [], "value_candidates": []}
    return {
        "table": table,
        **cands,
        "periods": ["auto", "D", "W", "M", "Q", "Y"],
        "methods": ["auto", "ses", "holt", "holt_winters", "linear"],
        "default_horizon": 6,
        "max_horizon": config.settings.forecast_max_horizon,
        "min_points": config.settings.forecast_min_points,
    }


@router.post("/forecast")
def do_forecast(body: ForecastBody, request: Request,
                tenant: Tenant | None = Depends(auth.resolve_tenant)):
    _gate(request, tenant)
    ctx = _runtime.get(tenant)
    try:
        result = forecast(
            ctx.connector, body.table, body.time_col, body.value_col,
            body.horizon, period=body.period, method=body.method,
            agg=body.agg, ci=body.ci,
        )
    except ForecastError as e:
        raise HTTPException(422, str(e))
    # render through the existing neutral pipeline (the forecast type is server-only)
    try:
        result["chart"] = to_vegalite(result["spec"], result["rows"])
    except Exception:
        result["chart"] = None
    return result
