# graph.py
"""
Pipeline Graph — PS-aligned flow
==================================

PS-defined flow:
  Sales Agent → Master Agent → Technical Agent → Pricing Agent → Master Agent

Implemented as:
  sales → master_start → technical → pricing → master_consolidate

Notes:
  - scoring_agent is REMOVED (not mentioned in the Problem Statement)
  - Master Agent is split into two nodes to bracket the worker agents:
      master_start      : selects RFP, dispatches role-specific summaries
      master_consolidate: receives outputs, consolidates final response + PDF
"""

from langgraph.graph import StateGraph

from agents.sales_agent   import sales_agent
from agents.master_agent  import master_agent_start, master_agent_consolidate
from agents.technical_agent import technical_agent
from agents.pricing_agent   import pricing_agent


def build_graph():
    graph = StateGraph(dict)

    # ── Register nodes ────────────────────────────────────────────────────
    graph.add_node("sales",              sales_agent)
    graph.add_node("master_start",       master_agent_start)
    graph.add_node("technical",          technical_agent)
    graph.add_node("pricing",            pricing_agent)
    graph.add_node("master_consolidate", master_agent_consolidate)

    # ── Define edges (PS-defined flow) ───────────────────────────────────
    graph.set_entry_point("sales")
    graph.add_edge("sales",        "master_start")       # Sales sends selected RFP to Master
    graph.add_edge("master_start", "technical")          # Master dispatches tech summary
    graph.add_edge("technical",    "pricing")            # Technical sends SKU table to Pricing
    graph.add_edge("pricing",      "master_consolidate") # Pricing sends cost table to Master

    return graph.compile()