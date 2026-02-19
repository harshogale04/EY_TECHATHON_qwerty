# agents/pricing_agent.py
"""
UPDATED PRICING AGENT  — v2 (3-fix release)
=============================================

Fix 1 — MOQ vs RFP Quantity
    Material cost now uses MAX(rfp_quantity, moq) instead of MOQ alone.
    The RFP quantity is parsed from the line-item text (e.g. "1900 meters").
    If rfp_quantity > moq  → we order rfp_quantity metres (correct billing).
    If rfp_quantity < moq  → we still must order moq metres (minimum order).
    Volume-discount table is also consulted so larger orders get the right
    discounted unit price automatically.

Fix 2 — Volume Discount pricing
    For the order quantity determined above, the Volume Discounts sheet is
    queried to find the correct discounted unit price instead of always using
    the base catalogue price.

Fix 3 — Voltage-class-aware test selection
    Tests are no longer the same flat list for every line item.
    Each line item's voltage class (LV / MV / HV) determines:
      • Which HV withstand test applies (HVWT-1.1KV / HVWT-3.5KV / HVWT-11KV)
      • Whether the advanced acceptance test (AT-02) is required (HV only)
      • Whether the routine insulation test (RT-01) applies (LV only)
    All other keyword-matched tests from the RFP text still apply.
"""

import re
from typing import List, Dict, Optional
from services.supabase_client import push_to_table


# ─────────────────────────────────────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────────────────────────────────────

# Voltage class thresholds (kV)
LV_MAX_KV  = 1.1   # LV  : ≤ 1.1 kV
MV_MAX_KV  = 6.6   # MV  : > 1.1 kV and ≤ 6.6 kV
# HV          : > 6.6 kV

# Tests that are always required regardless of voltage
UNIVERSAL_TESTS = ["IRT-10M", "DOC-01", "ET-01", "MI-01", "TT-01"]

# Tests that differ by voltage class
VOLTAGE_CLASS_TESTS = {
    "LV": ["RT-01", "HVWT-1.1KV", "ET-01"],          # LV: routine + 1.1 kV withstand
    "MV": ["HVWT-3.5KV", "AT-01", "ET-02"],           # MV: 3.5 kV withstand + acceptance
    "HV": ["HVWT-11KV", "AT-02", "ET-02"],            # HV: 11 kV withstand + advanced acceptance
}

# Keyword → test code(s) from RFP testing text (non-voltage-specific)
TEST_KEYWORD_MAP = {
    r'tensile\s*strength':            ["TST-360", "TST-350"],
    r'mechanical\s*installation':     ["MII-01"],
    r'mechanical\s*inspection':       ["MI-01"],
    r'documentation':                 ["DOC-01"],
    r'certif(?:icate|ication)':       ["DOC-01"],
    r'routine\s*(?:test|testing|insulation)': ["RT-01"],
    r'acceptance\s*(?:test|testing)': ["AT-01", "AT-02"],
    r'type\s*(?:test|testing)':       ["TT-01"],
    r'electrical\s*(?:test|testing)': ["ET-01", "ET-02"],
}


# ─────────────────────────────────────────────────────────────────────────────
# FIX 1 & 2 — RFP Quantity extraction + Volume Discount pricing
# ─────────────────────────────────────────────────────────────────────────────

def extract_rfp_quantity(line_item_text: str) -> Optional[int]:
    """
    Parse the ordered quantity (in metres) from a line-item description.

    Handles patterns like:
      "Quantity: 1900 meters"   "Qty: 1900 m"   "1,900 m"   "1900m"
    Returns None if no quantity found.
    """
    text = line_item_text.lower()

    # Explicit "quantity: NNN" or "qty: NNN"
    m = re.search(r'(?:quantity|qty)\s*[:\-]?\s*([\d,]+)\s*(?:m\b|meters?|metres?)', text)
    if m:
        return int(m.group(1).replace(",", ""))

    # Standalone "NNN meters" (fallback)
    m = re.search(r'([\d,]+)\s*(?:meters?|metres?)', text)
    if m:
        return int(m.group(1).replace(",", ""))

    return None


def get_discounted_unit_price(product_id: str, order_qty: int, volume_discounts_db) -> Optional[float]:
    """
    FIX 2 — Look up the correct discounted unit price for a given order quantity.

    Searches the Volume Discounts sheet for rows matching product_id where
    Min_Quantity_Meters <= order_qty <= Max_Quantity_Meters.

    Returns discounted unit price, or None if no match (caller falls back to
    catalogue price).
    """
    if volume_discounts_db is None:
        return None

    rows = volume_discounts_db[volume_discounts_db["Product_ID"] == product_id]
    if rows.empty:
        return None

    matched = rows[
        (rows["Min_Quantity_Meters"] <= order_qty) &
        (rows["Max_Quantity_Meters"] >= order_qty)
    ]
    if matched.empty:
        # order_qty exceeds all bands — use the highest-quantity band
        matched = rows[rows["Min_Quantity_Meters"] == rows["Min_Quantity_Meters"].max()]

    if matched.empty:
        return None

    return float(matched["Unit_Price_INR"].iloc[0])


# ─────────────────────────────────────────────────────────────────────────────
# FIX 3 — Voltage-class-aware test selection
# ─────────────────────────────────────────────────────────────────────────────

def _voltage_class(voltage_rating_str: str) -> str:
    """
    Classify a voltage string into LV / MV / HV.

    Examples:
      "0.4 kV", "0.6 kV", "1.1 kV" → LV
      "3.5 kV", "6.6 kV"           → MV
      "11 kV", "33 kV"             → HV
    """
    if not voltage_rating_str:
        return "LV"   # safe default

    # Extract numeric kV value
    m = re.search(r'(\d+(?:\.\d+)?)\s*kv', voltage_rating_str.lower())
    if not m:
        # Try bare volts, e.g. "415 V"
        m = re.search(r'(\d+)\s*v\b', voltage_rating_str.lower())
        if m:
            kv = float(m.group(1)) / 1000
        else:
            return "LV"
    else:
        kv = float(m.group(1))

    if kv <= LV_MAX_KV:
        return "LV"
    elif kv <= MV_MAX_KV:
        return "MV"
    else:
        return "HV"


def extract_required_tests(testing_requirements_text: str, voltage_rating: str = "") -> List[str]:
    """
    FIX 3 — Build the test list in two steps:

    Step A: Start with universal tests + voltage-class-specific tests.
            This ensures LV, MV, HV cables get the right withstand test
            and the right acceptance-test tier.

    Step B: Overlay any additional tests triggered by keywords in the RFP
            testing text (e.g. tensile, mechanical installation).

    Returns a deduplicated, sorted list of test codes.
    """
    found_codes: set = set()

    # ── Step A: universal + voltage-class tests ───────────────────────────
    found_codes.update(UNIVERSAL_TESTS)
    v_class = _voltage_class(voltage_rating)
    found_codes.update(VOLTAGE_CLASS_TESTS.get(v_class, []))

    # ── Step B: keyword overlay from RFP text ────────────────────────────
    if testing_requirements_text and testing_requirements_text.strip():
        text = testing_requirements_text.lower()
        for pattern, codes in TEST_KEYWORD_MAP.items():
            if re.search(pattern, text):
                found_codes.update(codes)

    return sorted(list(found_codes))


def get_test_details(test_codes: List[str], test_services_db) -> List[Dict]:
    """
    Look up test details from the Testing Services sheet.
    Unknown codes get an estimated price with a clear label.
    """
    results = []
    for code in test_codes:
        row = test_services_db[test_services_db["Test_Code"] == code]
        if not row.empty:
            results.append({
                "test_code":      code,
                "test_name":      row["Test_Name"].iloc[0],
                "price_inr":      float(row["Price_INR"].iloc[0]),
                "duration_hours": float(row["Duration_Hours"].iloc[0]),
            })
        else:
            results.append({
                "test_code":      code,
                "test_name":      f"Test {code} (estimated)",
                "price_inr":      10_000.0,
                "duration_hours": 2.0,
            })
    return results


# ─────────────────────────────────────────────────────────────────────────────
# MAIN AGENT
# ─────────────────────────────────────────────────────────────────────────────

def pricing_agent(state: dict) -> dict:
    """
    Pricing Agent — assigns unit prices and test costs per line item.

    Reads from state:
        pricing_summary      — from master agent (has testing_requirements)
        line_item_matches    — selected SKUs from technical agent
        product_db           — OEM Product Catalog
        volume_discounts_db  — Volume Discounts sheet  (NEW — needed for Fix 2)
        test_services_db     — Testing Services sheet

    Writes to state:
        consolidated_pricing — full cost breakdown
        prices               — list of line totals (backward compat)
    """
    pricing_summary      = state.get("pricing_summary", {})
    line_item_matches    = state.get("line_item_matches", [])
    product_db           = state["product_db"]
    test_services_db     = state.get("test_services_db")
    volume_discounts_db  = state.get("volume_discounts_db")   # may be None if not loaded

    testing_requirements_text = pricing_summary.get("testing_requirements", "")

    print(f"\n💰 Pricing Agent: Processing {len(line_item_matches)} line item(s)")

    if not line_item_matches:
        state["consolidated_pricing"] = {
            "line_item_pricing": [],
            "total_material_cost": 0,
            "total_test_cost": 0,
            "grand_total": 0,
        }
        state["prices"] = []
        return state

    line_item_pricing   = []
    total_material_cost = 0.0
    total_test_cost     = 0.0

    for item_result in line_item_matches:
        line_item_text = item_result.get("line_item", "")
        selected_sku   = item_result.get("selected_sku")

        if not selected_sku:
            line_item_pricing.append({
                "line_item":       line_item_text,
                "sku":             None,
                "unit_price_inr":  0,
                "rfp_qty_meters":  0,
                "order_qty_meters": 0,
                "moq_meters":      0,
                "material_cost_inr": 0,
                "applicable_tests":  [],
                "test_cost_inr":   0,
                "line_total_inr":  0,
                "note":            "No matching product found",
            })
            continue

        product_id = selected_sku["product_id"]

        # ── Catalogue values ──────────────────────────────────────────────
        product_row = product_db[product_db["Product_ID"] == product_id]
        if not product_row.empty:
            catalogue_unit_price = float(product_row["Unit_Price_INR_per_meter"].iloc[0])
            moq                  = int(product_row["Min_Order_Qty_Meters"].iloc[0])
            voltage_rating       = str(product_row["Voltage_Rating"].iloc[0])
        else:
            catalogue_unit_price = selected_sku.get("unit_price", 0.0)
            moq                  = selected_sku.get("moq", 100)
            voltage_rating       = ""

        # ── FIX 1: Use RFP quantity (not just MOQ) ───────────────────────
        rfp_qty   = extract_rfp_quantity(line_item_text)
        order_qty = max(rfp_qty or 0, moq)   # must order at least MOQ

        # ── FIX 2: Volume-discounted unit price ───────────────────────────
        discounted_price = get_discounted_unit_price(product_id, order_qty, volume_discounts_db)
        unit_price       = discounted_price if discounted_price is not None else catalogue_unit_price

        # Calculate discount % for display
        if discounted_price and catalogue_unit_price:
            discount_pct = round((1 - discounted_price / catalogue_unit_price) * 100, 1)
        else:
            discount_pct = 0.0

        material_cost = round(unit_price * order_qty, 2)

        # ── FIX 3: Voltage-class-aware test selection ─────────────────────
        required_test_codes = extract_required_tests(testing_requirements_text, voltage_rating)

        if test_services_db is not None:
            test_details = get_test_details(required_test_codes, test_services_db)
        else:
            test_details = [
                {"test_code": "RT-01",   "test_name": "Routine Insulation Test",        "price_inr": 8_000.0,  "duration_hours": 1.0},
                {"test_code": "IRT-10M", "test_name": "Insulation Resistance Test",     "price_inr": 12_000.0, "duration_hours": 1.0},
                {"test_code": "DOC-01",  "test_name": "Documentation and Certification","price_inr": 10_000.0, "duration_hours": 4.0},
            ]

        test_cost  = round(sum(t["price_inr"] for t in test_details), 2)
        line_total = round(material_cost + test_cost, 2)

        total_material_cost += material_cost
        total_test_cost     += test_cost

        row = {
            "line_item":          line_item_text,
            "sku":                product_id,
            "product_name":       selected_sku.get("product_name", ""),
            "voltage_class":      _voltage_class(voltage_rating),
            "catalogue_price_inr": catalogue_unit_price,
            "unit_price_inr":     unit_price,
            "discount_pct":       discount_pct,
            "rfp_qty_meters":     rfp_qty or 0,
            "moq_meters":         moq,
            "order_qty_meters":   order_qty,
            "material_cost_inr":  material_cost,
            "applicable_tests":   test_details,
            "test_cost_inr":      test_cost,
            "line_total_inr":     line_total,
        }
        line_item_pricing.append(row)

        print(f"\n   📦 {line_item_text[:60]}")
        print(f"      SKU           : {product_id}")
        print(f"      Voltage Class : {_voltage_class(voltage_rating)}")
        print(f"      RFP Qty       : {rfp_qty or '(not found)'} m")
        print(f"      MOQ           : {moq} m")
        print(f"      Order Qty     : {order_qty} m  ← FIX 1: max(rfp_qty, moq)")
        print(f"      Unit Price    : ₹{unit_price:,.2f}/m"
              + (f"  (disc {discount_pct}% from ₹{catalogue_unit_price:,.2f})" if discount_pct else ""))
        print(f"      Material Cost : ₹{material_cost:,.0f}  ← FIX 2: unit_price × order_qty")
        print(f"      Tests         : {[t['test_code'] for t in test_details]}")
        print(f"      Test Cost     : ₹{test_cost:,.0f}  ← FIX 3: voltage-class aware")
        print(f"      Line Total    : ₹{line_total:,.0f}")

    grand_total = round(total_material_cost + total_test_cost, 2)

    consolidated_pricing = {
        "line_item_pricing":  line_item_pricing,
        "total_material_cost": round(total_material_cost, 2),
        "total_test_cost":    round(total_test_cost, 2),
        "grand_total":        grand_total,
    }

    state["consolidated_pricing"] = consolidated_pricing
    state["prices"] = [r["line_total_inr"] for r in line_item_pricing]

    agent_output = {
        "line_item_count": len(line_item_pricing),
        "line_item_pricing": [
            {
                "line_item":        r["line_item"][:80],
                "sku":              r.get("sku"),
                "voltage_class":    r.get("voltage_class"),
                "rfp_qty_meters":   r.get("rfp_qty_meters"),
                "moq_meters":       r.get("moq_meters"),
                "order_qty_meters": r.get("order_qty_meters"),
                "catalogue_price":  r.get("catalogue_price_inr"),
                "unit_price_inr":   r.get("unit_price_inr"),
                "discount_pct":     r.get("discount_pct"),
                "material_cost_inr": r.get("material_cost_inr"),
                "test_codes":       [t["test_code"] for t in r.get("applicable_tests", [])],
                "test_cost_inr":    r.get("test_cost_inr"),
                "line_total_inr":   r.get("line_total_inr"),
            }
            for r in line_item_pricing
        ],
        "total_material_cost": total_material_cost,
        "total_test_cost":     total_test_cost,
        "grand_total":         grand_total,
    }


    # ── Push to Supabase ──────────────────────────────────────────────────
    import json as _json
    project_name = state.get("rfps", [{}])[0].get("projectName", "unknown")
    try:
        push_to_table("pricing_results", {
            "project_name":      project_name,
            "grand_total":       grand_total,
            "total_material_cost": total_material_cost,
            "total_test_cost":   total_test_cost,
            "full_output":       _json.loads(_json.dumps(agent_output, default=str)),
        })
    except Exception as e:
        print(f"⚠️  Failed to push pricing results to DB: {e}")

    print(f"\n   {'─'*45}")
    print(f"   Total Material : ₹{total_material_cost:,.0f}")
    print(f"   Total Tests    : ₹{total_test_cost:,.0f}")
    print(f"   GRAND TOTAL    : ₹{grand_total:,.0f}")

    return state