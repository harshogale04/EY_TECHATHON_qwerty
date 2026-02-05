import requests
from datetime import datetime, timedelta
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ---------------- HTTP Session with Retry ---------------- #

session = requests.Session()
retries = Retry(
    total=3,
    backoff_factor=2,
    status_forcelist=[500, 502, 503, 504],
)
session.mount("https://", HTTPAdapter(max_retries=retries))

SCRAPER_API = "https://ey-fmcg.onrender.com/scrape?months=1"


# ---------------- Date Parser ---------------- #

def parse_date(date_str):
    if not date_str:
        return None

    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%m/%d/%Y"):
        try:
            return datetime.strptime(date_str.replace("Z", ""), fmt)
        except ValueError:
            pass

    return None


# ---------------- Sales Agent ---------------- #

def sales_agent(state):
    print("🔍 Sales Agent fetching live scraped tenders...")

    # ALWAYS initialize rfps to keep LangGraph safe
    state["rfps"] = []

    try:
        response = session.get(SCRAPER_API, timeout=120)

        if response.status_code != 200:
            print(f"⚠️ Scraper API failed ({response.status_code})")
            return state

        data = response.json()

    except Exception as e:
        print("❌ Scraper API unreachable")
        print(e)
        return state

    rfps = data.get("data", [])

    if not rfps:
        print("⚠️ No tenders returned by scraper")
        return state

    today = datetime.today()
    three_months = today + timedelta(days=90)

    upcoming = []

    for rfp in rfps:
        due_date = parse_date(rfp.get("submission_deadline"))
        if not due_date:
            continue

        if not (today <= due_date <= three_months):
            continue

        sections = rfp.get("sections", {})

        upcoming.append({
            "projectName": rfp.get("project_name"),
            "issued_by": rfp.get("issued_by"),
            "category": rfp.get("category"),
            "submissionDeadline": rfp.get("submission_deadline"),

            "project_overview": sections.get("1. Project Overview", ""),
            "scope_of_supply": sections.get("2. Scope of Supply", ""),
            "technical_specifications": sections.get("3. Technical Specifications", ""),
            "testing_requirements": sections.get("4. Acceptance & Test Requirements", ""),
            "delivery_timeline": sections.get("5. Delivery Timeline", ""),
            "pricing_details": sections.get("6. Pricing Details", ""),
            "evaluation_criteria": sections.get("7. Evaluation Criteria", ""),
            "submission_format": sections.get("8. Submission Format", ""),
        })

    if not upcoming:
        print("⚠️ No valid tenders found after filtering")
        return state

    state["rfps"] = upcoming

    print(f"✅ Sales Agent shortlisted {len(upcoming)} tenders")

    return state
