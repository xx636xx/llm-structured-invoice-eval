"""Three head-to-head invoice extraction pipelines + optional local Ollama JSON adapter."""

from __future__ import annotations

from datetime import datetime
import json
import re
import time
import urllib.request

from .schemas import ExtractedInvoice, GroundTruthInvoice


def parse_multilocale_number(raw: str | None, fix_ocr: bool = False) -> tuple[float | None, bool]:
    """Parse EU (`1.250,50`) and US (`1,250.50`) amounts with optional OCR O->0 repair."""
    if not raw:
        return None, False
    cleaned = raw.strip().replace("€", "").replace("EUR", "").replace(" ", "")
    repaired = False
    if fix_ocr and ("O" in cleaned or "o" in cleaned):
        cleaned = cleaned.replace("O", "0").replace("o", "0")
        repaired = True

    if not re.fullmatch(r"-?\d[\d.,]*", cleaned):
        return None, False

    if "," in cleaned and "." in cleaned:
        # Whichever separator appears last is the decimal mark
        if cleaned.rfind(",") > cleaned.rfind("."):
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    elif "," in cleaned:
        # EU decimal comma (e.g., 450,25) vs thousands comma
        parts = cleaned.split(",")
        if len(parts[-1]) == 2:
            cleaned = cleaned.replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")

    try:
        return round(float(cleaned), 2), repaired
    except ValueError:
        return None, False


def parse_multilocale_date(raw: str | None) -> str | None:
    if not raw:
        return None
    s = raw.strip()
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _reconcile_accounting(
    subtotal: float | None,
    vat_rate: float | None,
    vat_amount: float | None,
    total: float | None,
    inv_num: str | None,
    issue_date: str | None,
    tax_id: str | None,
    allow_repair: bool,
    repairs: list[str],
) -> tuple[float | None, float | None, float | None, str, list[str]]:
    """Enforce deterministic accounting invariants before ERP auto-posting."""
    errors: list[str] = []

    if not inv_num:
        errors.append("MISSING_INVOICE_NUMBER")
    if not issue_date:
        errors.append("MISSING_OR_INVALID_DATE")
    if not tax_id:
        errors.append("MISSING_TAX_ID")

    # Deterministic repair: recover omitted VAT line ONLY if subtotal * (1 + rate) == total
    if allow_repair and vat_amount is None and subtotal is not None and vat_rate is not None and total is not None:
        inferred_vat = round(subtotal * vat_rate / 100.0, 2)
        if abs((subtotal + inferred_vat) - total) <= 0.02:
            vat_amount = inferred_vat
            repairs.append(f"INFERRED_MISSING_VAT_AMOUNT={inferred_vat:.2f}")

    if subtotal is None:
        errors.append("MISSING_SUBTOTAL")
    if vat_amount is None:
        errors.append("MISSING_VAT_AMOUNT")
    if total is None:
        errors.append("MISSING_TOTAL")

    if subtotal is not None and vat_amount is not None and total is not None:
        expected_total = round(subtotal + vat_amount, 2)
        if abs(expected_total - total) > 0.02:
            errors.append(
                f"ACCOUNTING_MISMATCH: subtotal({subtotal}) + vat({vat_amount}) = {expected_total} != total({total})"
            )
        if vat_rate is not None:
            expected_vat = round(subtotal * vat_rate / 100.0, 2)
            if abs(expected_vat - vat_amount) > 0.05:
                errors.append(
                    f"VAT_RATE_MISMATCH: {vat_rate}% of {subtotal} = {expected_vat} != {vat_amount}"
                )

    if errors:
        return subtotal, vat_amount, total, "NEEDS_HUMAN_REVIEW", errors
    status = "REPAIRED_AND_APPROVED" if repairs else "AUTO_APPROVED"
    return subtotal, vat_amount, total, status, errors


def extract_naive_regex(doc: GroundTruthInvoice) -> ExtractedInvoice:
    """Baseline 1: Single-locale English regex parser with NO accounting guardrail."""
    t0 = time.perf_counter()
    text = doc.raw_text

    inv_m = re.search(r"Invoice Number:\s*([A-Z0-9-]+)", text)
    dt_m = re.search(r"Invoice Date:\s*(\d{4}-\d{2}-\d{2})", text)
    tax_m = re.search(r"VAT ID:\s*([A-Z0-9]+)", text)
    sub_m = re.search(r"Subtotal:\s*(?:EUR\s*)?([\d,]+\.\d{2})", text)
    vat_m = re.search(r"VAT\s*\((\d+)%\):\s*(?:EUR\s*)?([\d,]+\.\d{2})", text)
    tot_m = re.search(r"Total Due:\s*(?:EUR\s*)?([\d,]+\.\d{2})", text)

    subtotal = float(sub_m.group(1).replace(",", "")) if sub_m else None
    vat_rate = float(vat_m.group(1)) if vat_m else None
    vat_amount = float(vat_m.group(2).replace(",", "")) if vat_m else None
    total = float(tot_m.group(1).replace(",", "")) if tot_m else None

    # Naive baseline lacks reconciliation checks: approves whenever regex matched a total
    status = "AUTO_APPROVED" if (inv_m and total is not None) else "NEEDS_HUMAN_REVIEW"
    errors = [] if status == "AUTO_APPROVED" else ["REGEX_PARSE_INCOMPLETE"]

    return ExtractedInvoice(
        doc_id=doc.doc_id,
        pipeline="naive_regex",
        invoice_number=inv_m.group(1) if inv_m else None,
        issue_date=dt_m.group(1) if dt_m else None,
        supplier_tax_id=tax_m.group(1) if tax_m else None,
        subtotal=subtotal,
        vat_rate_pct=vat_rate,
        vat_amount=vat_amount,
        total=total,
        reconciliation_status=status,
        validation_errors=errors,
        latency_ms=round((time.perf_counter() - t0) * 1000.0, 3),
    )


def _extract_multilocale_fields(text: str, fix_ocr: bool) -> tuple[dict, list[str]]:
    repairs: list[str] = []

    inv_m = re.search(
        r"(?:Invoice Number|Nº Factura|Ref\.\s*Fra|DOC_NO)\s*[:=]\s*([A-Z0-9-]+)",
        text,
        re.IGNORECASE,
    )
    dt_m = re.search(
        r"(?:Invoice Date|Fecha de emisión|Fecha|DATE)\s*[:=]\s*(\d{2,4}[-/]\d{2}[-/]\d{2,4})",
        text,
        re.IGNORECASE,
    )
    tax_m = re.search(
        r"(?:VAT ID|CIF/NIF|N\.I\.F\.|TAX_ID)\s*[:=]\s*([A-Z0-9]{8,12})",
        text,
        re.IGNORECASE,
    )
    num_pat = r"([0-9Oo][0-9Oo.,]+)" if fix_ocr else r"(\d[\d.,]+)"
    sub_m = re.search(
        rf"(?:Subtotal|Base imponible|Importe Neto \(Base\)|NET)\s*[:=]\s*(?:EUR\s*)?{num_pat}",
        text,
        re.IGNORECASE,
    )
    rate_m = re.search(
        r"(?:VAT\s*\(|IVA\s*\(|Cuota IVA\s+|Tipo Impositivo IVA:\s*|TAX_RATE=)(\d{1,2})%",
        text,
        re.IGNORECASE,
    )
    vat_m = re.search(
        rf"(?:(?:VAT|IVA)\s*\(\d+%\)|Cuota IVA\s+\d+%|TAX_AMT)\s*[:=]\s*(?:EUR\s*)?{num_pat}",
        text,
        re.IGNORECASE,
    )
    tot_m = re.search(
        rf"(?:Total Due|TOTAL A PAGAR|IMPORTE TOTAL|GROSS)\s*[:=]\s*(?:EUR\s*)?{num_pat}",
        text,
        re.IGNORECASE,
    )

    subtotal, sub_rep = parse_multilocale_number(sub_m.group(1) if sub_m else None, fix_ocr=fix_ocr)
    if sub_rep:
        repairs.append("REPAIRED_OCR_SUBTOTAL_DIGITS")
    vat_amount, vat_rep = parse_multilocale_number(vat_m.group(1) if vat_m else None, fix_ocr=fix_ocr)
    if vat_rep:
        repairs.append("REPAIRED_OCR_VAT_DIGITS")
    total, tot_rep = parse_multilocale_number(tot_m.group(1) if tot_m else None, fix_ocr=fix_ocr)
    if tot_rep:
        repairs.append("REPAIRED_OCR_TOTAL_DIGITS")

    fields = {
        "invoice_number": inv_m.group(1).strip() if inv_m else None,
        "issue_date": parse_multilocale_date(dt_m.group(1) if dt_m else None),
        "supplier_tax_id": tax_m.group(1).strip() if tax_m else None,
        "subtotal": subtotal,
        "vat_rate_pct": float(rate_m.group(1)) if rate_m else None,
        "vat_amount": vat_amount,
        "total": total,
    }
    return fields, repairs


def extract_validated_structured(doc: GroundTruthInvoice) -> ExtractedInvoice:
    """Pipeline 2: Multi-locale structured parser + Pydantic accounting reconciliation (no repair)."""
    t0 = time.perf_counter()
    fields, _ = _extract_multilocale_fields(doc.raw_text, fix_ocr=False)
    repairs: list[str] = []
    sub, vat, tot, status, errors = _reconcile_accounting(
        subtotal=fields["subtotal"],
        vat_rate=fields["vat_rate_pct"],
        vat_amount=fields["vat_amount"],
        total=fields["total"],
        inv_num=fields["invoice_number"],
        issue_date=fields["issue_date"],
        tax_id=fields["supplier_tax_id"],
        allow_repair=False,
        repairs=repairs,
    )
    return ExtractedInvoice(
        doc_id=doc.doc_id,
        pipeline="validated_structured",
        invoice_number=fields["invoice_number"],
        issue_date=fields["issue_date"],
        supplier_tax_id=fields["supplier_tax_id"],
        subtotal=sub,
        vat_rate_pct=fields["vat_rate_pct"],
        vat_amount=vat,
        total=tot,
        reconciliation_status=status,
        validation_errors=errors,
        repairs_applied=repairs,
        latency_ms=round((time.perf_counter() - t0) * 1000.0, 3),
    )


def extract_with_repair_guardrails(doc: GroundTruthInvoice) -> ExtractedInvoice:
    """Pipeline 3: Multi-locale parser + OCR digit repair + deterministic VAT recovery + accounting gate."""
    t0 = time.perf_counter()
    fields, repairs = _extract_multilocale_fields(doc.raw_text, fix_ocr=True)
    sub, vat, tot, status, errors = _reconcile_accounting(
        subtotal=fields["subtotal"],
        vat_rate=fields["vat_rate_pct"],
        vat_amount=fields["vat_amount"],
        total=fields["total"],
        inv_num=fields["invoice_number"],
        issue_date=fields["issue_date"],
        tax_id=fields["supplier_tax_id"],
        allow_repair=True,
        repairs=repairs,
    )
    return ExtractedInvoice(
        doc_id=doc.doc_id,
        pipeline="schema_repair_guardrails",
        invoice_number=fields["invoice_number"],
        issue_date=fields["issue_date"],
        supplier_tax_id=fields["supplier_tax_id"],
        subtotal=sub,
        vat_rate_pct=fields["vat_rate_pct"],
        vat_amount=vat,
        total=tot,
        reconciliation_status=status,
        validation_errors=errors,
        repairs_applied=repairs,
        latency_ms=round((time.perf_counter() - t0) * 1000.0, 3),
    )


def extract_with_ollama(
    raw_text: str,
    doc_id: str = "CLI-DOC",
    model: str = "qwen2.5:7b",
    base_url: str = "http://localhost:11434",
) -> ExtractedInvoice:
    """Optional local Ollama JSON-mode extraction wrapped in the exact same accounting guardrail."""
    t0 = time.perf_counter()
    prompt = (
        "Extract invoice fields strictly as JSON with keys: invoice_number, issue_date (YYYY-MM-DD), "
        "supplier_tax_id, subtotal (float), vat_rate_pct (float), vat_amount (float), total (float). "
        "Return ONLY valid JSON.\n\n"
        f"Invoice:\n{raw_text}"
    )
    payload = json.dumps({"model": model, "prompt": prompt, "format": "json", "stream": False}).encode("utf-8")
    req = urllib.request.Request(
        f"{base_url.rstrip('/')}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30.0) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        parsed = json.loads(data.get("response", "{}"))

    repairs: list[str] = []
    sub, vat, tot, status, errors = _reconcile_accounting(
        subtotal=parsed.get("subtotal"),
        vat_rate=parsed.get("vat_rate_pct"),
        vat_amount=parsed.get("vat_amount"),
        total=parsed.get("total"),
        inv_num=parsed.get("invoice_number"),
        issue_date=parse_multilocale_date(parsed.get("issue_date")),
        tax_id=parsed.get("supplier_tax_id"),
        allow_repair=True,
        repairs=repairs,
    )
    return ExtractedInvoice(
        doc_id=doc_id,
        pipeline=f"ollama:{model}",
        invoice_number=parsed.get("invoice_number"),
        issue_date=parse_multilocale_date(parsed.get("issue_date")),
        supplier_tax_id=parsed.get("supplier_tax_id"),
        subtotal=sub,
        vat_rate_pct=parsed.get("vat_rate_pct"),
        vat_amount=vat,
        total=tot,
        reconciliation_status=status,
        validation_errors=errors,
        repairs_applied=repairs,
        latency_ms=round((time.perf_counter() - t0) * 1000.0, 2),
    )
