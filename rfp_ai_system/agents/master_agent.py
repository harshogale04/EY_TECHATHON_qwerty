def master_agent(state):
    if not state["scores"]:
        state["best_rfp"] = "No tenders found"
        return state

    best = max(range(len(state["scores"])), key=lambda i: state["scores"][i])

    state["best_rfp"] = {
        "rfp": state["rfps"][best],
        "matches": state["tech_matches"][best],
        "price": state["prices"][best],
        "score": state["scores"][best]
    }

    return state