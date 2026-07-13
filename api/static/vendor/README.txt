Run scripts/vendor_assets.sh (with internet) to populate this dir for air-gapped deploys.

Vendored assets (served same-origin from /static/vendor/ — never a CDN at runtime):
  vega.min.js / vega-lite.min.js / vega-embed.min.js   chart engine
  world-110m.json   world-atlas@2 countries-110m topojson (choropleth country basemap)
  us-10m.json       us-atlas@3 states-10m topojson (choropleth us_state basemap)

The geoshape renderer references the topojson by same-origin URL and resolves region
names -> topojson feature ids server-side via the frozen index/region_lookup.json.
If you update world-110m.json / us-10m.json, re-run scripts/build_region_lookup.py.
