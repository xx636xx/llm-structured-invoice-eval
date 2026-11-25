"""Pydantic v2 contracts for extracted SME invoices and validation outcomes."""

from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field


class GroundTruthInvoice(BaseModel):
    doc_id: str
    layout_style: Literal["eu_spanish", "english_standard", "ocr_noisy", "compact_table"]
    has_accounting_error: bool
    raw_text: str
    invoice_number: str
    issue_date: str
    supplier_tax_id: str
    subtotal: float
    vat_rate_pct: float
    vat_amount: float
    total: float


class ExtractedInvoice(BaseModel):
    doc_id: str
    pipeline: str
    invoice_number: str | None = None
    issue_date: str | None = None
    supplier_tax_id: str | None = None
    subtotal: float | None = None
    vat_rate_pct: float | None = None
    vat_amount: float | None = None
    total: float | None = None
    reconciliation_status: Literal["AUTO_APPROVED", "REPAIRED_AND_APPROVED", "NEEDS_HUMAN_REVIEW"]
    validation_errors: list[str] = Field(default_factory=list)
    repairs_applied: list[str] = Field(default_factory=list)
    latency_ms: float = 0.0
