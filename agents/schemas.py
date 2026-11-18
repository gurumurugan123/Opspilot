"""
Pydantic Schemas for Structured Agent Outputs (Phase 5).
"""

from typing import List, Optional
from pydantic import BaseModel, Field


class PlanOutput(BaseModel):
    steps: List[str] = Field(description="Ordered list of diagnostic inspection steps.")
    focus_services: List[str] = Field(default_factory=list, description="Services identified as potentially degraded.")


class EvidenceItem(BaseModel):
    source: str = Field(description="Origin of the evidence (e.g. k8s:pod_logs, k8s:events, jenkins:build#42).")
    finding: str = Field(description="Concrete observed finding or error line.")
    timestamp: Optional[str] = Field(default=None, description="Timestamp of observed event if available.")


class ReviewOutput(BaseModel):
    is_approved: bool = Field(description="True if hypothesis is directly substantiated by evidence.")
    confidence: float = Field(description="Confidence score between 0.0 and 1.0.")
    critique: str = Field(description="Evaluation of whether evidence sufficiently proves the hypothesis.")
    recommended_checks: List[str] = Field(default_factory=list, description="Specific follow-up checks if confidence < 0.8.")


class ReportOutput(BaseModel):
    root_cause: str = Field(description="Identified root cause explaining why the service failed.")
    confidence: float = Field(description="Reviewer-approved confidence score (0.0 to 1.0).")
    suggested_fix: str = Field(description="Actionable remediation steps to resolve the outage.")
    evidence: List[str] = Field(description="Directly cited log lines, event descriptions, or commit IDs.")
    similar_incidents: List[str] = Field(default_factory=list, description="Cited past incident reports or runbooks.")
    what_was_ruled_out: List[str] = Field(default_factory=list, description="Hypotheses evaluated and ruled out.")
