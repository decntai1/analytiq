"""
Inference settings — the sampling/decoding parameters passed to whichever runtime
serves the brain's model. Mirrors what LM Studio / Open WebUI expose.

These are RUNTIME parameters (how the model decodes), distinct from app Settings
(deploy mode, scaffolding, security). They're held separately so the UI can let an
operator calibrate them live without touching deployment config, and so different
runtimes (Ollama, your Analytiq runtime, vLLM) receive them through one shape.

Defaults are tuned for analytics: temperature 0 (deterministic SQL/answers). Bump
temperature only if you want more varied phrasing in narrative answers — never for
the SQL-writing path, where determinism is correctness.

PARAM_META drives the settings UI: label, range, step, and a plain-English
explanation of what each control does. Not every runtime honors every parameter
(e.g. some ignore top_k); unknown params are passed through and safely dropped by
runtimes that don't use them.
"""
from __future__ import annotations

import os
from dataclasses import asdict, dataclass


@dataclass
class InferenceSettings:
    temperature: float = float(os.getenv("LLM_TEMPERATURE", "0"))
    top_p: float = float(os.getenv("LLM_TOP_P", "1.0"))
    top_k: int = int(os.getenv("LLM_TOP_K", "0"))            # 0 = disabled
    max_tokens: int = int(os.getenv("LLM_MAX_TOKENS", "2048"))
    presence_penalty: float = float(os.getenv("LLM_PRESENCE_PENALTY", "0"))
    frequency_penalty: float = float(os.getenv("LLM_FREQUENCY_PENALTY", "0"))
    repeat_penalty: float = float(os.getenv("LLM_REPEAT_PENALTY", "1.1"))  # ollama/llama.cpp
    seed: int = int(os.getenv("LLM_SEED", "0"))              # 0 = random
    stop: str = os.getenv("LLM_STOP", "")                    # comma-sep stop strings

    def to_openai_kwargs(self) -> dict:
        """Map to OpenAI-compatible chat-completions params. Only emit non-defaults
        that the OpenAI schema accepts; runtime-specific ones go via extra_body."""
        kw: dict = {
            "temperature": self.temperature,
            "top_p": self.top_p,
            "max_tokens": self.max_tokens,
        }
        if self.presence_penalty:
            kw["presence_penalty"] = self.presence_penalty
        if self.frequency_penalty:
            kw["frequency_penalty"] = self.frequency_penalty
        if self.seed:
            kw["seed"] = self.seed
        if self.stop:
            kw["stop"] = [s for s in (x.strip() for x in self.stop.split(",")) if s]
        # runtime-specific (Ollama/vLLM/your runtime read these from extra_body)
        extra: dict = {}
        if self.top_k:
            extra["top_k"] = self.top_k
        if self.repeat_penalty and self.repeat_penalty != 1.0:
            extra["repeat_penalty"] = self.repeat_penalty
        if extra:
            kw["extra_body"] = extra
        return kw

    def merged(self, overrides: dict | None) -> "InferenceSettings":
        """Return a copy with per-request overrides applied (validated/clamped)."""
        if not overrides:
            return self
        d = asdict(self)
        for k, v in overrides.items():
            if k in d and v is not None:
                d[k] = v
        s = InferenceSettings(**d)
        return s.clamped()

    def clamped(self) -> "InferenceSettings":
        self.temperature = _clip(self.temperature, 0.0, 2.0)
        self.top_p = _clip(self.top_p, 0.0, 1.0)
        self.top_k = int(_clip(self.top_k, 0, 200))
        self.max_tokens = int(_clip(self.max_tokens, 16, 32000))
        self.presence_penalty = _clip(self.presence_penalty, -2.0, 2.0)
        self.frequency_penalty = _clip(self.frequency_penalty, -2.0, 2.0)
        self.repeat_penalty = _clip(self.repeat_penalty, 0.5, 2.0)
        return self


def _clip(v, lo, hi):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return lo
    return max(lo, min(hi, v))


# Drives the settings UI. Each entry: control type + range + plain-English help.
PARAM_META = [
    {"key": "temperature", "label": "Temperature", "type": "slider",
     "min": 0, "max": 2, "step": 0.05, "default": 0,
     "help": "Randomness of word choice. 0 = deterministic and repeatable — best for "
             "SQL and factual answers. Higher = more varied phrasing, but also more "
             "risk of wrong queries. Keep low for analytics."},
    {"key": "top_p", "label": "Top-P (nucleus)", "type": "slider",
     "min": 0, "max": 1, "step": 0.01, "default": 1.0,
     "help": "Limits choices to the most likely tokens whose probabilities sum to P. "
             "1.0 = no limit. Lower (e.g. 0.9) trims unlikely words. Usually leave at "
             "1.0 and control variety with temperature instead."},
    {"key": "top_k", "label": "Top-K", "type": "number",
     "min": 0, "max": 200, "step": 1, "default": 0,
     "help": "Only consider the K most likely next tokens. 0 = disabled. Small values "
             "(e.g. 40) make output more focused. Not all runtimes honor this."},
    {"key": "max_tokens", "label": "Max output tokens", "type": "number",
     "min": 16, "max": 32000, "step": 16, "default": 2048,
     "help": "Cap on how long a single response can be. Raise it for long narrative "
             "answers or big tables; lower it to keep responses tight and faster."},
    {"key": "repeat_penalty", "label": "Repeat penalty", "type": "slider",
     "min": 0.5, "max": 2, "step": 0.05, "default": 1.1,
     "help": "Discourages repeating the same words/phrases. ~1.1 is a good default. "
             "Too high can make text stilted. (Local runtimes / llama.cpp / Ollama.)"},
    {"key": "presence_penalty", "label": "Presence penalty", "type": "slider",
     "min": -2, "max": 2, "step": 0.1, "default": 0,
     "help": "Positive values push the model toward introducing new topics rather than "
             "dwelling on ones already mentioned. Mostly cosmetic for analytics."},
    {"key": "frequency_penalty", "label": "Frequency penalty", "type": "slider",
     "min": -2, "max": 2, "step": 0.1, "default": 0,
     "help": "Positive values reduce verbatim repetition of frequent tokens. Leave at "
             "0 unless answers feel repetitive."},
    {"key": "seed", "label": "Seed", "type": "number",
     "min": 0, "max": 2147483647, "step": 1, "default": 0,
     "help": "Fix the random seed for reproducible outputs (same input → same output). "
             "0 = random each time. Set a value when you need repeatable demos or evals."},
    {"key": "stop", "label": "Stop sequences", "type": "text", "default": "",
     "help": "Comma-separated strings that, if generated, end the response early. "
             "Usually left empty. Advanced use only."},
]
