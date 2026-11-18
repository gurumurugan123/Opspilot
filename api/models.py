"""
Database Models for OpsPilot Incident Investigation Backend (Phase 3).

Stores:
  - Investigation: Tracks query/alert, status, current hypothesis, and ticket metadata.
  - ToolCall: Detailed audit log of every MCP tool invoked by the agent.
  - InvestigationReport: Final evidence-backed root-cause diagnosis.
  - Feedback: Human verification ratings (accuracy, helpfulness) for future evals.
"""

import uuid
from django.db import models


class Investigation(models.Model):
    class Status(models.TextChoices):
        QUEUED = "QUEUED", "Queued"
        IN_PROGRESS = "IN_PROGRESS", "In Progress"
        COMPLETED = "COMPLETED", "Completed"
        FAILED = "FAILED", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    query = models.TextField(help_text="User question or incident description (e.g. 'Why is payment-service failing?')")
    service_hint = models.CharField(max_length=128, blank=True, null=True, help_text="Optional suspected service name")
    namespace = models.CharField(max_length=64, default="opspilot-demo")
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.QUEUED, db_index=True)
    current_hypothesis = models.TextField(blank=True, default="")
    celery_task_id = models.CharField(max_length=128, blank=True, null=True, db_index=True)

    # Human-in-the-loop Ticket Approval Gate
    ticket_approved = models.BooleanField(default=False)
    ticket_created = models.BooleanField(default=False)
    ticket_url = models.URLField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(blank=True, null=True)

    def __str__(self):
        return f"Investigation {self.id} [{self.status}] - {self.query[:40]}"


class ToolCall(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    investigation = models.ForeignKey(
        Investigation, on_delete=models.CASCADE, related_name="tool_calls", db_index=True
    )
    step_number = models.PositiveIntegerField(default=1)
    tool_name = models.CharField(max_length=128, db_index=True)
    arguments = models.JSONField(default=dict)
    output_summary = models.TextField(blank=True, default="")
    raw_output = models.JSONField(default=dict, blank=True)
    duration_ms = models.FloatField(default=0.0)
    is_error = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["step_number", "created_at"]

    def __str__(self):
        return f"Step {self.step_number}: {self.tool_name} ({'ERR' if self.is_error else 'OK'})"


class InvestigationReport(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    investigation = models.OneToOneField(
        Investigation, on_delete=models.CASCADE, related_name="report", db_index=True
    )
    root_cause = models.TextField()
    confidence = models.FloatField(help_text="Confidence score from 0.0 to 1.0 assigned by Reviewer agent")
    suggested_fix = models.TextField()
    evidence = models.JSONField(default=list, help_text="Citations of log excerpts, pod events, or Jenkins builds")
    similar_incidents = models.JSONField(default=list, help_text="Past incident reports or runbooks cited")
    what_was_ruled_out = models.JSONField(default=list, blank=True)
    total_tokens = models.PositiveIntegerField(default=0)
    total_cost_usd = models.FloatField(default=0.0)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Report for {self.investigation_id} (Confidence: {self.confidence:.0%})"


class Feedback(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    investigation = models.ForeignKey(
        Investigation, on_delete=models.CASCADE, related_name="feedback_entries"
    )
    is_correct = models.BooleanField(help_text="Was the root cause diagnosis correct?")
    rating = models.PositiveSmallIntegerField(default=5, help_text="1 to 5 rating")
    comments = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Feedback for {self.investigation_id}: {'Correct' if self.is_correct else 'Incorrect'}"
