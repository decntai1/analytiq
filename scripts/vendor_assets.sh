#!/usr/bin/env bash
# Download the Vega chart libraries into api/static/vendor/ so the UI works fully
# offline / air-gapped (no CDN dependency). Run once on a machine WITH internet,
# then the bundle carries them. Re-run to update versions.
set -euo pipefail
DEST="$(dirname "$0")/../api/static/vendor"
mkdir -p "$DEST"
echo "→ downloading Vega libs into $DEST"
curl -fsSL "https://cdn.jsdelivr.net/npm/vega@5"          -o "$DEST/vega.min.js"
curl -fsSL "https://cdn.jsdelivr.net/npm/vega-lite@5"     -o "$DEST/vega-lite.min.js"
curl -fsSL "https://cdn.jsdelivr.net/npm/vega-embed@6"    -o "$DEST/vega-embed.min.js"
echo "→ downloading topojson basemaps (choropleth / geo_points)"
curl -fsSL "https://cdn.jsdelivr.net/npm/world-atlas@2/countries-110m.json" -o "$DEST/world-110m.json"
curl -fsSL "https://cdn.jsdelivr.net/npm/us-atlas@3/states-10m.json"         -o "$DEST/us-10m.json"
echo "✓ vendored. The UI loads these locally and falls back to CDN if absent."
echo "  NOTE: after refreshing the basemaps, re-run scripts/build_region_lookup.py"
echo "  so index/region_lookup.json stays in sync with the topojson feature ids."
