"""
Runtime layer — WHERE the brain's model is served.

Analytiq's brain only ever speaks the OpenAI-compatible chat API (base_url + /v1).
Anything that exposes that contract can serve it, so the serving backend is a clean
swap with ZERO changes to the orchestrator, connectors, or pipeline.

Two backends ship:
  - "ollama"   : the demo / quick-start default. Free, one command, just works.
                 Used for the online demo and simple installs.
  - "analytiq" : YOUR runtime (the DEcntAI-derived text-gen serving architecture),
                 running ON THE CUSTOMER'S hardware. Used for real/paid deployments
                 where you tune the model to the customer's box. Data never leaves
                 their boundary — your runtime code runs on their machine, not on any
                 shared network.

Both satisfy the same contract below. Selection is by LLM_RUNTIME (env) and each
runtime just resolves to a base_url; the registry/provider layer is unchanged.

THE CONTRACT a runtime must satisfy (so a new backend "just works"):
  - Expose POST {base_url}/chat/completions (OpenAI chat-completions shape).
  - Accept: model, messages, temperature, top_p, max_tokens, tools, tool_choice,
    and pass through extra_body params (top_k, repeat_penalty, seed) it supports.
  - Return choices[0].message with optional tool_calls in OpenAI format.
  - Be reachable at its base_url from the app container/host.
That's it. Ollama, vLLM, TGI, and your runtime all meet this.
"""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class RuntimeInfo:
    name: str           # "ollama" | "analytiq" | "custom"
    base_url: str       # OpenAI-compatible endpoint
    label: str          # human label for UI/health
    managed: bool       # True if Analytiq starts/stops it (ollama in compose)
    notes: str = ""


def active_runtime() -> RuntimeInfo:
    """Resolve the configured serving backend.

    LLM_RUNTIME selects:
      ollama   -> OLLAMA_BASE_URL (default http://ollama:11434/v1 in compose,
                  http://localhost:11434/v1 bare)
      analytiq -> ANALYTIQ_RUNTIME_URL (your runtime on the customer's box)
      custom   -> CUSTOM_RUNTIME_URL (any OpenAI-compatible server: vLLM/TGI/...)
    """
    kind = os.getenv("LLM_RUNTIME", "ollama").lower()

    if kind == "analytiq":
        url = os.getenv("ANALYTIQ_RUNTIME_URL", "http://analytiq-runtime:8000/v1")
        return RuntimeInfo("analytiq", url, "Analytiq runtime (on-prem, your hardware)",
                           managed=False,
                           notes="DEcntAI-derived text-gen runtime on the customer's box.")
    if kind == "custom":
        url = os.getenv("CUSTOM_RUNTIME_URL", "http://localhost:8000/v1")
        return RuntimeInfo("custom", url, "Custom OpenAI-compatible runtime",
                           managed=False, notes="vLLM / TGI / any OpenAI-compatible server.")
    # default: ollama (demo / quick-start)
    url = os.getenv("OLLAMA_BASE_URL",
                    os.getenv("LOCAL_LLM_BASE_URL", "http://localhost:11434/v1"))
    return RuntimeInfo("ollama", url, "Ollama (demo / quick-start)",
                       managed=True, notes="Free local runtime; default for demo + simple installs.")


def local_base_url() -> str:
    """The base_url every LOCAL model in the registry should point at.

    Lets the registry stay generic: local ModelSpecs read this so switching the
    runtime (ollama <-> analytiq) repoints all local models at once, no registry edit.
    """
    return active_runtime().base_url
