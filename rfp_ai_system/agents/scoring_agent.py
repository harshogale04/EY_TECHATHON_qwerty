# agents/scoring_agent.py
"""
Scoring Agent — RFP Bid Viability Scorer
==========================================
NOT a standalone pipeline node (PS doesn't define it as one).
Used INSIDE master_agent_start to score all shortlisted tenders
and pick the best one to respond to.

Usage (inside master_agent_start):
    from agents.scoring_agent import score_single_rfp, RFPScorer
    scorer = RFPScorer(product_db)
    result = score_single_rfp(scorer, rfp, product_db)

Scoring Factors & Weights:
    Technical Match       35%  — how many OEM products match the scope
    Price Competitiveness 25%  — margin quality vs benchmark
    Delivery Capability   15%  — lead times vs deadline
    Compliance            15%  — BIS certification & standards
    Risk Assessment       10%  — availability & MOQ risk
"""

import math
import re
from datetime import datetime
from typing import List, Dict, Any




# ─────────────────────────────────────────────────────────────
# Quick spec matcher — lightweight version used for pre-scoring
# (Full per-line-item matching is done by technical_agent.py)
# ─────────────────────────────────────────────────────────────

def _quick_match_rfp(rfp: dict, product_db) -> List[Dict]:
    """
    Lightweight spec match across the whole RFP text to get candidate products.
    Used only for scoring/ranking tenders — not for the final recommendation.
    Returns a flat list of matched products with spec_match_percent.
    """
    combined_text = " ".join([
        str(rfp.get("scope_of_supply", "")),
        str(rfp.get("technical_specifications", "")),
    ]).lower()
    combined_text = re.sub(r'[^\w\s]', ' ', combined_text)

    def _has(keywords):
        return any(k in combined_text for k in keywords)

    # Extract voltage
    vm = re.search(r'(\d+(?:\.\d+)?)\s*(?:kv|v\b)', combined_text)
    rfp_voltage = vm.group(0).replace(" ", "") if vm else None

    matches = []
    for _, row in product_db.iterrows():
        score = 0
        total = 0

        # Voltage
        if rfp_voltage:
            total += 1
            prod_v = re.sub(r'[^\w]', '', str(row["Voltage_Rating"]).lower())
            if rfp_voltage in prod_v or prod_v in rfp_voltage:
                score += 1

        # Conductor
        if _has(["copper", "cu "]):
            total += 1
            if "copper" in str(row["Conductor_Material"]).lower():
                score += 1
        elif _has(["aluminium", "aluminum", "al "]):
            total += 1
            if any(w in str(row["Conductor_Material"]).lower() for w in ["alum", "al"]):
                score += 1

        # Insulation
        if _has(["xlpe", "cross linked"]):
            total += 1
            if "xlpe" in str(row["Insulation_Type"]).lower():
                score += 1
        elif _has(["pvc"]):
            total += 1
            if "pvc" in str(row["Insulation_Type"]).lower():
                score += 1

        if total == 0:
            continue

        pct = round((score / total) * 100, 2)
        if pct > 0:
            matches.append({
                "product_id":         row["Product_ID"],
                "spec_match_percent": pct,
                "category":           row["Category"],
                "bis_certified":      str(row["BIS_Certified"]),
            })

    matches.sort(key=lambda x: x["spec_match_percent"], reverse=True)
    return matches[:10]   # top 10 for scoring purposes


# ─────────────────────────────────────────────────────────────
# RFPScorer — multi-factor scoring engine
# ─────────────────────────────────────────────────────────────

class RFPScorer:
    """
    Scores an RFP on bid viability using 5 weighted factors.
    Used by master_agent_start to pick the best RFP from the shortlist.
    """

    WEIGHTS = {
        'technical_match':       0.35,
        'price_competitiveness': 0.25,
        'delivery_capability':   0.15,
        'compliance':            0.15,
        'risk_score':            0.10,
    }

    IDEAL_MARGIN = 0.25   # 25% profit margin benchmark

    def __init__(self, product_db):
        self.product_db = product_db

    # ── Factor 1: Technical Match ────────────────────────────────────────
    def score_technical_match(self, matches: List[Dict]) -> float:
        """
        Score how well OEM products match the RFP (0-100).
        Uses exponential decay weighting across top matches.
        """
        valid = [m for m in matches if m and m.get('spec_match_percent', 0) > 0]
        if not valid:
            return 0.0

        total_score  = 0.0
        total_weight = 0.0
        for i, m in enumerate(valid[:5]):
            w = math.exp(-0.3 * i)   # 1.0, 0.74, 0.55, 0.41, 0.30
            total_score  += m['spec_match_percent'] * w
            total_weight += w

        avg = total_score / total_weight if total_weight > 0 else 0

        # Bonus for multiple good matches
        good = len([m for m in valid if m['spec_match_percent'] >= 70])
        multiplier = min(1.0 + (good - 1) * 0.05, 1.15)

        return min(avg * multiplier, 100.0)

    # ── Factor 2: Price Competitiveness ──────────────────────────────────
    def score_price_competitiveness(self, estimated_price: float, matches: List[Dict]) -> float:
        """
        Score pricing quality vs ideal margin benchmark (0-100).
        """
        if estimated_price <= 0 or not matches:
            return 0.0

        actual_cost = 0.0
        for m in matches:
            if not m:
                continue
            row = self.product_db[self.product_db['Product_ID'] == m.get('product_id')]
            if not row.empty:
                actual_cost += (row['Unit_Price_INR_per_meter'].iloc[0] *
                                row['Min_Order_Qty_Meters'].iloc[0])

        if actual_cost <= 0:
            actual_cost = estimated_price * 0.70

        margin = (estimated_price - actual_cost) / estimated_price if estimated_price > 0 else 0
        deviation = abs(margin - self.IDEAL_MARGIN)

        score = 100 / (1 + math.exp(10 * (deviation - 0.10)))
        if margin < 0.05:
            score *= 0.5
        elif margin > 0.50:
            score *= 0.6

        return max(0.0, min(score, 100.0))

    # ── Factor 3: Delivery Capability ────────────────────────────────────
    def score_delivery_capability(self, matches: List[Dict], deadline: str = None) -> float:
        """
        Score deliverability based on lead times vs deadline (0-100).
        """
        if not matches:
            return 0.0

        total_lt = 0
        total_w  = 0
        for m in matches:
            if not m:
                continue
            row = self.product_db[self.product_db['Product_ID'] == m.get('product_id')]
            if not row.empty:
                lt = row['Lead_Time_Days'].iloc[0]
                pct = m.get('spec_match_percent', 0)
                total_lt += lt * pct
                total_w  += pct

        avg_lt = total_lt / total_w if total_w > 0 else 30
        base   = max(40, 100 - (avg_lt - 15) * 0.8)

        if deadline:
            try:
                dl   = datetime.fromisoformat(deadline.replace('Z', ''))
                days = (dl - datetime.now()).days
                if avg_lt > days * 0.7:
                    base *= 0.7
            except Exception:
                pass

        return max(0.0, min(base, 100.0))

    # ── Factor 4: Compliance ─────────────────────────────────────────────
    def score_compliance(self, matches: List[Dict]) -> float:
        """
        Score BIS certification + standards compliance + warranty (0-100).
        """
        if not matches:
            return 0.0

        bis = standards = 0
        warranty_sum = 0
        total = 0

        for m in matches:
            if not m:
                continue
            row = self.product_db[self.product_db['Product_ID'] == m.get('product_id')]
            if row.empty:
                continue
            total += 1
            if row['BIS_Certified'].iloc[0].lower() == 'yes':
                bis += 1
            stds = str(row['Standards_Compliance'].iloc[0]).lower()
            if any(s in stds for s in ['is', 'iec', 'ieee', 'iso']):
                standards += 1
            warranty_sum += min(row['Warranty_Years'].iloc[0], 5)

        if total == 0:
            return 0.0

        return min(
            (bis / total) * 40 +
            (standards / total) * 40 +
            (warranty_sum / total / 5) * 20,
            100.0
        )

    # ── Factor 5: Risk Assessment ─────────────────────────────────────────
    def score_risk_assessment(self, matches: List[Dict], estimated_price: float) -> float:
        """
        Score risk — availability, diversity, MOQ (0-100, higher = lower risk).
        """
        if not matches:
            return 0.0

        availability = min(len(matches) * 20, 50)
        categories   = {m.get('category', 'Unknown') for m in matches if m}
        diversity    = min(len(categories) * 15, 30)

        high_moq = 0
        for m in matches:
            if not m:
                continue
            row = self.product_db[self.product_db['Product_ID'] == m.get('product_id')]
            if not row.empty and row['Min_Order_Qty_Meters'].iloc[0] > 500:
                high_moq += 1

        consistency = max(20 - high_moq * 5, 0)
        return min(availability + diversity + consistency, 100.0)

    # ── Final score ───────────────────────────────────────────────────────
    def calculate_final_score(
        self,
        matches: List[Dict],
        estimated_price: float,
        rfp_deadline: str = None,
    ) -> Dict[str, Any]:
        """
        Calculate weighted final score with full breakdown.

        Returns dict with:
            final_score         — 0-100
            grade               — A+/A/B+/B/C/D
            normalized_score    — 0-1 (for sorting)
            component_scores    — per-factor breakdown
            recommendation      — human-readable action
        """
        tech     = self.score_technical_match(matches)
        price    = self.score_price_competitiveness(estimated_price, matches)
        delivery = self.score_delivery_capability(matches, rfp_deadline)
        comply   = self.score_compliance(matches)
        risk     = self.score_risk_assessment(matches, estimated_price)

        final = (
            tech     * self.WEIGHTS['technical_match'] +
            price    * self.WEIGHTS['price_competitiveness'] +
            delivery * self.WEIGHTS['delivery_capability'] +
            comply   * self.WEIGHTS['compliance'] +
            risk     * self.WEIGHTS['risk_score']
        )

        if   final >= 85: grade = 'A+ (Excellent)'
        elif final >= 75: grade = 'A (Very Good)'
        elif final >= 65: grade = 'B+ (Good)'
        elif final >= 55: grade = 'B (Satisfactory)'
        elif final >= 45: grade = 'C (Marginal)'
        else:             grade = 'D (Poor)'

        if final >= 75:
            rec = "STRONGLY RECOMMEND — Proceed with bid preparation"
        elif final >= 60:
            if tech < 60:
                rec = "CONDITIONAL — Technical gaps identified, assess feasibility"
            elif price < 60:
                rec = "CONDITIONAL — Pricing optimisation needed, review cost structure"
            else:
                rec = "RECOMMEND — Good opportunity with minor optimisation potential"
        elif final >= 45:
            rec = "CAUTION — Significant gaps, evaluate strategic value before proceeding"
        else:
            rec = "DO NOT PURSUE — Poor fit, resources better allocated elsewhere"

        return {
            'final_score':      round(final, 2),
            'grade':            grade,
            'normalized_score': round(final / 100, 4),
            'component_scores': {
                'technical_match':       round(tech, 2),
                'price_competitiveness': round(price, 2),
                'delivery_capability':   round(delivery, 2),
                'compliance':            round(comply, 2),
                'risk_assessment':       round(risk, 2),
            },
            'weighted_contributions': {
                'technical_match':       round(tech     * self.WEIGHTS['technical_match'], 2),
                'price_competitiveness': round(price    * self.WEIGHTS['price_competitiveness'], 2),
                'delivery_capability':   round(delivery * self.WEIGHTS['delivery_capability'], 2),
                'compliance':            round(comply   * self.WEIGHTS['compliance'], 2),
                'risk_assessment':       round(risk     * self.WEIGHTS['risk_score'], 2),
            },
            'recommendation': rec,
        }


# ─────────────────────────────────────────────────────────────
# Convenience function — called by master_agent_start
# ─────────────────────────────────────────────────────────────

def score_single_rfp(scorer: RFPScorer, rfp: dict, product_db) -> Dict:
    """
    Score one RFP for bid viability.
    Called by master_agent_start for each shortlisted tender.

    Steps:
      1. Quick-match the RFP text against the product DB
      2. Estimate a rough price from matched products
      3. Run the full RFPScorer to get weighted score + breakdown

    Returns the score result dict from calculate_final_score().
    """
    matches        = _quick_match_rfp(rfp, product_db)
    estimated_price = sum(
        product_db[product_db['Product_ID'] == m['product_id']]['Unit_Price_INR_per_meter'].iloc[0] *
        product_db[product_db['Product_ID'] == m['product_id']]['Min_Order_Qty_Meters'].iloc[0]
        for m in matches
        if not product_db[product_db['Product_ID'] == m['product_id']].empty
    ) * 1.25   # add 25% margin estimate

    return scorer.calculate_final_score(
        matches=matches,
        estimated_price=estimated_price,
        rfp_deadline=rfp.get("submissionDeadline"),
    )