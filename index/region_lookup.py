"""
Frozen, deterministic region -> topojson-id resolution.

The geographic-chart scaffold (choropleth / geo_points) never lets the LLM guess a
region code. The model emits a neutral spec naming a COLUMN (e.g. region="country");
the renderer resolves each data value to a topojson feature id through the frozen
table in region_lookup.json — a pure function of (value, level). This keeps maps
model-independent BY CONSTRUCTION (same determinism boundary as glossary_pin) and
lets the renderer fail HONESTLY when the data isn't actually geographic.

Matching is deterministic and dumb on purpose: normalize (lowercase, strip accents
& punctuation, collapse whitespace) then exact-key lookup. NO synonyms, stemming, or
fuzzy matching — "Deutschland" won't resolve, "EMEA" won't resolve, and that refusal
is the correct behavior. Add real-world aliases to the generator, never a fuzzy step.

region_lookup.json is BUILT by scripts/build_region_lookup.py from the vendored
topojson + the ISO-3166 table and then COMMITTED (frozen). Re-run that generator only
when the vendored basemaps change.
"""
from __future__ import annotations

import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

_DATA = Path(__file__).with_name("region_lookup.json")

# Basemap metadata for each level: the vendored topojson URL (same-origin, air-gap
# safe), the topojson object/feature name, and the Vega-Lite projection to use.
BASEMAPS = {
    "country":  {"url": "/static/vendor/world-110m.json", "feature": "countries",
                 "projection": "equalEarth"},
    "us_state": {"url": "/static/vendor/us-10m.json", "feature": "states",
                 "projection": "albersUsa"},
}

LEVELS = tuple(BASEMAPS)

_PUNCT = re.compile(r"[^\w\s]", re.UNICODE)
_WS = re.compile(r"\s+")


def normalize_region(value) -> str:
    """Canonical key for a raw region value. Shared by the generator and the renderer
    so the frozen table and runtime lookups agree exactly."""
    if value is None:
        return ""
    s = unicodedata.normalize("NFKD", str(value))
    s = "".join(c for c in s if not unicodedata.combining(c))  # drop accents
    s = _PUNCT.sub(" ", s.lower())
    return _WS.sub(" ", s).strip()


@lru_cache(maxsize=1)
def _tables() -> dict:
    return json.loads(_DATA.read_text(encoding="utf-8"))


def table_for(level: str) -> dict:
    return _tables().get("levels", {}).get(level, {})


def resolve_choropleth(rows: list[dict], region_field: str, value_field: str, level: str):
    """Resolve a query result's region column to topojson ids, ready to inline as a
    Vega-Lite lookup source.

    Returns (values, rate):
      values: list of {"id": <topojson id str>, "value": <float>, "label": <raw region>},
              one per resolved topojson feature (duplicate ids summed — SQL usually
              pre-aggregates, so this only matters for un-grouped input).
      rate:   distinct-resolved / distinct-non-empty region values — the coverage the
              renderer gates on (>=0.8). 0.0 when the column is empty or non-geographic,
              which is exactly how "this isn't map data" surfaces as an honest refusal.
    """
    table = table_for(level)
    seen: set[str] = set()
    resolved: set[str] = set()
    by_id: dict[str, list] = {}  # id -> [summed value, label]
    for r in rows:
        raw = r.get(region_field)
        key = normalize_region(raw)
        if not key:
            continue
        seen.add(key)
        tid = table.get(key)
        if tid is None:
            continue
        resolved.add(key)
        try:
            num = float(r.get(value_field))
        except (TypeError, ValueError):
            continue  # region resolved but value non-numeric — counts toward coverage, not drawn
        if tid in by_id:
            by_id[tid][0] += num
        else:
            by_id[tid] = [num, str(raw)]
    values = [{"id": tid, "value": v, "label": label} for tid, (v, label) in by_id.items()]
    rate = (len(resolved) / len(seen)) if seen else 0.0
    return values, rate
