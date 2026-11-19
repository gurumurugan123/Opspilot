"""
Planner Agent Node for OpsPilot LangGraph Workflow (Phase 5).
"""

from typing import Dict, Any
from agents.schemas import PlanOutput
from agents.state import IncidentState
from mcp_server.security import sanitize_user_input


def planner_node(state: IncidentState) -> Dict[str, Any]:
    """
    Evaluates the incident query/alert and establishes the diagnostic plan.
    Prioritizes high-level namespace sweeps before deep log dives.
    """
    question = sanitize_user_input(state.get("question", ""))
    service_hint = state.get("service_hint")

    plan_steps = [
        "Sweep namespace pods to identify unhealthy or crashing replicas (list_pods)",
        "Check recent cluster warning events (get_k8s_events)",
        "Inspect rollout revisions and recent container image changes (get_recent_deployments)",
        "Drill down into failing pod details, resource limits, and exit codes (describe_pod)",
        "Extract redacted container logs and error tracebacks (get_pod_logs)",
        "Query internal SRE runbooks and postmortems via Hybrid RAG (search_runbooks)",
    ]

    focus = [service_hint] if service_hint else []

    plan_data = PlanOutput(steps=plan_steps, focus_services=focus)

    return {
        "plan": plan_data.steps,
        "current_hypothesis": "Initial plan formulated. Starting namespace health inspection...",
        "iteration_count": state.get("iteration_count", 0) + 1,
    }
