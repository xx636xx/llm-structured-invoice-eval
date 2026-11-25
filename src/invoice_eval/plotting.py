"""Publication-grade 4-panel dashboard for structured invoice extraction benchmark."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np


def render_invoice_eval_dashboard(report: dict[str, Any], output_path: Path) -> Path:
    pipes = report["pipelines"]
    ds = report["dataset_summary"]

    fig, axes = plt.subplots(2, 2, figsize=(13.8, 8.4), dpi=180)
    fig.patch.set_facecolor("#FFFFFF")

    order = [
        ("naive_regex", "Naive Regex\nBaseline"),
        ("validated_structured", "Multi-Locale +\nPydantic Gate"),
        ("schema_repair_guardrails", "Schema + OCR Repair\n+ Accounting Gate"),
    ]

    # Panel 1 (Top-Left): Overall Extraction & STP KPIs
    ax1 = axes[0, 0]
    ax1.set_facecolor("#F8FAFC")
    x = np.arange(len(order))
    w = 0.25

    f1s = [pipes[k]["micro_f1"] * 100 for k, _ in order]
    ems = [pipes[k]["doc_exact_match_rate"] * 100 for k, _ in order]
    stps = [pipes[k]["clean_stp_rate"] * 100 for k, _ in order]

    b1 = ax1.bar(x - w, f1s, w, label="Field Micro-F1 (%)", color="#2563EB", alpha=0.90)
    b2 = ax1.bar(x, ems, w, label="Doc Exact Match (%)", color="#7C3AED", alpha=0.90)
    b3 = ax1.bar(x + w, stps, w, label="Clean Straight-Through (%)", color="#059669", alpha=0.90)

    for bars in (b1, b2, b3):
        for bar in bars:
            h = bar.get_height()
            ax1.text(
                bar.get_x() + bar.get_width() / 2,
                h + 1.6,
                f"{h:.0f}%",
                ha="center",
                va="bottom",
                fontsize=7.9,
                fontweight="bold",
                color="#0F172A",
            )

    ax1.set_xticks(x)
    ax1.set_xticklabels([lbl for _, lbl in order], fontsize=8.4, color="#1E293B")
    ax1.set_ylim(0, 126)
    ax1.set_yticks([0, 20, 40, 60, 80, 100])
    ax1.set_ylabel("Score (%)", fontsize=9.3, color="#334155")
    ax1.set_title(
        "1. Extraction Accuracy & Straight-Through Processing (60 Invoices)",
        fontsize=10.5,
        fontweight="bold",
        color="#0F172A",
        loc="left",
        pad=8,
    )
    ax1.grid(True, axis="y", linestyle="--", alpha=0.35, color="#94A3B8")
    ax1.legend(loc="upper center", frameon=True, facecolor="#FFFFFF", fontsize=7.6, ncol=3)

    # Panel 2 (Top-Right): Exact Match by Invoice Layout Style
    ax2 = axes[0, 1]
    ax2.set_facecolor("#F8FAFC")
    layouts = [
        ("english_standard", "English\nStandard"),
        ("eu_spanish", "EU / Spanish\n(1.250,50 €)"),
        ("compact_table", "Compact\nERP Export"),
        ("ocr_noisy", "OCR-Noisy\n(O/0 + No VAT)"),
    ]
    lx = np.arange(len(layouts))
    lw = 0.25

    l_naive = [pipes["naive_regex"]["exact_match_by_layout"][k] * 100 for k, _ in layouts]
    l_val = [pipes["validated_structured"]["exact_match_by_layout"][k] * 100 for k, _ in layouts]
    l_rep = [pipes["schema_repair_guardrails"]["exact_match_by_layout"][k] * 100 for k, _ in layouts]

    lb1 = ax2.bar(lx - lw, l_naive, lw, label="Naive Regex", color="#DC2626", alpha=0.86)
    lb2 = ax2.bar(lx, l_val, lw, label="Multi-Locale Gate", color="#D97706", alpha=0.88)
    lb3 = ax2.bar(lx + lw, l_rep, lw, label="Schema + Repair Gate", color="#16A34A", alpha=0.90)

    for bars in (lb1, lb2, lb3):
        for bar in bars:
            h = bar.get_height()
            ax2.text(
                bar.get_x() + bar.get_width() / 2,
                h + 1.6,
                f"{h:.0f}%",
                ha="center",
                va="bottom",
                fontsize=7.7,
                fontweight="bold",
                color="#0F172A",
            )

    ax2.set_xticks(lx)
    ax2.set_xticklabels([lbl for _, lbl in layouts], fontsize=8.3, color="#1E293B")
    ax2.set_ylim(0, 126)
    ax2.set_yticks([0, 20, 40, 60, 80, 100])
    ax2.set_ylabel("Document Exact Match (%)", fontsize=9.3, color="#334155")
    ax2.set_title(
        "2. Robustness Across Multi-Locale & OCR-Noisy Layouts",
        fontsize=10.5,
        fontweight="bold",
        color="#0F172A",
        loc="left",
        pad=8,
    )
    ax2.grid(True, axis="y", linestyle="--", alpha=0.35, color="#94A3B8")
    ax2.legend(loc="upper center", frameon=True, facecolor="#FFFFFF", fontsize=7.6, ncol=3)

    # Panel 3 (Bottom-Left): Field-Level F1 (Naive vs Schema+Repair)
    ax3 = axes[1, 0]
    ax3.set_facecolor("#F8FAFC")
    fields = [
        ("invoice_number", "Invoice #"),
        ("issue_date", "Issue Date"),
        ("supplier_tax_id", "Tax ID"),
        ("subtotal", "Subtotal"),
        ("vat_amount", "VAT Amount"),
        ("total", "Total"),
    ]
    fy = np.arange(len(fields))
    fh = 0.34
    f_naive = [pipes["naive_regex"]["field_metrics"][k]["f1"] * 100 for k, _ in fields]
    f_rep = [pipes["schema_repair_guardrails"]["field_metrics"][k]["f1"] * 100 for k, _ in fields]

    fb1 = ax3.barh(fy - fh / 2, f_naive, fh, label="Naive Regex", color="#DC2626", alpha=0.85)
    fb2 = ax3.barh(fy + fh / 2, f_rep, fh, label="Schema + Repair Gate", color="#059669", alpha=0.90)
    ax3.set_yticks(fy)
    ax3.set_yticklabels([lbl for _, lbl in fields], fontsize=8.6, color="#1E293B")
    ax3.set_ylim(len(fields) - 0.3, -1.25)
    ax3.set_xlim(0, 118)
    ax3.set_xticks([0, 20, 40, 60, 80, 100])
    ax3.set_xlabel("Field F1 Score (%)", fontsize=9.3, color="#334155")
    for bars in (fb1, fb2):
        for bar in bars:
            val = bar.get_width()
            ax3.text(val + 1.5, bar.get_y() + bar.get_height() / 2, f"{val:.0f}%", va="center", fontsize=7.8, fontweight="bold", color="#0F172A")
    ax3.set_title(
        "3. Field-Level F1 Across 6 Mandatory Accounting Fields",
        fontsize=10.5,
        fontweight="bold",
        color="#0F172A",
        loc="left",
        pad=8,
    )
    ax3.grid(True, axis="x", linestyle="--", alpha=0.35, color="#94A3B8")
    ax3.legend(loc="upper center", frameon=True, facecolor="#FFFFFF", fontsize=7.8, ncol=2)

    # Panel 4 (Bottom-Right): Reconciliation Routing & Accounting Trap Safety
    ax4 = axes[1, 1]
    ax4.set_facecolor("#F8FAFC")
    p_names = [lbl for _, lbl in order]
    auto_ok = [pipes[k]["status_counts"].get("AUTO_APPROVED", 0) for k, _ in order]
    repaired_ok = [pipes[k]["status_counts"].get("REPAIRED_AND_APPROVED", 0) for k, _ in order]
    review_n = [pipes[k]["status_counts"].get("NEEDS_HUMAN_REVIEW", 0) for k, _ in order]
    px = np.arange(len(p_names))

    ax4.bar(px, auto_ok, width=0.48, color="#16A34A", alpha=0.90, label="Auto-Approved")
    ax4.bar(px, repaired_ok, width=0.48, bottom=auto_ok, color="#2563EB", alpha=0.90, label="Repaired & Approved")
    bottom_rev = [a + r for a, r in zip(auto_ok, repaired_ok)]
    ax4.bar(px, review_n, width=0.48, bottom=bottom_rev, color="#D97706", alpha=0.90, label="Routed to Human Review")

    ax4.set_ylim(0, 86)
    for idx, (k, _) in enumerate(order):
        caught = round(pipes[k]["accounting_error_catch_rate"] * ds["accounting_error_traps"])
        leaked = pipes[k]["corrupted_invoices_auto_posted"]
        ax4.text(
            idx,
            62.5,
            f"Traps caught: {caught}/{ds['accounting_error_traps']}\nBad auto-posted: {leaked}",
            ha="center",
            va="bottom",
            fontsize=7.9,
            fontweight="bold",
            color="#991B1B" if leaked > 0 else "#166534",
        )

    ax4.set_xticks(px)
    ax4.set_xticklabels(p_names, fontsize=8.4, color="#1E293B")
    ax4.set_ylabel("Invoices Routed (n=60)", fontsize=9.3, color="#334155")
    ax4.set_title(
        "4. Accounting Guardrail Safety (Subtotal + VAT = Total)",
        fontsize=10.5,
        fontweight="bold",
        color="#0F172A",
        loc="left",
        pad=8,
    )
    ax4.grid(True, axis="y", linestyle="--", alpha=0.35, color="#94A3B8")
    ax4.legend(loc="upper center", frameon=True, facecolor="#FFFFFF", fontsize=7.4, ncol=3)

    rep = pipes["schema_repair_guardrails"]
    fig.suptitle(
        "LLM Structured Invoice Eval — Multi-Locale Extraction, Pydantic Guardrails & Accounting Reconciliation",
        fontsize=12.9,
        fontweight="bold",
        color="#0F172A",
        y=0.985,
    )
    fig.text(
        0.5,
        0.946,
        f"60 Synthetic SME Invoices (4 layouts, {ds['accounting_error_traps']} arithmetic traps)  |  "
        f"Schema+Repair Micro-F1: {rep['micro_f1']*100:.1f}%  |  Clean STP: {rep['clean_stp_rate']*100:.0f}%  |  "
        f"Corrupted Auto-Posted: {rep['corrupted_invoices_auto_posted']}",
        ha="center",
        fontsize=9.1,
        color="#475569",
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout(rect=[0.01, 0.01, 0.99, 0.93])
    fig.savefig(output_path, dpi=180, bbox_inches="tight", pad_inches=0.22)
    plt.close(fig)
    return output_path
