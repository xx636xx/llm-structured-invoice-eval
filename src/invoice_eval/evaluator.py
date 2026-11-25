"""Field-level Precision/Recall/F1, exact-match, and accounting-discrepancy benchmark."""

from __future__ import annotations

from collections import Counter
from typing import Any, Callable

import numpy as np

from .extractors import (
    extract_naive_regex,
    extract_validated_structured,
    extract_with_repair_guardrails,
)
from .generator import generate_synthetic_invoices
from .schemas import ExtractedInvoice, GroundTruthInvoice

EVAL_FIELDS = (
    "invoice_number",
    "issue_date",
    "supplier_tax_id",
    "subtotal",
    "vat_amount",
    "total",
)


def _field_matches(gt_val: Any, pred_val: Any) -> bool:
    if pred_val is None:
        return False
    if isinstance(gt_val, float):
        return abs(float(gt_val) - float(pred_val)) <= 0.01
    return str(gt_val).strip() == str(pred_val).strip()


def evaluate_pipeline(
    name: str,
    extractor_fn: Callable[[GroundTruthInvoice], ExtractedInvoice],
    docs: list[GroundTruthInvoice],
) -> dict[str, Any]:
    preds = [extractor_fn(d) for d in docs]

    # Field-level precision / recall / F1
    field_metrics: dict[str, dict[str, float]] = {}
    total_tp = total_fp = total_fn = 0

    for field in EVAL_FIELDS:
        tp = fp = fn = 0
        for gt, pr in zip(docs, preds):
            gt_v = getattr(gt, field)
            pr_v = getattr(pr, field)
            if pr_v is None:
                fn += 1
            elif _field_matches(gt_v, pr_v):
                tp += 1
            else:
                fp += 1
                fn += 1
        prec = tp / (tp + fp) if (tp + fp) else 0.0
        rec = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = (2 * prec * rec / (prec + rec)) if (prec + rec) else 0.0
        field_metrics[field] = {
            "precision": round(prec, 4),
            "recall": round(rec, 4),
            "f1": round(f1, 4),
        }
        total_tp += tp
        total_fp += fp
        total_fn += fn

    micro_p = total_tp / (total_tp + total_fp) if (total_tp + total_fp) else 0.0
    micro_r = total_tp / (total_tp + total_fn) if (total_tp + total_fn) else 0.0
    micro_f1 = (2 * micro_p * micro_r / (micro_p + micro_r)) if (micro_p + micro_r) else 0.0

    # Document exact match across all 6 core fields
    exact_matches = sum(
        1
        for gt, pr in zip(docs, preds)
        if all(_field_matches(getattr(gt, f), getattr(pr, f)) for f in EVAL_FIELDS)
    )

    # Exact match by layout style
    by_layout: dict[str, float] = {}
    for layout in ("eu_spanish", "english_standard", "ocr_noisy", "compact_table"):
        pairs = [(gt, pr) for gt, pr in zip(docs, preds) if gt.layout_style == layout]
        if pairs:
            ok = sum(
                1
                for gt, pr in pairs
                if all(_field_matches(getattr(gt, f), getattr(pr, f)) for f in EVAL_FIELDS)
            )
            by_layout[layout] = round(ok / len(pairs), 4)

    # Accounting error trap detection & safe straight-through processing (STP) rate
    err_docs = [(gt, pr) for gt, pr in zip(docs, preds) if gt.has_accounting_error]
    clean_docs = [(gt, pr) for gt, pr in zip(docs, preds) if not gt.has_accounting_error]

    caught_accounting_errors = sum(
        1 for _gt, pr in err_docs if pr.reconciliation_status == "NEEDS_HUMAN_REVIEW"
    )
    corrupted_auto_approved = sum(
        1 for _gt, pr in err_docs if pr.reconciliation_status != "NEEDS_HUMAN_REVIEW"
    )
    clean_auto_approved = sum(
        1 for _gt, pr in clean_docs if pr.reconciliation_status in ("AUTO_APPROVED", "REPAIRED_AND_APPROVED")
    )
    repaired_count = sum(1 for pr in preds if pr.reconciliation_status == "REPAIRED_AND_APPROVED")
    status_counts = dict(Counter(pr.reconciliation_status for pr in preds))

    return {
        "pipeline": name,
        "micro_precision": round(micro_p, 4),
        "micro_recall": round(micro_r, 4),
        "micro_f1": round(micro_f1, 4),
        "doc_exact_match_rate": round(exact_matches / len(docs), 4),
        "exact_match_by_layout": by_layout,
        "accounting_error_catch_rate": round(caught_accounting_errors / len(err_docs), 4),
        "corrupted_invoices_auto_posted": corrupted_auto_approved,
        "clean_stp_rate": round(clean_auto_approved / len(clean_docs), 4),
        "repaired_and_approved": repaired_count,
        "status_counts": status_counts,
        "mean_latency_ms": round(float(np.mean([p.latency_ms for p in preds])), 3),
        "field_metrics": field_metrics,
        "sample_outputs": [
            preds[0].model_dump(),
            preds[2].model_dump(),
            preds[7].model_dump(),  # Accounting discrepancy trap
        ],
    }


def run_benchmark(n_docs: int = 60, seed: int = 42) -> dict[str, Any]:
    docs = generate_synthetic_invoices(n_docs=n_docs, seed=seed)
    pipelines = [
        ("naive_regex", extract_naive_regex),
        ("validated_structured", extract_validated_structured),
        ("schema_repair_guardrails", extract_with_repair_guardrails),
    ]
    results = {name: evaluate_pipeline(name, fn, docs) for name, fn in pipelines}
    return {
        "dataset_summary": {
            "total_invoices": len(docs),
            "clean_invoices": sum(1 for d in docs if not d.has_accounting_error),
            "accounting_error_traps": sum(1 for d in docs if d.has_accounting_error),
            "layouts": dict(Counter(d.layout_style for d in docs)),
        },
        "pipelines": results,
    }
