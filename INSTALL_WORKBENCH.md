# Workbench — install on the VPS (bolt-on module, 2-line integration)

AI-assisted data cleansing on SANDBOXED COPIES. Separate subpage at /workbench.
Battery-verified in the advisor's tree (37/37 + full existing-stack regression);
the module is deliberately isolated so it drops onto the diverged VPS tree
without merge archaeology.

## Files (new — no existing file is modified except app.py's 2 lines)
- core/workbench.py            sessions, profiler, CAPABILITY ops, executor, propose
- api/workbench_routes.py      APIRouter: /workbench (page) + /workbench/api/*
- api/static/workbench.html    standalone page (does NOT touch index.html)
- scripts/workbench_battery.py the acceptance gate (isolated tempdir, zero prod writes)

## Integration (the ONLY edit to existing code)
In api/app.py, after the app's routers/mounts:
    from api.workbench_routes import router as workbench_router
    app.include_router(workbench_router)
(The advisor's tree anchors this after `app.include_router(accounts_router)`;
the VPS lineage has no accounts router — anchor after `app = FastAPI(...)`
middleware/setup instead. Any point before uvicorn serves is fine.)

## Safety model (what the battery proves)
- Source files are IMMUTABLE: sha256 recorded at session start; battery asserts
  byte-identical after a full clean/apply/reset/download cycle.
- The LLM gets NO TOOLS — it emits a plan in the whitelisted vocabulary only;
  the deterministic executor is the sole actor, every op logged as SQL (recipe).
- validate_plan rejects unknown ops, unknown/mistyped columns, bad regexes,
  path-smuggled args. Rejected ops are dropped with reasons, never repaired.
- Sessions: own folder + own DuckDB file under WORKBENCH_DIR (default
  ./workbench), realpath-confined; sid pattern-validated (escape rejected).
  NOTE: on the VPS's relative-path layout this lands at /opt/analytiq/workbench
  — fine, but add `workbench/` to .gitignore (session data is state, not code).
- Zero use of the shared upload-duck connection: file-backed sources are
  re-ingested from the COPY on a throwaway connector; connector-backed sources
  materialize via one read-only run_query (row-cap WORKBENCH_MAX_ROWS=250000).

## Cross-lineage note (already handled in code)
Source-file resolution prefers the connector's `_view_source` ledger (this VPS
has it, from the delete feature); it falls back to a data-dir stem scan where
the ledger doesn't exist. No action needed — just don't strip the getattr.

## Same AI as Analytiq
propose() resolves through core.llm.get_provider — same MODEL_REGISTRY, same
per-request model selection; the page's model picker is fed by GET /models.
With DEFAULT_MODEL=stub the propose degrades gracefully (note field, no 500).

## Verify (the gate) — before restart
    python3 scripts/workbench_battery.py     # from repo root; must exit 0
Then restart analytiq.service (new module import) and live-verify:
open /workbench → pick a table (e.g. the NBA raw dataset) → Copy to workbench
→ Scan & propose ("clean this file") on ollama-cloud → tick a subset → Preview
→ Apply → Download cleaned CSV → confirm the ORIGINAL table in /app unchanged.

## Deliberately out of v1 (documented, not forgotten)
- "Promote to workspace": download + re-upload via the normal upload button
  covers it with zero coupling; a one-click promote can reuse the upload path
  later as its own concern.
- xlsx export (CSV only), scheduled/recurring recipes, recipe re-apply to a new
  file (the recipe format already supports it — it's an executor call away).
