def scoring_agent(state):
    scores = []

    for matches, price in zip(state["tech_matches"], state["prices"]):
        if not matches or len(matches) == 0:
            scores.append(0)
            continue

        # Only count matches that have products
        valid_matches = [m for m in matches if m]
        if not valid_matches:
            scores.append(0)
            continue

        tech_score = sum(
            m["spec_match_percent"] for m in valid_matches
        ) / len(valid_matches)

        price_score = max(1, 200000 / price) if price > 0 else 0

        final = round(0.6 * (tech_score/100) + 0.4 * price_score, 2)
        scores.append(final)

    state["scores"] = scores
    return state