"""
Tenant runtime — builds and caches the per-tenant data layer.

For each tenant we lazily build an isolated {connector, schema-index, doc-index,
orchestrator}, cache it, and reuse it across requests. Re-index is per-tenant, so an
upload by tenant A never touches tenant B. In single-tenant mode there's one context
keyed "default" using the global env config (on-prem behaviour, unchanged).
"""
from __future__ import annotations

import dataclasses
import os
import threading

import config
from connectors.duckdb_conn import DuckDBConnector
from connectors.factory import build_connector
from connectors.multi import MultiConnector
from connectors.sql import SQLConnector
from connectors.base import StructuredConnector
from core.embeddings import get_embedder
from core.orchestrator import Orchestrator
from core.tenancy import Tenant
from index.doc_index import DocIndex
from index.schema_index import SchemaIndex


class TenantContext:
    def __init__(self, connector: StructuredConnector, schema_index: SchemaIndex,
                 doc_index: DocIndex, tenant: Tenant | None) -> None:
        self.connector = connector
        self.schema_index = schema_index
        self.doc_index = doc_index
        self.tenant = tenant

    def orchestrator(self) -> Orchestrator:
        return Orchestrator(self.connector, self.schema_index, self.doc_index)

    def upload_duck(self) -> DuckDBConnector | None:
        up = self.tenant.upload_dir() if self.tenant else config.settings.upload_dir
        cands = self.connector.sources if isinstance(self.connector, MultiConnector) else [self.connector]
        for c in cands:
            if isinstance(c, DuckDBConnector) and os.path.abspath(c.data_dir) == os.path.abspath(up):
                return c
        return None

    def docs_dir(self) -> str:
        return self.tenant.docs_dir() if self.tenant else config.settings.docs_dir

    def reindex(self) -> None:
        emb = get_embedder()
        si = SchemaIndex(emb)
        si.build(self.connector.schema_by_table())
        self.schema_index = si
        self.doc_index.store.items.clear()
        self.doc_index.ingest_dir(self.docs_dir())


class TenantRuntime:
    """Builds + caches a TenantContext per tenant."""

    def __init__(self) -> None:
        self._cache: dict[str, TenantContext] = {}
        self._lock = threading.Lock()
        self._embedder = get_embedder()

    def _build_for(self, tenant: Tenant | None) -> TenantContext:
        emb = self._embedder
        if tenant is None:
            # single-tenant: global env config
            connector = build_connector()
            docs = config.settings.docs_dir
        else:
            tenant.ensure_dirs()
            connector = self._build_tenant_connector(tenant)
            docs = tenant.docs_dir()
        si = SchemaIndex(emb); si.build(connector.schema_by_table())
        di = DocIndex(emb); di.ingest_dir(docs)
        return TenantContext(connector, si, di, tenant)

    @staticmethod
    def _build_tenant_connector(t: Tenant) -> StructuredConnector:
        from connectors.factory import ensure_upload_store
        mode = t.data_source
        if mode == "database":
            base = SQLConnector(t.db_url)
            return ensure_upload_store(base, t.upload_dir()) if t.enable_uploads else base
        if mode == "upload":
            return DuckDBConnector(data_dir=t.upload_dir())
        if mode == "files":
            base = DuckDBConnector(data_dir=t.data_dir())
            return ensure_upload_store(base, t.upload_dir()) if t.enable_uploads else base
        # all
        srcs: list[StructuredConnector] = []
        if t.db_url:
            try: srcs.append(SQLConnector(t.db_url))
            except Exception: pass
        for d in (t.data_dir(), t.upload_dir()):
            os.makedirs(d, exist_ok=True)
            try: srcs.append(DuckDBConnector(data_dir=d))
            except Exception: pass
        if not srcs:
            srcs.append(DuckDBConnector(data_dir=t.upload_dir()))
        return MultiConnector(srcs)

    def get(self, tenant: Tenant | None) -> TenantContext:
        key = tenant.tenant_id if tenant else "default"
        with self._lock:
            if key not in self._cache:
                self._cache[key] = self._build_for(tenant)
            return self._cache[key]

    def invalidate(self, tenant: Tenant | None) -> None:
        key = tenant.tenant_id if tenant else "default"
        with self._lock:
            self._cache.pop(key, None)
