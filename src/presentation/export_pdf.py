"""
PDF экспорт данных клуба.
Использует reportlab с Unicode-шрифтом для поддержки кириллицы.
"""
from __future__ import annotations

import io
import os
from datetime import datetime
from decimal import Decimal

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib import colors

_FONT_NORMAL = "ClubFont"
_FONT_BOLD = "ClubFontBold"


def _register_font():
    """Register a font that supports Cyrillic. Tries multiple paths."""
    if _FONT_NORMAL in pdfmetrics.fontNames:
        return

    paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        os.path.join(os.environ.get("WINDIR", "C:/Windows"), "Fonts", "arial.ttf"),
        os.path.join(os.environ.get("WINDIR", "C:/Windows"), "Fonts", "ARIAL.TTF"),
        os.path.join(os.environ.get("WINDIR", "C:/Windows"), "Fonts", "ARIALBD.TTF"),
    ]
    for path in paths:
        try:
            if os.path.exists(path):
                pdfmetrics.registerFont(TTFont(_FONT_NORMAL, path))
                # Bold: same path but subfontIndex=1, or find a bold variant
                bold_path = path.replace(".ttf", "BD.ttf") if "arial" in path.lower() else path
                if not os.path.exists(bold_path):
                    bold_path = path.replace("DejaVuSans.ttf", "DejaVuSans-Bold.ttf")
                if os.path.exists(bold_path):
                    pdfmetrics.registerFont(TTFont(_FONT_BOLD, bold_path))
                else:
                    pdfmetrics.registerFont(TTFont(_FONT_BOLD, path, subfontIndex=1))
                return
        except Exception:
            continue


def _get_styles():
    """Create paragraph styles using the registered font."""
    _register_font()
    f_normal = _FONT_NORMAL if _FONT_NORMAL in pdfmetrics.fontNames else "Helvetica"
    f_bold = _FONT_BOLD if _FONT_BOLD in pdfmetrics.fontNames else "Helvetica-Bold"

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="TitleRU", fontName=f_bold, fontSize=18,
                              leading=24, alignment=TA_CENTER, spaceAfter=12 * mm))
    styles.add(ParagraphStyle(name="HeadingRU", fontName=f_bold, fontSize=13,
                              leading=16, spaceBefore=8 * mm, spaceAfter=4 * mm,
                              textColor=colors.HexColor("#1a5276")))
    styles.add(ParagraphStyle(name="BodyRU", fontName=f_normal, fontSize=9,
                              leading=13, spaceAfter=3 * mm))
    return styles


# ─── Генератор PDF ─────────────────────────────────────────────────────────


def generate_export_pdf(
    users: list,
    payments: list,
    fines: list,
    expenses: list,
) -> io.BytesIO:
    """Generate a PDF report of all club data."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=15 * mm,
        bottomMargin=15 * mm,
    )

    styles = _get_styles()
    elements = []

    # ── Заголовок ──
    from src.infrastructure.timezone import now_msk
    now_str = now_msk().strftime("%d %B %Y")
    elements.append(Paragraph(f"<b>Отчёт клуба</b>", styles["TitleRU"]))
    elements.append(Paragraph(f"Дата формирования: {now_str}", styles["BodyRU"]))
    elements.append(Spacer(1, 6 * mm))

    # ── Раздел: Участники ──
    elements.append(Paragraph("👥 Участники", styles["HeadingRU"]))
    if users:
        user_rows = [["ID", "Telegram ID", "Ник", "Роль", "Баланс"]]
        for u in users:
            user_rows.append([
                str(u.id or ""),
                str(u.telegram_id or ""),
                (u.full_name or "")[:20],
                u.role.value if hasattr(u.role, "value") else str(u.role),
                f"{u.balance_credit or Decimal('0'):.2f}₽",
            ])
        t = Table(user_rows, colWidths=[18 * mm, 28 * mm, 50 * mm, 25 * mm, 30 * mm])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2e4057")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
            ("ALIGN", (0, 0), (-1, -1), "LEFT"),
            ("FONTNAME", (0, 0), (-1, 0), _FONT_BOLD),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
            ("TOPPADDING", (0, 0), (-1, 0), 6),
            ("BOTTOMPADDING", (0, 1), (-1, -1), 4),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f0f4f8")]),
        ]))
        elements.append(t)
    else:
        elements.append(Paragraph("Нет участников.", styles["BodyRU"]))
    elements.append(PageBreak())

    # ── Раздел: Платежи ──
    elements.append(Paragraph("💰 Платежи", styles["HeadingRU"]))
    if payments:
        pay_rows = [["ID", "Сумма", "Месяц", "Тип", "Статус", "Комментарий"]]
        for p in payments[:100]:  # limit to 100
            pay_rows.append([
                str(p.id or ""),
                f"{p.amount or Decimal('0'):.2f}₽",
                f"{p.year}-{p.month:02d}" if p.year else "",
                "штраф" if (p.payment_type or "") == "fine" else "взнос",
                p.status.value if hasattr(p.status, "value") else str(p.status),
                (p.comment or "")[:30],
            ])
        t = Table(pay_rows, colWidths=[15 * mm, 25 * mm, 25 * mm, 20 * mm, 25 * mm, 80 * mm])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e6f52")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
            ("ALIGN", (0, 0), (-1, -1), "LEFT"),
            ("FONTNAME", (0, 0), (-1, 0), _FONT_BOLD),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
            ("TOPPADDING", (0, 0), (-1, 0), 6),
            ("BOTTOMPADDING", (0, 1), (-1, -1), 4),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#eaf5f1")]),
        ]))
        elements.append(t)
    else:
        elements.append(Paragraph("Нет платежей.", styles["BodyRU"]))
    elements.append(PageBreak())

    # ── Раздел: Штрафы ──
    elements.append(Paragraph("⚠️ Штрафы", styles["HeadingRU"]))
    if fines:
        fine_rows = [["ID", "Сумма", "Причина", "Статус"]]
        for f in fines[:100]:
            fine_rows.append([
                str(f.id or ""),
                f"{f.amount or Decimal('0'):.2f}₽",
                (f.reason or "")[:40],
                f.status.value if hasattr(f.status, "value") else str(f.status),
            ])
        t = Table(fine_rows, colWidths=[18 * mm, 28 * mm, 100 * mm, 30 * mm])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#922b21")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
            ("ALIGN", (0, 0), (-1, -1), "LEFT"),
            ("FONTNAME", (0, 0), (-1, 0), _FONT_BOLD),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
            ("TOPPADDING", (0, 0), (-1, 0), 6),
            ("BOTTOMPADDING", (0, 1), (-1, -1), 4),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#fdedec")]),
        ]))
        elements.append(t)
    else:
        elements.append(Paragraph("Нет активных штрафов.", styles["BodyRU"]))
    elements.append(PageBreak())

    # ── Раздел: Расходы ──
    elements.append(Paragraph("💸 Расходы", styles["HeadingRU"]))
    if expenses:
        exp_rows = [["ID", "Сумма", "Категория", "Дата", "Комментарий"]]
        for e in expenses[:100]:
            exp_rows.append([
                str(e.id or ""),
                f"{e.amount or Decimal('0'):.2f}₽",
                e.category.value if hasattr(e.category, "value") else str(e.category),
                e.expense_date.isoformat() if e.expense_date else "",
                (e.comment or "")[:40],
            ])
        t = Table(exp_rows, colWidths=[15 * mm, 25 * mm, 30 * mm, 30 * mm, 70 * mm])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#7d3c98")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
            ("ALIGN", (0, 0), (-1, -1), "LEFT"),
            ("FONTNAME", (0, 0), (-1, 0), _FONT_BOLD),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
            ("TOPPADDING", (0, 0), (-1, 0), 6),
            ("BOTTOMPADDING", (0, 1), (-1, -1), 4),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f4ecf7")]),
        ]))
        elements.append(t)
    else:
        elements.append(Paragraph("Нет расходов.", styles["BodyRU"]))

    doc.build(elements)
    buf.seek(0)
    return buf
