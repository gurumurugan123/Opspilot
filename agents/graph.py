"""
LangGraph Multi-Agent Orchestration Graph for OpsPilot (Phase 5).

Workflow Topology:
  [START]
     │
     ▼
  [Planner Node]
     │
     ▼
  [Investigator Node] <────────┐  (Conditional Edge: Reviewer requests extra checks)
     │                         │
     ▼                         │
  [Reviewer Node] ─────────────┘
     │ (is_approved == True OR max iterations reached)
     ▼
  [Reporter Node]
     │
     ▼
   [END]
"""

from typing import Any, Dict, Optional
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from agents.investigator import investigator_node
from agents.planner import planner_node
from agents.reporter import reporter_node
from agents.reviewer import reviewer_node
from agents.state import IncidentState


def reviewer_decision(state: IncidentState) -> str:
    """
    Conditional edge logic:
    If the reviewer approved the evidence-backed hypothesis (confidence >= 0.80),
    proceed to report generation. Otherwise, loop back to the investigator.
    """
    is_approved = state.get("is_approved", False)
    iteration = state.get("iteration_count", 1)

    if is_approved or iteration >= 2:
        return "reporter"
    return "investigator"


def compile_investigation_graph(checkpointer: Optional[Any] = None):
    """Compile and return the runnable LangGraph state machine."""
    workflow = StateGraph(IncidentState)

    # 1. Register Nodes
    workflow.add_node("planner", planner_node)
    workflow.add_node("investigator", investigator_node)
    workflow.add_node("reviewer", reviewer_node)
    workflow.add_node("reporter", reporter_node)

    # 2. Establish Edges
    workflow.set_entry_point("planner")
    workflow.add_edge("planner", "investigator")
    workflow.add_edge("investigator", "reviewer")

    # 3. Conditional Verification Edge
    workflow.add_conditional_edges(
        "reviewer",
        reviewer_decision,
        {
            "investigator": "investigator",
            "reporter": "reporter",
        },
    )

    workflow.add_edge("reporter", END)

    saver = checkpointer or MemorySaver()
    return workflow.compile(checkpointer=saver)


def run_investigation_graph(
    question: str,
    namespace: str = "opspilot-demo",
    service_hint: Optional[str] = None,
    investigation_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Executes an end-to-end multi-agent investigation over the LangGraph workflow.
    """
    graph = compile_investigation_graph()

    initial_state: IncidentState = {
        "investigation_id": investigation_id,
        "question": question,
        "namespace": namespace,
        "service_hint": service_hint,
        "plan": [],
        "evidence": [],
        "current_hypothesis": "",
        "focus_pod": None,
        "confidence": 0.0,
        "is_approved": False,
        "critique": "",
        "recommended_checks": [],
        "tool_call_count": 0,
        "iteration_count": 0,
        "final_report": None,
    }

    config = {"configurable": {"thread_id": investigation_id or "local_dev_run"}}
    final_state = graph.invoke(initial_state, config=config)
    return final_state
