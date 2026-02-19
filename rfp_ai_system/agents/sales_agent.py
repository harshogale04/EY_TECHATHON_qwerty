# agents/sales_agent.py
"""
Sales Agent
============
PS requirements:
  ✓ Identifies RFPs due for submission in the next three months
  ✓ Scans identified web URLs to summarise RFPs with their due dates
  ✓ Identifies ONE RFP to be selected for response and sends it to the Master Agent

The agent fetches all upcoming tenders, then selects the single most
urgent one (earliest deadline) before putting it in state.
"""

import requests
from datetime import datetime, timedelta
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from services.supabase_client import upsert_to_table, move_expired_tenders

# ── HTTP session with retry ───────────────────────────────────────────────
session = requests.Session()
retries = Retry(
    total=3,
    backoff_factor=2,
    status_forcelist=[500, 502, 503, 504],
)
session.mount("https://", HTTPAdapter(max_retries=retries))

SCRAPER_API = "https://ey-fmcg.onrender.com/scrape?months=3&url=https://tender-frontend-eight.vercel.app"


def parse_date(date_str):
    if not date_str:
        return None
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%m/%d/%Y"):
        try:
            return datetime.strptime(date_str.replace("Z", ""), fmt)
        except ValueError:
            pass
    return None


def sales_agent(state: dict) -> dict:
    """
    Sales Agent — fetches live tenders, filters to 3-month window,
    selects the ONE most urgent RFP, and puts it in state['rfps'].

    PS requirement: 'Identifies one RFP to be selected for response
    and sends this to the Main Agent.'
    """
    print("🔍 Sales Agent fetching live scraped tenders...")

    # Always initialise to keep LangGraph safe
    state["rfps"] = []

    try:
        response = session.get(SCRAPER_API, timeout=120)
        if response.status_code != 200:
            print(f"⚠️  Scraper API failed ({response.status_code})")
            return state
        data = response.json()
    except Exception as e:
        print(f"❌ Scraper API unreachable: {e}")
        return state

    rfps = data.get("data", [])
    if not rfps:
        print("⚠️  No tenders returned by scraper")
        return state

    # ── Step 0: Expire old tenders in Supabase ───────────────────────────
    try:
        move_expired_tenders()
    except Exception as e:
        print(f"⚠️  Tender expiration check failed: {e}")

    today        = datetime.today()
    three_months = today + timedelta(days=90)

    # ── Step 1: Filter to tenders due within 3 months ────────────────────
    upcoming = []
    for rfp in rfps:
        due_date = parse_date(rfp.get("submission_deadline"))
        if not due_date:
            continue
        if not (today <= due_date <= three_months):
            continue

        sections = rfp.get("sections", {})
        upcoming.append({
            "projectName":           rfp.get("project_name"),
            "issued_by":             rfp.get("issued_by"),
            "category":              rfp.get("category"),
            "submissionDeadline":    rfp.get("submission_deadline"),
            "_due_date":             due_date,          # internal, for sorting
            "project_overview":      sections.get("1. Project Overview", ""),
            "scope_of_supply":       sections.get("2. Scope of Supply", ""),
            "technical_specifications": sections.get("3. Technical Specifications", ""),
            "testing_requirements":  sections.get("4. Acceptance & Test Requirements", ""),
            "delivery_timeline":     sections.get("5. Delivery Timeline", ""),
            "pricing_details":       sections.get("6. Pricing Details", ""),
            "evaluation_criteria":   sections.get("7. Evaluation Criteria", ""),
            "submission_format":     sections.get("8. Submission Format", ""),
        })

    if not upcoming:
        print("⚠️  No valid tenders found after filtering")
        return state

    print(f"📋 Sales Agent found {len(upcoming)} tender(s) in the 3-month window:")
    for t in upcoming:
        print(f"   • {t['projectName']} — deadline {t['submissionDeadline']}")

    # ── Step 1b: Push today's valid tenders to Supabase ──────────────────
    import json as _json
    for t in upcoming:
        tender_row = {
            "project_name":       t["projectName"],
            "issued_by":          t.get("issued_by"),
            "category":           t.get("category"),
            "submission_deadline": t["submissionDeadline"],
            "tender_data":        _json.loads(_json.dumps({
                k: v for k, v in t.items() if k != "_due_date"
            }, default=str)),
        }
        try:
            upsert_to_table("tenders", tender_row)
        except Exception as e:
            print(f"⚠️  Failed to push tender '{t['projectName']}' to DB: {e}")

    # ── Step 2: Select ONE — the most urgent (earliest deadline) ─────────
    selected = min(upcoming, key=lambda t: t["_due_date"])

    # Remove internal sorting field before passing to next agents
    selected.pop("_due_date", None)
    for t in upcoming:
        t.pop("_due_date", None)

    print(f"\n✅ Sales Agent selected: '{selected['projectName']}' (deadline: {selected['submissionDeadline']})")

    # PS: "sends this to the Main Agent" — put only the selected RFP in state
    state["rfps"] = [selected]


    return state