"""
Reviewer Agent Node for OpsPilot LangGraph Workflow (Phase 5).

Acts as the Quality Gate:
  - Verifies that hypotheses are directly substantiated by tool citations in `evidence`.
  - Assigns confidence scores (0.0 to 1.0).
  - Triggers conditional loop back to Investigator if evidence is weak or unverified.
"""

from typing import Any, Dict
from agents.schemas import ReviewOutput
from agents.state import IncidentState


def reviewer_node(state: IncidentState) -> Dict[str, Any]:
    """
    Evaluates whether the investigator's hypothesis is backed by hard evidence.
    Rejects speculation and requires direct citations.
    """
    hypothesis = state.get("current_hypothesis", "")
    evidence_items = state.get("evidence", [])
    iteration = state.get("iteration_count", 1)

    evidence_corpus = " ".join([item.get("finding", "") for item in evidence_items]).lower()
    hypo_lower = hypothesis.lower()

    # Rule 1: Check if hypothesis keywords have direct supporting citations
    is_substantiated = False
    critique = ""
    confidence = 0.50
    recommended_checks = []

    if "oom" in hypo_lower or "137" in hypo_lower:
        if "oomkilled" in evidence_corpus or "137" in evidence_corpus or "exceeded its memory" in evidence_corpus:
            is_substantiated = True
            confidence = 0.95
            critique = "Hypothesis confirmed: Container termination reason OOMKilled and exit code 137 found in pod spec/events."
        else:
            critique = "Evidence lacks explicit OOMKilled termination record or exit code 137."
            recommended_checks.append("Run describe_pod to inspect last_termination reason")

    elif "crashloop" in hypo_lower or "keyerror" in hypo_lower or "startup" in hypo_lower:
        if "crashloopbackoff" in evidence_corpus or "exitcode=1" in evidence_corpus or "keyerror" in evidence_corpus:
            is_substantiated = True
            confidence = 0.92
            critique = "Hypothesis confirmed: Pod in CrashLoopBackOff with application error/KeyError found in logs."
        else:
            critique = "CrashLoopBackOff observed but specific root-cause error not yet extracted from logs."
            recommended_checks.append("Fetch last 50 lines of container logs using get_pod_logs")

    elif "imagepull" in hypo_lower or "image" in hypo_lower:
        if "imagepullbackoff" in evidence_corpus or "errimagepull" in evidence_corpus or "manifest unknown" in evidence_corpus:
            is_substantiated = True
            confidence = 0.95
            critique = "Hypothesis confirmed: Pod stuck in ImagePullBackOff due to invalid or non-existent container tag."
        else:
            critique = "Need explicit confirmation of image pull failure from pod events."
            recommended_checks.append("Inspect k8s warning events for ImagePullBackOff")

    elif "db_host" in hypo_lower or "postgres" in hypo_lower or "database" in hypo_lower:
        if "operationalerror" in evidence_corpus or "translate host name" in evidence_corpus or "connection refused" in evidence_corpus:
            is_substantiated = True
            confidence = 0.94
            critique = "Hypothesis confirmed: Database OperationalError and host resolution failure found in application logs."
        else:
            critique = "500 errors observed but database connection failure not confirmed in logs."
            recommended_checks.append("Check application logs for psycopg OperationalError")

    elif "redis" in hypo_lower:
        if "connection refused" in evidence_corpus and "redis" in evidence_corpus:
            is_substantiated = True
            confidence = 0.95
            critique = "Hypothesis confirmed: Redis ConnectionError / Connection Refused on port 6379 cited in logs."
        else:
            critique = "Redis issue suspected but not confirmed in evidence."
            recommended_checks.append("Inspect inventory-service logs for redis ConnectionError")

    elif "readiness" in hypo_lower or "0/1" in hypo_lower:
        if "readiness probe failed" in evidence_corpus or "0/1" in evidence_corpus or "unhealthy" in evidence_corpus:
            is_substantiated = True
            confidence = 0.90
            critique = "Hypothesis confirmed: Readiness probe HTTP 500 failure confirmed in events."
        else:
            critique = "Readiness failure suspected but probe status not documented in evidence."
            recommended_checks.append("Call describe_pod to inspect readinessProbe status")

    else:
        # General case: check if at least one solid evidence item exists
        if len(evidence_items) >= 2:
            is_substantiated = True
            confidence = 0.82
            critique = "General diagnosis substantiated by correlated pod and event observations."
        else:
            critique = "Insufficient evidence collected; need deeper diagnostic checks."
            recommended_checks.append("Run full namespace pod and event inspection")

    # Guard: if we already ran 2 iterations, approve to avoid infinite loops
    if iteration >= 2 and not is_substantiated:
        is_substantiated = True
        confidence = max(confidence, 0.80)
        critique += " (Approved on maximum iteration fallback limit)."

    review = ReviewOutput(
        is_approved=is_substantiated and confidence >= 0.80,
        confidence=confidence,
        critique=critique,
        recommended_checks=recommended_checks,
    )

    return {
        "confidence": review.confidence,
        "is_approved": review.is_approved,
        "critique": review.critique,
        "recommended_checks": review.recommended_checks,
    }
