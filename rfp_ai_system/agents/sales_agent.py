# agents/sales_agent.py
"""
Sales Agent
============
PS requirements:
  ✓ Identifies RFPs due for submission in the next three months
  ✓ Scans identified web URLs to summarise RFPs with their due dates
  ✓ Identifies ONE RFP to be selected for response and sends it to the Master Agent

Now supports multiple source URLs — scrapes each one independently,
pools all tenders together, then selects the single most urgent one.
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

SCRAPER_BASE  = "https://ey-fmcg.onrender.com/scrape"
DEFAULT_URL   = "https://tender-frontend-eight.vercel.app"


def build_scraper_url(tender_site_url: str) -> str:
    """Build the scraper API endpoint for a given tender site URL."""
    return f"{SCRAPER_BASE}?months=3&url={tender_site_url}"


def parse_date(date_str):
    if not date_str:
        return None
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%m/%d/%Y"):
        try:
            return datetime.strptime(date_str.replace("Z", ""), fmt)
        except ValueError:
            pass
    return None


def fetch_tenders_from_url(tender_site_url: str) -> list:
    """
    Call the scraper API for a single tender site URL.
    Returns a list of raw tender dicts (or empty list on failure).
    """
    api_url = build_scraper_url(tender_site_url)
    print(f"   📡 Scraping: {tender_site_url}")
    try:
        response = session.get(api_url, timeout=120)
        if response.status_code != 200:
            print(f"   ⚠️  Scraper returned {response.status_code} for {tender_site_url}")
            return []
        data = response.json()
        tenders = data.get("data", [])
        print(f"   ✅ Found {len(tenders)} tender(s) from {tender_site_url}")
        return tenders
    except Exception as e:
        print(f"   ❌ Failed to scrape {tender_site_url}: {e}")
        return []


def sales_agent(state: dict) -> dict:
    """
    Sales Agent — scrapes one or more tender site URLs, pools all tenders,
    filters to the 3-month window, selects the ONE most urgent RFP,
    and puts it in state['rfps'].

    Reads state['source_urls'] (list) if provided by app.py.
    Falls back to the hardcoded DEFAULT_URL if not set.
    """
    print("🔍 Sales Agent fetching live scraped tenders...")

    state["rfps"] = []

    # ── Determine which URLs to scrape ───────────────────────────────────
    source_urls = state.get("source_urls") or [DEFAULT_URL]
    if isinstance(source_urls, str):
        source_urls = [source_urls]

    print(f"🌐 Scraping {len(source_urls)} source URL(s)...")

    # ── Scrape all URLs and pool results ─────────────────────────────────
    all_raw_rfps = []
    for url in source_urls:
        tenders = fetch_tenders_from_url(url)
        # Tag each tender with which source it came from
        for t in tenders:
            t["_source_url"] = url
        all_raw_rfps.extend(tenders)

    if not all_raw_rfps:
        print("⚠️  No tenders returned from any source URL")
        return state

    print(f"📦 Total tenders pooled across all sources: {len(all_raw_rfps)}")

    # ── Expire old tenders in Supabase ───────────────────────────────────
    try:
        move_expired_tenders()
    except Exception as e:
        print(f"⚠️  Tender expiration check failed: {e}")

    today        = datetime.today()
    three_months = today + timedelta(days=90)

    # ── Filter to tenders due within 3 months ────────────────────────────
    upcoming = []
    for rfp in all_raw_rfps:
        due_date = parse_date(rfp.get("submission_deadline"))
        if not due_date:
            continue
        if not (today <= due_date <= three_months):
            continue

        sections = rfp.get("sections", {})
        upcoming.append({
            "projectName":              rfp.get("project_name"),
            "issued_by":                rfp.get("issued_by"),
            "category":                 rfp.get("category"),
            "submissionDeadline":       rfp.get("submission_deadline"),
            "_due_date":                due_date,           # internal, for sorting
            "_source_url":              rfp.get("_source_url", ""),  # track origin
            "project_overview":         sections.get("1. Project Overview", ""),
            "scope_of_supply":          sections.get("2. Scope of Supply", ""),
            "technical_specifications": sections.get("3. Technical Specifications", ""),
            "testing_requirements":     sections.get("4. Acceptance & Test Requirements", ""),
            "delivery_timeline":        sections.get("5. Delivery Timeline", ""),
            "pricing_details":          sections.get("6. Pricing Details", ""),
            "evaluation_criteria":      sections.get("7. Evaluation Criteria", ""),
            "submission_format":        sections.get("8. Submission Format", ""),
        })

    if not upcoming:
        print("⚠️  No valid tenders found in the 3-month window across all sources")
        return state

    print(f"\n📋 Sales Agent found {len(upcoming)} tender(s) in the 3-month window:")
    for t in upcoming:
        print(f"   • [{t['_source_url']}] {t['projectName']} — deadline {t['submissionDeadline']}")

    # ── Push all valid tenders to Supabase ───────────────────────────────
    import json as _json
    for t in upcoming:
        tender_row = {
            "project_name":        t["projectName"],
            "issued_by":           t.get("issued_by"),
            "category":            t.get("category"),
            "submission_deadline": t["submissionDeadline"],
            "tender_data":         _json.loads(_json.dumps({
                k: v for k, v in t.items() if k not in ("_due_date", "_source_url")
            }, default=str)),
        }
        try:
            upsert_to_table("tenders", tender_row)
        except Exception as e:
            print(f"⚠️  Failed to push tender '{t['projectName']}' to DB: {e}")

    # ── Select ONE — the most urgent across ALL sources ───────────────────
    selected = min(upcoming, key=lambda t: t["_due_date"])

    # Remove internal fields before passing downstream
    selected.pop("_due_date", None)
    selected.pop("_source_url", None)
    for t in upcoming:
        t.pop("_due_date", None)
        t.pop("_source_url", None)

    print(f"\n✅ Sales Agent selected: '{selected['projectName']}' (deadline: {selected['submissionDeadline']})")

    state["rfps"] = [selected]
    return state