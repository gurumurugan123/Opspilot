"""
Phase 0 Practice: Minimal LangGraph State Machine
Demonstrates State, Nodes, Edges, and Conditional Feedback Loops.
"""

from typing import TypedDict, List, Annotated
import operator

# 1. Define Graph State
class IncidentState(TypedDict):
    question: str
    plan: List[str]
    evidence: Annotated[List[str], operator.add]
    hypothesis: str
    confidence: float
    iteration_count: int
    is_resolved: bool

# 2. Define Node Functions
def planner_node(state: IncidentState) -> dict:
    """Reads the question and formulates an initial diagnostic plan."""
    print(f"\n[Planner] Analyzing incident: '{state['question']}'")
    plan = [
        "Check pod health and restart counts",
        "Inspect recent pod logs for traceback"
    ]
    return {
        "plan": plan,
        "iteration_count": state.get("iteration_count", 0) + 1
    }

def investigator_node(state: IncidentState) -> dict:
    """Simulates tool execution and evidence gathering."""
    iteration = state.get("iteration_count", 1)
    print(f"[Investigator] Gathering evidence (Pass {iteration})...")
    
    if iteration == 1:
        new_evidence = ["Pod payment-service-78f99 is CrashLoopBackOff (exit code 1)."]
        hypothesis = "Payment service crashed due to startup error."
    else:
        new_evidence = ["Log excerpt: DB_PASSWORD environment variable is missing."]
        hypothesis = "Payment service crashed because required DB_PASSWORD env var is missing."
        
    return {
        "evidence": new_evidence,
        "hypothesis": hypothesis
    }

def reviewer_node(state: IncidentState) -> dict:
    """Validates if hypothesis is backed by clear evidence."""
    print(f"[Reviewer] Evaluating hypothesis: '{state['hypothesis']}'")
    # If the root cause is specific (mentions DB_PASSWORD), confidence is high
    if "DB_PASSWORD" in state.get("hypothesis", ""):
        confidence = 0.95
        is_resolved = True
        print(f"[Reviewer] -> Approved! Confidence: {confidence:.2f}")
    else:
        confidence = 0.50
        is_resolved = False
        print(f"[Reviewer] -> Insufficient evidence. Confidence: {confidence:.2f}. Requesting deeper log checks.")

    return {
        "confidence": confidence,
        "is_resolved": is_resolved
    }

# 3. Conditional Edge Logic
def should_continue(state: IncidentState) -> str:
    if state["is_resolved"] or state.get("iteration_count", 0) >= 3:
        return "end"
    return "investigate"

# 4. Build and Compile Graph
def build_graph():
    try:
        from langgraph.graph import StateGraph, END
    except ImportError:
        print("Note: langgraph is not installed yet in the current environment.")
        return None

    workflow = StateGraph(IncidentState)

    workflow.add_node("planner", planner_node)
    workflow.add_node("investigator", investigator_node)
    workflow.add_node("reviewer", reviewer_node)

    workflow.set_entry_point("planner")
    workflow.add_edge("planner", "investigator")
    workflow.add_edge("investigator", "reviewer")

    workflow.add_conditional_edges(
        "reviewer",
        should_continue,
        {
            "investigate": "investigator",
            "end": END
        }
    )

    return workflow.compile()

if __name__ == "__main__":
    app = build_graph()
    if app:
        initial_state: IncidentState = {
            "question": "Why is payment-service throwing 500 errors?",
            "plan": [],
            "evidence": [],
            "hypothesis": "",
            "confidence": 0.0,
            "iteration_count": 0,
            "is_resolved": False
        }
        final_state = app.invoke(initial_state)
        print("\n--- Final Graph State ---")
        print(f"Hypothesis: {final_state['hypothesis']}")
        print(f"Confidence: {final_state['confidence']}")
        print("Evidence gathered:")
        for ev in final_state["evidence"]:
            print(f"  - {ev}")
    else:
        # Fallback simulator if packages are not installed yet
        print("\nRunning simulated graph flow:")
        state = {
            "question": "Why is payment-service throwing 500 errors?",
            "plan": [],
            "evidence": [],
            "hypothesis": "",
            "confidence": 0.0,
            "iteration_count": 0,
            "is_resolved": False
        }
        state.update(planner_node(state))
        state.update(investigator_node(state))
        state.update(reviewer_node(state))
        decision = should_continue(state)
        if decision == "investigate":
            state["iteration_count"] += 1
            state.update(investigator_node(state))
            state.update(reviewer_node(state))
        print("\nSimulated graph flow completed successfully!")
