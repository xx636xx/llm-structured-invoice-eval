"""Deterministic generator for 60 messy synthetic SME invoices across 4 layout styles.

Includes:
  - EU/Spanish locale formatting (1.250,50 EUR, DD/MM/YYYY, CIF/NIF, IVA)
  - English standard formatting (1,250.50 EUR, YYYY-MM-DD, VAT ID)
  - OCR-noisy scans (O/0 digit swaps, irregular spacing, missing explicit VAT line)
  - Compact ERP text exports
  - 6 genuine accounting-discrepancy traps (subtotal + VAT != total) that must be flagged
    for human review instead of silently auto-posted!
"""

from __future__ import annotations

from datetime import date, timedelta
import random

from .schemas import GroundTruthInvoice

SUPPLIERS = [
    ("Iberica Logistica S.L.", "B14829301"),
    ("Andalucia Industrial Supply S.A.", "A28471920"),
    ("Cordoba Cloud Systems S.L.", "B14592018"),
    ("Nordic Packaging GmbH", "DE294817263"),
    ("Soluciones Energeticas Sur S.L.", "B41920384"),
    ("BioLab Reagents Europe S.L.", "B08394812"),
]

VAT_RATES = [21.0, 10.0, 4.0, 21.0, 21.0]


def _fmt_eu(amount: float) -> str:
    s = f"{amount:,.2f}"
    return s.replace(",", "_").replace(".", ",").replace("_", ".")


def _fmt_us(amount: float) -> str:
    return f"{amount:,.2f}"


def generate_synthetic_invoices(n_docs: int = 60, seed: int = 42) -> list[GroundTruthInvoice]:
    """Generate 60 realistic multi-layout SME invoices with ground-truth labels."""
    rng = random.Random(seed)
    start = date(2026, 1, 5)
    styles = ["eu_spanish", "english_standard", "ocr_noisy", "compact_table"]

    # Deterministic 6 genuine arithmetic-error traps spread across layouts
    error_indices = {7, 16, 27, 38, 49, 56}
    docs: list[GroundTruthInvoice] = []

    for i in range(n_docs):
        doc_id = f"DOC-{i + 1:03d}"
        style = styles[i % len(styles)]
        supplier_name, tax_id = rng.choice(SUPPLIERS)
        issue_dt = start + timedelta(days=i * 2 + rng.randint(0, 3))
        inv_num = f"FAC-2026-{1040 + i:04d}" if style in ("eu_spanish", "ocr_noisy") else f"INV-2026-{2040 + i:04d}"

        subtotal = round(rng.uniform(280.0, 6850.0), 2)
        vat_rate = rng.choice(VAT_RATES)
        vat_amount = round(subtotal * vat_rate / 100.0, 2)
        true_total = round(subtotal + vat_amount, 2)

        has_error = i in error_indices
        printed_total = round(true_total + rng.choice([45.0, -32.5, 88.0, 19.95]), 2) if has_error else true_total

        if style == "eu_spanish":
            dt_str = issue_dt.strftime("%d/%m/%Y")
            raw = (
                f"FACTURA COMERCIAL\n"
                f"Proveedor: {supplier_name}\n"
                f"CIF/NIF: {tax_id}\n"
                f"Nº Factura: {inv_num}\n"
                f"Fecha de emisión: {dt_str}\n"
                f"-------------------------------------\n"
                f"Base imponible: {_fmt_eu(subtotal)} €\n"
                f"IVA ({int(vat_rate)}%): {_fmt_eu(vat_amount)} €\n"
                f"TOTAL A PAGAR: {_fmt_eu(printed_total)} €\n"
            )
        elif style == "english_standard":
            dt_str = issue_dt.isoformat()
            raw = (
                f"COMMERCIAL INVOICE\n"
                f"Vendor: {supplier_name}\n"
                f"VAT ID: {tax_id}\n"
                f"Invoice Number: {inv_num}\n"
                f"Invoice Date: {dt_str}\n"
                f"-------------------------------------\n"
                f"Subtotal: EUR {_fmt_us(subtotal)}\n"
                f"VAT ({int(vat_rate)}%): EUR {_fmt_us(vat_amount)}\n"
                f"Total Due: EUR {_fmt_us(printed_total)}\n"
            )
        elif style == "ocr_noisy":
            # Realistic OCR noise: O->0 in numbers, DD-MM-YYYY date, occasionally omitted VAT amount line
            dt_str = issue_dt.strftime("%d-%m-%Y")
            sub_str = _fmt_eu(subtotal).replace("0", "O", 1) if (i % 8 == 2 and not has_error) else _fmt_eu(subtotal)
            tot_str = _fmt_eu(printed_total)
            omit_vat = (i % 12 == 2) and not has_error
            vat_line = (
                f"Tipo Impositivo IVA: {int(vat_rate)}% (cuota no impresa)\n"
                if omit_vat
                else f"Cuota IVA {int(vat_rate)}% : {_fmt_eu(vat_amount)} EUR\n"
            )
            raw = (
                f"  FACTURA   ESCANEADA  \n"
                f"Emisor: {supplier_name}   N.I.F.: {tax_id}\n"
                f"Ref. Fra:  {inv_num}    Fecha: {dt_str}\n"
                f"Importe Neto (Base):  {sub_str} EUR\n"
                f"{vat_line}"
                f"IMPORTE TOTAL :  {tot_str} EUR\n"
            )
        else:  # compact_table
            dt_str = issue_dt.strftime("%Y/%m/%d")
            raw = (
                f"ERP_EXPORT | VENDOR={supplier_name} | TAX_ID={tax_id}\n"
                f"DOC_NO={inv_num} | DATE={dt_str} | CURRENCY=EUR\n"
                f"NET={_fmt_us(subtotal)} | TAX_RATE={int(vat_rate)}% | TAX_AMT={_fmt_us(vat_amount)} | GROSS={_fmt_us(printed_total)}\n"
            )

        docs.append(
            GroundTruthInvoice(
                doc_id=doc_id,
                layout_style=style,
                has_accounting_error=has_error,
                raw_text=raw,
                invoice_number=inv_num,
                issue_date=issue_dt.isoformat(),
                supplier_tax_id=tax_id,
                subtotal=subtotal,
                vat_rate_pct=vat_rate,
                vat_amount=vat_amount,
                total=printed_total,
            )
        )

    return docs
