"""
Deterministic forecasting — the third point on the capability spectrum.

Declarative chart transforms (viz/spec.py) sit at one end; arbitrary code
execution (rejected — a sandbox we will not build) at the other. This module is
the middle: a FIXED, parameterized statistical function. Same inputs -> same
outputs, byte-for-byte, every time. No LLM in the compute path, no generated
Python, no sandbox. It is the workbench's whitelisted-ops argument applied to
prediction: statistical capability WITHOUT a code interpreter.

Flow:
  question form -> aggregate the series with ordinary read-only SQL (GROUP BY a
  date_trunc bucket, through the tenant connector's guarded run_query) -> fit a
  fixed statsmodels model (Holt-Winters / ETS, with a linear-trend fallback) ->
  return history + forecast points WITH prediction intervals.

The band IS the honesty. A point forecast with no interval is a fabrication with
extra steps, so intervals are always computed and always returned. Refusals are
honest and typed (ForecastError -> the route answers 422, never a 500): too few
points, an unparseable time column, a non-numeric value column, a series too
sparse or too long to bucket.

Determinism: statsmodels' optimizer is deterministic given the data (no random
seed involved); we set no random state and add no jitter. The one place order
could leak in — bucket gaps — is closed by reindexing to a regular frequency
before the fit. tests/test_forecast.py asserts byte-identical repeats.
"""
from __future__ import annotations

import warnings
from typing import Any

import config

# period unit -> DuckDB date_trunc arg, seasonal period m, pandas reindex freq,
# and a human label. 'week'/'7D' align because DuckDB date_trunc('week') snaps to
# Monday and a 7-day step from the first Monday lands on every subsequent Monday.
_UNITS: dict[str, dict[str, Any]] = {
    "D": {"trunc": "day",     "m": 7,  "freq": "D",   "label": "daily",     "days": 1},
    "W": {"trunc": "week",    "m": 52, "freq": "7D",  "label": "weekly",    "days": 7},
    "M": {"trunc": "month",   "m": 12, "freq": "MS",  "label": "monthly",   "days": 30.4},
    "Q": {"trunc": "quarter", "m": 4,  "freq": "QS",  "label": "quarterly", "days": 91.3},
    "Y": {"trunc": "year",    "m": 1,  "freq": "YS",  "label": "yearly",    "days": 365.25},
}
_AGGS = {"sum", "avg", "min", "max", "count"}
_METHODS = {"auto", "ses", "holt", "holt_winters", "linear"}
_MAX_FILL_FRAC = 0.5   # >50% of buckets empty -> the series is too sparse to trust


class ForecastError(ValueError):
    """A user-facing, honest refusal. The route maps it to HTTP 422, never a 500."""


def _q(name: str) -> str:
    """Quote a SQL identifier. Callers must pass names already validated against
    the connector's real schema, so this only needs to be quote-safe."""
    return '"' + name.replace('"', '""') + '"'


def _tables(connector) -> set[str]:
    try:
        return set(connector.schema_by_table().keys())
    except Exception:
        return set()


def _columns(connector, table: str) -> list[str]:
    """Column names for a table via a zero-row SELECT (works on every connector,
    unlike DESCRIBE which run_query's read-only guard rejects)."""
    res = connector.run_query(f"SELECT * FROM {_q(table)} LIMIT 0")
    return list(res.columns)


def _auto_unit(span_days: float) -> str:
    """Pick a bucket size from the series span so a fit has enough, but not too
    many, points. Deterministic; the user can always override via `period`."""
    if span_days <= 45:
        return "D"
    if span_days <= 210:
        return "W"
    if span_days <= 365 * 4:
        return "M"
    return "Q"


def forecast(
    connector,
    table: str,
    time_col: str,
    value_col: str,
    horizon: int,
    period: str = "auto",
    method: str = "auto",
    agg: str = "sum",
    ci: float | None = None,
) -> dict:
    """Aggregate `value_col` by `time_col` and forecast `horizon` steps ahead.

    Returns a dict with history, forecast points (+ lower/upper), the neutral
    chart spec + rows (for viz.render_vegalite.to_vegalite), the exact
    aggregation SQL used (transparency), diagnostics, and a method note.
    Raises ForecastError on any honest refusal.
    """
    ci = float(config.settings.forecast_default_ci if ci is None else ci)
    if not (0.5 <= ci < 1.0):
        raise ForecastError("Confidence must be between 0.5 and 0.99.")
    period = (period or "auto").upper() if period != "auto" else "auto"
    method = (method or "auto").lower()
    agg = (agg or "sum").lower()
    if method not in _METHODS:
        raise ForecastError(f"Unknown method {method!r}. Choose one of {sorted(_METHODS)}.")
    if agg not in _AGGS:
        raise ForecastError(f"Unknown aggregation {agg!r}. Choose one of {sorted(_AGGS)}.")
    max_h = config.settings.forecast_max_horizon
    if not isinstance(horizon, int) or horizon < 1 or horizon > max_h:
        raise ForecastError(f"Horizon must be an integer between 1 and {max_h}.")

    # --- identifier safety: everything interpolated into SQL must be a real name
    if table not in _tables(connector):
        raise ForecastError(f"Unknown table {table!r}.")
    cols = _columns(connector, table)
    if time_col not in cols:
        raise ForecastError(f"Column {time_col!r} is not in table {table!r}.")
    if value_col not in cols:
        raise ForecastError(f"Column {value_col!r} is not in table {table!r}.")

    tq, vq, tblq = _q(time_col), _q(value_col), _q(table)
    tcast = f"TRY_CAST({tq} AS TIMESTAMP)"
    vcast = f"TRY_CAST({vq} AS DOUBLE)"

    # --- resolve the period (auto = infer from the series span) --------------
    if period == "auto":
        try:
            probe = connector.run_query(
                f"SELECT min({tcast}) AS lo, max({tcast}) AS hi, count({tcast}) AS n FROM {tblq}"
            )
        except Exception as e:
            raise ForecastError(
                "Couldn't read this data source for forecasting — it may not support "
                "the date functions forecasting needs (uploaded tables do)."
            ) from e
        prow = probe.rows[0] if probe.rows else {}
        lo, hi = prow.get("lo"), prow.get("hi")
        if lo is None or hi is None:
            raise ForecastError(
                f"Couldn't read any dates from {time_col!r}. Pick a column that holds "
                "dates or timestamps."
            )
        span_days = (hi - lo).total_seconds() / 86400.0
        unit = _auto_unit(span_days)
    else:
        if period not in _UNITS:
            raise ForecastError(f"Unknown period {period!r}. Choose one of {sorted(_UNITS)} or 'auto'.")
        unit = period
    u = _UNITS[unit]

    # --- aggregate the series with ordinary read-only SQL --------------------
    agg_sql = (
        f"SELECT date_trunc('{u['trunc']}', {tcast}) AS bucket, {agg}({vcast}) AS value\n"
        f"FROM {tblq}\n"
        f"WHERE {tcast} IS NOT NULL AND {vcast} IS NOT NULL\n"
        f"GROUP BY 1 ORDER BY 1"
    )
    try:
        res = connector.run_query(agg_sql)
    except Exception as e:
        raise ForecastError(
            "Couldn't aggregate this series for forecasting — this data source may not "
            "support the date functions forecasting needs (uploaded tables do)."
        ) from e
    if res.truncated:
        raise ForecastError(
            f"The {u['label']} series is longer than we forecast in one pass. "
            "Choose a coarser period (e.g. monthly or quarterly)."
        )
    obs = [(r["bucket"], r["value"]) for r in res.rows if r.get("bucket") is not None
           and r.get("value") is not None]
    if not obs:
        raise ForecastError(
            f"No numeric values in {value_col!r} to forecast (after casting). "
            "Pick a numeric column."
        )

    return _fit_and_pack(
        obs=obs, unit=unit, horizon=horizon, method=method, agg=agg, ci=ci,
        table=table, time_col=time_col, value_col=value_col, agg_sql=agg_sql,
    )


def _fit_and_pack(*, obs, unit, horizon, method, agg, ci, table, time_col,
                  value_col, agg_sql) -> dict:
    """The deterministic numerical core (kept import-light: heavy libs load here,
    so `import core.forecast` never requires statsmodels)."""
    import numpy as np
    import pandas as pd

    u = _UNITS[unit]
    m = u["m"]
    # regularise the series: a GROUP BY only emits buckets that HAVE data, so gaps
    # would make the index irregular and mislead a seasonal fit. Reindex to a full
    # range and fill interior gaps with 0 (flow-measure semantics: a month with no
    # rows contributed nothing). Refuse if the series is mostly gaps.
    raw = pd.Series(
        {pd.Timestamp(b).normalize(): float(v) for b, v in obs}
    ).sort_index()
    idx = pd.date_range(raw.index.min(), raw.index.max(), freq=u["freq"])
    s = pd.Series(0.0, index=idx)
    s.update(raw)
    n = int(len(s))
    filled = int((s.index.isin(raw.index) == False).sum())  # noqa: E712 (vectorised)
    min_pts = config.settings.forecast_min_points
    if n < min_pts:
        raise ForecastError(
            f"Need at least {min_pts} points to forecast; this series has {n} "
            f"{u['label']} point(s). Try a finer period or a longer history."
        )
    if filled / n > _MAX_FILL_FRAC:
        raise ForecastError(
            f"This {u['label']} series is too sparse to forecast "
            f"({filled} of {n} periods have no data). Try a coarser period."
        )

    min_cycles = config.settings.forecast_min_cycles
    seasonal_ok = m > 1 and n >= min_cycles * m
    method_used, seasonal_periods, note, points = _fit(
        np, pd, s, unit, horizon, method, ci, m, seasonal_ok, min_cycles,
    )

    # --- assemble history + forecast + the neutral chart payload -------------
    def _iso(ts) -> str:
        return pd.Timestamp(ts).date().isoformat()

    history = [{"x": _iso(ts), "y": round(float(v), 6)} for ts, v in s.items()]
    forecast_pts = [
        {"x": _iso(p["x"]), "y": round(float(p["mean"]), 6),
         "lower": round(float(p["lower"]), 6), "upper": round(float(p["upper"]), 6)}
        for p in points
    ]

    # chart rows: history line (no band) + a bridge point (zero-width band at the
    # last actual so the dashed forecast line connects) + forecast line + band.
    rows: list[dict] = [
        {"x": h["x"], "value": h["y"], "lower": None, "upper": None, "kind": "history"}
        for h in history
    ]
    if history:
        last = history[-1]
        rows.append({"x": last["x"], "value": last["y"], "lower": last["y"],
                     "upper": last["y"], "kind": "forecast"})
    for f in forecast_pts:
        rows.append({"x": f["x"], "value": f["y"], "lower": f["lower"],
                     "upper": f["upper"], "kind": "forecast"})

    spec = {
        "type": "forecast",
        "title": f"{value_col} — {u['label']} forecast ({method_used.replace('_', ' ')})",
        "encoding": {"x": "x", "y": "value", "lower": "lower", "upper": "upper",
                     "kind": "kind"},
    }

    return {
        "ok": True,
        "table": table, "time_col": time_col, "value_col": value_col,
        "agg": agg, "period": unit, "period_label": u["label"],
        "method_used": method_used, "n_points": n, "n_filled": filled,
        "horizon": horizon, "ci": ci,
        "history": history, "forecast": forecast_pts,
        "method_note": note,
        "diagnostics": {
            "seasonal_periods": seasonal_periods,
            "filled_pct": round(100.0 * filled / n, 1),
            "interval": f"{round(ci * 100)}% prediction interval",
        },
        "sql": agg_sql,
        "spec": spec,
        "rows": rows,
    }


def _fit(np, pd, s, unit, horizon, method, ci, m, seasonal_ok, min_cycles):
    """Return (method_used, seasonal_periods, note, points) where points is a list
    of {x, mean, lower, upper}. Chooses/honours the method; ETS with a linear
    fallback. Never raises for numerical reasons — falls back to linear instead."""
    u = _UNITS[unit]
    n = len(s)

    # explicit seasonal request that the data can't support -> honest refusal
    if method == "holt_winters" and not seasonal_ok:
        raise ForecastError(
            f"Holt-Winters needs at least {min_cycles} full {u['label']} cycles "
            f"({min_cycles * m} points); this series has {n}. Use method 'auto', or "
            "a period with enough history."
        )

    chosen = method
    if method == "auto":
        chosen = "holt_winters" if seasonal_ok else ("holt" if n >= 4 else "ses")

    if chosen == "linear":
        return _linear(np, pd, s, unit, horizon, ci)

    # statsmodels ETS (state-space exponential smoothing) — analytic prediction
    # intervals, deterministic optimiser (no random seed).
    try:
        from statsmodels.tsa.exponential_smoothing.ets import ETSModel
        trend = None if chosen == "ses" else "add"
        seasonal = "add" if chosen == "holt_winters" else None
        kw = {"error": "add", "trend": trend, "seasonal": seasonal}
        if seasonal:
            kw["seasonal_periods"] = m
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            model = ETSModel(s.astype(float), **kw)
            fit = model.fit(disp=False)
            pred = fit.get_prediction(start=n, end=n + horizon - 1)
            sf = pred.summary_frame(alpha=1.0 - ci)
        mean_col = "mean" if "mean" in sf else sf.columns[0]
        lo_col = "pi_lower" if "pi_lower" in sf else sf.columns[-2]
        hi_col = "pi_upper" if "pi_upper" in sf else sf.columns[-1]
        future = pd.date_range(s.index.max(), periods=horizon + 1, freq=u["freq"])[1:]
        points = [
            {"x": future[i], "mean": float(sf[mean_col].iloc[i]),
             "lower": float(sf[lo_col].iloc[i]), "upper": float(sf[hi_col].iloc[i])}
            for i in range(horizon)
        ]
        label = {"ses": "Simple exponential smoothing", "holt": "Holt linear trend",
                 "holt_winters": f"Holt-Winters (additive trend + season, {m}-period)"}[chosen]
        note = f"{label}, fitted on {n} {u['label']} points"
        seasonal_periods = m if seasonal else None
        return chosen, seasonal_periods, note, points
    except ForecastError:
        raise
    except Exception:
        # numerical trouble (non-convergence, degenerate series): fall back to the
        # simplest honest model rather than 500. The band still communicates risk.
        return _linear(np, pd, s, unit, horizon, ci)


def _linear(np, pd, s, unit, horizon, ci):
    """Ordinary-least-squares linear trend with a t-based prediction interval.
    Pure numpy/scipy; fully deterministic."""
    from scipy import stats
    u = _UNITS[unit]
    n = len(s)
    y = s.to_numpy(dtype=float)
    x = np.arange(n, dtype=float)
    b1, b0 = np.polyfit(x, y, 1)
    yhat = b0 + b1 * x
    dof = max(n - 2, 1)
    sse = float(np.sum((y - yhat) ** 2))
    s_err = (sse / dof) ** 0.5
    xbar = float(np.mean(x))
    sxx = float(np.sum((x - xbar) ** 2)) or 1.0
    tval = float(stats.t.ppf((1.0 + ci) / 2.0, dof))
    future = pd.date_range(s.index.max(), periods=horizon + 1, freq=u["freq"])[1:]
    points = []
    for i in range(horizon):
        xf = n + i
        mean = b0 + b1 * xf
        # prediction interval for a new observation (includes the +1 term)
        se = s_err * (1.0 + 1.0 / n + (xf - xbar) ** 2 / sxx) ** 0.5
        points.append({"x": future[i], "mean": float(mean),
                       "lower": float(mean - tval * se), "upper": float(mean + tval * se)})
    note = f"Linear trend (OLS), fitted on {n} {u['label']} points"
    return "linear", None, note, points
