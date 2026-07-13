import os
from openai import OpenAI

c = OpenAI(base_url="https://ollama.com/v1", api_key=os.environ["OLLAMA_API_KEY"])
TOOLS = [{"type": "function", "function": {
    "name": "run_sql", "description": "Execute read-only SQL and return rows.",
    "parameters": {"type": "object", "properties": {"query": {"type": "string"}},
                   "required": ["query"]}}}]
msgs = [
    {"role": "system", "content": "You are an analytics agent. Table: sales(revenue REAL). Use the run_sql tool to answer."},
    {"role": "user", "content": "What is the total revenue across all sales?"},
]
CANDIDATES = ["qwen3-coder-next", "devstral-small-2:24b", "devstral-2:123b", "kimi-k2.7-code"]
for m in CANDIDATES:
    try:
        r = c.chat.completions.create(model=m, messages=msgs, tools=TOOLS,
                                      tool_choice="auto", temperature=0)
        msg = r.choices[0].message
        tcs = msg.tool_calls or []
        if tcs:
            print(f"{m:22} TOOL-OK   -> {tcs[0].function.name}({tcs[0].function.arguments})")
        else:
            snippet = (msg.content or "")[:80]
            print(f"{m:22} NO-TOOLCALL  content={snippet!r}")
    except Exception as e:
        print(f"{m:22} ERROR  {type(e).__name__}: {str(e)[:120]}")
