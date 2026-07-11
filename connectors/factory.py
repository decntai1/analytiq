"""
Connector factory — assembles the structured data layer from DATA_SOURCE.

  upload   -> DuckDB over UPLOAD_DIR (files uploaded via the UI; demo/SaaS trial)
  database -> SQLAlchemy over DB_URL (customer's own DB)
  files    -> DuckDB over DATA_DIR (data files sitting on an on-prem box)
  all      -> MultiConnector merging database + files + uploads

One place decides the wiring, so app.py and the eval stay mode-agnostic. Adding a
source type later (warehouse, API) = one branch here.
"""
from __future__ import annotations

import os

import config
from connectors.base import StructuredConnector
from connectors.duckdb_conn import DuckDBConnector, analytics_db_path
from connectors.multi import MultiConnector
from connectors.sql import SQLConnector


def ensure_upload_store(base: StructuredConnector, upload_dir: str) -> StructuredConnector:
    """Merge a DuckDB store rooted at upload_dir into the stack.

    Called when uploads are ENABLED but the chosen DATA_SOURCE doesn't already
    include one (database/files): without this, ENABLE_UPLOADS=1 ships a dead
    upload button — the endpoint is on, but /upload finds no store to register
    files into (.env.demo's exact posture: DATA_SOURCE=database + uploads on).
    """
    os.makedirs(upload_dir, exist_ok=True)
    return MultiConnector([base, DuckDBConnector(
        data_dir=upload_dir, db_path=analytics_db_path(upload_dir, "analytics_uploads.duckdb"))])


def build_connector() -> StructuredConnector:
    mode = config.settings.data_source
    s = config.settings

    if mode == "database":
        base = SQLConnector(s.db_url)
        return ensure_upload_store(base, s.upload_dir) if s.enable_uploads else base

    if mode == "upload":
        os.makedirs(s.upload_dir, exist_ok=True)
        return DuckDBConnector(data_dir=s.upload_dir,
                               db_path=analytics_db_path(s.upload_dir, "analytics.duckdb"))

    if mode == "files":
        os.makedirs(s.data_dir, exist_ok=True)
        base = DuckDBConnector(data_dir=s.data_dir,
                               db_path=analytics_db_path(s.data_dir, "analytics_files.duckdb"))
        return ensure_upload_store(base, s.upload_dir) if s.enable_uploads else base

    # "all": merge whatever is configured. Order = DB first, then on-prem files, then uploads.
    sources: list[StructuredConnector] = []
    # only add a DB if DB_URL points somewhere real-ish (skip the default sqlite if absent)
    if s.db_url and not (s.db_url.startswith("sqlite") and not _sqlite_exists(s.db_url)):
        try:
            sources.append(SQLConnector(s.db_url))
        except Exception:
            pass
    for d, name in ((s.data_dir, "analytics_files.duckdb"), (s.upload_dir, "analytics_uploads.duckdb")):
        os.makedirs(d, exist_ok=True)
        try:
            sources.append(DuckDBConnector(data_dir=d, db_path=analytics_db_path(d, name)))
        except Exception:
            pass
    if not sources:
        # nothing configured yet — empty DuckDB so the app still boots
        os.makedirs(s.upload_dir, exist_ok=True)
        sources.append(DuckDBConnector(
            data_dir=s.upload_dir, db_path=analytics_db_path(s.upload_dir, "analytics_uploads.duckdb")))
    return MultiConnector(sources)


def _sqlite_exists(db_url: str) -> bool:
    path = db_url.replace("sqlite:///", "").replace("sqlite://", "")
    return bool(path) and os.path.exists(path)
