"""
RFP Bid Evaluation PDF Report Generator — v3
=============================================
Merges the robust data structure & helpers from pdf_generator_v2.py
with the premium UI / presentation from the second design.

Cross-platform fixes retained:
  _f() / _inr() / _pct() / _days() / _date()  — all safe on Windows & Linux
"""

import os
import io
import re as _re
from datetime import datetime

from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, HRFlowable, KeepTogether,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_RIGHT, TA_LEFT
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus.flowables import Flowable
from reportlab.graphics.shapes import Drawing, Rect, String, Line


# ─── Cross-platform Unicode font registration ────────────────────────────────

def _find_font(candidates):
    for path in candidates:
        if os.path.isfile(path):
            return path
    return None

_NORMAL_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans.ttf",
    "/Library/Fonts/Arial.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    r"C:\Windows\Fonts\arial.ttf",
    r"C:\Windows\Fonts\calibri.ttf",
]
_BOLD_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
    "/Library/Fonts/Arial Bold.ttf",
    r"C:\Windows\Fonts\arialbd.ttf",
    r"C:\Windows\Fonts\calibrib.ttf",
]

_npath = _find_font(_NORMAL_CANDIDATES)
_bpath = _find_font(_BOLD_CANDIDATES)

if _npath and _bpath:
    pdfmetrics.registerFont(TTFont("DV",   _npath))
    pdfmetrics.registerFont(TTFont("DV-B", _bpath))
    FONT_NORMAL = "DV"
    FONT_BOLD   = "DV-B"
    print(f"[PDF] Using TTF font: {os.path.basename(_npath)}")
else:
    FONT_NORMAL = "Helvetica"
    FONT_BOLD   = "Helvetica-Bold"
    print("[PDF] WARNING: No TTF font found — falling back to Helvetica (limited Unicode)")


# ─── Brand palette (premium navy + gold from design 2) ───────────────────────
NAVY        = colors.HexColor("#0D2B4E")
STEEL       = colors.HexColor("#1F4788")
ACCENT_GOLD = colors.HexColor("#C9A84C")   # gold accent lines
C_ACCENT    = colors.HexColor("#2E86C1")   # blue accent (kept for spec tables)
C_ACCENT2   = colors.HexColor("#1ABC9C")   # teal (selected SKU highlight)
C_ORANGE    = colors.HexColor("#E67E22")
C_RED       = colors.HexColor("#B71C1C")
C_GREEN     = colors.HexColor("#1A7F5A")
GREEN_BG    = colors.HexColor("#E6F4EF")
AMBER_BG    = colors.HexColor("#FDF3E2")
RED_BG      = colors.HexColor("#FDECEA")
C_AMBER     = colors.HexColor("#C07000")
LIGHT_BLUE  = colors.HexColor("#EBF2FA")
MID_GREY    = colors.HexColor("#F4F6F8")
RULE_GREY   = colors.HexColor("#D0D7E0")
C_MUTED     = colors.HexColor("#888888")
C_TEXT      = colors.HexColor("#1A1A2E")
C_TEXT_MID  = colors.HexColor("#4A4A6A")
WHITE       = colors.white


# ─── Safe formatting helpers (unchanged from v2) ─────────────────────────────

def _f(x, default: float = 0.0) -> float:
    if x is None:
        return default
    try:
        v = float(x)
        if v != v or v == float("inf") or v == float("-inf"):
            return default
        return v
    except (TypeError, ValueError):
        pass
    cleaned = _re.sub(r"[^\d.\-]", "", str(x))
    try:
        v = float(cleaned) if cleaned else default
        return v if (v == v) else default
    except ValueError:
        return default


def _inr(val, decimals: int = 0) -> str:
    return f"\u20b9 {_f(val):,.{decimals}f}"


def _pct(val) -> str:
    return f"{_f(val):.1f}%"


def _days(val) -> str:
    if val is None:
        return "N/A"
    try:
        v = int(float(str(val)))
        return f"{v} d"
    except (TypeError, ValueError):
        return "N/A"


def _date(include_time: bool = False) -> str:
    now = datetime.now()
    base = f"{now.day} {now.strftime('%B %Y')}"
    return f"{base} at {now.strftime('%H:%M')}" if include_time else base


def _grade_color(grade: str):
    g = str(grade).strip().upper()
    if g.startswith("A"): return C_GREEN
    if g.startswith("B"): return C_AMBER
    return C_RED


def _score_bar(score: float, width: int = 18) -> str:
    filled = max(0, min(width, round((_f(score) / 100) * width)))
    return "\u2588" * filled + "\u2591" * (width - filled)


def _match_icon(match_str: str) -> str:
    s = str(match_str)
    if "No Match" in s: return "\u2717"
    if "Match"    in s: return "\u2713"
    return "\u2013"


# ─── Score gauge (horizontal progress bar from design 2) ─────────────────────

def _score_gauge(score_0_to_100: float) -> Drawing:
    """Horizontal progress-bar gauge. score_0_to_100 is 0–100."""
    score = _f(score_0_to_100) / 100.0
    bar_w, bar_h = 380, 28
    d = Drawing(bar_w + 20, 70)

    d.add(Rect(10, 30, bar_w, bar_h,
               fillColor=MID_GREY, strokeColor=RULE_GREY, strokeWidth=0.5))

    fill = bar_w * max(0.0, min(1.0, score))
    bar_col = C_GREEN if score >= 0.75 else (C_AMBER if score >= 0.50 else C_RED)
    d.add(Rect(10, 30, fill, bar_h,
               fillColor=bar_col, strokeColor=None, strokeWidth=0))

    d.add(String(10 + fill / 2, 40,
                 f"{score:.0%}",
                 fontSize=13, fontName=FONT_BOLD,
                 fillColor=WHITE, textAnchor="middle"))

    for pct in [0, 25, 50, 75, 100]:
        x = 10 + bar_w * pct / 100
        d.add(String(x, 22, f"{pct}%",
                     fontSize=7, fontName=FONT_NORMAL,
                     fillColor=C_TEXT_MID, textAnchor="middle"))
        d.add(Line(x, 29, x, 26, strokeColor=RULE_GREY, strokeWidth=0.5))

    d.add(String(10 + bar_w / 2, 8,
                 "Overall Bid Viability Score",
                 fontSize=8, fontName=FONT_NORMAL,
                 fillColor=C_TEXT_MID, textAnchor="middle"))
    return d


# ─── Header / Footer ─────────────────────────────────────────────────────────

def _header_footer(canvas_obj, doc):
    canvas_obj.saveState()
    W, H = A4
    LM = 0.75 * inch
    RM = W - 0.75 * inch

    if doc.page > 1:
        # Gold top rule
        canvas_obj.setStrokeColor(ACCENT_GOLD)
        canvas_obj.setLineWidth(3)
        canvas_obj.line(LM, H - 0.52 * inch, RM, H - 0.52 * inch)
        # Navy underbar
        canvas_obj.setStrokeColor(NAVY)
        canvas_obj.setLineWidth(0.5)
        canvas_obj.line(LM, H - 0.63 * inch, RM, H - 0.63 * inch)

        canvas_obj.setFont(FONT_BOLD, 7.5)
        canvas_obj.setFillColor(NAVY)
        canvas_obj.drawString(LM, H - 0.46 * inch, "RFP BID EVALUATION REPORT")

        canvas_obj.setFont(FONT_NORMAL, 7.5)
        canvas_obj.setFillColor(C_MUTED)
        canvas_obj.drawRightString(RM, H - 0.46 * inch, _date())

    # Footer
    canvas_obj.setStrokeColor(NAVY)
    canvas_obj.setLineWidth(0.5)
    canvas_obj.line(LM, 0.75 * inch, RM, 0.75 * inch)
    canvas_obj.setStrokeColor(ACCENT_GOLD)
    canvas_obj.setLineWidth(2.5)
    canvas_obj.line(LM, 0.72 * inch, RM, 0.72 * inch)

    canvas_obj.setFont(FONT_NORMAL, 7)
    canvas_obj.setFillColor(C_MUTED)
    canvas_obj.drawString(LM, 0.50 * inch, "CONFIDENTIAL \u2013 For Internal Use Only")

    canvas_obj.setFont(FONT_BOLD, 7.5)
    canvas_obj.setFillColor(NAVY)
    canvas_obj.drawRightString(RM, 0.50 * inch, f"Page {doc.page}")
    canvas_obj.restoreState()


def _cover_page(canvas_obj, doc):
    """Draws the full-bleed cover background then delegates to normal header/footer."""
    _header_footer(canvas_obj, doc)
    W, H = A4
    canvas_obj.saveState()
    # Full navy header band
    canvas_obj.setFillColor(NAVY)
    canvas_obj.rect(0, H - 3.9 * inch, W, 3.9 * inch, fill=1, stroke=0)
    # Gold accent stripe at bottom of band
    canvas_obj.setFillColor(ACCENT_GOLD)
    canvas_obj.rect(0, H - 4.0 * inch, W, 0.12 * inch, fill=1, stroke=0)
    canvas_obj.restoreState()


# ─── Style factory ────────────────────────────────────────────────────────────

def _styles():
    base = getSampleStyleSheet()

    def ps(name, **kw):
        kw.setdefault("fontName", FONT_NORMAL)
        base.add(ParagraphStyle(name=name, parent=base["Normal"], **kw))

    ps("DocTitle",    fontSize=28, textColor=WHITE, alignment=TA_CENTER,
       fontName=FONT_BOLD, leading=34, spaceAfter=4)
    ps("DocSubtitle", fontSize=13, textColor=colors.HexColor("#BFD4F0"),
       alignment=TA_CENTER, spaceAfter=6)
    ps("CoverMeta",   fontSize=10, textColor=colors.HexColor("#C8DCF5"),
       alignment=TA_CENTER, spaceAfter=3)

    ps("SectionHeader", fontSize=11, textColor=WHITE, fontName=FONT_BOLD,
       leading=14, spaceAfter=14, spaceBefore=4)
    ps("SubHead",  fontSize=10, textColor=NAVY, fontName=FONT_BOLD,
       spaceBefore=10, spaceAfter=6)
    ps("Body",     fontSize=9.5, textColor=C_TEXT, leading=14, alignment=TA_JUSTIFY)
    ps("BulletItem", fontSize=9.5, textColor=C_TEXT, leading=14, leftIndent=18, spaceAfter=3)
    ps("Cell",     fontSize=8.5, textColor=C_TEXT, leading=11)
    ps("CellBold", fontSize=8.5, textColor=NAVY,   leading=11, fontName=FONT_BOLD)
    ps("Score",    fontSize=30,  textColor=NAVY, alignment=TA_CENTER, fontName=FONT_BOLD)
    ps("Grade",    fontSize=16,  alignment=TA_CENTER, fontName=FONT_BOLD)
    ps("CoverLbl", fontSize=9,   textColor=C_TEXT_MID, fontName=FONT_BOLD, alignment=TA_RIGHT)
    ps("CoverVal", fontSize=9.5, textColor=C_TEXT)
    ps("Foot",     fontSize=7.5, textColor=C_MUTED, alignment=TA_CENTER)
    ps("TableCell",fontSize=9,   textColor=C_TEXT, leading=12)
    return base


# ─── Section header block (navy band with gold top rule, design 2 style) ─────

def _section_block(title, styles):
    tbl = Table([[Paragraph(title, styles["SectionHeader"])]],
                colWidths=[7.0 * inch])
    tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), NAVY),
        ("LEFTPADDING",   (0, 0), (-1, -1), 12),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 12),
        ("TOPPADDING",    (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LINEABOVE",     (0, 0), (-1,  0), 3, ACCENT_GOLD),
    ]))
    return tbl


# ─── Table style preset ───────────────────────────────────────────────────────

def _ts(header_bg=NAVY):
    return TableStyle([
        ("BACKGROUND",    (0, 0), (-1,  0), header_bg),
        ("TEXTCOLOR",     (0, 0), (-1,  0), WHITE),
        ("FONTNAME",      (0, 0), (-1,  0), FONT_BOLD),
        ("FONTNAME",      (0, 1), (-1, -1), FONT_NORMAL),
        ("FONTSIZE",      (0, 0), (-1, -1), 8.5),
        ("ALIGN",         (0, 0), (-1,  0), "CENTER"),
        ("ALIGN",         (0, 1), (-1, -1), "LEFT"),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",    (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("LEFTPADDING",   (0, 0), (-1, -1), 9),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 9),
        ("LINEABOVE",     (0, 0), (-1,  0), 3, ACCENT_GOLD),
        ("LINEBELOW",     (0, 0), (-1,  0), 1, C_ACCENT),
        ("GRID",          (0, 0), (-1, -1), 0.4, RULE_GREY),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [WHITE, LIGHT_BLUE]),
    ])


# ─── KPI metrics strip ────────────────────────────────────────────────────────

def _kpi_strip(metrics):
    """
    metrics: list of (label, value, value_color) tuples.
    Returns a Table flowable.
    """
    S = _styles()
    cells = [[
        Table(
            [[Paragraph(label, ParagraphStyle(
                f"_KL{i}", fontName=FONT_NORMAL, fontSize=7.5, leading=10,
                textColor=C_MUTED, alignment=TA_CENTER))],
             [Paragraph(value, ParagraphStyle(
                f"_KV{i}", fontName=FONT_BOLD, fontSize=11, leading=14,
                textColor=vcol, alignment=TA_CENTER))]],
            colWidths=[1.6 * inch]
        )
        for i, (label, value, vcol) in enumerate(metrics)
    ]]
    n = len(metrics)
    col_w = 7.0 * inch / n
    tbl = Table(cells, colWidths=[col_w] * n)
    tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), WHITE),
        ("BOX",           (0, 0), (-1, -1), 1,   RULE_GREY),
        ("INNERGRID",     (0, 0), (-1, -1), 0.5, RULE_GREY),
        ("LINEABOVE",     (0, 0), (-1,  0), 3,   NAVY),
        ("TOPPADDING",    (0, 0), (-1, -1), 12),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
        ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
    ]))
    return tbl


# ─── Main generator ───────────────────────────────────────────────────────────

def generate_rfp_pdf(rfp_data: dict) -> bytes:
    """Generate a PDF report and return raw PDF bytes (no file written to disk)."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=0.75 * inch, rightMargin=0.75 * inch,
        topMargin=1.1  * inch, bottomMargin=1.0 * inch,
        title="RFP Bid Evaluation Report",
    )
    S     = _styles()
    story = []

    # ── Unpack ──────────────────────────────────────────────────────────────
    project_name = rfp_data.get("project_name", "N/A")
    issued_by    = rfp_data.get("issued_by",    "N/A")
    deadline     = rfp_data.get("deadline",     "N/A")
    line_items   = rfp_data.get("line_items",   [])
    summary      = rfp_data.get("summary",      {})
    bid          = rfp_data.get("bid_viability",{})

    bid_score  = _f(bid.get("score", 0))
    bid_grade  = str(bid.get("grade", "N/A"))
    bid_rec    = str(bid.get("recommendation", ""))
    components = bid.get("component_scores",       {}) or {}
    weighted   = bid.get("weighted_contributions", {}) or {}

    total_mat   = _f(summary.get("total_material_cost_inr", 0))
    total_test  = _f(summary.get("total_test_cost_inr",     0))
    grand_total = _f(summary.get("grand_total_inr",         0))

    # Recommendation styling
    if bid_score >= 75:
        rec_text, rec_color, rec_bg = "PROCEED WITH BID", C_GREEN, GREEN_BG
    elif bid_score >= 50:
        rec_text, rec_color, rec_bg = "REVIEW REQUIRED",  C_AMBER, AMBER_BG
    else:
        rec_text, rec_color, rec_bg = "DO NOT PROCEED",   C_RED,   RED_BG

    grade_c = _grade_color(bid_grade)

    # ══════════════════════════════════════════════════════════════════════
    # 1. COVER PAGE
    # ══════════════════════════════════════════════════════════════════════
    story.append(Spacer(1, 0.35 * inch))   # push into navy band

    story.append(Paragraph("TECHNICAL &amp; COMMERCIAL PROPOSAL", S["DocTitle"]))
    story.append(Paragraph("RFP Bid Evaluation Report",            S["DocSubtitle"]))
    story.append(Paragraph(f"Prepared: {_date()}",                 S["CoverMeta"]))

    story.append(Spacer(1, 1.4 * inch))   # clear gold stripe into white area

    # Project name card
    proj_card = Table(
        [[Paragraph(f"<b>{project_name}</b>",
                    ParagraphStyle("_PC", fontName=FONT_BOLD, fontSize=13,
                                   textColor=NAVY, alignment=TA_CENTER, leading=16))]],
        colWidths=[6.5 * inch]
    )
    proj_card.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), WHITE),
        ("BOX",           (0, 0), (-1, -1), 2, NAVY),
        ("LINEABOVE",     (0, 0), (-1,  0), 4, ACCENT_GOLD),
        ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING",    (0, 0), (-1, -1), 18),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 18),
    ]))
    story.append(proj_card)
    story.append(Spacer(1, 0.4 * inch))

    # Cover detail rows
    cover_rows = [
        ("Tendering Authority",  issued_by),
        ("Submission Deadline",  deadline),
        ("Report Classification","CONFIDENTIAL"),
        ("Report Date",          _date()),
    ]
    cov_tbl = Table(
        [[Paragraph(k, S["CoverLbl"]), Paragraph(v, S["CoverVal"])]
         for k, v in cover_rows],
        colWidths=[2.1 * inch, 4.4 * inch]
    )
    cov_tbl.setStyle(TableStyle([
        ("LINEBELOW",     (0, 0), (-1, -2), 0.5, RULE_GREY),
        ("TOPPADDING",    (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
        ("LEFTPADDING",   (1, 0), (1, -1),  12),
        ("RIGHTPADDING",  (0, 0), (0, -1),  8),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(cov_tbl)
    story.append(Spacer(1, 0.7 * inch))

    story.append(HRFlowable(width="100%", thickness=0.5, color=RULE_GREY))
    story.append(Spacer(1, 0.1 * inch))
    story.append(Paragraph(
        "This document contains proprietary and confidential information. "
        "Unauthorised distribution or reproduction is strictly prohibited.",
        S["Foot"]
    ))
    story.append(PageBreak())

    # ══════════════════════════════════════════════════════════════════════
    # 2. TABLE OF CONTENTS
    # ══════════════════════════════════════════════════════════════════════
    story.append(_section_block("TABLE OF CONTENTS", S))
    story.append(Spacer(1, 0.15 * inch))

    toc_items = [
        ("1", "Executive Summary"),
        ("2", "Bid Viability Score"),
        ("3", "Project Details"),
        ("4", "Scope of Supply \u2014 OEM Recommendations"),
        ("5", "Consolidated Pricing"),
        ("6", "Recommended Action Items"),
    ]
    for num, title in toc_items:
        row = Table(
            [[Paragraph(f"{num}.  {title}",
                        ParagraphStyle("_TOC", fontName=FONT_NORMAL,
                                       fontSize=10, textColor=NAVY))]],
            colWidths=[7.0 * inch]
        )
        row.setStyle(TableStyle([
            ("LINEBELOW",     (0, 0), (-1, -1), 0.5, RULE_GREY),
            ("TOPPADDING",    (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ("LEFTPADDING",   (0, 0), (-1, -1), 8),
        ]))
        story.append(row)
    story.append(PageBreak())

    # ══════════════════════════════════════════════════════════════════════
    # 3. EXECUTIVE SUMMARY
    # ══════════════════════════════════════════════════════════════════════
    story.append(_section_block("1.   EXECUTIVE SUMMARY", S))
    story.append(Spacer(1, 0.15 * inch))

    # KPI strip
    story.append(_kpi_strip([
        ("MATERIAL COST",   _inr(total_mat),   C_ACCENT),
        ("TEST COST",       _inr(total_test),  C_ORANGE),
        ("GRAND TOTAL",     _inr(grand_total), NAVY),
        ("LINE ITEMS",      str(len(line_items)), NAVY),
    ]))
    story.append(Spacer(1, 0.2 * inch))

    # Score gauge
    story.append(_score_gauge(bid_score))
    story.append(Spacer(1, 0.2 * inch))

    story.append(Paragraph("1.1  Overview", S["SubHead"]))
    story.append(Paragraph(
        f"This report presents OEM product recommendations and consolidated pricing for the tender "
        f"<b>'{project_name}'</b> issued by <b>{issued_by}</b>, deadline <b>{deadline}</b>. "
        f"The scope has been parsed into <b>{len(line_items)}</b> line item(s). "
        f"For each, the top 3 OEM products were evaluated with equal-weighted spec matching "
        f"across voltage, conductor material, insulation type, cores, armoring, and standards. "
        f"The overall bid viability score is <b>{bid_score:.1f} / 100</b>.",
        S["Body"]
    ))
    story.append(Spacer(1, 0.12 * inch))

    story.append(Paragraph("1.2  Cost Summary", S["SubHead"]))
    sum_data = [
        ["Cost Component",             "Amount (INR)"],
        ["Total Material Cost",        _inr(total_mat)],
        ["Total Test & Services Cost", _inr(total_test)],
        ["GRAND TOTAL",                _inr(grand_total)],
    ]
    s_ts = _ts()
    s_ts.add("ALIGN",      (1, 0),  (1, -1),  "RIGHT")
    s_ts.add("FONTNAME",   (0, -1), (-1, -1), FONT_BOLD)
    s_ts.add("BACKGROUND", (0, -1), (-1, -1), LIGHT_BLUE)
    s_ts.add("TEXTCOLOR",  (0, -1), (-1, -1), NAVY)
    sum_t = Table(sum_data, colWidths=[4.5 * inch, 2.5 * inch])
    sum_t.setStyle(s_ts)
    story.append(sum_t)
    story.append(PageBreak())

    # ══════════════════════════════════════════════════════════════════════
    # 4. BID VIABILITY SCORE
    # ══════════════════════════════════════════════════════════════════════
    story.append(_section_block("2.   BID VIABILITY SCORE", S))
    story.append(Spacer(1, 0.15 * inch))

    # Recommendation banner
    banner = Table(
        [[Paragraph(
            f"Recommendation:  <b>{rec_text}</b>  |  Score: <b>{bid_score:.1f} / 100</b>  |  Grade: <b>{bid_grade}</b>",
            ParagraphStyle("_Ban", fontName=FONT_NORMAL, fontSize=10,
                           textColor=rec_color, alignment=TA_CENTER)
        )]],
        colWidths=[7.0 * inch]
    )
    banner.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), rec_bg),
        ("BOX",           (0, 0), (-1, -1), 1, rec_color),
        ("LINEABOVE",     (0, 0), (-1,  0), 3, rec_color),
        ("TOPPADDING",    (0, 0), (-1, -1), 12),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
    ]))
    story.append(banner)
    story.append(Spacer(1, 0.18 * inch))

    story.append(Paragraph(
        "Five weighted factors are assessed against our OEM portfolio to evaluate bid viability.",
        S["Body"]
    ))
    story.append(Spacer(1, 0.12 * inch))

    story.append(Paragraph("2.1  Recommendation Detail", S["SubHead"]))
    story.append(Paragraph(bid_rec, S["Body"]))
    story.append(Spacer(1, 0.15 * inch))

    factor_defs = {
        "technical_match":       ("Technical Match",       "35%"),
        "price_competitiveness": ("Price Competitiveness", "25%"),
        "delivery_capability":   ("Delivery Capability",   "15%"),
        "compliance":            ("Compliance & Certs",    "15%"),
        "risk_assessment":       ("Risk Assessment",       "10%"),
    }
    f_rows = [["Factor", "Weight", "Raw Score", "Progress", "Weighted"]]
    for key, (label, wt) in factor_defs.items():
        raw     = _f(components.get(key, 0))
        contrib = _f(weighted.get(key,   0))
        f_rows.append([label, wt, f"{raw:.1f}", _score_bar(raw), f"{contrib:.2f}"])
    f_rows.append(["TOTAL BID VIABILITY SCORE", "", "", "", f"{bid_score:.2f}"])

    f_ts = _ts()
    f_ts.add("ALIGN",      (1, 0),  (1, -1),  "CENTER")
    f_ts.add("ALIGN",      (2, 0),  (2, -1),  "CENTER")
    f_ts.add("ALIGN",      (4, 0),  (4, -1),  "RIGHT")
    f_ts.add("FONTNAME",   (3, 1),  (3, -2),  "Courier")
    f_ts.add("FONTSIZE",   (3, 1),  (3, -2),  7.5)
    f_ts.add("TEXTCOLOR",  (3, 1),  (3, -2),  C_ACCENT)
    f_ts.add("FONTNAME",   (0, -1), (-1, -1), FONT_BOLD)
    f_ts.add("BACKGROUND", (0, -1), (-1, -1), LIGHT_BLUE)
    f_ts.add("TEXTCOLOR",  (0, -1), (-1, -1), NAVY)
    f_ts.add("SPAN",       (0, -1), (3, -1))
    f_ts.add("ALIGN",      (0, -1), (3, -1),  "RIGHT")
    f_t = Table(f_rows, colWidths=[2.2 * inch, 0.75 * inch, 0.85 * inch, 2.1 * inch, 0.85 * inch],
                repeatRows=1)
    f_t.setStyle(f_ts)
    story.append(f_t)
    story.append(PageBreak())

    # ══════════════════════════════════════════════════════════════════════
    # 5. PROJECT DETAILS
    # ══════════════════════════════════════════════════════════════════════
    story.append(_section_block("3.   PROJECT DETAILS", S))
    story.append(Spacer(1, 0.15 * inch))

    proj_rows = [
        ["Attribute",           "Details"],
        ["Project Name",        project_name],
        ["Tendering Authority", issued_by],
        ["Submission Deadline", deadline],
        ["Evaluation Date",     _date()],
        ["Line Items in Scope", str(len(line_items))],
        ["Grand Total (INR)",   _inr(grand_total)],
        ["Report Status",       "FINAL \u2014 CONFIDENTIAL"],
    ]
    # Convert data rows to styled paragraphs
    styled_proj = [proj_rows[0]]  # header as strings
    for k, v in proj_rows[1:]:
        styled_proj.append([
            Paragraph(k, ParagraphStyle("_DK", fontName=FONT_BOLD, fontSize=9, textColor=NAVY)),
            Paragraph(v, S["TableCell"])
        ])

    p_ts = _ts()
    proj_t = Table(styled_proj, colWidths=[2.2 * inch, 4.8 * inch])
    proj_t.setStyle(p_ts)
    story.append(proj_t)
    story.append(PageBreak())

    # ══════════════════════════════════════════════════════════════════════
    # 6. SCOPE OF SUPPLY — OEM RECOMMENDATIONS
    # ══════════════════════════════════════════════════════════════════════
    story.append(_section_block("4.   SCOPE OF SUPPLY \u2014 OEM RECOMMENDATIONS", S))
    story.append(Spacer(1, 0.12 * inch))
    story.append(Paragraph(
        "Top 3 OEM products per line item, ranked by Spec Match %. "
        "The selected SKU (\u2605) is highlighted.",
        S["Body"]
    ))
    story.append(Spacer(1, 0.15 * inch))

    for idx, item in enumerate(line_items, 1):
        line_text = str(item.get("line_item", f"Item {idx}"))
        top_3     = item.get("top_3_recommendations", [])
        selected  = item.get("selected_sku") or {}

        story.append(KeepTogether([
            Paragraph(
                f"<b>4.{idx}&nbsp; Line Item {idx}:</b>&nbsp; {line_text[:130]}",
                S["SubHead"]
            ),
            Spacer(1, 0.06 * inch),
        ]))

        if not top_3:
            story.append(Paragraph(
                "\u26a0  No matching OEM products found. Manual sourcing required.",
                S["Body"]
            ))
            story.append(Spacer(1, 0.15 * inch))
            continue

        # Top-3 table
        t3h = ["Rank", "SKU / Product Name", "Spec Match", "Unit Price", "Lead Time", "BIS"]
        t3d = [t3h]
        for m in top_3:
            sel   = m.get("product_id") == selected.get("product_id")
            r_lbl = "#1 \u2605 SELECTED" if sel else f"#{m.get('rank', '?')}"
            pid   = str(m.get("product_id",   ""))
            pname = str(m.get("product_name", ""))
            t3d.append([
                Paragraph(r_lbl, S["CellBold"] if sel else S["Cell"]),
                Paragraph(
                    f"<b>{pid}</b><br/>"
                    f"<font size='7.5' color='#888888'>{pname}</font>",
                    S["Cell"]
                ),
                _pct(m.get("spec_match_percent", 0)),
                _inr(m.get("unit_price", 0), decimals=2),
                _days(m.get("lead_time_days")),
                str(m.get("bis_certified", "N/A")),
            ])

        t3_ts = _ts()
        t3_ts.add("ALIGN",      (2, 0), (2, -1), "CENTER")
        t3_ts.add("ALIGN",      (3, 0), (3, -1), "RIGHT")
        t3_ts.add("ALIGN",      (4, 0), (5, -1), "CENTER")
        # Highlight selected row (row 1 = first data row)
        t3_ts.add("BACKGROUND", (0, 1), (-1, 1), colors.HexColor("#E8F8F0"))
        t3_ts.add("LINEABOVE",  (0, 1), (-1, 1), 1.2, C_ACCENT2)
        t3_ts.add("LINEBELOW",  (0, 1), (-1, 1), 1.2, C_ACCENT2)
        t3_t = Table(
            t3d,
            colWidths=[1.15 * inch, 2.7 * inch, 0.85 * inch, 1.05 * inch, 0.8 * inch, 0.45 * inch],
            repeatRows=1,
        )
        t3_t.setStyle(t3_ts)
        story.append(t3_t)
        story.append(Spacer(1, 0.14 * inch))

        # Spec comparison table
        story.append(Paragraph("Specification Comparison:", S["SubHead"]))
        comp_src = top_3[0].get("comparison_table") if top_3 else None
        if comp_src:
            comp_hdr = ["Spec Parameter", "RFP Requirement",
                        "#1 Product Value", "#2 Product Value", "#3 Product Value"]
            comp_rows = [comp_hdr]
            for sk in comp_src:
                label   = sk.replace("_", " ").title()
                rfp_val = str(top_3[0]["comparison_table"].get(sk, {})
                              .get("rfp_requirement", "N/A"))
                row = [label, rfp_val]
                for m in top_3:
                    ct   = m.get("comparison_table", {}).get(sk, {})
                    pv   = str(ct.get("product_value", "\u2013"))
                    if pv in ("nan", "None", ""): pv = "\u2013"
                    icon = _match_icon(ct.get("match", ""))
                    clr  = C_GREEN if icon == "\u2713" else (C_RED if icon == "\u2717" else C_MUTED)
                    row.append(Paragraph(
                        f"{pv} &nbsp;<font color='#{clr.hexval()[2:]}'><b>{icon}</b></font>",
                        S["Cell"]
                    ))
                comp_rows.append(row)

            comp_ts = _ts(header_bg=STEEL)
            comp_t  = Table(comp_rows,
                            colWidths=[1.4 * inch, 1.15 * inch, 1.55 * inch, 1.55 * inch, 1.35 * inch],
                            repeatRows=1)
            comp_t.setStyle(comp_ts)
            story.append(comp_t)

        story.append(Spacer(1, 0.1 * inch))
        story.append(HRFlowable(width="100%", thickness=0.5, color=RULE_GREY, spaceAfter=10))
        story.append(PageBreak())

    # ══════════════════════════════════════════════════════════════════════
    # 7. CONSOLIDATED PRICING
    # ══════════════════════════════════════════════════════════════════════
    story.append(_section_block("5.   CONSOLIDATED PRICING", S))
    story.append(Spacer(1, 0.12 * inch))
    story.append(Paragraph(
        "Unit prices from OEM Product Catalog. "
        "Material cost = unit price \u00d7 MOQ. "
        "Test costs from Testing Services price list.",
        S["Body"]
    ))
    story.append(Spacer(1, 0.14 * inch))

    p_hdr = ["#", "OEM SKU", "Unit Price\n(\u20b9/m)", "MOQ (m)",
             "Material Cost (\u20b9)", "Test Cost (\u20b9)", "Line Total (\u20b9)"]
    p_rows = [p_hdr]
    for idx, item in enumerate(line_items, 1):
        sku    = item.get("selected_sku") or {}
        sku_id = str(sku.get("product_id", item.get("sku", "N/A")))
        p_rows.append([
            str(idx),
            Paragraph(sku_id, S["Cell"]),
            _inr(item.get("unit_price_inr",   0), decimals=2),
            str(item.get("moq_meters", 0)),
            _inr(item.get("material_cost_inr", 0)),
            _inr(item.get("test_cost_inr",     0)),
            _inr(item.get("line_total_inr",    0)),
        ])
    p_rows.append([
        "TOTAL", "", "", "",
        _inr(total_mat), _inr(total_test), _inr(grand_total),
    ])
    p_ts2 = _ts()
    p_ts2.add("ALIGN",      (2, 0),  (-1, -1), "RIGHT")
    p_ts2.add("ALIGN",      (0, 0),  (1, -1),  "LEFT")
    p_ts2.add("ALIGN",      (3, 0),  (3, -1),  "CENTER")
    p_ts2.add("FONTNAME",   (0, -1), (-1, -1), FONT_BOLD)
    p_ts2.add("BACKGROUND", (0, -1), (-1, -1), LIGHT_BLUE)
    p_ts2.add("TEXTCOLOR",  (0, -1), (-1, -1), NAVY)
    price_t = Table(
        p_rows,
        colWidths=[0.38 * inch, 2.2 * inch, 1.0 * inch, 0.62 * inch, 1.1 * inch, 1.0 * inch, 0.7 * inch],
        repeatRows=1,
    )
    price_t.setStyle(p_ts2)
    story.append(price_t)
    story.append(Spacer(1, 0.22 * inch))

    # Test services breakdown
    story.append(Paragraph("5.1  Test &amp; Services Breakdown", S["SubHead"]))
    t_hdr = ["Item #", "Test Code", "Test Name", "Cost (\u20b9)", "Duration (hrs)"]
    t_rows = [t_hdr]
    for idx, item in enumerate(line_items, 1):
        for t in item.get("applicable_tests", []):
            t_rows.append([
                str(idx),
                str(t.get("test_code", "")),
                str(t.get("test_name", "")),
                _inr(t.get("price_inr", 0)),
                str(t.get("duration_hours", "")),
            ])
    t_ts = _ts()
    t_ts.add("ALIGN", (3, 0), (4, -1), "RIGHT")
    test_t = Table(
        t_rows,
        colWidths=[0.6 * inch, 1.0 * inch, 3.2 * inch, 1.1 * inch, 1.1 * inch],
        repeatRows=1,
    )
    test_t.setStyle(t_ts)
    story.append(test_t)
    story.append(PageBreak())

    # ══════════════════════════════════════════════════════════════════════
    # 8. ACTION ITEMS & SIGN-OFF
    # ══════════════════════════════════════════════════════════════════════
    story.append(_section_block("6.   RECOMMENDED ACTION ITEMS", S))
    story.append(Spacer(1, 0.12 * inch))

    acts = [
        ["Phase",      "Action Item",                                               "Owner"],
        ["Pre-Bid",    "Validate Bill of Quantities against tender specifications",  "Technical Team"],
        ["Pre-Bid",    "Obtain BIS / test certificates from recommended OEMs",      "Procurement"],
        ["Pre-Bid",    "Confirm lead times align with delivery schedule",            "Supply Chain"],
        ["Bid Prep",   "Finalise commercial terms and prepare bid documentation",   "Commercial Team"],
        ["Bid Prep",   "Review liquidated damages and penalty clauses",             "Legal Team"],
        ["Submission", "Internal review and management approval",                   "Bid Manager"],
        ["Submission", "Submit complete bid package before deadline",               "Bid Manager"],
    ]
    act_t = Table(acts, colWidths=[1.1 * inch, 4.4 * inch, 1.5 * inch], repeatRows=1)
    act_t.setStyle(_ts())
    story.append(act_t)
    story.append(Spacer(1, 0.28 * inch))

    story.append(Paragraph("6.1  Approval &amp; Authorisation", S["SubHead"]))
    story.append(Spacer(1, 0.06 * inch))
    sign_rows = [
        ["Prepared By:",  "_" * 35, "Date:", "_" * 22],
        ["",              "",        "",      ""],
        ["Reviewed By:",  "_" * 35, "Date:", "_" * 22],
        ["",              "",        "",      ""],
        ["Approved By:",  "_" * 35, "Date:", "_" * 22],
    ]
    so_t = Table(sign_rows, colWidths=[1.15 * inch, 2.95 * inch, 0.7 * inch, 2.2 * inch])
    so_t.setStyle(TableStyle([
        ("FONTSIZE",      (0, 0), (-1, -1), 9),
        ("FONTNAME",      (0, 0), (0, -1),  FONT_BOLD),
        ("TEXTCOLOR",     (0, 0), (0, -1),  NAVY),
        ("FONTNAME",      (2, 0), (2, -1),  FONT_BOLD),
        ("TEXTCOLOR",     (2, 0), (2, -1),  NAVY),
        ("VALIGN",        (0, 0), (-1, -1), "BOTTOM"),
        ("TOPPADDING",    (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    story.append(so_t)
    story.append(Spacer(1, 0.5 * inch))

    story.append(HRFlowable(width="100%", thickness=0.5, color=RULE_GREY))
    story.append(Spacer(1, 0.1 * inch))
    story.append(Paragraph(
        f"<i>End of Report \u2013 Generated {_date(include_time=True)}</i>",
        S["Foot"]
    ))

    doc.build(story, onFirstPage=_cover_page, onLaterPages=_header_footer)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes