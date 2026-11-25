"""CLI entrypoint for running the structured invoice extraction benchmark."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .evaluator import run_benchmark
from .extractors import extract_with_ollama, extract_with_repair_guardrails
from .generator import generate_synthetic_invoices
from .plotting import render_invoice_eval_dashboard


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="invoice-eval",
        description="Structured SME invoice extraction benchmark and Pydantic reconciliation harness",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_eval = sub.add_parser("eval", help="Run the 60-invoice multi-layout benchmark and render chart")
    p_eval.add_argument("--n-docs", type=int, default=60)
    p_eval.add_argument("--output-dir", type=Path, default=Path("outputs"))
    p_eval.add_argument("--chart-path", type=Path, default=Path("assets/invoice_eval_overview.png"))

    p_parse = sub.add_parser("parse-sample", help="Run guardrail parser (or optional Ollama) on a sample doc")
    p_parse.add_argument("--doc-index", type=int, default=0)
    p_parse.add_argument("--ollama-model", type=str, default=None)

    args = parser.parse_args()
    if args.command == "eval":
        args.output_dir.mkdir(parents=True, exist_ok=True)
        report = run_benchmark(n_docs=args.n_docs, seed=42)
        render_invoice_eval_dashboard(report, output_path=args.chart_path)
        (args.output_dir / "invoice_eval_report.json").write_text(
            json.dumps(report, indent=2), encoding="utf-8"
        )
        print(json.dumps(report, indent=2))
    elif args.command == "parse-sample":
        docs = generate_synthetic_invoices(n_docs=60, seed=42)
        doc = docs[args.doc_index]
        if args.ollama_model:
            res = extract_with_ollama(doc.raw_text, doc_id=doc.doc_id, model=args.ollama_model)
        else:
            res = extract_with_repair_guardrails(doc)
        print(json.dumps(res.model_dump(), indent=2))


if __name__ == "__main__":
    main()
