"""Total JSON fallback for serializing DB-derived rows.

DuckDB (and SQLAlchemy on non-sqlite backends) return NATIVE Python objects for
typed columns — datetime.date/datetime/time, Decimal, bytes, UUID, ... — none of
which the stdlib json encoder can serialize. Any bare json.dumps of query rows or
of a chart spec that embeds those rows therefore 500s the request (see the /ask
regression: orchestrator run_sql tool-result + persisted chart history).

`json_default` is deliberately TOTAL: it coerces the known types to natural JSON
and str()s anything else, so a tool-result / chart dump can never crash a request
on a type DuckDB grows later. An ugly string in a tool message is strictly better
than a 500.

Decimal -> float (not str): the same helper serializes chart data.values, where
Vega-Lite quantitative encodings require NUMERIC json, and where FastAPI's own
jsonable_encoder already renders Decimal->float on the live response path — so
persisted chat history renders identically to the live answer. These are
DB-rounded values and json uses shortest-round-trip float repr, so money artifacts
("1234.5600000001") don't surface in practice.
"""
from __future__ import annotations

import datetime
from decimal import Decimal


def json_default(o):
    """default= for json.dumps: coerce native DB types; str() everything else."""
    if isinstance(o, (datetime.date, datetime.time)):  # datetime is a date subclass
        return o.isoformat()
    if isinstance(o, Decimal):
        return float(o)
    if isinstance(o, (bytes, bytearray)):
        return o.decode("utf-8", "replace")
    return str(o)
