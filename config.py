"""
Central configuration.

Two things make this thesis-friendly and product-ready:

1. MODEL REGISTRY — every LLM you might test is one entry: a friendly name mapped
   to a provider + endpoint + credential. Select per request. This is the analog
   of DEcntAI's model catalog + dispatch: the caller asks for "qwen2.5-14b" or
   "claude" or "grok" and the right adapter/endpoint is resolved. Add a model on a
   bigger GPU box by adding one entry — no code change.

2. DEPLOY_MODE — "cloud" (hosted APIs) vs "onprem" (local LLM + local embeddings,
   data never leaves the box). Same image, different env.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class ModelSpec:
    name: str               # friendly id used in requests
    provider: str           # "openai_compatible" | "anthropic"
    model_id: str           # the provider's actual model string
    base_url: str           # endpoint (ignored for anthropic native)
    api_key_env: str        # env var holding the key ("" for keyless local)
    notes: str = ""


# ---------------------------------------------------------------------------
# Model registry. Edit/extend freely. Names on the left are what you request.
# Local entries point at the ACTIVE RUNTIME (core.runtime): ollama for demo,
# your Analytiq runtime for production — switched by LLM_RUNTIME, no registry edit.
# ---------------------------------------------------------------------------
def _local_url() -> str:
    # late import to avoid a cycle; runtime only reads env
    from core.runtime import local_base_url
    return local_base_url()


MODEL_REGISTRY: dict[str, ModelSpec] = {
    # --- local (served by the active runtime: ollama demo / analytiq prod) ---
    "qwen2.5-14b": ModelSpec(
        "qwen2.5-14b", "openai_compatible", os.getenv("QWEN_MODEL_ID", "qwen2.5:14b-instruct"),
        _local_url(), "", "Default on-prem pick; fits 16GB at Q4/Q5.",
    ),
    "llama3.1-8b": ModelSpec(
        "llama3.1-8b", "openai_compatible", os.getenv("LLAMA_MODEL_ID", "llama3.1:8b-instruct"),
        _local_url(), "",
    ),
    # add on a bigger GPU box, e.g.:
    # "qwen2.5-72b": ModelSpec("qwen2.5-72b","openai_compatible","qwen2.5:72b",
    #     "http://gpu-box:11434/v1", ""),

    # --- Ollama Cloud (DEMO: the model runs on Ollama's servers, not this box) ---
    # The OpenAI-compatible endpoint is https://ollama.com/v1 (NOT /api/v1).
    # Get a key at https://ollama.com/settings/keys and set OLLAMA_API_KEY.
    # model_id is a CLOUD-CATALOG id (not a local pull name) — pick a tool-capable one;
    # list them with:  curl https://ollama.com/v1/models -H "Authorization: Bearer $OLLAMA_API_KEY"
    "ollama-cloud": ModelSpec(
        "ollama-cloud", "openai_compatible",
        os.getenv("OLLAMA_CLOUD_MODEL", "gpt-oss:120b"),
        "https://ollama.com/v1", "OLLAMA_API_KEY",
        "Ollama Cloud (hosted, tool-capable). Keeps the host light; needs OLLAMA_API_KEY.",
    ),

    # --- cloud (thesis comparison; bring your keys) ------------------------
    "gpt-4o-mini": ModelSpec(
        "gpt-4o-mini", "openai_compatible", "gpt-4o-mini",
        "https://api.openai.com/v1", "OPENAI_API_KEY",
    ),
    "gpt-4o": ModelSpec(
        "gpt-4o", "openai_compatible", "gpt-4o",
        "https://api.openai.com/v1", "OPENAI_API_KEY",
    ),
    "grok-2": ModelSpec(
        "grok-2", "openai_compatible", "grok-2-latest",
        "https://api.x.ai/v1", "XAI_API_KEY",
    ),
    "claude-3.5-sonnet": ModelSpec(
        "claude-3.5-sonnet", "anthropic", "claude-3-5-sonnet-latest",
        "https://api.anthropic.com", "ANTHROPIC_API_KEY",
    ),

    # --- offline scripted stub (no endpoint, no key) ------------------------
    # Deterministic canned "model" for smoke-testing the harness + pipeline:
    #   python -m eval.score --stub
    "stub": ModelSpec(
        "stub", "stub", "stub", "", "",
        "Scripted offline stub — structure checks only, not a real model.",
    ),
}


@dataclass(frozen=True)
class Settings:
    deploy_mode: str = os.getenv("DEPLOY_MODE", "cloud")  # "cloud" | "onprem"

    # default model when a request doesn't specify one
    default_model: str = os.getenv("DEFAULT_MODEL", "gpt-4o-mini")
    temperature: float = float(os.getenv("LLM_TEMPERATURE", "0"))
    max_steps: int = int(os.getenv("LLM_MAX_STEPS", "8"))

    # embeddings: "openai" (cloud), "local" (sentence-transformers), "test" (hash, offline)
    embedding_mode: str = os.getenv("EMBEDDING_MODE", "auto")
    embedding_model_openai: str = os.getenv("EMBEDDING_MODEL_OPENAI", "text-embedding-3-small")
    embedding_model_local: str = os.getenv("EMBEDDING_MODEL_LOCAL", "all-MiniLM-L6-v2")

    # data sources
    # DATA_SOURCE selects how structured data is connected:
    #   "upload"   : query files uploaded to the server (DuckDB over UPLOAD_DIR) — demo/SaaS trial
    #   "database" : connect to the customer's own DB via DB_URL (SQLAlchemy) — SaaS/on-prem
    #   "files"    : query a folder of data files on the box (DuckDB over DATA_DIR) — on-prem
    #   "all"      : merge database + uploads + files into one table surface (default)
    data_source: str = os.getenv("DATA_SOURCE", "all")
    db_url: str = os.getenv("DB_URL", "sqlite:///ecommerce_large.db")
    data_dir: str = os.getenv("DATA_DIR", "./data")          # on-prem data files (csv/parquet)
    upload_dir: str = os.getenv("UPLOAD_DIR", "./uploads")   # files uploaded via the UI
    enable_uploads: bool = os.getenv("ENABLE_UPLOADS", "1") == "1"  # turn off for locked-down on-prem
    sql_row_limit: int = int(os.getenv("SQL_ROW_LIMIT", "5000"))
    docs_dir: str = os.getenv("DOCS_DIR", "./documents")     # unstructured corpus
    schema_top_k: int = int(os.getenv("SCHEMA_TOP_K", "6"))  # tables retrieved per question
    doc_top_k: int = int(os.getenv("DOC_TOP_K", "5"))        # chunks retrieved per question

    # --- SCAFFOLDING TOGGLES (the thesis independent variable) --------------
    # Each switch turns one layer of deterministic scaffolding on/off so the eval
    # can measure accuracy vs. scaffolding-level across model sizes. All default
    # ON (full product behaviour); the eval harness flips them per run.
    scaffold_schema_rag: bool = os.getenv("SCAFFOLD_SCHEMA_RAG", "1") == "1"
    scaffold_validate_chart: bool = os.getenv("SCAFFOLD_VALIDATE_CHART", "1") == "1"
    scaffold_repair: bool = os.getenv("SCAFFOLD_REPAIR", "1") == "1"      # feed tool errors back for a retry
    scaffold_glossary: bool = os.getenv("SCAFFOLD_GLOSSARY", "1") == "1"  # inject metric definitions
    scaffold_router: bool = os.getenv("SCAFFOLD_ROUTER", "1") == "1"      # intent routing vs. always-structured
    glossary_path: str = os.getenv("GLOSSARY_PATH", "./glossary.json")

    # --- multi-tenancy + security ------------------------------------------
    # MULTI_TENANT=0 (default): single implicit tenant, no auth (on-prem behaviour).
    # MULTI_TENANT=1: per-tenant isolation + API-key auth on every request.
    multi_tenant: bool = os.getenv("MULTI_TENANT", "0") == "1"
    tenants_file: str = os.getenv("TENANTS_FILE", "./tenants/tenants.json")
    tenants_root: str = os.getenv("TENANTS_ROOT", "./tenants")
    admin_token: str = os.getenv("ADMIN_TOKEN", "")          # required to create tenants
    cors_origins: str = os.getenv("CORS_ORIGINS", "")        # comma-sep allowlist ("" = none)
    rate_limit_per_min: int = int(os.getenv("RATE_LIMIT_PER_MIN", "60"))  # per tenant/IP; 0=off
    max_upload_mb: int = int(os.getenv("MAX_UPLOAD_MB", "50"))

    # accounts / tiers
    accounts_db: str = os.getenv("ACCOUNTS_DB", "./data/accounts.db")

    @property
    def is_onprem(self) -> bool:
        return self.deploy_mode == "onprem"

    def scaffold_label(self) -> str:
        """Compact id for the active scaffolding combo (for eval logging)."""
        bits = [
            ("rag", self.scaffold_schema_rag), ("val", self.scaffold_validate_chart),
            ("rep", self.scaffold_repair), ("glo", self.scaffold_glossary),
            ("rou", self.scaffold_router),
        ]
        on = [name for name, v in bits if v]
        return "+".join(on) if on else "none"


# Mutable singleton so the eval harness can flip flags per run.
settings = Settings()


def apply_scaffold(level: dict) -> None:
    """Override scaffolding flags at runtime (used by the eval harness).
    level: {"schema_rag": bool, "validate_chart": bool, "repair": bool,
            "glossary": bool, "router": bool}. Missing keys keep current value."""
    global settings
    import dataclasses
    settings = dataclasses.replace(
        settings,
        scaffold_schema_rag=level.get("schema_rag", settings.scaffold_schema_rag),
        scaffold_validate_chart=level.get("validate_chart", settings.scaffold_validate_chart),
        scaffold_repair=level.get("repair", settings.scaffold_repair),
        scaffold_glossary=level.get("glossary", settings.scaffold_glossary),
        scaffold_router=level.get("router", settings.scaffold_router),
    )


# ---------------------------------------------------------------------------
# Live inference settings (sampling params). Held as a mutable singleton so the
# settings UI can calibrate them at runtime without redeploying. Per-request
# overrides merge on top of these (see core/inference.py).
# ---------------------------------------------------------------------------
from core.inference import InferenceSettings  # noqa: E402

inference = InferenceSettings()


def update_inference(overrides: dict) -> InferenceSettings:
    """Apply UI/API changes to the live inference settings (validated + clamped)."""
    global inference
    inference = inference.merged(overrides)
    return inference


# ---------------------------------------------------------------------------
# PLANS — the cloud tier definitions (pricing lives on the website; the app
# enforces capability + credits). A question = 1 credit; a deck export = 10.
# memory: whether conversation history is re-fed to the model (paid feature).
# dedicated_llm: tenant may point at its own vLLM endpoint (company tier).
# ---------------------------------------------------------------------------
PLANS: dict[str, dict] = {
    "free":     {"label": "Explore",  "credits_month": 15,   "memory": False, "dedicated_llm": False, "deck_export": False, "max_upload_mb": 5,
                 "price": "€0",            "price_note": "forever",
                 "blurb": "Try it on your own files. 15 questions a month."},
    "analyst":  {"label": "Analyst",  "credits_month": 300,  "memory": True,  "dedicated_llm": False, "deck_export": True,  "max_upload_mb": 20,
                 "price": "€29",           "price_note": "per user / month",
                 "blurb": "For the person who answers everyone's data questions. 300 credits, decks, session memory."},
    "business": {"label": "Team", "credits_month": 3000, "memory": True,  "dedicated_llm": True,  "deck_export": True,  "max_upload_mb": 100,
                 "price": "€940",          "price_note": "per month, up to 10 users",
                 "blurb": "Your team, your dedicated private model endpoint. 3000 pooled credits."},
}
DECK_CREDITS = 10


def plan_of(name: str) -> dict:
    return PLANS.get(name or "free", PLANS["free"])
