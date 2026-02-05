import random

def pricing_agent(state):
    totals = []

    for tender in state["tech_matches"]:
        tender_total = 0

        for product_list in tender:
            if product_list:
                tender_total += random.randint(50000, 150000)

        totals.append(tender_total)

    state["prices"] = totals
    return state