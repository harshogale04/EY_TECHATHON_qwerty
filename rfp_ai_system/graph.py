from langgraph.graph import StateGraph

from agents.sales_agent import sales_agent
from agents.technical_agent import technical_agent
from agents.pricing_agent import pricing_agent
from agents.scoring_agent import scoring_agent
from agents.master_agent import master_agent

def build_graph():
    graph = StateGraph(dict)

    graph.add_node("sales", sales_agent)
    graph.add_node("technical", technical_agent)
    graph.add_node("pricing", pricing_agent)
    graph.add_node("scoring", scoring_agent)
    graph.add_node("master", master_agent)

    graph.set_entry_point("sales")
    graph.add_edge("sales", "technical")
    graph.add_edge("technical", "pricing")
    graph.add_edge("pricing", "scoring")
    graph.add_edge("scoring", "master")

    return graph.compile()
