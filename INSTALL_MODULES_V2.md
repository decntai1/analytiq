# Analytiq modules v2 — Dashboard + Workbench recipes (VPS install)

Battery-verified bolt-ons for the diverged VPS tree. Everything here is
module-owned or additive; the ONLY existing-file edits are app.py hook lines
and one small pin-button snippet for index.html.

## What's new since the workbench v1 module
1. DASHBOARD (3rd subpage, /dashboard): pin chat answers as tiles
   {question, sql, spec}. Refresh re-runs the saved SQL through the tenant
   connector — the read-only guard applies on EVERY refresh (battery-proven:
   a tile edited to `DELETE FROM…` refuses to run and data is untouched) —
   and re-binds fresh rows into the saved chart. Monitoring without
   re-prompting; zero LLM calls on refresh. Boards, per-tile refresh/edit
   (title + SQL)/delete, auto-refresh, board→PPTX export (deps already on
   this VPS), table tiles for chart-less queries.
2. WORKBENCH RECIPE LIBRARY: save an applied recipe by name; re-apply it to
   next month's file — misfit ops (missing columns etc.) are SKIPPED with
   reasons, never guessed.

## Files (drop in; workbench files REPLACE the v1 module files verbatim)
- core/dashboards.py                 NEW
- api/dashboard_routes.py            NEW
- api/static/dashboard.html          NEW
- scripts/dashboard_battery.py       NEW (lineage-adaptive: runs single-tenant here)
- core/workbench.py                  v2 (adds recipe library — v1 + additions only)
- api/workbench_routes.py            v2 (3 recipe endpoints appended)
- api/static/workbench.html          v2 (Save-as-recipe + apply dropdown)
- scripts/workbench_battery.py       v2 (recipe section added)

## app.py hook (after the workbench router lines from v1)
    from api.dashboard_routes import router as dashboard_router
    app.include_router(dashboard_router)
Add `dashboards/` and `workbench/` to .gitignore (session/tile data is state).

## Chat-side pin button — the ONE index.html edit (CC: recon your actions/
## answer-render area first; anchor where the answer's trace/actions render,
## `data` = the /ask response object, `q` = the question string)
    const pin=document.createElement('button');
    pin.className='pinbtn';pin.textContent='📌 Pin';
    pin.title='Save to /dashboard: re-runs this SQL on refresh, no re-prompting';
    pin.addEventListener('click',async()=>{
      const sql=(data.sql_log&&data.sql_log.length)?data.sql_log[data.sql_log.length-1]:'';
      const spec=(data.charts&&data.charts[0]&&!data.charts[0]._kind)?data.charts[0]:null;
      if(!sql){pin.textContent='No SQL';return;}
      const r=await fetch('/dashboard/api/tiles',{method:'POST',
        headers:{'content-type':'application/json'},
        body:JSON.stringify({title:q.slice(0,100),question:q,sql,spec})});
      pin.textContent=r.ok?'Pinned ✓':'Pin failed';});
    /* append `pin` next to the answer's trace toggle */
NOTE: this VPS's /ask response also carries table_scope — no interaction; the
pin stores the final SQL, which is already scope-resolved.

## Verify (the gates) — from repo root, before restart
    python3 scripts/workbench_battery.py     # must exit 0 (now 41 checks)
    python3 scripts/dashboard_battery.py     # must exit 0 (D10 auto-skips here)
Then restart analytiq.service and live-verify: ask "goals per team from
wcgames2, bar chart" → 📌 Pin → open /dashboard → tile renders → upload a
changed wcgames2 → ↻ on the tile → new data, no LLM call in the logs.

## NOT in this module (full-tree only, by design)
Stripe billing. Billing needs accounts/plans, and this lineage has none — it
ships fully wired + battery-tested (signature-verified webhooks, live plan
flips) in the r4 full tree, and activates whenever the lineages reconcile.
