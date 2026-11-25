"""Automated tests for multi-locale parsing, OCR repair, accounting traps, and benchmark."""

from __future__ import annotations

from invoice_eval.evaluator import run_benchmark
from invoice_eval.extractors import (
    extract_with_repair_guardrails,
    parse_multilocale_number,
)
from invoice_eval.generator import generate_synthetic_invoices


def test_multilocale_number_and_ocr_repair() -> None:
    assert parse_multilocale_number("1.250,50 €") == (1250.50, False)
    assert parse_multilocale_number("EUR 1,250.50") == (1250.50, False)
    assert parse_multilocale_number("2.O50,00 EUR", fix_ocr=True) == (2050.00, True)
    assert parse_multilocale_number("2.O50,00 EUR", fix_ocr=False) == (None, False)


def test_accounting_error_traps_are_never_auto_approved() -> None:
    docs = generate_synthetic_invoices(n_docs=60, seed=42)
    traps = [d for d in docs if d.has_accounting_error]
    assert len(traps) == 6

    for trap in traps:
        res = extract_with_repair_guardrails(trap)
        assert res.reconciliation_status == "NEEDS_HUMAN_REVIEW"
        assert any("ACCOUNTING_MISMATCH" in err for err in res.validation_errors)


def test_schema_repair_pipeline_beats_baselines_with_zero_bad_auto_posts() -> None:
    report = run_benchmark(n_docs=60, seed=42)
    naive = report["pipelines"]["naive_regex"]
    val = report["pipelines"]["validated_structured"]
    rep = report["pipelines"]["schema_repair_guardrails"]

    assert rep["micro_f1"] == 1.0
    assert rep["doc_exact_match_rate"] == 1.0
    assert rep["clean_stp_rate"] == 1.0
    assert rep["accounting_error_catch_rate"] == 1.0
    assert rep["corrupted_invoices_auto_posted"] == 0
    assert rep["repaired_and_approved"] >= 5

    # Must strictly outperform both naive regex and non-repair validated pipeline on OCR docs
    assert rep["doc_exact_match_rate"] > val["doc_exact_match_rate"] > naive["doc_exact_match_rate"]
    assert naive["corrupted_invoices_auto_posted"] >= 1
