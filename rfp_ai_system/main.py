# main.py
"""
Entry point — loads both DB sheets and runs the pipeline.
"""

from graph import build_graph
from utils.loader import load_oem
from config import OEM_PATH, TENDER_SITE
import pandas as pd


def main():
    # Load product catalog
    product_db = load_oem(OEM_PATH)

    # Load testing services (new — needed by pricing agent)
    test_services_db = pd.read_excel(OEM_PATH, sheet_name="Testing Services")
    print(f"✅ Loaded {len(product_db)} products and {len(test_services_db)} test services")

    graph = build_graph()

    state = {
        "base_url": TENDER_SITE,
        "product_db": product_db,
        "test_services_db": test_services_db,
    }

    final_state = graph.invoke(state)

    print("\n" + "="*60)
    print("🏆 PIPELINE COMPLETE")
    print("="*60)

    final = final_state.get("final_response", {})
    if final:
        print(f"Project : {final.get('project_name')}")
        print(f"Issued  : {final.get('issued_by')}")
        print(f"Deadline: {final.get('deadline')}")
        print(f"\nLine Items ({len(final.get('line_items', []))}):")
        for item in final.get("line_items", []):
            print(f"\n  📦 {item['line_item'][:70]}")
            print(f"     SKU          : {item.get('selected_sku', {}).get('product_id', 'N/A')}")
            print(f"     Material Cost: ₹{item.get('material_cost_inr', 0):,.0f}")
            print(f"     Test Cost    : ₹{item.get('test_cost_inr', 0):,.0f}")
            print(f"     Line Total   : ₹{item.get('line_total_inr', 0):,.0f}")
        s = final.get("summary", {})
        print(f"\n  Total Material : ₹{s.get('total_material_cost_inr', 0):,.0f}")
        print(f"  Total Tests    : ₹{s.get('total_test_cost_inr', 0):,.0f}")
        print(f"  GRAND TOTAL    : ₹{s.get('grand_total_inr', 0):,.0f}")
    else:
        print("No final response generated.")

    pdf = final_state.get("pdf_path")
    if pdf:
        print(f"\n📄 PDF Report: {pdf}")


if __name__ == "__main__":
    main()