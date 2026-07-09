"""
Tenancy — per-customer isolation for the multi-tenant SaaS.

Each tenant has: its own data source (DB URL or isolated upload/doc dirs), its own
schema-RAG + doc-RAG indexes, its own API key, and its own deploy/model defaults.
Tenants never see each other's tables, documents, or uploads.

Single-tenant mode (on-prem, MULTI_TENANT=0) bypasses all of this — there's exactly
one implicit tenant ("default") and no auth required. So the SAME codebase runs
locked-down on-prem AND multi-tenant SaaS; the flag decides.

Storage: tenant registry is a JSON file (TENANTS_FILE). For production scale, swap
this class's load/save for a real DB — the interface stays the same.
"""
from __future__ import annotations

import json
import os
import secrets
import threading
from dataclasses import asdict, dataclass, field

import config


@dataclass
class Tenant:
    tenant_id: str
    name: str
    api_key: str
    data_source: str = "upload"            # upload | database | files | all
    db_url: str = ""                        # for data_source in (database, all)
    default_model: str = ""                 # overrides global default if set
    enable_uploads: bool = True
    # --- cloud tiers (see config.PLANS) --------------------------------------
    plan: str = "free"                      # free | analyst | business
    invite_code: str = ""                   # company join code ("" = closed)
    stripe_customer_id: str = ""            # set by the billing webhook
    # dedicated model endpoint (Business): the company's own vLLM box.
    # Concurrent users of the same company share it via continuous batching.
    llm_base_url: str = ""                  # e.g. http://10.0.0.5:8000/v1
    llm_model_id: str = ""                  # served model id on that endpoint

    def data_dir(self) -> str:
        return os.path.join(config.settings.tenants_root, self.tenant_id, "files")

    def upload_dir(self) -> str:
        return os.path.join(config.settings.tenants_root, self.tenant_id, "uploads")

    def docs_dir(self) -> str:
        return os.path.join(config.settings.tenants_root, self.tenant_id, "documents")

    def ensure_dirs(self) -> None:
        for d in (self.data_dir(), self.upload_dir(), self.docs_dir()):
            os.makedirs(d, exist_ok=True)


class TenantStore:
    """Thread-safe JSON-backed tenant registry."""

    def __init__(self, path: str | None = None) -> None:
        self.path = path or config.settings.tenants_file
        self._lock = threading.Lock()
        self._tenants: dict[str, Tenant] = {}
        self._by_key: dict[str, str] = {}
        self._load()

    def _load(self) -> None:
        if os.path.exists(self.path):
            with open(self.path, encoding="utf-8") as f:
                raw = json.load(f)
            for t in raw.get("tenants", []):
                tn = Tenant(**t)
                self._tenants[tn.tenant_id] = tn
                self._by_key[tn.api_key] = tn.tenant_id

    def _save(self) -> None:
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump({"tenants": [asdict(t) for t in self._tenants.values()]}, f, indent=2)

    def create(self, name: str, **kw) -> Tenant:
        with self._lock:
            tid = kw.pop("tenant_id", None) or secrets.token_hex(6)
            key = "aq_" + secrets.token_urlsafe(24)
            t = Tenant(tenant_id=tid, name=name, api_key=key, **kw)
            t.ensure_dirs()
            self._tenants[tid] = t
            self._by_key[key] = tid
            self._save()
            return t

    def by_key(self, api_key: str) -> Tenant | None:
        tid = self._by_key.get(api_key or "")
        return self._tenants.get(tid) if tid else None

    def by_id(self, tenant_id: str) -> Tenant | None:
        return self._tenants.get(tenant_id)

    def by_invite(self, code: str) -> Tenant | None:
        if not code:
            return None
        for t in self._tenants.values():
            if t.invite_code and secrets.compare_digest(t.invite_code, code):
                return t
        return None

    def update(self, tenant: Tenant) -> None:
        with self._lock:
            self._tenants[tenant.tenant_id] = tenant
            self._by_key[tenant.api_key] = tenant.tenant_id
            self._save()

    def all(self) -> list[Tenant]:
        return list(self._tenants.values())
