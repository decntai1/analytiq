#!/usr/bin/env python3
"""
Build index/region_lookup.json — the FROZEN region -> topojson-id table used by the
geoshape renderer. Build-time tool (needs internet for the ISO-3166 table), like
scripts/vendor_assets.sh. Its OUTPUT is committed and deterministic at runtime.

Sources (all provenance, no runtime dependency):
  api/static/vendor/world-110m.json  world-atlas@2 countries-110m (feature id = ISO-3166 numeric)
  api/static/vendor/us-10m.json      us-atlas@3 states-10m       (feature id = FIPS)
  ISO-3166 CSV (lukes/ISO-3166-Countries-with-Regional-Codes)    name/alpha-2/alpha-3/numeric

Re-run whenever the vendored basemaps change:
  python scripts/build_region_lookup.py
"""
from __future__ import annotations

import csv
import io
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from index.region_lookup import normalize_region  # noqa: E402  (shared normalizer)

VENDOR = ROOT / "api" / "static" / "vendor"
OUT = ROOT / "index" / "region_lookup.json"
ISO_CSV_URL = ("https://raw.githubusercontent.com/lukes/"
               "ISO-3166-Countries-with-Regional-Codes/master/all/all.csv")

# Common real-world aliases the ISO/topojson names don't carry. Kept explicit (never a
# fuzzy step): value -> ISO-3166 numeric code (as it appears in the topojson feature id).
COUNTRY_ALIASES = {
    "usa": "840", "us": "840", "u s a": "840", "u s": "840", "united states": "840",
    "america": "840", "uk": "826", "u k": "826", "britain": "826", "great britain": "826",
    "england": "826", "south korea": "410", "korea": "410", "north korea": "408",
    "russia": "643", "iran": "364", "syria": "760", "vietnam": "704", "laos": "418",
    "czech republic": "203", "czechia": "203", "ivory coast": "384", "cote d ivoire": "384",
    "congo": "178", "dr congo": "180", "drc": "180", "democratic republic of the congo": "180",
    "bolivia": "068", "venezuela": "862", "tanzania": "834", "brunei": "096",
    "moldova": "498", "uae": "784", "united arab emirates": "784", "taiwan": "158",
    "turkey": "792", "turkiye": "792", "netherlands": "528", "holland": "528",
}

# European endonyms (self-names). A European customer typing their own country name
# in their data is the realistic case — "Deutschland doesn't resolve" would read as a
# bug to exactly our target market. These are FROZEN exact-match keys, identical in
# status to the ISO codes and COUNTRY_ALIASES above — NOT a fuzzy step. normalize_region
# strips accents/case (Österreich -> "osterreich"), so the accented source form is just
# self-documentation. Latin-script only, and only unambiguous names (Ísland -> "island"
# is deliberately omitted — it would collide with the English word). value -> ISO numeric.
COUNTRY_ENDONYMS = {
    "Deutschland": "276", "Magyarország": "348", "España": "724", "Italia": "380",
    "Nederland": "528", "Österreich": "040", "Suomi": "246", "Sverige": "752",
    "Norge": "578", "Danmark": "208", "Polska": "616", "België": "056",
    "Belgique": "056", "Schweiz": "756", "Suisse": "756", "Svizzera": "756",
    "Hrvatska": "191", "Česko": "203", "Česká republika": "203", "Éire": "372",
    "Hellas": "300", "Lietuva": "440", "Latvija": "428", "Eesti": "233",
    "Slovensko": "703", "Slovenija": "705", "Lëtzebuerg": "442", "Shqipëria": "008",
}

# 50 states + DC: 2-letter USPS abbreviation -> FIPS (the us-atlas feature id, zero-padded).
US_STATE_ABBR = {
    "AL": "01", "AK": "02", "AZ": "04", "AR": "05", "CA": "06", "CO": "08", "CT": "09",
    "DE": "10", "DC": "11", "FL": "12", "GA": "13", "HI": "15", "ID": "16", "IL": "17",
    "IN": "18", "IA": "19", "KS": "20", "KY": "21", "LA": "22", "ME": "23", "MD": "24",
    "MA": "25", "MI": "26", "MN": "27", "MS": "28", "MO": "29", "MT": "30", "NE": "31",
    "NV": "32", "NH": "33", "NJ": "34", "NM": "35", "NY": "36", "NC": "37", "ND": "38",
    "OH": "39", "OK": "40", "OR": "41", "PA": "42", "RI": "44", "SC": "45", "SD": "46",
    "TN": "47", "TX": "48", "UT": "49", "VT": "50", "VA": "51", "WA": "53", "WV": "54",
    "WI": "55", "WY": "56",
}


def _load_topojson(path: Path, feature: str) -> list[dict]:
    obj = json.loads(path.read_text(encoding="utf-8"))
    return obj["objects"][feature]["geometries"]


def _add(table: dict, value, tid: str) -> None:
    key = normalize_region(value)
    if key and tid:
        table.setdefault(key, tid)  # first writer wins -> stable, order-independent


def build_countries() -> dict:
    geoms = _load_topojson(VENDOR / "world-110m.json", "countries")
    table: dict[str, str] = {}
    # 1) topojson's own display names (e.g. "W. Sahara", "United States of America")
    for g in geoms:
        tid = str(g.get("id"))
        name = (g.get("properties") or {}).get("name")
        _add(table, name, tid)
    ids_present = {str(g.get("id")) for g in geoms}
    # 2) ISO-3166 names + alpha-2 + alpha-3, joined by numeric code present in the atlas
    with urllib.request.urlopen(ISO_CSV_URL, timeout=30) as resp:
        rows = list(csv.DictReader(io.StringIO(resp.read().decode("utf-8"))))
    for r in rows:
        tid = r["country-code"]  # 3-digit numeric, matches atlas feature id
        if tid not in ids_present:
            continue
        _add(table, r["name"], tid)
        _add(table, r["alpha-2"], tid)
        _add(table, r["alpha-3"], tid)
    # 3) curated aliases + European endonyms (only those whose id is in the atlas)
    for alias, tid in {**COUNTRY_ALIASES, **COUNTRY_ENDONYMS}.items():
        if tid in ids_present:
            _add(table, alias, tid)
    return table


def build_us_states() -> dict:
    geoms = _load_topojson(VENDOR / "us-10m.json", "states")
    table: dict[str, str] = {}
    for g in geoms:  # full state/territory names, e.g. "California", "Puerto Rico"
        _add(table, (g.get("properties") or {}).get("name"), str(g.get("id")))
    ids_present = {str(g.get("id")) for g in geoms}
    for abbr, tid in US_STATE_ABBR.items():  # 2-letter USPS codes
        if tid in ids_present:
            _add(table, abbr, tid)
    return table


def main() -> int:
    for f in ("world-110m.json", "us-10m.json"):
        if not (VENDOR / f).exists():
            print(f"ERROR: {VENDOR / f} missing — run scripts/vendor_assets.sh first.")
            return 1
    country = build_countries()
    us_state = build_us_states()
    payload = {
        "_note": "FROZEN — built by scripts/build_region_lookup.py; do not hand-edit.",
        "_sources": {"country": "world-atlas@2 countries-110m + ISO-3166",
                     "us_state": "us-atlas@3 states-10m + USPS abbreviations"},
        "levels": {"country": country, "us_state": us_state},
    }
    OUT.write_text(json.dumps(payload, indent=1, ensure_ascii=True, sort_keys=True) + "\n",
                   encoding="utf-8")
    print(f"✓ wrote {OUT.relative_to(ROOT)}: {len(country)} country keys, "
          f"{len(us_state)} us_state keys")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
