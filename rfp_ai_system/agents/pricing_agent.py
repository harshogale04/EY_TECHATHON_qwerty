# agents/pricing_agent.py
"""
UPDATED PRICING AGENT
======================
Correctly implements the PS requirements:

1. Receives:
   - pricing_summary from Master Agent (contains testing_requirements section)
   - tech_matches (selected OEM SKUs from Technical Agent)
   - product_db (OEM Product Catalog)
   - test_services_db (Testing Services sheet from OEM database)

2. Extracts acceptance/type/routine tests from the RFP testing requirements
   and maps each to the services price table.

3. For each line item (recommended SKU):
   - Unit price from product catalog
   - MOQ (minimum order quantity)
   - Material cost = unit_price × MOQ
   - Applicable tests + test costs (from services price table)
   - Line total = material cost + test costs

4. Outputs:
   - consolidated_pricing: {
       line_item_pricing: [...],
       total_material_cost,
       total_test_cost,
       grand_total
     }
"""

import re
from typing import List, Dict
from utils.agent_io import save_agent_output


# ─────────────────────────────────────────────
# TEST KEYWORD MAPPING
# Maps keywords found in RFP test requirements → test codes in the services table
# ─────────────────────────────────────────────

TEST_KEYWORD_MAP = {
    # High voltage withstand tests
    r'high\s*voltage\s*withstand': ["HVWT-1.1KV", "HVWT-3.5KV", "HVWT-11KV"],
    r'hv\s*withstand': ["HVWT-1.1KV", "HVWT-3.5KV", "HVWT-11KV"],
    r'voltage\s*withstand': ["HVWT-1.1KV", "HVWT-3.5KV", "HVWT-11KV"],
    # Insulation resistance
    r'insulation\s*resistance': ["IRT-10M"],
    r'\birt\b': ["IRT-10M"],
    # Tensile / mechanical
    r'tensile\s*strength': ["TST-360", "TST-350"],
    r'mechanical\s*(?:test|testing|strength)': ["TST-360", "MI-01"],
    r'mechanical\s*installation': ["MII-01"],
    r'mechanical\s*inspection': ["MI-01"],
    # Documentation / certification
    r'documentation': ["DOC-01"],
    r'certif(?:icate|ication)': ["DOC-01"],
    # Routine tests
    r'routine\s*(?:test|testing|insulation)': ["RT-01", "ET-01"],
    # Acceptance tests
    r'acceptance\s*(?:test|testing)': ["AT-01", "AT-02"],
    # Type tests
    r'type\s*(?:test|testing)': ["TT-01"],
    # Electrical tests
    r'electrical\s*(?:test|testing)': ["ET-01", "ET-02"],
}


def extract_required_tests(testing_requirements_text: str, voltage_rating: str = None) -> List[str]:
    """
    Parse the testing_requirements section of the RFP and return
    a deduplicated list of applicable test codes.

    Args:
        testing_requirements_text: Raw text from the RFP testing section
        voltage_rating: Voltage of the selected product (e.g. "11 kV") to filter HV tests

    Returns:
        List of test codes (e.g. ["HVWT-11KV", "IRT-10M", "AT-01"])
    """
    if not testing_requirements_text or not testing_requirements_text.strip():
        # Default minimal tests if no testing section found
        return ["RT-01", "IRT-10M", "DOC-01"]

    text = testing_requirements_text.lower()
    found_codes = set()

    for pattern, codes in TEST_KEYWORD_MAP.items():
        if re.search(pattern, text):
            for code in codes:
                found_codes.add(code)

    # If HV withstand tests found, filter to the right voltage
    if voltage_rating:
        v = voltage_rating.lower().replace(" ", "")
        hv_codes = {"HVWT-1.1KV", "HVWT-3.5KV", "HVWT-11KV"}
        hv_found = hv_codes.intersection(found_codes)
        if hv_found:
            # Keep only the test matching the product voltage
            if "11kv" in v:
                found_codes -= {"HVWT-1.1KV", "HVWT-3.5KV"}
            elif "1.1kv" in v or "1.1" in v:
                found_codes -= {"HVWT-11KV", "HVWT-3.5KV"}
            elif "0.6kv" in v or "415v" in v or "0.4kv" in v:
                found_codes -= {"HVWT-11KV"}

    # Always include documentation if not already
    if not any(c.startswith("DOC") for c in found_codes):
        found_codes.add("DOC-01")

    # If nothing matched but text is non-empty, add basic tests
    if len(found_codes) == 1:  # only DOC-01
        found_codes.update(["RT-01", "IRT-10M"])

    return sorted(list(found_codes))


def get_test_details(test_codes: List[str], test_services_db) -> List[Dict]:
    """
    Look up test details from the Testing Services sheet.

    Returns:
        List of {test_code, test_name, price_inr, duration_hours}
    """
    results = []
    for code in test_codes:
        row = test_services_db[test_services_db["Test_Code"] == code]
        if not row.empty:
            results.append({
                "test_code": code,
                "test_name": row["Test_Name"].iloc[0],
                "price_inr": float(row["Price_INR"].iloc[0]),
                "duration_hours": float(row["Duration_Hours"].iloc[0]),
            })
        else:
            # Test code not in DB — add with estimated price
            results.append({
                "test_code": code,
                "test_name": f"Test {code} (estimated)",
                "price_inr": 10000.0,
                "duration_hours": 2.0,
            })
    return results


def pricing_agent(state: dict) -> dict:
    """
    Pricing Agent - assigns unit prices and test costs per line item.

    Reads from state:
        - pricing_summary (from master agent - has testing_requirements)
        - tech_matches (selected SKUs from technical agent, one per line item)
        - line_item_matches (full per-item data from technical agent)
        - product_db
        - test_services_db (Testing Services sheet)

    Writes to state:
        - consolidated_pricing: full cost breakdown
        - prices: list of grand totals per line item (backward compat)
    """
    pricing_summary = state.get("pricing_summary", {})
    line_item_matches = state.get("line_item_matches", [])
    product_db = state["product_db"]
    test_services_db = state.get("test_services_db")

    testing_requirements_text = pricing_summary.get("testing_requirements", "")

    print(f"\n💰 Pricing Agent: Processing {len(line_item_matches)} line item(s)")

    if not line_item_matches:
        state["consolidated_pricing"] = {
            "line_item_pricing": [],
            "total_material_cost": 0,
            "total_test_cost": 0,
            "grand_total": 0
        }
        state["prices"] = []
        return state

    line_item_pricing = []
    total_material_cost = 0.0
    total_test_cost = 0.0

    for item_result in line_item_matches:
        line_item_text = item_result.get("line_item", "")
        selected_sku = item_result.get("selected_sku")

        if not selected_sku:
            # No OEM product matched this line item
            line_item_pricing.append({
                "line_item": line_item_text,
                "sku": None,
                "unit_price_inr": 0,
                "moq_meters": 0,
                "material_cost_inr": 0,
                "applicable_tests": [],
                "test_cost_inr": 0,
                "line_total_inr": 0,
                "note": "No matching product found"
            })
            continue

        product_id = selected_sku["product_id"]

        # ── Material Pricing ──
        product_row = product_db[product_db["Product_ID"] == product_id]
        if not product_row.empty:
            unit_price = float(product_row["Unit_Price_INR_per_meter"].iloc[0])
            moq = int(product_row["Min_Order_Qty_Meters"].iloc[0])
            voltage_rating = str(product_row["Voltage_Rating"].iloc[0])
        else:
            # Fallback to what technical agent stored
            unit_price = selected_sku.get("unit_price", 0.0)
            moq = selected_sku.get("moq", 100)
            voltage_rating = ""

        material_cost = round(unit_price * moq, 2)

        # ── Test Pricing ──
        required_test_codes = extract_required_tests(testing_requirements_text, voltage_rating)
        if test_services_db is not None:
            test_details = get_test_details(required_test_codes, test_services_db)
        else:
            # Fallback if test_services_db not loaded
            test_details = [
                {"test_code": "RT-01", "test_name": "Routine Insulation Test", "price_inr": 8000.0, "duration_hours": 1.0},
                {"test_code": "IRT-10M", "test_name": "Insulation Resistance Test", "price_inr": 12000.0, "duration_hours": 1.0},
                {"test_code": "DOC-01", "test_name": "Documentation and Certification", "price_inr": 10000.0, "duration_hours": 4.0},
            ]

        test_cost = round(sum(t["price_inr"] for t in test_details), 2)
        line_total = round(material_cost + test_cost, 2)

        total_material_cost += material_cost
        total_test_cost += test_cost

        row = {
            "line_item": line_item_text,
            "sku": product_id,
            "product_name": selected_sku.get("product_name", ""),
            "unit_price_inr": unit_price,
            "moq_meters": moq,
            "material_cost_inr": material_cost,
            "applicable_tests": test_details,
            "test_cost_inr": test_cost,
            "line_total_inr": line_total,
        }
        line_item_pricing.append(row)

        print(f"\n   📦 {line_item_text[:60]}")
        print(f"      SKU          : {product_id}")
        print(f"      Unit Price   : ₹{unit_price:,.2f}/m")
        print(f"      MOQ          : {moq} m")
        print(f"      Material Cost: ₹{material_cost:,.0f}")
        print(f"      Tests        : {[t['test_code'] for t in test_details]}")
        print(f"      Test Cost    : ₹{test_cost:,.0f}")
        print(f"      Line Total   : ₹{line_total:,.0f}")

    grand_total = round(total_material_cost + total_test_cost, 2)

    consolidated_pricing = {
        "line_item_pricing": line_item_pricing,
        "total_material_cost": round(total_material_cost, 2),
        "total_test_cost": round(total_test_cost, 2),
        "grand_total": grand_total,
    }

    state["consolidated_pricing"] = consolidated_pricing
    # Backward compat: prices as list of line totals
    state["prices"] = [row["line_total_inr"] for row in line_item_pricing]

    save_agent_output("pricing_agent", {
        "line_item_count": len(line_item_pricing),
        "line_item_pricing": [
            {
                "line_item": r["line_item"][:80],
                "sku": r.get("sku"),
                "unit_price_inr": r.get("unit_price_inr"),
                "moq_meters": r.get("moq_meters"),
                "material_cost_inr": r.get("material_cost_inr"),
                "test_codes": [t["test_code"] for t in r.get("applicable_tests", [])],
                "test_cost_inr": r.get("test_cost_inr"),
                "line_total_inr": r.get("line_total_inr"),
            }
            for r in line_item_pricing
        ],
        "total_material_cost": total_material_cost,
        "total_test_cost": total_test_cost,
        "grand_total": grand_total,
    })

    print(f"\n   ─────────────────────────────────")
    print(f"   Total Material : ₹{total_material_cost:,.0f}")
    print(f"   Total Tests    : ₹{total_test_cost:,.0f}")
    print(f"   GRAND TOTAL    : ₹{grand_total:,.0f}")

    return state