from graph import build_graph
from utils.loader import load_oem
from config import OEM_PATH, TENDER_SITE

def main():
    graph = build_graph()

    state = {
        "base_url": TENDER_SITE,
        "product_db": load_oem(OEM_PATH)
    }

    final_state = graph.invoke(state)

    print("\n🏆 BEST RFP SELECTED:\n")
    print(final_state["best_rfp"])

if __name__ == "__main__":
    main()
