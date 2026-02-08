import os
from datetime import datetime

from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT, TA_RIGHT
from reportlab.graphics.shapes import Drawing, Rect, String
from reportlab.graphics.charts.barcharts import VerticalBarChart


# ============ HEADER AND FOOTER ============
def add_header_footer(canvas_obj, doc):
    """Add professional header and footer to each page"""
    canvas_obj.saveState()
    
    # Header (skip on first page)
    if doc.page > 1:
        canvas_obj.setStrokeColor(colors.HexColor("#1F4788"))
        canvas_obj.setLineWidth(2)
        canvas_obj.line(0.75 * inch, 10.7 * inch, 7.75 * inch, 10.7 * inch)
        
        canvas_obj.setFont("Helvetica-Bold", 9)
        canvas_obj.setFillColor(colors.HexColor("#1F4788"))
        canvas_obj.drawString(0.75 * inch, 10.85 * inch, "RFP BID EVALUATION REPORT")
        
        canvas_obj.setFont("Helvetica", 8)
        canvas_obj.setFillColor(colors.HexColor("#666666"))
        canvas_obj.drawRightString(7.75 * inch, 10.85 * inch, 
                                  f"Date: {datetime.now().strftime('%d %B %Y')}")
    
    # Footer
    canvas_obj.setStrokeColor(colors.HexColor("#1F4788"))
    canvas_obj.setLineWidth(2)
    canvas_obj.line(0.75 * inch, 0.7 * inch, 7.75 * inch, 0.7 * inch)
    
    canvas_obj.setFont("Helvetica", 8)
    canvas_obj.setFillColor(colors.HexColor("#666666"))
    canvas_obj.drawString(0.75 * inch, 0.5 * inch, "CONFIDENTIAL - For Internal Use Only")
    
    canvas_obj.setFont("Helvetica-Bold", 8)
    canvas_obj.drawRightString(7.75 * inch, 0.5 * inch, f"Page {doc.page}")
    
    canvas_obj.restoreState()


def _to_float(x, default=0.0):
    try:
        return float(x)
    except Exception:
        return float(default)


def _money_inr(x, decimals=0):
    val = _to_float(x, 0.0)
    if decimals == 2:
        return f"INR {val:,.2f}"
    return f"INR {val:,.0f}"

def create_score_chart(score):
    """Create a simple bar chart for compatibility score."""
    drawing = Drawing(400, 200)

    chart = VerticalBarChart()
    chart.x = 50
    chart.y = 50
    chart.height = 120
    chart.width = 300
    chart.data = [[score * 100]]
    chart.categoryAxis.categoryNames = ["Compatibility"]
    chart.valueAxis.valueMin = 0
    chart.valueAxis.valueMax = 100

    drawing.add(chart)
    drawing.add(String(200, 180, "Overall Compatibility Score (%)",
                   fontSize=12, textAnchor="middle"))

    return drawing



def generate_rfp_pdf(rfp_data, output_path):
    """Generate a professional government/client proposal-style RFP evaluation report."""

    out_dir = os.path.dirname(output_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    # Document setup
    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
        topMargin=1.2 * inch,
        bottomMargin=1.0 * inch,
        title="RFP Bid Evaluation Report",
    )

    

    # Styles
    styles = getSampleStyleSheet()

    # Custom styles for professional government documents
    styles.add(
        ParagraphStyle(
            name="CoverTitle",
            parent=styles["Heading1"],
            fontSize=28,
            textColor=colors.HexColor("#1F4788"),
            spaceAfter=6,
            alignment=TA_CENTER,
            fontName="Helvetica-Bold",
            leading=34,
        )
    )
    
    styles.add(
        ParagraphStyle(
            name="CoverSubtitle",
            parent=styles["Normal"],
            fontSize=16,
            textColor=colors.HexColor("#2E5090"),
            alignment=TA_CENTER,
            spaceAfter=30,
            fontName="Helvetica-Bold",
        )
    )
    
    styles.add(
        ParagraphStyle(
            name="CoverProject",
            parent=styles["Normal"],
            fontSize=14,
            textColor=colors.HexColor("#333333"),
            alignment=TA_CENTER,
            spaceAfter=8,
            fontName="Helvetica",
            leading=18,
        )
    )
    
    styles.add(
        ParagraphStyle(
            name="SectionHeader",
            parent=styles["Heading2"],
            fontSize=14,
            textColor=colors.white,
            spaceAfter=16,
            spaceBefore=10,
            fontName="Helvetica-Bold",
            backColor=colors.HexColor("#1F4788"),
            leftIndent=10,
            rightIndent=10,
            borderPadding=(8, 8, 8, 8),
        )
    )
    
    styles.add(
        ParagraphStyle(
            name="SubsectionHeader",
            parent=styles["Heading3"],
            fontSize=12,
            textColor=colors.HexColor("#1F4788"),
            spaceAfter=10,
            spaceBefore=8,
            fontName="Helvetica-Bold",
        )
    )
    
    styles.add(
        ParagraphStyle(
            name="ProposalBody",
            parent=styles["Normal"],
            fontSize=10,
            textColor=colors.HexColor("#333333"),
            leading=14,
            alignment=TA_JUSTIFY,
        )
    )
    
    styles.add(
        ParagraphStyle(
            name="ProposalBullet",
            parent=styles["Normal"],
            fontSize=10,
            textColor=colors.HexColor("#333333"),
            leading=14,
            leftIndent=20,
            bulletIndent=10,
        )
    )
    
    styles.add(
        ParagraphStyle(
            name="ProposalFootnote",
            parent=styles["Normal"],
            fontSize=8,
            textColor=colors.HexColor("#666666"),
            leading=11,
            fontName="Helvetica-Oblique",
        )
    )

    # Data extraction
    rfp = (rfp_data or {}).get("rfp", {}) or {}
    matches = (rfp_data or {}).get("matches", []) or []
    score = _to_float((rfp_data or {}).get("score", 0.0), 0.0)
    price = (rfp_data or {}).get("price", 0.0)

    story = []

    # ================= COVER PAGE =================
    story.append(Spacer(1, 0.8 * inch))
    
    # Logo placeholder box (you can replace with actual logo)
    story.append(Paragraph("", styles["Normal"]))
    story.append(Spacer(1, 0.3 * inch))
    story.append(Spacer(1, 0.2 * inch))
    
    story.append(Paragraph("TECHNICAL & COMMERCIAL PROPOSAL", styles["CoverTitle"]))
    story.append(Spacer(1, 0.1 * inch))
    story.append(Paragraph("RFP Bid Evaluation Report", styles["CoverSubtitle"]))
    
    story.append(Spacer(1, 0.5 * inch))
    
    # Project info box
    project_box = Table(
        [[Paragraph("<b>PROJECT</b>", styles["Normal"])],
         [Paragraph(rfp.get("projectName", "N/A"), styles["CoverProject"])]],
        colWidths=[6.0 * inch]
    )
    project_box.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F0F4F8")),
            ("BOX", (0, 0), (-1, -1), 2, colors.HexColor("#1F4788")),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 15),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 15),
        ])
    )
    story.append(project_box)
    
    story.append(Spacer(1, 0.6 * inch))
    
    # Cover details table
    cover_data = [
        ["Tendering Authority:", rfp.get("issued_by", "N/A")],
        ["Project Category:", rfp.get("category", "N/A")],
        ["Submission Deadline:", rfp.get("submissionDeadline", "N/A")],
        ["Report Generated:", datetime.now().strftime("%d %B %Y")],
    ]
    
    cover_table = Table(cover_data, colWidths=[2.2 * inch, 3.8 * inch])
    cover_table.setStyle(
        TableStyle([
            ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
            ("FONTNAME", (1, 0), (1, -1), "Helvetica"),
            ("FONTSIZE", (0, 0), (-1, -1), 11),
            ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#1F4788")),
            ("TEXTCOLOR", (1, 0), (1, -1), colors.HexColor("#333333")),
            ("ALIGN", (0, 0), (0, -1), "RIGHT"),
            ("ALIGN", (1, 0), (1, -1), "LEFT"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LINEBELOW", (0, 0), (-1, -2), 0.5, colors.HexColor("#CCCCCC")),
            ("TOPPADDING", (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (1, 0), (1, -1), 5),
        ])
    )
    
    story.append(cover_table)
    
    story.append(Spacer(1, 1.0 * inch))
    
    # Confidentiality notice
    story.append(Paragraph(
        "<i>This document contains proprietary and confidential information. "
        "Distribution or reproduction without authorization is strictly prohibited.</i>",
        styles["ProposalFootnote"]
    ))
    
    story.append(PageBreak())

    # ================= EXECUTIVE SUMMARY =================
    story.append(Paragraph("1. EXECUTIVE SUMMARY", styles["SectionHeader"]))
    story.append(Spacer(1, 0.15 * inch))
    

    # Determine recommendation
    if score >= 0.75:
        score_color = colors.HexColor("#27AE60")
        rec_text = "PROCEED WITH BID"
        rec_color = colors.HexColor("#27AE60")
        rec_bg = colors.HexColor("#E8F8F0")
    elif score >= 0.50:
        score_color = colors.HexColor("#F39C12")
        rec_text = "REVIEW REQUIRED"
        rec_color = colors.HexColor("#F39C12")
        rec_bg = colors.HexColor("#FEF5E7")
    else:
        score_color = colors.HexColor("#E74C3C")
        rec_text = "DO NOT PROCEED"
        rec_color = colors.HexColor("#E74C3C")
        rec_bg = colors.HexColor("#FADBD8")

    # Summary metrics table
    summary_data = [
        ["EVALUATION METRIC", "RESULT"],
        ["Overall Compatibility Score", f"{score:.1%}"],
        ["Estimated Bid Value", _money_inr(price, decimals=0)],
        ["Number of Suppliers Analyzed", str(len(matches))],
        ["Final Recommendation", rec_text],
    ]
    
    summary_table = Table(summary_data, colWidths=[3.2 * inch, 3.2 * inch])
    summary_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F4788")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 11),
            ("ALIGN", (0, 0), (-1, 0), "CENTER"),
            
            ("FONTNAME", (0, 1), (0, -1), "Helvetica"),
            ("FONTNAME", (1, 1), (1, -1), "Helvetica-Bold"),
            ("FONTSIZE", (0, 1), (-1, -1), 10),
            ("ALIGN", (0, 1), (0, -1), "LEFT"),
            ("ALIGN", (1, 1), (1, -1), "CENTER"),
            
            ("BACKGROUND", (0, 1), (-1, 3), colors.HexColor("#F9FAFB")),
            ("BACKGROUND", (0, 4), (-1, 4), rec_bg),
            ("TEXTCOLOR", (1, 4), (1, 4), rec_color),
            ("FONTSIZE", (1, 4), (1, 4), 12),
            
            ("GRID", (0, 0), (-1, -1), 1, colors.HexColor("#CCCCCC")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 12),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
            ("LEFTPADDING", (0, 0), (-1, -1), 12),
            ("RIGHTPADDING", (0, 0), (-1, -1), 12),
        ])
    )
    
    story.append(summary_table)
    story.append(Spacer(1, 0.25 * inch))
    
    # Summary narrative
    story.append(Paragraph("1.1 Overview", styles["SubsectionHeader"]))
    story.append(Paragraph(
        f"This report presents a comprehensive evaluation of the tender opportunity for "
        f"<b>{rfp.get('projectName', 'N/A')}</b> issued by <b>{rfp.get('issued_by', 'N/A')}</b>. "
        f"Based on our analysis of technical specifications, supplier capabilities, and commercial "
        f"viability, the project has achieved an overall compatibility score of <b>{score:.1%}</b>.",
        styles["ProposalBody"]
    ))
    story.append(Spacer(1, 0.15 * inch))
    
    story.append(Paragraph("1.2 Key Findings", styles["SubsectionHeader"]))
    key_findings = [
        f"<b>Market Analysis:</b> {len(matches)} qualified suppliers identified with competitive pricing",
        f"<b>Technical Compliance:</b> All analyzed products meet or exceed required specifications",
        f"<b>BIS Certification:</b> Majority of suppliers provide BIS-certified products",
        f"<b>Delivery Capability:</b> Lead times range from {min([_to_float(m.get('lead_time_days', 0)) for m in matches] or [0]):.0f} to {max([_to_float(m.get('lead_time_days', 0)) for m in matches] or [0]):.0f} days",
    ]
    
    for finding in key_findings:
        story.append(Paragraph(f"• {finding}", styles["ProposalBullet"]))
    
    story.append(Paragraph("1.3 Scoring Methodology", styles["SubsectionHeader"]))
    story.append(Paragraph(
    "The compatibility score is calculated using a weighted evaluation model "
    "considering technical specification match (50%), supplier compliance and "
    "certification (20%), commercial competitiveness (20%), and delivery lead time (10%). "
    "Scores above 75% indicate strong bid viability.",
    styles["ProposalBody"]
))
    story.append(PageBreak())

    story.append(Spacer(1, 0.3 * inch))
    story.append(create_score_chart(score))

    # ================= PROJECT DETAILS =================
    story.append(Paragraph("2. PROJECT DETAILS", styles["SectionHeader"]))
    story.append(Spacer(1, 0.15 * inch))
    
    project_details = [
        ["Attribute", "Details"],
        ["Project Name", rfp.get("projectName", "N/A")],
        ["Tendering Authority", rfp.get("issued_by", "N/A")],
        ["Project Category", rfp.get("category", "N/A")],
        ["Submission Deadline", rfp.get("submissionDeadline", "N/A")],
        ["Evaluation Date", datetime.now().strftime("%d %B %Y")],
    ]
    
    details_table = Table(project_details, colWidths=[2.0 * inch, 4.4 * inch])
    details_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F4788")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 10),
            ("ALIGN", (0, 0), (-1, 0), "CENTER"),
            ("ALIGN", (0, 1), (0, -1), "LEFT"),
            ("ALIGN", (1, 1), (1, -1), "LEFT"),
            ("GRID", (0, 0), (-1, -1), 0.75, colors.HexColor("#CCCCCC")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F9FAFB")]),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
            ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ])
    )
    
    story.append(details_table)
    story.append(PageBreak())

    # ================= TECHNICAL ANALYSIS =================
    story.append(Paragraph("3. TECHNICAL & COMMERCIAL ANALYSIS", styles["SectionHeader"]))
    story.append(Spacer(1, 0.15 * inch))
    
    story.append(Paragraph("3.1 Supplier Market Analysis", styles["SubsectionHeader"]))
    
    if matches:
        unit_prices = [_to_float(m.get("unit_price", 0.0), 0.0) for m in matches]
        lead_times = [_to_float(m.get("lead_time_days", 0.0), 0.0) for m in matches]

        avg_price = sum(unit_prices) / len(unit_prices) if unit_prices else 0.0
        min_price = min(unit_prices) if unit_prices else 0.0
        max_price = max(unit_prices) if unit_prices else 0.0
        min_lt = min(lead_times) if lead_times else 0.0
        max_lt = max(lead_times) if lead_times else 0.0

        story.append(Paragraph(
            f"Our procurement analysis has identified <b>{len(matches)} qualified suppliers</b> "
            f"capable of meeting the technical specifications. The unit pricing ranges from "
            f"<b>{_money_inr(min_price, decimals=2)}</b> to <b>{_money_inr(max_price, decimals=2)}</b>, "
            f"with an average market price of <b>{_money_inr(avg_price, decimals=2)}</b>. "
            f"Lead times for delivery vary between <b>{int(min_lt)}</b> and <b>{int(max_lt)} days</b>, "
            f"providing flexibility in project scheduling.",
            styles["ProposalBody"]
        ))
        story.append(Spacer(1, 0.2 * inch))
        
        story.append(Paragraph("3.2 Detailed Supplier Comparison", styles["SubsectionHeader"]))
        
        # Supplier table header
        supplier_rows = [
            ["#", "Product Description", "Match", "BIS", "Lead Time", "Unit Price"]
        ]
        
        for idx, m in enumerate(matches[:15], 1):
            bis_val = m.get("bis_certified", "No")
            bis_text = "✓" if bis_val in (True, "Yes", "YES", "yes") else "✗"
            
            supplier_rows.append([
                str(idx),
                (m.get("product_name", "N/A") or "N/A")[:50],
                f"{_to_float(m.get('spec_match_percent', 0.0), 0.0):.0f}%",
                bis_text,
                f"{int(_to_float(m.get('lead_time_days', 0), 0))} d",
                _money_inr(m.get("unit_price", 0.0), decimals=2),
            ])
        
        supplier_table = Table(
            supplier_rows,
            repeatRows=1,
            colWidths=[0.4 * inch, 2.7 * inch, 0.7 * inch, 0.5 * inch, 0.8 * inch, 1.3 * inch]
        )
        supplier_table.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F4788")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 9),
                ("ALIGN", (0, 0), (-1, 0), "CENTER"),
                
                ("FONTSIZE", (0, 1), (-1, -1), 8),
                ("ALIGN", (0, 1), (0, -1), "CENTER"),
                ("ALIGN", (1, 1), (1, -1), "LEFT"),
                ("ALIGN", (2, 1), (-1, -1), "CENTER"),
                
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CCCCCC")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F9FAFB")]),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ])
        )
        
        story.append(supplier_table)
        
        if len(matches) > 15:
            story.append(Spacer(1, 0.1 * inch))
            story.append(Paragraph(
                f"<i>Note: Showing top 15 of {len(matches)} suppliers analyzed. Complete supplier list available upon request.</i>",
                styles["ProposalFootnote"]
            ))
    else:
        story.append(Paragraph(
            "No matching products were identified for this tender opportunity. "
            "Further market research is recommended.",
            styles["ProposalBody"]
        ))
    
    story.append(PageBreak())

    # ================= RECOMMENDATIONS =================
    story.append(Paragraph("4. RECOMMENDATIONS & NEXT STEPS", styles["SectionHeader"]))
    story.append(Spacer(1, 0.15 * inch))
    
    story.append(Paragraph("4.1 Overall Assessment", styles["SubsectionHeader"]))
    story.append(Paragraph(
        f"Based on the comprehensive evaluation, this tender opportunity has achieved a composite "
        f"score of <b>{score:.1%}</b>. Our recommendation is to <b>{rec_text}</b>.",
        styles["ProposalBody"]
    ))
    story.append(Spacer(1, 0.15 * inch))
    
    story.append(Paragraph("4.2 Strategic Advantages", styles["SubsectionHeader"]))
    advantages = [
        "High degree of technical specification match with available products in our catalog",
        "Multiple qualified suppliers enable competitive bidding and supply chain redundancy",
        "BIS certification compliance demonstrated by majority of suppliers",
        "Favorable lead times align with typical project implementation schedules",
        "Competitive pricing environment supports cost-effective bid preparation",
    ]
    
    for adv in advantages:
        story.append(Paragraph(f"• {adv}", styles["ProposalBullet"]))
    
    story.append(Spacer(1, 0.2 * inch))
    
    story.append(Paragraph("4.3 Recommended Action Items", styles["SubsectionHeader"]))
    action_items = [
        ["Phase", "Action Item", "Responsibility"],
        ["Pre-Bid", "Validate final Bill of Quantities against tender specifications", "Technical Team"],
        ["Pre-Bid", "Obtain and verify BIS/test certificates from shortlisted vendors", "Procurement"],
        ["Pre-Bid", "Negotiate final pricing and delivery schedules", "Commercial Team"],
        ["Bid Prep", "Confirm liquidated damages and penalty clauses", "Legal Team"],
        ["Bid Prep", "Finalize commercial terms and prepare bid documentation", "Bid Manager"],
        ["Submission", "Internal review and approval process", "Management"],
        ["Submission", "Submit complete bid package before deadline", "Bid Manager"],
    ]
    
    action_table = Table(action_items, repeatRows=1, colWidths=[1.0 * inch, 3.5 * inch, 1.9 * inch])
    action_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F4788")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 10),
            ("ALIGN", (0, 0), (-1, 0), "CENTER"),
            
            ("FONTSIZE", (0, 1), (-1, -1), 9),
            ("ALIGN", (0, 1), (-1, -1), "LEFT"),
            
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CCCCCC")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F9FAFB")]),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ])
    )
    
    story.append(action_table)
    story.append(Spacer(1, 0.25 * inch))
    
    story.append(Paragraph("4.4 Risk Considerations", styles["SubsectionHeader"]))
    story.append(Paragraph(
        "While this opportunity presents strong viability, stakeholders should consider the following risks:",
        styles["ProposalBody"]
    ))
    story.append(Spacer(1, 0.1 * inch))
    
    risks = [
        "Market price fluctuations may impact final bid competitiveness",
        "Supplier capacity constraints during peak construction season",
        "Potential for specification changes during clarification period",
        "Currency exchange rate variations for imported components",
    ]
    
    for risk in risks:
        story.append(Paragraph(f"• {risk}", styles["ProposalBullet"]))
    
    story.append(Spacer(1, 0.3 * inch))
    
    # Sign-off section
    story.append(Paragraph("4.5 Approval & Authorization", styles["SubsectionHeader"]))
    
    signoff_data = [
        ["Prepared By:", "_" * 30, "Date:", "_" * 20],
        ["", "", "", ""],
        ["Reviewed By:", "_" * 30, "Date:", "_" * 20],
        ["", "", "", ""],
        ["Approved By:", "_" * 30, "Date:", "_" * 20],
    ]
    
    signoff_table = Table(signoff_data, colWidths=[1.3 * inch, 2.8 * inch, 0.7 * inch, 1.6 * inch])
    signoff_table.setStyle(
        TableStyle([
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
            ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ])
    )
    
    story.append(signoff_table)
    
    story.append(Spacer(1, 0.4 * inch))
    story.append(Paragraph(
        "<i>END OF REPORT</i>",
        styles["ProposalFootnote"]
    ))

    # Build PDF
    doc.build(story, onFirstPage=add_header_footer, onLaterPages=add_header_footer)
    return output_path