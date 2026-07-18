"""PDF invoice generation using ReportLab."""

import math
import os
import re
from datetime import date

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# Prototype placeholder — a flat tax rate, not tied to any jurisdiction.
TAX_RATE = 0.05

INVOICES_DIR = "invoices"


def _safe_filename_part(name: str) -> str:
    """Strip characters that are unsafe in filenames."""
    name = name.strip() or "customer"
    return re.sub(r"[^A-Za-z0-9_-]+", "_", name)


def _price_is_missing(unit_price) -> bool:
    return unit_price is None or (isinstance(unit_price, float) and math.isnan(unit_price))


def generate_invoice(order: dict) -> str:
    """Generate a PDF invoice from a validated order dict.

    Expects order to contain "customer_name" and "items" (list of
    dicts with "item", "quantity", "unit_price"). Saves the PDF to
    invoices/invoice_{customer_name}_{date}.pdf and returns the path.
    """
    os.makedirs(INVOICES_DIR, exist_ok=True)

    customer_name = order.get("customer_name") or "Unknown Customer"
    items = order.get("items") or []
    today_str = date.today().isoformat()

    filename = f"invoice_{_safe_filename_part(customer_name)}_{today_str}.pdf"
    filepath = os.path.join(INVOICES_DIR, filename)

    doc = SimpleDocTemplate(filepath, pagesize=letter)
    styles = getSampleStyleSheet()
    elements = []

    elements.append(Paragraph("SafeX Solutions", styles["Title"]))
    elements.append(Paragraph("Invoice", styles["Heading2"]))
    elements.append(Spacer(1, 0.2 * inch))
    elements.append(Paragraph(f"Customer: {customer_name}", styles["Normal"]))
    elements.append(Paragraph(f"Date: {today_str}", styles["Normal"]))
    elements.append(Spacer(1, 0.3 * inch))

    table_data = [["Item", "Quantity", "Unit Price", "Line Total"]]
    subtotal = 0.0
    pending_price_rows = []
    for row_index, item in enumerate(items, start=1):
        qty = item.get("quantity", 0) or 0
        unit_price = item.get("unit_price", 0.0)
        if _price_is_missing(unit_price):
            pending_price_rows.append(row_index)
            table_data.append(
                [
                    item.get("item", ""),
                    str(qty),
                    "Pending pricing",
                    "Pending pricing",
                ]
            )
            continue
        unit_price = unit_price or 0.0
        line_total = qty * unit_price
        subtotal += line_total
        table_data.append(
            [
                item.get("item", ""),
                str(qty),
                f"${unit_price:.2f}",
                f"${line_total:.2f}",
            ]
        )

    tax = subtotal * TAX_RATE
    total = subtotal + tax

    all_items_pending = bool(items) and len(pending_price_rows) == len(items)
    if all_items_pending:
        subtotal_str, tax_str, total_str = "Pending", "Pending", "Pending"
    else:
        subtotal_str, tax_str, total_str = f"${subtotal:.2f}", f"${tax:.2f}", f"${total:.2f}"

    table_data.append(["", "", "Subtotal", subtotal_str])
    table_data.append(["", "", f"Tax ({TAX_RATE * 100:.0f}%)", tax_str])
    table_data.append(["", "", "Total", total_str])

    table_style = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F2937")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("GRID", (0, 0), (-1, len(items)), 0.5, colors.grey),
        ("FONTNAME", (2, len(table_data) - 3), (-1, -1), "Helvetica-Bold"),
        ("LINEABOVE", (2, len(table_data) - 3), (-1, len(table_data) - 3), 1, colors.black),
    ]
    for row_index in pending_price_rows:
        table_style.append(("TEXTCOLOR", (2, row_index), (3, row_index), colors.grey))
        table_style.append(("FONTNAME", (2, row_index), (3, row_index), "Helvetica-Oblique"))

    table = Table(table_data, colWidths=[2.5 * inch, 1 * inch, 1.5 * inch, 1.5 * inch])
    table.setStyle(TableStyle(table_style))

    elements.append(table)

    if pending_price_rows:
        elements.append(Spacer(1, 0.15 * inch))
        elements.append(
            Paragraph(
                "Items marked 'Pending pricing' require manual price "
                "confirmation before this invoice is finalized.",
                styles["Italic"],
            )
        )

    doc.build(elements)

    return filepath
