"""
RAG Models for Runbook and Past Incident Knowledge Base (Phase 4).
"""

import uuid
from django.db import models


class RunbookChunk(models.Model):
    class DocType(models.TextChoices):
        RUNBOOK = "RUNBOOK", "Runbook"
        INCIDENT_REPORT = "INCIDENT_REPORT", "Incident Report"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    source_file = models.CharField(max_length=128, db_index=True)
    doc_type = models.CharField(max_length=32, choices=DocType.choices, default=DocType.RUNBOOK)
    title = models.CharField(max_length=256)
    section = models.CharField(max_length=256, db_index=True)
    content = models.TextField()
    service = models.CharField(max_length=64, default="general", db_index=True)
    tags = models.JSONField(default=list, blank=True)
    embedding = models.JSONField(default=list, blank=True, help_text="Dense vector embedding")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["source_file", "id"]

    def __str__(self):
        return f"[{self.source_file}] {self.section}"
