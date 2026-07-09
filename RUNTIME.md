# Model Runtimes — demo vs. production

Analytiq's brain talks ONLY to an OpenAI-compatible chat endpoint (`base_url` + `/v1`).
Whatever serves that contract serves the model — so the serving backend is a clean
swap with **zero changes** to the app. Selected by `LLM_RUNTIME`.

| LLM_RUNTIME | backend | used for | data boundary |
|-------------|---------|----------|---------------|
| `ollama` (default) | Ollama container | online demo, simple installs | local |
| `analytiq` | **your** runtime (DEcntAI-derived) on the customer's box | real/paid deployments | **customer's hardware — never leaves** |
| `custom` | any OpenAI-compatible server (vLLM/TGI) | flexibility | wherever you run it |

## Demo (free, easy)
`LLM_RUNTIME=ollama` (default). The on-prem compose starts Ollama and pulls the model.
Nothing to build. This is what the online demo uses.

## Production (your runtime, on the customer's hardware)
`LLM_RUNTIME=analytiq` + `ANALYTIQ_RUNTIME_URL=http://<your-runtime>:8000/v1`.
Your DEcntAI-derived text-gen runtime runs on the **customer's** GPU box, tuned to
their hardware (quantization, VRAM packing, batching, model choice). The app connects
to it over the customer's own network. Their data never leaves their boundary — your
runtime is code on their machine, not a shared network.

Use `docker-compose.prod-onprem-runtime.yml`: either add your runtime as a service
(option A, with GPU passthrough) or point `ANALYTIQ_RUNTIME_URL` at a runtime you run
separately (option B).

### The contract your runtime must satisfy
So a new model/runtime "just works" with the brain, your runtime must:
- Expose `POST {base_url}/chat/completions` (OpenAI chat-completions shape).
- Accept `model, messages, temperature, top_p, max_tokens, tools, tool_choice`, and
  pass through `extra_body` params it supports (`top_k, repeat_penalty, seed`).
- Return `choices[0].message` with optional `tool_calls` in OpenAI format.
- Be reachable at its `base_url` from the app.

That's the entire interface. Ollama, vLLM, TGI, and your runtime all meet it.

**Adding a new model = a runtime that serves it + a `MODEL_REGISTRY` entry + an eval
run.** The runtime makes it *run*; the gold-set eval (`eval/score.py`) confirms it runs
*accurately enough* to put in front of a customer. Never ship a model customer-facing
without the eval pass — a runtime can serve a model that quietly writes wrong SQL.

## Inference settings (live, in the UI)
The workspace ⚙ panel (and `/settings/inference`) calibrates sampling params —
temperature, top_p, top_k, max_tokens, repeat/presence/frequency penalty, seed, stop —
like LM Studio / Open WebUI, each with an explanation. Changes apply to the next
question, no restart. Standard params go through the OpenAI schema; runtime-specific
ones (`top_k`, `repeat_penalty`) ride in `extra_body` so any runtime that honors them
gets them and others safely ignore them.

**For analytics, keep temperature at 0** on the SQL-writing path — determinism is
correctness there. Raise it only for narrative phrasing if you want more variety.
