# agents/master_agent.py
"""
Master Agent - True Orchestrator
==================================
Phase 1 (master_agent_start):
  - Receives ALL shortlisted RFPs from Sales Agent
  - Scores each one using RFPScorer (bid viability: technical, price,
    delivery, compliance, risk)
  - Selects the HIGHEST-SCORED RFP (smarter than just earliest deadline)
  - Prepares role-specific summaries for Technical and Pricing agents
  - Starts the conversation

Phase 2 (master_agent_consolidate):
  - Receives line_item_matches from Technical Agent
  - Receives consolidated_pricing from Pricing Agent
  - Builds the final response: OEM SKUs + prices + test costs per line item
  - Attaches the bid viability score to the final response
  - Generates the PDF report
  - Ends the conversation
"""

import os
from utils.agent_io import save_agent_output


# ─── Role-specific summary builders ──────────────────────────────────────────

def _prepare_technical_summary(rfp: dict) -> dict:
    """
    Summary for the Technical Agent.
    Focuses on scope of supply, technical specifications, standards.
    """
    return {
        "projectName":              rfp.get("projectName", ""),
        "issued_by":                rfp.get("issued_by", ""),
        "submissionDeadline":       rfp.get("submissionDeadline", ""),
        "scope_of_supply":          rfp.get("scope_of_supply", ""),
        "technical_specifications": rfp.get("technical_specifications", ""),
        "testing_requirements":     rfp.get("testing_requirements", ""),
        "delivery_timeline":        rfp.get("delivery_timeline", ""),
        "project_overview":         rfp.get("project_overview", ""),
        "_agent_context": (
            "You are receiving this RFP to: "
            "(1) Parse the scope of supply into individual product line items. "
            "(2) For each line item, recommend the top 3 OEM products with equal-weighted Spec Match %. "
            "(3) Prepare a comparison table of RFP spec requirements vs Top-1/2/3 OEM product values. "
            "(4) Select the single best OEM SKU per line item based on Spec Match. "
            "Focus ONLY on: voltage, conductor material, insulation type, cores, armoring, standards."
        ),
    }


def _prepare_pricing_summary(rfp: dict) -> dict:
    """
    Summary for the Pricing Agent.
    Focuses on acceptance/test requirements and pricing details.
    """
    return {
        "projectName":        rfp.get("projectName", ""),
        "issued_by":          rfp.get("issued_by", ""),
        "submissionDeadline": rfp.get("submissionDeadline", ""),
        "testing_requirements": rfp.get("testing_requirements", ""),
        "pricing_details":    rfp.get("pricing_details", ""),
        "evaluation_criteria": rfp.get("evaluation_criteria", ""),
        "scope_of_supply":    rfp.get("scope_of_supply", ""),
        "_agent_context": (
            "You are receiving this RFP to: "
            "(1) Extract all acceptance/type/routine tests from the testing requirements. "
            "(2) Map each test to the services price table and assign a cost. "
            "(3) Once you receive the OEM SKUs from the Technical Agent, assign unit prices "
            "    from the product catalog and calculate total material cost. "
            "(4) Produce: Line Item | OEM SKU | Unit Price | MOQ | Material Cost | Tests | Test Cost | Total."
        ),
    }


# ─── Phase 1: Select RFP + dispatch summaries ─────────────────────────────────

def master_agent_start(state: dict) -> dict:
    """
    PHASE 1 — Entry point of the conversation.

    1. Imports RFPScorer and scores every shortlisted RFP from Sales Agent
    2. Selects the highest-scored RFP (best bid viability)
    3. Prepares role-specific summaries for Technical and Pricing agents
    4. Saves score breakdown for reporting

    Reads from state:
        rfps       — list from sales_agent (may be 1 or more)
        product_db

    Writes to state:
        selected_rfp        — the chosen RFP dict
        rfp_score           — bid viability score breakdown
        technical_summary   — summary for technical_agent
        pricing_summary     — summary for pricing_agent
    """
    from agents.scoring_agent import RFPScorer, score_single_rfp

    rfps       = state.get("rfps", [])
    product_db = state["product_db"]

    if not rfps:
        print("❌ Master Agent: No RFPs received from Sales Agent.")
        state["selected_rfp"]      = None
        state["rfp_score"]         = {}
        state["technical_summary"] = {}
        state["pricing_summary"]   = {}
        return state

    scorer = RFPScorer(product_db)

    # ── Score every shortlisted RFP ───────────────────────────────────────
    if len(rfps) == 1:
        selected   = rfps[0]
        rfp_score  = score_single_rfp(scorer, selected, product_db)
        print(f"✅ Master Agent: 1 RFP received — '{selected.get('projectName', 'Unnamed')}'")
        print(f"   Bid Viability Score : {rfp_score['final_score']}/100 ({rfp_score['grade']})")
        print(f"   Recommendation      : {rfp_score['recommendation']}")
    else:
        print(f"📊 Master Agent: Scoring {len(rfps)} shortlisted RFP(s)...\n")
        scored = []
        for rfp in rfps:
            sc = score_single_rfp(scorer, rfp, product_db)
            scored.append((rfp, sc))
            print(f"   • {rfp.get('projectName', 'Unnamed'):<50} "
                  f"Score: {sc['final_score']:5.1f}/100  Grade: {sc['grade']}")

        # Pick highest scoring RFP
        scored.sort(key=lambda x: x[1]['final_score'], reverse=True)
        selected, rfp_score = scored[0]

        print(f"\n✅ Master Agent selected: '{selected.get('projectName', 'Unnamed')}'")
        print(f"   Score       : {rfp_score['final_score']}/100 ({rfp_score['grade']})")
        print(f"   Deadline    : {selected.get('submissionDeadline', 'N/A')}")
        print(f"   Recommendation: {rfp_score['recommendation']}")

    state["selected_rfp"] = selected
    state["rfp_score"]    = rfp_score

    # ── Dispatch role-specific summaries ─────────────────────────────────
    state["technical_summary"] = _prepare_technical_summary(selected)
    state["pricing_summary"]   = _prepare_pricing_summary(selected)

    print(f"\n📋 Master Agent dispatching summaries:")
    print(f"   → Technical Agent : scope_of_supply + technical_specifications")
    print(f"   → Pricing Agent   : testing_requirements + pricing_details")

    save_agent_output("master_agent_phase1", {
        "selected_rfp_name": selected.get("projectName"),
        "issued_by":         selected.get("issued_by"),
        "deadline":          selected.get("submissionDeadline"),
        "bid_viability": {
            "score":          rfp_score["final_score"],
            "grade":          rfp_score["grade"],
            "recommendation": rfp_score["recommendation"],
            "components":     rfp_score["component_scores"],
        },
        "technical_summary_keys": list(state["technical_summary"].keys()),
        "pricing_summary_keys":   list(state["pricing_summary"].keys()),
    })

    return state


# ─── Phase 2: Consolidate + generate report ───────────────────────────────────

def master_agent_consolidate(state: dict) -> dict:
    """
    PHASE 2 — End of the conversation.

    1. Merges Technical Agent output (line_item_matches) with
       Pricing Agent output (consolidated_pricing)
    2. Attaches the bid viability score to the final response
    3. Generates the PDF report

    Reads from state:
        selected_rfp        — the chosen RFP
        rfp_score           — bid viability score from phase 1
        line_item_matches   — from technical_agent
        consolidated_pricing — from pricing_agent

    Writes to state:
        final_response  — complete consolidated output
        pdf_path        — path to generated PDF
    """
    from pdf_generator_v2 import generate_rfp_pdf

    rfp                  = state.get("selected_rfp", {})
    rfp_score            = state.get("rfp_score", {})
    line_item_matches    = state.get("line_item_matches", [])
    consolidated_pricing = state.get("consolidated_pricing", {})

    if not rfp:
        print("❌ Master Agent Consolidate: No selected RFP found.")
        state["final_response"] = {}
        state["pdf_path"]       = None
        return state

    # ── Build final consolidated response ─────────────────────────────────
    final_response = {
        "project_name": rfp.get("projectName", ""),
        "issued_by":    rfp.get("issued_by", ""),
        "deadline":     rfp.get("submissionDeadline", ""),
        # Bid viability score from scoring agent
        "bid_viability": {
            "score":              rfp_score.get("final_score", 0),
            "grade":              rfp_score.get("grade", "N/A"),
            "recommendation":     rfp_score.get("recommendation", ""),
            "component_scores":   rfp_score.get("component_scores", {}),
            "weighted_contributions": rfp_score.get("weighted_contributions", {}),
        },
        "line_items": [],
        "summary": {
            "total_material_cost_inr": consolidated_pricing.get("total_material_cost", 0),
            "total_test_cost_inr":     consolidated_pricing.get("total_test_cost", 0),
            "grand_total_inr":         consolidated_pricing.get("grand_total", 0),
        },
    }

    # ── Merge technical + pricing per line item ───────────────────────────
    pricing_rows    = consolidated_pricing.get("line_item_pricing", [])
    pricing_by_item = {row["line_item"]: row for row in pricing_rows}

    for item in line_item_matches:
        item_name = item.get("line_item", "")
        pricing   = pricing_by_item.get(item_name, {})

        final_response["line_items"].append({
            "line_item":             item_name,
            "rfp_specs":             item.get("rfp_specs", {}),
            "top_3_recommendations": item.get("top_3", []),
            "selected_sku":          item.get("selected_sku", {}),
            "unit_price_inr":        pricing.get("unit_price_inr", 0),
            "moq_meters":            pricing.get("moq_meters", 0),
            "material_cost_inr":     pricing.get("material_cost_inr", 0),
            "applicable_tests":      pricing.get("applicable_tests", []),
            "test_cost_inr":         pricing.get("test_cost_inr", 0),
            "line_total_inr":        pricing.get("line_total_inr", 0),
        })

    state["final_response"] = final_response

    # ── Generate PDF ──────────────────────────────────────────────────────
    try:
        output_dir = os.path.join(os.getcwd(), "outputs")
        os.makedirs(output_dir, exist_ok=True)
        pdf_path = generate_rfp_pdf(
            rfp_data=final_response,
            output_path=os.path.join(output_dir, "rfp_bid_report.pdf"),
        )
        state["pdf_path"] = pdf_path
        print(f"✅ PDF report generated: {pdf_path}")
    except Exception as e:
        print(f"❌ PDF generation failed: {e}")
        state["pdf_path"] = None

    save_agent_output("master_agent_phase2", {
        "project_name":     final_response["project_name"],
        "line_items_count": len(final_response["line_items"]),
        "bid_viability":    final_response["bid_viability"],
        "total_material":   final_response["summary"]["total_material_cost_inr"],
        "total_tests":      final_response["summary"]["total_test_cost_inr"],
        "grand_total":      final_response["summary"]["grand_total_inr"],
        "pdf_path":         state.get("pdf_path"),
    })

    print(f"\n🏆 FINAL RESPONSE CONSOLIDATED")
    print(f"   Project     : {final_response['project_name']}")
    print(f"   Items       : {len(final_response['line_items'])}")
    print(f"   Bid Score   : {rfp_score.get('final_score', 0)}/100 ({rfp_score.get('grade', 'N/A')})")
    print(f"   Material    : ₹{final_response['summary']['total_material_cost_inr']:,.0f}")
    print(f"   Tests       : ₹{final_response['summary']['total_test_cost_inr']:,.0f}")
    print(f"   TOTAL       : ₹{final_response['summary']['grand_total_inr']:,.0f}")

    return state