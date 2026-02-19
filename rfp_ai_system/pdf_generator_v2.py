# pdf_generator_v2.py
"""
RFP Bid Evaluation PDF Report Generator — Redesigned UI
=========================================================
Cross-platform fixes applied:
  1. _f() / _inr() — safe numeric coercion (handles None, NaN, pre-formatted strings)
  2. _date() — replaces strftime("%-d") which is Linux-only; crashes on Windows
  3. _pct() — safe spec_match_percent formatter (value may arrive as string from JSON)
  4. _days() — safe lead_time_days formatter (value may be None/NaN)
"""

import os
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
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_RIGHT
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus.flowables import Flowable


# ─── Cross-platform Unicode font registration ────────────────────────────────

def _find_font(candidates: list):
    for path in candidates:
        if os.path.isfile(path):
            return path
    return None

_NORMAL_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",       # Linux (Debian/Ubuntu)
    "/usr/share/fonts/dejavu/DejaVuSans.ttf",                # Linux (RHEL/Fedora)
    "/Library/Fonts/Arial.ttf",                              # macOS
    "/System/Library/Fonts/Helvetica.ttc",                   # macOS fallback
    r"C:\Windows\Fonts\arial.ttf",                           # Windows
    r"C:\Windows\Fonts\calibri.ttf",                         # Windows fallback
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


# ─── Brand palette ───────────────────────────────────────────────────────────
C_PRIMARY   = colors.HexColor("#1A3A6B")
C_ACCENT    = colors.HexColor("#2E86C1")
C_ACCENT2   = colors.HexColor("#1ABC9C")
C_ORANGE    = colors.HexColor("#E67E22")
C_RED       = colors.HexColor("#C0392B")
C_GREEN     = colors.HexColor("#27AE60")
C_HEADER_BG = colors.HexColor("#1A3A6B")
C_ROW_ALT   = colors.HexColor("#F0F4FA")
C_ROW_WHITE = colors.white
C_BORDER    = colors.HexColor("#C8D6E8")
C_MUTED     = colors.HexColor("#6C7A89")
C_TEXT      = colors.HexColor("#1C2833")
C_LIGHT_BG  = colors.HexColor("#EBF5FB")


# ─── Safe formatting helpers ─────────────────────────────────────────────────
# Every helper below is deliberately defensive: no helper may raise an
# exception regardless of what type or value it receives.

def _f(x, default: float = 0.0) -> float:
    """
    Safely coerce any value to float.
    Handles: int, float, numpy.float64, None, NaN, Inf,
             and pre-formatted strings like '₹ 1,23,456.78' or '1,130.62'.
    """
    if x is None:
        return default
    try:
        v = float(x)
        # Reject NaN and Inf — they crash f-string :.Xf formatters
        if v != v or v == float("inf") or v == float("-inf"):
            return default
        return v
    except (TypeError, ValueError):
        pass
    # Strip currency symbols, commas, spaces and retry
    cleaned = _re.sub(r"[^\d.\-]", "", str(x))
    try:
        v = float(cleaned) if cleaned else default
        return v if (v == v) else default
    except ValueError:
        return default


def _inr(val, decimals: int = 0) -> str:
    """
    Format as Indian Rupee.  Always returns a plain string — never raises.
    Examples: _inr(9648809) → '₹ 9,648,809'
              _inr(None)    → '₹ 0'
              _inr('₹ 1,130.62', 2) → '₹ 1,130.62'  (idempotent)
    """
    return f"\u20b9 {_f(val):,.{decimals}f}"


def _pct(val) -> str:
    """
    Format a spec-match percentage.
    Handles float, int, string ('71.4'), or None — never raises.
    Example: _pct('71.4') → '71.4%'   _pct(None) → '0.0%'
    """
    return f"{_f(val):.1f}%"


def _days(val) -> str:
    """
    Format a lead-time value as '<N> d'.
    Handles int, float, string, None — never raises.
    Example: _days(30) → '30 d'   _days(None) → 'N/A'
    """
    if val is None:
        return "N/A"
    try:
        v = int(float(str(val)))
        return f"{v} d"
    except (TypeError, ValueError):
        return "N/A"


def _date(include_time: bool = False) -> str:
    """
    Cross-platform date string without leading zero on the day.
    Avoids strftime('%-d') which is Linux-only and crashes on Windows.
    Example: '19 February 2026'  or  '19 February 2026 at 14:35'
    """
    now = datetime.now()
    base = f"{now.day} {now.strftime('%B %Y')}"
    return f"{base} at {now.strftime('%H:%M')}" if include_time else base


def _grade_color(grade: str):
    g = str(grade).strip().upper()
    if g.startswith("A"): return C_GREEN
    if g.startswith("B"): return C_ORANGE
    return C_RED


def _score_bar(score: float, width: int = 18) -> str:
    """Unicode block progress bar (DejaVu renders ██░░ correctly)."""
    filled = max(0, min(width, round((_f(score) / 100) * width)))
    return "\u2588" * filled + "\u2591" * (width - filled)


def _match_icon(match_str: str) -> str:
    s = str(match_str)
    if "No Match" in s: return "\u2717"   # ✗
    if "Match"    in s: return "\u2713"   # ✓
    return "\u2013"                        # –


# ─── Custom flowables ─────────────────────────────────────────────────────────

class SectionHeader(Flowable):
    """Section title with a thick left colour bar on a light background."""
    def __init__(self, text, number=None, fontsize=12,
                 bar_color=C_PRIMARY, text_color=C_PRIMARY, width=None):
        super().__init__()
        self.text       = text
        self.number     = number
        self.fontsize   = fontsize
        self.bar_color  = bar_color
        self.text_color = text_color
        self._width     = width or (7.0 * inch)
        self.height     = fontsize + 18

    def wrap(self, aw, ah):
        return self._width, self.height

    def draw(self):
        c = self.canv
        h, w = self.height, self._width
        c.setFillColor(C_LIGHT_BG)
        c.roundRect(0, 0, w, h, 4, fill=1, stroke=0)
        c.setFillColor(self.bar_color)
        c.roundRect(0, 0, 5, h, 2, fill=1, stroke=0)
        c.setFont(FONT_BOLD, self.fontsize)
        c.setFillColor(self.text_color)
        label = f"{self.number}.  {self.text}" if self.number else self.text
        c.drawString(14, (h - self.fontsize) / 2 + 2, label)


class KPICard(Flowable):
    """Metric card with a top colour strip, big value, and small label."""
    def __init__(self, label, value, value_color=C_PRIMARY,
                 card_w=2.1*inch, card_h=0.9*inch):
        super().__init__()
        self.label       = label
        self.value       = str(value)
        self.value_color = value_color
        self.card_w      = card_w
        self.card_h      = card_h

    def wrap(self, aw, ah):
        return self.card_w, self.card_h

    def draw(self):
        c = self.canv
        w, h = self.card_w, self.card_h
        c.setFillColor(colors.white)
        c.setStrokeColor(C_BORDER)
        c.setLineWidth(1)
        c.roundRect(0, 0, w, h, 5, fill=1, stroke=1)
        c.setFillColor(C_ACCENT)
        c.roundRect(0, h - 6, w, 6, 3, fill=1, stroke=0)
        c.setFont(FONT_BOLD, 12)
        c.setFillColor(self.value_color)
        c.drawCentredString(w / 2, h * 0.35, self.value)
        c.setFont(FONT_NORMAL, 7)
        c.setFillColor(C_MUTED)
        c.drawCentredString(w / 2, h * 0.13, self.label.upper())


# ─── Header / Footer ─────────────────────────────────────────────────────────

def _header_footer(canvas_obj, doc):
    canvas_obj.saveState()
    W = A4[0]
    if doc.page > 1:
        canvas_obj.setStrokeColor(C_PRIMARY)
        canvas_obj.setLineWidth(2)
        canvas_obj.line(0.65*inch, 10.72*inch, W - 0.65*inch, 10.72*inch)
        canvas_obj.setFont(FONT_BOLD, 8)
        canvas_obj.setFillColor(C_PRIMARY)
        canvas_obj.drawString(0.65*inch, 10.82*inch, "RFP BID EVALUATION REPORT")
        canvas_obj.setFont(FONT_NORMAL, 7.5)
        canvas_obj.setFillColor(C_MUTED)
        # _date() — no %-d, safe on Windows
        canvas_obj.drawRightString(W - 0.65*inch, 10.82*inch, _date())
    canvas_obj.setStrokeColor(C_ACCENT)
    canvas_obj.setLineWidth(1.5)
    canvas_obj.line(0.65*inch, 0.68*inch, W - 0.65*inch, 0.68*inch)
    canvas_obj.setFont(FONT_NORMAL, 7)
    canvas_obj.setFillColor(C_MUTED)
    canvas_obj.drawString(0.65*inch, 0.48*inch,
                          "CONFIDENTIAL \u2013 For Internal Use Only")
    canvas_obj.setFillColor(C_PRIMARY)
    canvas_obj.roundRect(W - 1.1*inch, 0.38*inch, 0.6*inch, 0.22*inch,
                         3, fill=1, stroke=0)
    canvas_obj.setFont(FONT_BOLD, 7.5)
    canvas_obj.setFillColor(colors.white)
    canvas_obj.drawCentredString(W - 0.8*inch, 0.44*inch, f"Page {doc.page}")
    canvas_obj.restoreState()


# ─── Style factory ────────────────────────────────────────────────────────────

def _styles():
    base = getSampleStyleSheet()

    def ps(name, **kw):
        kw.setdefault("fontName", FONT_NORMAL)
        base.add(ParagraphStyle(name=name, parent=base["Normal"], **kw))

    ps("H_Cover",  fontSize=28, textColor=C_PRIMARY, alignment=TA_CENTER,
       fontName=FONT_BOLD, leading=34, spaceAfter=4)
    ps("H_Sub",    fontSize=13, textColor=C_ACCENT,  alignment=TA_CENTER,
       fontName=FONT_BOLD, spaceAfter=18)
    ps("Body",     fontSize=9.5, textColor=C_TEXT, leading=14, alignment=TA_JUSTIFY)
    ps("SubHead",  fontSize=10.5, textColor=C_ACCENT, fontName=FONT_BOLD,
       spaceBefore=10, spaceAfter=5)
    ps("Cell",     fontSize=8.5, textColor=C_TEXT, leading=11)
    ps("CellBold", fontSize=8.5, textColor=C_PRIMARY, leading=11, fontName=FONT_BOLD)
    ps("Score",    fontSize=30, textColor=C_PRIMARY, alignment=TA_CENTER,
       fontName=FONT_BOLD)
    ps("Grade",    fontSize=16, alignment=TA_CENTER, fontName=FONT_BOLD)
    ps("CoverLbl", fontSize=10, textColor=C_MUTED,  fontName=FONT_BOLD)
    ps("CoverVal", fontSize=10, textColor=C_TEXT)
    ps("Foot",     fontSize=8,  textColor=C_MUTED,  alignment=TA_CENTER)
    return base


# ─── Table style preset ───────────────────────────────────────────────────────

def _ts(header_bg=C_HEADER_BG):
    return TableStyle([
        ("BACKGROUND",    (0, 0), (-1,  0),  header_bg),
        ("TEXTCOLOR",     (0, 0), (-1,  0),  colors.white),
        ("FONTNAME",      (0, 0), (-1,  0),  FONT_BOLD),
        ("FONTNAME",      (0, 1), (-1, -1),  FONT_NORMAL),
        ("FONTSIZE",      (0, 0), (-1, -1),  8.5),
        ("ALIGN",         (0, 0), (-1,  0),  "CENTER"),
        ("ALIGN",         (0, 1), (-1, -1),  "LEFT"),
        ("VALIGN",        (0, 0), (-1, -1),  "MIDDLE"),
        ("TOPPADDING",    (0, 0), (-1, -1),  6),
        ("BOTTOMPADDING", (0, 0), (-1, -1),  6),
        ("LEFTPADDING",   (0, 0), (-1, -1),  8),
        ("RIGHTPADDING",  (0, 0), (-1, -1),  8),
        ("LINEBELOW",     (0, 0), (-1,  0),  1.5, C_ACCENT),
        ("LINEBELOW",     (0, 1), (-1, -2),  0.4, C_BORDER),
        ("BOX",           (0, 0), (-1, -1),  0.5, C_BORDER),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1),  [C_ROW_WHITE, C_ROW_ALT]),
    ])


# ─── Main generator ───────────────────────────────────────────────────────────

def generate_rfp_pdf(rfp_data: dict, output_path: str) -> str:
    out_dir = os.path.dirname(output_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    doc = SimpleDocTemplate(
        output_path, pagesize=A4,
        leftMargin=0.65*inch, rightMargin=0.65*inch,
        topMargin=1.15*inch,  bottomMargin=0.9*inch,
        title="RFP Bid Evaluation Report",
    )
    S     = _styles()
    story = []

    # Unpack — all numerics go through _f() immediately
    project_name = rfp_data.get("project_name", "N/A")
    issued_by    = rfp_data.get("issued_by",    "N/A")
    deadline     = rfp_data.get("deadline",     "N/A")
    line_items   = rfp_data.get("line_items",   [])
    summary      = rfp_data.get("summary",      {})
    bid          = rfp_data.get("bid_viability",{})

    bid_score  = _f(bid.get("score", 0))
    bid_grade  = str(bid.get("grade", "N/A"))
    bid_rec    = str(bid.get("recommendation", ""))
    components = bid.get("component_scores",        {}) or {}
    weighted   = bid.get("weighted_contributions",  {}) or {}

    total_mat   = _f(summary.get("total_material_cost_inr", 0))
    total_test  = _f(summary.get("total_test_cost_inr",     0))
    grand_total = _f(summary.get("grand_total_inr",         0))

    # ══════════════════════════════════════════════════════════════════════
    # 1. COVER PAGE
    # ══════════════════════════════════════════════════════════════════════
    story.append(Spacer(1, 0.6*inch))
    story.append(Paragraph("RFP BID EVALUATION REPORT", S["H_Cover"]))
    story.append(Paragraph("OEM Product Recommendation &amp; Pricing Analysis", S["H_Sub"]))
    story.append(HRFlowable(width="100%", thickness=2, color=C_ACCENT, spaceAfter=18))

    cov_data = [
        [Paragraph("<b>Project Name</b>",        S["CoverLbl"]), Paragraph(project_name, S["CoverVal"])],
        [Paragraph("<b>Tendering Authority</b>",  S["CoverLbl"]), Paragraph(issued_by,    S["CoverVal"])],
        [Paragraph("<b>Submission Deadline</b>",  S["CoverLbl"]), Paragraph(deadline,     S["CoverVal"])],
        # _date() instead of strftime("%-d ...") — works on Windows
        [Paragraph("<b>Report Date</b>",          S["CoverLbl"]), Paragraph(_date(),      S["CoverVal"])],
    ]
    cov_t = Table(cov_data, colWidths=[1.8*inch, 4.8*inch])
    cov_t.setStyle(TableStyle([
        ("FONTNAME",      (0, 0), (-1, -1), FONT_NORMAL),
        ("FONTSIZE",      (0, 0), (-1, -1), 10),
        ("TOPPADDING",    (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
        ("LEFTPADDING",   (0, 0), (-1, -1), 10),
        ("LINEBELOW",     (0, 0), (-1, -2), 0.5, C_BORDER),
        ("BACKGROUND",    (0, 0), (0, -1),  C_LIGHT_BG),
    ]))
    story.append(cov_t)
    story.append(Spacer(1, 0.25*inch))

    grade_c = _grade_color(bid_grade)
    banner = [[
        # bid_score already a float — safe to format directly
        Paragraph(f"<b>{bid_score:.1f} / 100</b>", S["Score"]),
        Paragraph(f"<font color='#{grade_c.hexval()[2:]}'><b>{bid_grade}</b></font>", S["Grade"]),
        Paragraph(f"<b>Recommendation:</b><br/>{bid_rec}", S["Body"]),
    ]]
    banner_t = Table(banner, colWidths=[1.8*inch, 1.5*inch, 3.3*inch])
    banner_t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (0, 0),   C_LIGHT_BG),
        ("BOX",           (0, 0), (-1, -1), 1.5, C_PRIMARY),
        ("LINEAFTER",     (0, 0), (1, 0),   0.5, C_BORDER),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",    (0, 0), (-1, -1), 12),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
        ("LEFTPADDING",   (0, 0), (-1, -1), 12),
    ]))
    story.append(banner_t)
    story.append(PageBreak())

    # ══════════════════════════════════════════════════════════════════════
    # 2. EXECUTIVE SUMMARY
    # ══════════════════════════════════════════════════════════════════════
    story.append(SectionHeader("EXECUTIVE SUMMARY", number=1))
    story.append(Spacer(1, 0.12*inch))
    story.append(Paragraph(
        f"This report presents OEM product recommendations and consolidated pricing for the tender "
        f"<b>'{project_name}'</b> issued by <b>{issued_by}</b>, deadline <b>{deadline}</b>. "
        f"The scope has been parsed into <b>{len(line_items)}</b> line item(s). "
        f"For each, the top 3 OEM products were evaluated with equal-weighted spec matching "
        f"across voltage, conductor material, insulation type, cores, armoring, and standards.",
        S["Body"]
    ))
    story.append(Spacer(1, 0.18*inch))

    kpi_row = [[
        KPICard("Material Cost", _inr(total_mat),   C_ACCENT),
        KPICard("Test Cost",     _inr(total_test),  C_ORANGE),
        KPICard("Grand Total",   _inr(grand_total), C_PRIMARY),
    ]]
    kpi_t = Table(kpi_row, colWidths=[2.3*inch, 2.3*inch, 2.3*inch])
    kpi_t.setStyle(TableStyle([
        ("ALIGN",        (0, 0), (-1, -1), "CENTER"),
        ("VALIGN",       (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING",  (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(kpi_t)
    story.append(Spacer(1, 0.2*inch))

    sum_data = [
        ["Cost Component",             "Amount (INR)"],
        ["Total Material Cost",        _inr(total_mat)],
        ["Total Test & Services Cost", _inr(total_test)],
        ["GRAND TOTAL",                _inr(grand_total)],
    ]
    s_ts = _ts()
    s_ts.add("ALIGN",      (1, 0),  (1, -1),  "RIGHT")
    s_ts.add("FONTNAME",   (0, -1), (-1, -1), FONT_BOLD)
    s_ts.add("BACKGROUND", (0, -1), (-1, -1), C_LIGHT_BG)
    s_ts.add("TEXTCOLOR",  (0, -1), (-1, -1), C_PRIMARY)
    sum_t = Table(sum_data, colWidths=[4.0*inch, 2.7*inch])
    sum_t.setStyle(s_ts)
    story.append(sum_t)
    story.append(PageBreak())

    # ══════════════════════════════════════════════════════════════════════
    # 3. BID VIABILITY SCORE
    # ══════════════════════════════════════════════════════════════════════
    story.append(SectionHeader("BID VIABILITY SCORE", number=2))
    story.append(Spacer(1, 0.1*inch))
    story.append(Paragraph(
        "Five weighted factors are assessed against our OEM portfolio to evaluate bid viability.",
        S["Body"]
    ))
    story.append(Spacer(1, 0.15*inch))

    grade_c = _grade_color(bid_grade)
    sb_data = [[
        Paragraph(
            f"<font size='34'><b>{bid_score:.1f}</b></font>"
            f"<font size='9'><br/>out of 100</font>",
            S["Score"]
        ),
        Paragraph(
            f"<font color='#{grade_c.hexval()[2:]}' size='20'><b>{bid_grade}</b></font>",
            S["Grade"]
        ),
        Paragraph(f"<b>Recommendation</b><br/>{bid_rec}", S["Body"]),
    ]]
    sb_t = Table(sb_data, colWidths=[1.7*inch, 1.4*inch, 3.6*inch])
    sb_t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (0, 0),   C_LIGHT_BG),
        ("BOX",           (0, 0), (-1, -1), 1.5, C_PRIMARY),
        ("LINEAFTER",     (0, 0), (1,  0),  0.5, C_BORDER),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN",         (0, 0), (1,  0),  "CENTER"),
        ("TOPPADDING",    (0, 0), (-1, -1), 14),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 14),
        ("LEFTPADDING",   (0, 0), (-1, -1), 12),
    ]))
    story.append(sb_t)
    story.append(Spacer(1, 0.2*inch))

    factor_defs = {
        "technical_match":       ("Technical Match",       "35%"),
        "price_competitiveness": ("Price Competitiveness", "25%"),
        "delivery_capability":   ("Delivery Capability",   "15%"),
        "compliance":            ("Compliance & Certs",    "15%"),
        "risk_assessment":       ("Risk Assessment",       "10%"),
    }
    f_rows = [["Factor", "Weight", "Raw Score", "Progress", "Weighted"]]
    for key, (label, wt) in factor_defs.items():
        # _f() guards both dicts in case values are strings or missing
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
    f_ts.add("BACKGROUND", (0, -1), (-1, -1), C_LIGHT_BG)
    f_ts.add("TEXTCOLOR",  (0, -1), (-1, -1), C_PRIMARY)
    f_ts.add("SPAN",       (0, -1), (3, -1))
    f_ts.add("ALIGN",      (0, -1), (3, -1),  "RIGHT")
    f_t = Table(f_rows, colWidths=[2.1*inch, 0.7*inch, 0.8*inch, 2.0*inch, 0.8*inch],
                repeatRows=1)
    f_t.setStyle(f_ts)
    story.append(f_t)
    story.append(PageBreak())

    # ══════════════════════════════════════════════════════════════════════
    # 4. PROJECT DETAILS
    # ══════════════════════════════════════════════════════════════════════
    story.append(SectionHeader("PROJECT DETAILS", number=3))
    story.append(Spacer(1, 0.12*inch))
    proj_rows = [
        ["Attribute",           "Details"],
        ["Project Name",        project_name],
        ["Tendering Authority", issued_by],
        ["Submission Deadline", deadline],
        ["Evaluation Date",     _date()],           # _date() — Windows-safe
        ["Line Items in Scope", str(len(line_items))],
        ["Grand Total (INR)",   _inr(grand_total)],
    ]
    p_ts = _ts()
    p_ts.add("FONTNAME",  (0, 1), (0, -1), FONT_BOLD)
    p_ts.add("TEXTCOLOR", (0, 1), (0, -1), C_PRIMARY)
    proj_t = Table(proj_rows, colWidths=[2.0*inch, 4.6*inch])
    proj_t.setStyle(p_ts)
    story.append(proj_t)
    story.append(PageBreak())

    # ══════════════════════════════════════════════════════════════════════
    # 5. SCOPE OF SUPPLY — OEM RECOMMENDATIONS
    # ══════════════════════════════════════════════════════════════════════
    story.append(SectionHeader("SCOPE OF SUPPLY \u2014 OEM RECOMMENDATIONS", number=4))
    story.append(Spacer(1, 0.1*inch))
    story.append(Paragraph(
        "Top 3 OEM products per line item, ranked by Spec Match %. "
        "The selected SKU (\u2605) is highlighted in green.",
        S["Body"]
    ))
    story.append(Spacer(1, 0.15*inch))

    for idx, item in enumerate(line_items, 1):
        line_text = str(item.get("line_item", f"Item {idx}"))
        top_3     = item.get("top_3_recommendations", [])
        selected  = item.get("selected_sku") or {}

        story.append(KeepTogether([
            Paragraph(
                f"<b>4.{idx}&nbsp; Line Item {idx}:</b>&nbsp; {line_text[:130]}",
                S["SubHead"]
            ),
            Spacer(1, 0.06*inch),
        ]))

        if not top_3:
            story.append(Paragraph(
                "\u26a0  No matching OEM products found. Manual sourcing required.",
                S["Body"]
            ))
            story.append(Spacer(1, 0.15*inch))
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
                    f"<font size='7.5' color='#6C7A89'>{pname}</font>",
                    S["Cell"]
                ),
                # _pct() — safe even if spec_match_percent is a string
                _pct(m.get("spec_match_percent", 0)),
                # _inr() — safe even if unit_price is None or string
                _inr(m.get("unit_price", 0), decimals=2),
                # _days() — safe even if lead_time_days is None
                _days(m.get("lead_time_days")),
                str(m.get("bis_certified", "N/A")),
            ])

        t3_ts = _ts()
        t3_ts.add("ALIGN",      (2, 0),  (2, -1), "CENTER")
        t3_ts.add("ALIGN",      (3, 0),  (3, -1), "RIGHT")
        t3_ts.add("ALIGN",      (4, 0),  (5, -1), "CENTER")
        t3_ts.add("BACKGROUND", (0, 1),  (-1, 1), colors.HexColor("#E8F8F0"))
        t3_ts.add("LINEABOVE",  (0, 1),  (-1, 1), 1.2, C_ACCENT2)
        t3_ts.add("LINEBELOW",  (0, 1),  (-1, 1), 1.2, C_ACCENT2)
        t3_t = Table(
            t3d,
            colWidths=[1.1*inch, 2.6*inch, 0.8*inch, 1.0*inch, 0.75*inch, 0.4*inch],
            repeatRows=1,
        )
        t3_t.setStyle(t3_ts)
        story.append(t3_t)
        story.append(Spacer(1, 0.12*inch))

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
                    ct  = m.get("comparison_table", {}).get(sk, {})
                    pv  = str(ct.get("product_value", "\u2013"))
                    if pv in ("nan", "None", ""): pv = "\u2013"
                    icon = _match_icon(ct.get("match", ""))
                    clr  = C_GREEN if icon == "\u2713" else (C_RED if icon == "\u2717" else C_MUTED)
                    row.append(Paragraph(
                        f"{pv} &nbsp;<font color='#{clr.hexval()[2:]}'><b>{icon}</b></font>",
                        S["Cell"]
                    ))
                comp_rows.append(row)

            comp_ts = _ts(header_bg=C_ACCENT)
            comp_t  = Table(comp_rows,
                            colWidths=[1.3*inch, 1.1*inch, 1.5*inch, 1.5*inch, 1.2*inch],
                            repeatRows=1)
            comp_t.setStyle(comp_ts)
            story.append(comp_t)

        story.append(Spacer(1, 0.1*inch))
        story.append(HRFlowable(width="100%", thickness=0.5, color=C_BORDER, spaceAfter=10))
        story.append(PageBreak())

    # ══════════════════════════════════════════════════════════════════════
    # 6. CONSOLIDATED PRICING
    # ══════════════════════════════════════════════════════════════════════
    story.append(SectionHeader("CONSOLIDATED PRICING", number=5))
    story.append(Spacer(1, 0.1*inch))
    story.append(Paragraph(
        "Unit prices from OEM Product Catalog. "
        "Material cost = unit price \u00d7 MOQ. "
        "Test costs from Testing Services price list.",
        S["Body"]
    ))
    story.append(Spacer(1, 0.14*inch))

    p_hdr = ["#", "OEM SKU", "Unit Price\n(\u20b9/m)", "MOQ (m)",
             "Material Cost (\u20b9)", "Test Cost (\u20b9)", "Line Total (\u20b9)"]
    p_rows = [p_hdr]
    for idx, item in enumerate(line_items, 1):
        sku    = item.get("selected_sku") or {}
        sku_id = str(sku.get("product_id", item.get("sku", "N/A")))
        p_rows.append([
            str(idx),
            Paragraph(sku_id, S["Cell"]),
            _inr(item.get("unit_price_inr",  0), decimals=2),
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
    p_ts2.add("BACKGROUND", (0, -1), (-1, -1), C_LIGHT_BG)
    p_ts2.add("TEXTCOLOR",  (0, -1), (-1, -1), C_PRIMARY)
    price_t = Table(
        p_rows,
        colWidths=[0.35*inch, 2.15*inch, 0.95*inch, 0.6*inch, 1.05*inch, 0.95*inch, 1.0*inch],
        repeatRows=1,
    )
    price_t.setStyle(p_ts2)
    story.append(price_t)
    story.append(Spacer(1, 0.22*inch))

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
        colWidths=[0.6*inch, 1.0*inch, 3.1*inch, 1.0*inch, 0.95*inch],
        repeatRows=1,
    )
    test_t.setStyle(t_ts)
    story.append(test_t)
    story.append(PageBreak())

    # ══════════════════════════════════════════════════════════════════════
    # 7. ACTION ITEMS & SIGN-OFF
    # ══════════════════════════════════════════════════════════════════════
    story.append(SectionHeader("RECOMMENDED ACTION ITEMS", number=6))
    story.append(Spacer(1, 0.12*inch))
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
    act_t = Table(acts, colWidths=[1.1*inch, 4.2*inch, 1.4*inch], repeatRows=1)
    act_t.setStyle(_ts())
    story.append(act_t)
    story.append(Spacer(1, 0.3*inch))

    story.append(Paragraph("6.1  Approval &amp; Authorization", S["SubHead"]))
    story.append(Spacer(1, 0.06*inch))
    sign_rows = [
        ["Prepared By:",  "_" * 35, "Date:", "_" * 22],
        ["",              "",        "",      ""],
        ["Reviewed By:",  "_" * 35, "Date:", "_" * 22],
        ["",              "",        "",      ""],
        ["Approved By:",  "_" * 35, "Date:", "_" * 22],
    ]
    so_t = Table(sign_rows, colWidths=[1.1*inch, 2.9*inch, 0.7*inch, 1.9*inch])
    so_t.setStyle(TableStyle([
        ("FONTSIZE",     (0, 0), (-1, -1), 9),
        ("FONTNAME",     (0, 0), (0, -1),  FONT_BOLD),
        ("TEXTCOLOR",    (0, 0), (0, -1),  C_PRIMARY),
        ("VALIGN",       (0, 0), (-1, -1), "BOTTOM"),
        ("TOPPADDING",   (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 2),
    ]))
    story.append(so_t)
    story.append(Spacer(1, 0.5*inch))
    story.append(HRFlowable(width="100%", thickness=1, color=C_BORDER))
    story.append(Spacer(1, 0.08*inch))
    # _date(include_time=True) — Windows-safe replacement for strftime("%-d ... at %H:%M")
    story.append(Paragraph(
        f"<i>End of Report \u2013 Generated {_date(include_time=True)}</i>",
        S["Foot"]
    ))

    doc.build(story, onFirstPage=_header_footer, onLaterPages=_header_footer)
    return output_path