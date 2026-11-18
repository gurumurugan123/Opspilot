"""
LangGraph Investigation State Definition (Phase 5).
"""

import operator
from typing import Annotated, Any, Dict, List, Optional, TypedDict


class IncidentState(TypedDict):
    # Core Inputs
    investigation_id: Optional[str]
    question: str
    namespace: str
    service_hint: Optional[str]

    # Diagnostics & Planning
    plan: List[str]
    evidence: Annotated[List[Dict[str, Any]], operator.add]
    current_hypothesis: str
    focus_pod: Optional[str]

    # Review & Quality Gate
    confidence: float
    is_approved: bool
    critique: str
    recommended_checks: List[str]

    # Execution Bounds
    tool_call_count: int
    iteration_count: int

    # Final Output
    final_report: Optional[Dict[str, Any]]
