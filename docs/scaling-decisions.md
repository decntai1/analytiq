# Scaling decisions (foundation package, 2026-07-11)

Sizing this build to the **actual** target, so a future agent doesn't relitigate it.

## Envelope we are building for
- **Tenants:** < 20.  **Users:** < 200.
- **Data:** small — < 100 MB typical per tenant.
- **Boundary:** **on-prem, privacy-first is the primary product path.** The cloud
  site (analytiq.dcentai.tech) is a **demo / trial surface**, not a SaaS scale target.
- **Load:** low, interactive. The one natural burst source is the dashboard
  `refresh_tile` path (several pinned panels re-executing at once) — the connector
  fix below explicitly covers it.

## Built now — the foundation package
1. **DuckDB thread-safety.** A per-connector re-entrant lock in `connectors/duckdb_conn.py`
   serializes every touch of the shared connection **and** the shared Python state
   (`_views`/`_ts_hints`/`_source_of`/`last_ingest`) across `run_query`, `register_file`,
   `schema_by_table`, `delete_view`. Same-tenant requests share ONE cached connector
   (`core/tenant_runtime`) in FastAPI's sync threadpool, so concurrent `/ask`, an upload
   racing a query, and a refresh burst all arrive together. Chose a lock over per-query
   `cursor()` because it also guards the Python-side mutations a cursor would leave racy,
   and the load makes serialization cost negligible. Proven by `tests/concurrency_smoke.py`
   (0 errors with the lock; the same stress raises `TypeError`s without it).
2. **File-backed per-tenant DuckDB.** `:memory:` → `tenants_root/<tid>/analytics*.duckdb`.
   RAM — not tenant size — is the binding constraint on this box; a file-backed DB pages
   tables to disk and survives a restart. One file **per store** (`analytics.duckdb` for the
   upload store; `analytics_files.duckdb` / `analytics_uploads.duckdb` when a tenant has
   several) because DuckDB is single-writer per file. xlsx sheets are now materialized as
   TABLEs (not views over an ephemeral registered frame) so they persist cleanly.
   **Migration for existing tenants is lazy and automatic:** the startup re-scan
   (`_register_files`) rebuilds every view from the tenant's own upload files on first
   construction after deploy — no data move, no migration script.
3. **WAL on `accounts.db`.** Already present (`core/accounts.py`: `PRAGMA journal_mode=WAL`
   at connect). Verified, not re-added.

## Parked — recorded, deliberately NOT built
Postgres · Redis · Uvicorn `--workers` / process replicas · connector eviction / TTL /
LRU cache · a concurrency queue or admission control · per-tenant dedicated inference
(RunPod / dedicated vLLM box).

**Rationale.** On-prem single-tenant is the product path, so a shared-plane, multi-worker
scale-out has **no customer** today. Adding it now buys operational complexity (a second
datastore to run and back up, cross-worker cache invalidation, connection-pool tuning) for
load that doesn't exist. The store interfaces stay **pluggable** (`TenantStore` /
`AccountStore` both carry a "swap for a real DB" seam; the connector factory is one branch
per source type) — that pluggability is the insurance, so none of this is hard to add later.

**Revisit trigger.** The cloud demo becoming a **real SaaS bet** — i.e. we intend to run
many concurrent tenants on shared infrastructure with an uptime commitment. Concretely, any
of: sustained multi-worker deployment (`--workers > 1`, which breaks the in-process caches
and single-writer DuckDB files → needs Postgres + a shared cache), tenants outgrowing the
~100 MB / small-data envelope, or the RAM ceiling on the box (3.7 GB / no swap — see the
`ram-ceiling-vps` note) being hit under real traffic. Until then: don't build it.

### Notes for whoever picks up the revisit
- Multi-worker is the hard cliff: `TenantRuntime._cache`, `TenantStore`, and the
  file-backed DuckDB single-writer lock are all **per-process**. `--workers > 1` needs a
  shared metadata DB (Postgres) and either a shared query engine or per-worker affinity.
- `TenantRuntime.invalidate()` now `close()`s the evicted connector first, so it releases
  the DuckDB file lock before a rebuild reopens the same path — safe to start wiring cache
  eviction on top of it when that day comes.
