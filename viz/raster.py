"""
Render a Vega-Lite spec to a PNG (deterministic, accurate — real data, not generated
pixels). Used by the presentation generator and any image export.

vl-convert bundles its own Vega runtime, so this works server-side with no browser.
"""
from __future__ import annotations


def vegalite_to_png(spec: dict, scale: float = 2.0) -> bytes:
    import vl_convert as vlc
    # ensure a concrete width/height (vl-convert can't use "container")
    s = dict(spec)
    if s.get("width") in (None, "container"):
        s["width"] = 600
    if s.get("height") in (None, "container"):
        s["height"] = 360
    return vlc.vegalite_to_png(vl_spec=s, scale=scale)
