from utils.spec_flattener import flatten_json

def normalize(val):
    return str(val).lower().strip()


def technical_agent(state):
    db = state["product_db"]   # pandas DataFrame from Excel
    results = []

    for rfp in state["rfps"]:
        tech_text = normalize(
    flatten_json(rfp["technical_specifications"]) +
    " " +
    flatten_json(rfp["scope_of_supply"])
)

        matches = []

        for _, row in db.iterrows():
            matched = 0
            total = 6

            specs = {
                "voltage": row["Voltage_Rating"],
                "material": row["Conductor_Material"],
                "insulation": row["Insulation_Type"],
                "cores": row["Number_of_Cores"],
                "armoring": row["Armoring"],
                "standards": row["Standards_Compliance"],
            }

            for value in specs.values():
                if normalize(value) in tech_text:
                    matched += 1

            spec_match = round((matched / total) * 100, 2)

            if spec_match > 0:
                matches.append({
                    "product_id": row["Product_ID"],
                    "product_name": row["Product_Name"],
                    "spec_match_percent": spec_match,
                    "category": row["Category"]
                })

        matches.sort(key=lambda x: x["spec_match_percent"], reverse=True)

        results.append(matches[:5])

    state["tech_matches"] = results
    return state