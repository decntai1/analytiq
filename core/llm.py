"""
LLM provider abstraction — multi-model, swappable, per-request selectable.

Two adapters implement one interface (`chat`):
  - OpenAICompatibleProvider: OpenAI, Grok/xAI, Ollama, vLLM, Together, DeepSeek...
  - AnthropicProvider:        Claude (native tool-calling translated to our shape)

`get_provider(model_name)` resolves a registry entry to the right adapter, so the
rest of the system is model-agnostic. The thesis eval harness sweeps model names
through this single call.

Scale-up note: to add 100+ providers with no new adapter code, drop in `litellm`
and route everything through it — the interface here stays identical.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

from config import MODEL_REGISTRY, ModelSpec


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: str  # JSON string


@dataclass
class LLMResponse:
    content: str | None
    tool_calls: list[ToolCall]


class BaseProvider:
    def chat(self, messages: list[dict], tools: list[dict] | None = None) -> LLMResponse:
        raise NotImplementedError


# --------------------------------------------------------------------------- #
# OpenAI-compatible (covers OpenAI, Grok, Ollama, vLLM, and most local servers)
# --------------------------------------------------------------------------- #
class OpenAICompatibleProvider(BaseProvider):
    def __init__(self, spec: ModelSpec, inference: Any = None) -> None:
        from openai import OpenAI
        key = os.getenv(spec.api_key_env, "") if spec.api_key_env else "local"
        self._client = OpenAI(base_url=spec.base_url, api_key=key or "local")
        self.model_id = spec.model_id
        self._inference = inference  # optional per-request InferenceSettings

    def chat(self, messages: list[dict], tools: list[dict] | None = None) -> LLMResponse:
        import config
        inf = self._inference or config.inference  # live settings unless overridden
        kwargs: dict[str, Any] = {"model": self.model_id, "messages": messages}
        kwargs.update(inf.to_openai_kwargs())
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        msg = self._client.chat.completions.create(**kwargs).choices[0].message
        tcs = [
            ToolCall(id=tc.id, name=tc.function.name, arguments=tc.function.arguments or "{}")
            for tc in (msg.tool_calls or [])
        ]
        return LLMResponse(content=msg.content, tool_calls=tcs)


# --------------------------------------------------------------------------- #
# Anthropic native (Claude). Translates OpenAI-style messages/tools <-> Anthropic.
# --------------------------------------------------------------------------- #
class AnthropicProvider(BaseProvider):
    def __init__(self, spec: ModelSpec) -> None:
        from anthropic import Anthropic
        self._client = Anthropic(api_key=os.getenv(spec.api_key_env, ""))
        self.model_id = spec.model_id

    @staticmethod
    def _to_anthropic_tools(tools: list[dict] | None) -> list[dict]:
        out = []
        for t in tools or []:
            fn = t["function"]
            out.append({
                "name": fn["name"],
                "description": fn.get("description", ""),
                "input_schema": fn.get("parameters", {"type": "object", "properties": {}}),
            })
        return out

    @staticmethod
    def _split_messages(messages: list[dict]) -> tuple[str, list[dict]]:
        """Pull out the system prompt; convert the rest to Anthropic message blocks."""
        system = ""
        conv: list[dict] = []
        for m in messages:
            role = m["role"]
            if role == "system":
                system += (m.get("content") or "") + "\n"
                continue
            if role == "tool":
                conv.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": m["tool_call_id"],
                        "content": m.get("content") or "",
                    }],
                })
                continue
            if role == "assistant" and m.get("tool_calls"):
                blocks: list[dict] = []
                if m.get("content"):
                    blocks.append({"type": "text", "text": m["content"]})
                for tc in m["tool_calls"]:
                    blocks.append({
                        "type": "tool_use",
                        "id": tc["id"],
                        "name": tc["function"]["name"],
                        "input": json.loads(tc["function"]["arguments"] or "{}"),
                    })
                conv.append({"role": "assistant", "content": blocks})
                continue
            conv.append({"role": role, "content": m.get("content") or ""})
        return system.strip(), conv

    def chat(self, messages: list[dict], tools: list[dict] | None = None) -> LLMResponse:
        import config
        inf = config.inference
        system, conv = self._split_messages(messages)
        resp = self._client.messages.create(
            model=self.model_id,
            max_tokens=int(inf.max_tokens),
            temperature=inf.temperature,
            top_p=inf.top_p,
            system=system or None,
            messages=conv,
            tools=self._to_anthropic_tools(tools) or None,
        )
        text_parts, tcs = [], []
        for block in resp.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tcs.append(ToolCall(id=block.id, name=block.name,
                                    arguments=json.dumps(block.input)))
        return LLMResponse(content="".join(text_parts) or None, tool_calls=tcs)


# --------------------------------------------------------------------------- #
# Scripted stub — the offline "model" behind `eval.score --stub`.
# Deterministically walks the whole pipeline (router -> run_sql -> make_chart ->
# search_documents -> final answer) using keyword rules, so the harness and
# orchestrator can be smoke-tested with NO endpoint and NO key. It checks
# STRUCTURE only; it says nothing about any real model's accuracy.
# --------------------------------------------------------------------------- #
class ScriptedStubProvider(BaseProvider):
    _CHART_WORDS = ("chart", "plot", "graph", "line", "bar", "pie", "scatter", "trend", "top ")
    _DOC_WORDS = ("why", "policy", "explain", "reason", "document", "notes")

    def chat(self, messages: list[dict], tools: list[dict] | None = None) -> LLMResponse:
        system = messages[0]["content"] if messages and messages[0].get("role") == "system" else ""
        user_q = next((m.get("content") or "" for m in messages if m.get("role") == "user"), "")
        ql = user_q.lower()

        # 1) the router's classify call
        if system.startswith("Classify a business question"):
            arm = "both" if any(w in ql for w in self._DOC_WORDS) else "structured"
            wants_chart = any(w in ql for w in self._CHART_WORDS)
            return LLMResponse(json.dumps({"arm": arm, "wants_chart": wants_chart}), [])

        # 2) agent loop — pick the next action from what was already ATTEMPTED
        # (attempted = a prior assistant tool_call, whether or not it succeeded;
        #  a scripted stub must never blind-retry a failing action, or with
        #  scaffold_repair off it would spin until max_steps burning err counts)
        attempted = {tc["function"]["name"]
                     for m in messages if m.get("role") == "assistant"
                     for tc in (m.get("tool_calls") or [])}

        if "run_sql" not in attempted:
            table, first_col = self._pick_table(system, ql)
            q = f'SELECT "{first_col}" AS x, COUNT(*) AS y FROM "{table}" GROUP BY 1 ORDER BY 1 LIMIT 24'
            return LLMResponse(None, [ToolCall("stub-sql", "run_sql", json.dumps({"query": q}))])

        if "make_chart" not in attempted and any(w in ql for w in self._CHART_WORDS):
            ctype = next((t for t in ("line", "pie", "scatter", "area", "bar") if t in ql), "bar")
            enc = {"category": "x", "value": "y"} if ctype == "pie" else {"x": "x", "y": "y"}
            return LLMResponse(None, [ToolCall("stub-chart", "make_chart", json.dumps(
                {"type": ctype, "title": user_q[:60], "encoding": enc}))])

        if "search_documents" not in attempted and any(w in ql for w in self._DOC_WORDS):
            return LLMResponse(None, [ToolCall("stub-docs", "search_documents",
                                               json.dumps({"query": user_q}))])

        return LLMResponse("Stub answer grounded in tool results (offline smoke test).", [])

    @staticmethod
    def _pick_table(system: str, ql: str) -> tuple[str, str]:
        first = None
        for ln in system.splitlines():
            ln = ln.strip()
            if not ln.startswith("TABLE "):
                continue
            name = ln.split()[1]
            inner = ln[ln.find("(") + 1: ln.find(")")]
            col = inner.split(",")[0].split()[0] if inner else "1"
            first = first or (name, col)
            if name.lower() in ql or name.lower().rstrip("s") in ql:
                return name, col
        return first or ("sales", "month")


# --------------------------------------------------------------------------- #
def get_provider(model_name: str | None = None,
                 spec_override: ModelSpec | None = None) -> BaseProvider:
    import config  # read settings LIVE — module-level binding goes stale after apply_scaffold()
    if spec_override is not None:
        # dedicated per-tenant endpoint (a company's own vLLM box): concurrent
        # users of that company share it via the server's continuous batching.
        if spec_override.provider == "openai_compatible":
            return OpenAICompatibleProvider(spec_override)
        raise ValueError(f"Unsupported override provider {spec_override.provider!r}")
    name = model_name or config.settings.default_model
    if name not in MODEL_REGISTRY:
        raise ValueError(f"Unknown model {name!r}. Registered: {list(MODEL_REGISTRY)}")
    spec = MODEL_REGISTRY[name]
    if spec.provider == "stub":
        return ScriptedStubProvider()
    if spec.provider == "openai_compatible":
        return OpenAICompatibleProvider(spec)
    if spec.provider == "anthropic":
        return AnthropicProvider(spec)
    raise ValueError(f"Unknown provider {spec.provider!r}")
