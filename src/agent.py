"""
LangGraph graph construction and compilation for the Semantic Census Pipeline.

Defines a strictly linear execution flow:
START → node_1 → node_2 → node_3 → node_4 → node_5 → node_6 → END
"""

from langgraph.graph import StateGraph, START, END
from src.state import AgentState
from src.nodes.node_1_config_manager import node_1_config_manager
from src.nodes.node_1b_baseline_manager import node_1b_baseline_manager
from src.nodes.node_2_git_extractor import node_2_git_extractor
from src.nodes.node_3_roslyn_parser import node_3_roslyn_parser
from src.nodes.node_4_semantic_filter import node_4_semantic_filter
from src.nodes.node_5_mapper import node_5_mapper
from src.nodes.node_6_exporter import node_6_exporter


# ── Build the LangGraph Pipeline ─────────────────────────────────────────────
workflow = StateGraph(AgentState)

# Register nodes
workflow.add_node("config_manager", node_1_config_manager)
workflow.add_node("baseline_manager", node_1b_baseline_manager)
workflow.add_node("git_extractor", node_2_git_extractor)
workflow.add_node("roslyn_parser", node_3_roslyn_parser)
workflow.add_node("semantic_filter", node_4_semantic_filter)
workflow.add_node("mapper", node_5_mapper)
workflow.add_node("exporter", node_6_exporter)

# Define linear edges
workflow.add_edge(START, "config_manager")
workflow.add_edge("config_manager", "baseline_manager")
workflow.add_edge("baseline_manager", "git_extractor")
workflow.add_edge("git_extractor", "roslyn_parser")
workflow.add_edge("roslyn_parser", "semantic_filter")
workflow.add_edge("semantic_filter", "mapper")
workflow.add_edge("mapper", "exporter")
workflow.add_edge("exporter", END)

# Compile the graph
app = workflow.compile()
