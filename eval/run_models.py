"""
Thesis eval harness — run the SAME question across MANY models and compare.

This is the reasoning-comparison tool your thesis needs: it sweeps a list of
registered model names through the identical pipeline (same schema-RAG, same
tools, same data) so the only variable is the model. Captures the answer, the SQL
the model wrote, whether it produced a valid chart, and latency.

Usage:
    python -m eval.run_models "Why were Q3 sales weak?" qwen2.5-14b gpt-4o-mini claude-3.5-sonnet

On your 16GB box you might compare local models; on a rented GPU box add the
bigger entries to the registry and include them here.
"""
from __future__ import annotations

import sys
import time

from connectors.sql import SQLConnector
from core.embeddings import get_embedder
from core.orchestrator import Orchestrator
from index.doc_index import DocIndex
from index.schema_index import SchemaIndex
from config import settings


def build_orchestrator() -> Orchestrator:
    emb = get_embedder()
    conn = SQLConnector()
    si = SchemaIndex(emb)
    si.build(conn.schema_by_table())
    di = DocIndex(emb)
    di.ingest_dir(settings.docs_dir)
    return Orchestrator(conn, si, di)


def main() -> None:
    if len(sys.argv) < 3:
        print('Usage: python -m eval.run_models "<question>" <model1> <model2> ...')
        raise SystemExit(1)
    question = sys.argv[1]
    models = sys.argv[2:]
    orch = build_orchestrator()

    print(f"\nQUESTION: {question}\n" + "=" * 72)
    for model in models:
        t0 = time.time()
        try:
            r = orch.ask(question, model_name=model)
            dt = time.time() - t0
            print(f"\n### {model}   ({dt:.1f}s, arm={r['plan']['arm']}, "
                  f"charts={len(r['charts'])}, sql={len(r['sql_log'])})")
            print(f"ANSWER: {r['answer'][:800]}")
            if r["sql_log"]:
                print(f"SQL:    {r['sql_log'][0][:200]}")
        except Exception as e:
            print(f"\n### {model}   ERROR: {e}")
    print("\n" + "=" * 72)


if __name__ == "__main__":
    main()
