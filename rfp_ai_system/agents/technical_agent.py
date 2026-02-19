# agents/technical_agent.py
"""
TECHNICAL AGENT
================
PS Requirements:
  * Receives summary RFP from Master Agent
  * Summarizes products in scope of supply
  * Recommends top 3 OEM products per line item with Spec Match %
  * Spec Match = equal-weighted across ALL specified RFP specs
  * Prepares comparison table: RFP spec vs Top-1, Top-2, Top-3 values
  * Selects best OEM SKU per line item (highest Spec Match)
  * Sends final table of line items + recommended SKUs to Master Agent
    and Pricing Agent (via state)
"""

import re
from typing import List, Dict, Optional
from utils.agent_io import save_agent_output


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 1 — Scope-of-supply parser
# ─────────────────────────────────────────────────────────────────────────────

# Keywords that mark the START of a new product line item in the scope text.
# The scraper API returns all items concatenated with NO newlines, e.g.:
#   "MV Power Cable 0.6 kV ... 90°C MV Power Cable 1.1 kV ... LT Cable ..."
PRODUCT_START_KEYWORDS = [
    r'MV\s+Power\s+Cable',
    r'LT\s+(?:Power\s+)?Cable',
    r'HT\s+(?:Power\s+)?Cable',
    r'HV\s+(?:Power\s+)?Cable',
    r'EHV\s+(?:Power\s+)?Cable',
    r'Control\s+Cable',
    r'Instrumentation\s+Cable',
    r'Flexible\s+Cable',
    r'Solar\s+Cable',
    r'Aerial\s+(?:Bunch(?:ed)?\s+)?Cable',
    r'Fire[\s\-](?:Resistant|Retardant|Proof)\s+Cable',
    r'Armou?red\s+Cable',
    r'Unarmou?red\s+Cable',
    r'Single\s+Core\s+Cable',
    r'Multi(?:[\s\-]core)?\s+Cable',
    r'Power\s+Cable',
    r'Earthing\s+Cable',
    r'Screened\s+Cable',
    r'(?:XLPE|PVC|EPR)[\s\-]Insulated\s+Cable',
    r'(?:1\.1|0\.6|3\.5|6\.6|11|22|33|66|132)\s*kV\s+Cable',
    r'Cable\s+Tray',
    r'Cable\s+Duct',
    r'Conduit',
    r'Junction\s+Box',
    r'Distribution\s+Panel',
    r'Switchgear',
    r'Transformer',
    r'Bus\s*(?:bar|duct)',
]

_PRODUCT_PATTERN = '|'.join(f'(?:{kw})' for kw in PRODUCT_START_KEYWORDS)

# Split BEFORE a product keyword that is not at position 0
_INLINE_SPLIT_RE = re.compile(
    rf'(?<=[a-zA-Z0-9\u00b0\u00b2\s])(?=\s*(?:{_PRODUCT_PATTERN}))',
    re.IGNORECASE,
)


def parse_scope_into_line_items(scope_text: str) -> List[str]:
    """
    Parse scope_of_supply into individual product line items.
    Tries multiple strategies; first one that yields > 1 item wins.
    """
    if not scope_text or not scope_text.strip():
        return []

    text = scope_text.strip()

    # Strategy 1: Numbered / bulleted list
    structured = r'(?:^|\n)\s*(?:\(\d+\)\s+|\d+[\.\)]\s+|[a-zA-Z][\.\)]\s+|[•\-\*]\s+)'
    if re.search(structured, text, re.MULTILINE):
        parts = re.split(structured, text, flags=re.MULTILINE)
        items = [p.strip() for p in parts if p.strip() and len(p.strip()) >= 10]
        if len(items) > 1:
            return items

    # Strategy 2: Semicolon-delimited (>= 2 semicolons)
    if text.count(';') >= 2:
        parts = re.split(r';\s*', text)
        items = [p.strip() for p in parts if p.strip() and len(p.strip()) >= 10]
        if len(items) > 1:
            return items

    # Strategy 3: Newline-separated
    if '\n' in text:
        parts = re.split(r'\n+', text)
        items = [p.strip() for p in parts if p.strip() and len(p.strip()) >= 10]
        if len(items) > 1:
            return items

    # Strategy 4: Inline product-keyword boundary (handles no-newline API format)
    parts = _INLINE_SPLIT_RE.split(text)
    items = [p.strip() for p in parts if p.strip() and len(p.strip()) >= 10]
    if len(items) > 1:
        return items

    # Strategy 5: Fallback — treat entire text as one item
    return [text]


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 2 — RFP spec extractor (expanded)
# ─────────────────────────────────────────────────────────────────────────────

def extract_rfp_specs(line_item_text: str) -> Dict[str, Optional[str]]:
    """
    Extract ALL measurable spec parameters from a line item description.

    Extracts:
      voltage, conductor_material, insulation_type, cores,
      armoring, conductor_size_mm2, temperature_rating_c,
      quantity_meters, standards

    All extracted specs participate equally in Spec Match scoring.
    Unextracted specs (None) are excluded from the denominator.
    """
    text = line_item_text.lower()
    specs: Dict[str, Optional[str]] = {}

    # Voltage rating — e.g. "0.6 kV", "1.1kV", "11 kV", "415V"
    v = re.search(r'(\d+(?:\.\d+)?)\s*(?:kv|v\b)', text)
    specs["voltage"] = v.group(0).strip() if v else None

    # Conductor material
    if any(w in text for w in ["copper", " cu ", "cu-", "(cu)", "material: copper"]):
        specs["conductor_material"] = "copper"
    elif any(w in text for w in ["aluminum", "aluminium", " al ", "al-", "(al)",
                                  "material: aluminum", "material: aluminium"]):
        specs["conductor_material"] = "aluminum"
    else:
        specs["conductor_material"] = None

    # Insulation type
    if "xlpe" in text or "cross linked" in text or "cross-linked" in text:
        specs["insulation_type"] = "xlpe"
    elif "pvc" in text or "polyvinyl" in text:
        specs["insulation_type"] = "pvc"
    elif "epr" in text or "ethylene propylene" in text:
        specs["insulation_type"] = "epr"
    else:
        specs["insulation_type"] = None

    # Number of cores
    c = re.search(r'(\d+)\s*(?:core|cores|\bc\b)', text)
    specs["cores"] = c.group(1) if c else None

    # Armoring
    if any(w in text for w in ["armoured", "armored", "swa", "steel wire", "steel tape"]):
        specs["armoring"] = "armoured"
    elif "unarmoured" in text or "unarmored" in text:
        specs["armoring"] = "unarmoured"
    else:
        specs["armoring"] = None

    # Conductor size in mm²
    # Matches "185 mm²", "185mm2", "185 sq mm", "conductor size: 185"
    cs = re.search(
        r'(?:conductor\s*size\s*[:\-]?\s*)?(\d+(?:\.\d+)?)\s*(?:mm[²2]|sq\.?\s*mm)',
        text
    )
    specs["conductor_size_mm2"] = cs.group(1) if cs else None

    # Temperature rating in °C
    tr = re.search(r'(\d+)\s*°?\s*c\b', text)
    # Filter out voltages accidentally caught (e.g. "0.6 kV" → skip)
    if tr and int(tr.group(1)) >= 50:   # realistic temp range: 50–120 °C
        specs["temperature_rating_c"] = tr.group(1)
    else:
        specs["temperature_rating_c"] = None

    # Standards
    found_stds = []
    for std in ["is 1554", "is 7098", "iec 60502", "iec 60228", "is 694", "iec 60227"]:
        if std in text:
            found_stds.append(std.upper())
    specs["standards"] = ", ".join(found_stds) if found_stds else None

    return specs


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 3 — Spec matcher (product DB columns → rfp_specs keys)
# ─────────────────────────────────────────────────────────────────────────────

# Maps each rfp_specs key → the product DB column to compare against
SPEC_TO_DB_COL = {
    "voltage":              "Voltage_Rating",
    "conductor_material":   "Conductor_Material",
    "insulation_type":      "Insulation_Type",
    "cores":                "Number_of_Cores",
    "armoring":             "Armoring",
    "conductor_size_mm2":   "Conductor_Size_mm2",
    "temperature_rating_c": "Temperature_Rating_C",
    "standards":            "Standards_Compliance",
}

MATERIAL_SYNONYMS = {
    "copper":   ["cu", "copper"],
    "aluminum": ["al", "aluminium", "aluminum", "alumunium"],
}

INSULATION_SYNONYMS = {
    "xlpe": ["xlpe", "cross-linked polyethylene", "cross linked polyethylene"],
    "pvc":  ["pvc", "polyvinyl chloride"],
    "epr":  ["epr", "ethylene propylene rubber"],
}


def _norm(val) -> str:
    if val is None:
        return ""
    return re.sub(r'[^\w\s]', ' ', str(val).lower()).strip()


def _match_spec(spec_key: str, rfp_val: str, product_row) -> bool:
    """Return True if the product satisfies the given RFP spec."""
    col = SPEC_TO_DB_COL.get(spec_key)
    if col is None:
        return False

    # Some columns may not exist in the DB — treat as no match
    if col not in product_row.index:
        return False

    prod_val = str(product_row[col])
    if prod_val in ("nan", "", "None"):
        return False

    p = _norm(prod_val)
    r = _norm(rfp_val)

    if spec_key == "voltage":
        return r.replace(" ", "") in p.replace(" ", "") or p.replace(" ", "") in r.replace(" ", "")

    if spec_key == "conductor_material":
        for canonical, variants in MATERIAL_SYNONYMS.items():
            if rfp_val in variants or rfp_val == canonical:
                return any(v in p for v in variants) or canonical in p
        return r in p

    if spec_key == "insulation_type":
        for canonical, variants in INSULATION_SYNONYMS.items():
            if rfp_val in variants or rfp_val == canonical:
                return any(v in p for v in variants) or canonical in p
        return r in p

    if spec_key == "cores":
        return r in p

    if spec_key == "armoring":
        if rfp_val == "armoured":
            return any(w in p for w in ["steel", "swa", "armour"])
        elif rfp_val == "unarmoured":
            return "unarmour" in p or p == "" or prod_val == "nan"
        return False

    if spec_key == "conductor_size_mm2":
        # Numeric proximity: match if product size >= rfp size (upward compatible)
        try:
            rfp_size  = float(rfp_val)
            prod_size = float(re.search(r'\d+(?:\.\d+)?', prod_val).group())
            return prod_size >= rfp_size * 0.9  # allow 10% tolerance
        except Exception:
            return r in p

    if spec_key == "temperature_rating_c":
        try:
            rfp_temp  = float(rfp_val)
            prod_temp = float(re.search(r'\d+(?:\.\d+)?', prod_val).group())
            return prod_temp >= rfp_temp
        except Exception:
            return r in p

    if spec_key == "standards":
        for std in rfp_val.split(","):
            std = std.strip().lower()
            if std and std in p:
                return True
        return False

    return r in p


def compute_spec_match(rfp_specs: Dict, product_row) -> tuple:
    """
    Equal-weighted spec match.
    Score = (# specs matched) / (# specs specified in RFP) * 100
    Specs not specified by the RFP are excluded from denominator.
    """
    matched         = 0
    total_specified = 0
    component       = {}

    for spec_key in SPEC_TO_DB_COL:
        rfp_val = rfp_specs.get(spec_key)
        if rfp_val is None:
            component[spec_key] = "N/A (not specified)"
            continue
        total_specified += 1
        hit = _match_spec(spec_key, rfp_val, product_row)
        component[spec_key] = "Match" if hit else "No Match"
        if hit:
            matched += 1

    if total_specified == 0:
        return 0.0, component

    return round((matched / total_specified) * 100, 2), component


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 4 — Line-item matcher
# ─────────────────────────────────────────────────────────────────────────────

def match_line_item(line_item_text: str, product_db) -> Dict:
    """
    Match one scope line item against the full product DB.
    Returns:
      - rfp_specs:    extracted spec dict
      - top_3:        top-3 OEM products with Spec Match % and comparison table
      - selected_sku: the #1 ranked product
    """
    rfp_specs  = extract_rfp_specs(line_item_text)
    candidates = []

    for _, row in product_db.iterrows():
        match_pct, component_matches = compute_spec_match(rfp_specs, row)
        if match_pct > 0:
            # Build comparison table: RFP requirement vs product value, per spec
            comparison_table = {}
            for spec_key, db_col in SPEC_TO_DB_COL.items():
                rfp_val  = rfp_specs.get(spec_key) or "Not specified"
                prod_val = str(row[db_col]) if db_col in row.index else "N/A"
                match_result = component_matches.get(spec_key, "N/A")
                comparison_table[spec_key] = {
                    "rfp_requirement": rfp_val,
                    "product_value":   prod_val if prod_val not in ("nan", "None") else "—",
                    "match":           match_result,
                }

            candidates.append({
                "product_id":         row["Product_ID"],
                "product_name":       row["Product_Name"],
                "category":           row["Category"],
                "spec_match_percent": match_pct,
                "component_matches":  component_matches,
                "comparison_table":   comparison_table,
                "unit_price":         float(row["Unit_Price_INR_per_meter"]),
                "moq":                int(row["Min_Order_Qty_Meters"]),
                "lead_time_days":     int(row["Lead_Time_Days"]),
                "bis_certified":      str(row["BIS_Certified"]),
            })

    candidates.sort(key=lambda x: x["spec_match_percent"], reverse=True)
    top_3 = candidates[:3]
    for i, c in enumerate(top_3):
        c["rank"] = i + 1

    return {
        "line_item":    line_item_text,
        "rfp_specs":    rfp_specs,
        "top_3":        top_3,
        "selected_sku": top_3[0] if top_3 else None,
    }


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 5 — Final summary table builder
# ─────────────────────────────────────────────────────────────────────────────

def build_summary_table(results: List[Dict]) -> List[Dict]:
    """
    Build the clean final table sent to Master Agent and Pricing Agent.

    Each row:
      line_item | selected_sku | spec_match_% | top_2_sku | top_3_sku |
      unit_price | moq | lead_time
    """
    table = []
    for r in results:
        top3     = r.get("top_3", [])
        selected = r.get("selected_sku")
        table.append({
            "line_item":        r["line_item"][:120],
            "rfp_specs":        r["rfp_specs"],
            "selected_sku":     selected["product_id"]         if selected else None,
            "selected_name":    selected["product_name"]        if selected else None,
            "spec_match_%":     selected["spec_match_percent"]  if selected else 0,
            "rank_2_sku":       top3[1]["product_id"]           if len(top3) > 1 else None,
            "rank_2_match_%":   top3[1]["spec_match_percent"]   if len(top3) > 1 else None,
            "rank_3_sku":       top3[2]["product_id"]           if len(top3) > 2 else None,
            "rank_3_match_%":   top3[2]["spec_match_percent"]   if len(top3) > 2 else None,
            "unit_price_inr":   selected["unit_price"]          if selected else 0,
            "moq_meters":       selected["moq"]                 if selected else 0,
            "lead_time_days":   selected["lead_time_days"]      if selected else 0,
        })
    return table


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 6 — Main agent function
# ─────────────────────────────────────────────────────────────────────────────

def technical_agent(state: dict) -> dict:
    """
    Technical Agent — per-line-item OEM product matching.

    Reads from state:
        technical_summary  — prepared by master_agent_start
        product_db

    Writes to state:
        line_item_matches  — full per-item results (for Master Agent PDF)
        tech_matches       — flat list of selected SKUs (for Pricing Agent)
        sku_summary_table  — clean final table (for Master + Pricing display)
    """
    summary    = state.get("technical_summary", {})
    product_db = state["product_db"]

    scope_text      = summary.get("scope_of_supply", "")
    tech_specs_text = summary.get("technical_specifications", "")

    if not scope_text.strip():
        scope_text = tech_specs_text

    # ── Parse line items ──────────────────────────────────────────────────
    line_items = parse_scope_into_line_items(scope_text)

    print(f"\n🔧 Technical Agent: {len(line_items)} line item(s) parsed from scope of supply:")
    for i, item in enumerate(line_items, 1):
        print(f"   {i}. {item[:90]}{'...' if len(item) > 90 else ''}")

    if not line_items:
        print("⚠️  Technical Agent: No line items found.")
        state["line_item_matches"] = []
        state["tech_matches"]      = []
        state["sku_summary_table"] = []
        return state

    # ── Match each line item ──────────────────────────────────────────────
    results = []
    for item_text in line_items:
        result   = match_line_item(item_text, product_db)
        selected = result["selected_sku"]
        label    = item_text[:65] + ("..." if len(item_text) > 65 else "")

        print(f"\n   📦 {label}")
        if selected:
            print(f"      ✅ #1  {selected['product_id']:<40} {selected['spec_match_percent']}% match")
        for m in result["top_3"][1:]:
            print(f"         #{m['rank']}  {m['product_id']:<40} {m['spec_match_percent']}% match")
        if not selected:
            print(f"      ❌ No matching product found")

        results.append(result)

    # ── Build final summary table ─────────────────────────────────────────
    summary_table = build_summary_table(results)

    print(f"\n📋 Final SKU Summary Table ({len(summary_table)} item(s)):")
    print(f"   {'#':<3} {'Line Item':<45} {'Selected SKU':<40} {'Match%'}")
    print(f"   {'-'*3} {'-'*45} {'-'*40} {'-'*6}")
    for i, row in enumerate(summary_table, 1):
        sku   = row["selected_sku"] or "—"
        match = f"{row['spec_match_%']}%" if row["selected_sku"] else "—"
        print(f"   {i:<3} {row['line_item'][:45]:<45} {sku:<40} {match}")

    # ── Write to state ────────────────────────────────────────────────────
    tech_matches = [r["selected_sku"] for r in results if r["selected_sku"]]

    state["line_item_matches"] = results
    state["tech_matches"]      = tech_matches
    state["sku_summary_table"] = summary_table   # ← clean table for Master + Pricing

    save_agent_output("technical_agent", {
        "line_items_parsed":  len(line_items),
        "spec_weightage":     "Equal — each specified param = 1/N",
        "specs_evaluated":    list(SPEC_TO_DB_COL.keys()),
        "sku_summary_table":  summary_table,
        "line_items": [
            {
                "line_item":          r["line_item"][:120],
                "rfp_specs":          r["rfp_specs"],
                "top_3_count":        len(r["top_3"]),
                "selected_sku":       r["selected_sku"]["product_id"] if r["selected_sku"] else None,
                "selected_match_pct": r["selected_sku"]["spec_match_percent"] if r["selected_sku"] else 0,
                "top_3": [
                    {
                        "rank":               m["rank"],
                        "product_id":         m["product_id"],
                        "product_name":       m["product_name"],
                        "spec_match_percent": m["spec_match_percent"],
                        "comparison_table":   m["comparison_table"],
                    }
                    for m in r["top_3"]
                ],
            }
            for r in results
        ],
    })

    return state