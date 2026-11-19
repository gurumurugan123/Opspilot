"""
Unit and Integration Tests for Phase 8: Observability, SRE Dashboard & Prometheus Metrics.

Tests:
  - Dashboard Web UI rendering (GET /, GET /dashboard/).
  - Prometheus metrics exposition endpoint (GET /api/metrics/).
  - Metric counters reflect live investigation, tool call, ticket approval, and feedback state.
"""

from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from api.models import Feedback, Investigation, InvestigationReport, ToolCall


class TestObservability(TestCase):
    """Test dashboard interface, metrics endpoint, and Prometheus counters."""

    def setUp(self):
        self.client = APIClient()

    def test_dashboard_view_renders_successfully(self):
        """Dashboard endpoint GET / returns HTTP 200 with HTML content and core UI sections."""
        resp = self.client.get(reverse("dashboard"))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn("text/html", resp["Content-Type"])

        html = resp.content.decode("utf-8")
        self.assertIn("OpsPilot", html)
        self.assertIn("Launch AI Investigation", html)
        self.assertIn("Live Diagnostic Stream", html)
        self.assertIn("Human-in-the-Loop Governance", html)
        self.assertIn("Investigation Audit History", html)

    def test_dashboard_alt_route_renders_successfully(self):
        """Alternative route GET /dashboard/ also renders successfully."""
        resp = self.client.get(reverse("dashboard-alt"))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn("OpsPilot", resp.content.decode("utf-8"))

    def test_metrics_endpoint_exposition_format(self):
        """Metrics endpoint GET /api/metrics/ returns Prometheus text exposition with standard headers."""
        resp = self.client.get(reverse("metrics"))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn("text/plain", resp["Content-Type"])

        body = resp.content.decode("utf-8")
        self.assertIn("# HELP opspilot_uptime_seconds", body)
        self.assertIn("# TYPE opspilot_uptime_seconds gauge", body)
        self.assertIn("# HELP opspilot_investigations_total", body)
        self.assertIn("# TYPE opspilot_investigations_total counter", body)
        self.assertIn("# HELP opspilot_ticket_approvals_total", body)
        self.assertIn("# HELP opspilot_tool_calls_total", body)
        self.assertIn("# HELP opspilot_feedback_total", body)

    def test_metrics_reflect_live_database_state(self):
        """Verify metric counters dynamically increment based on live database state."""
        # 1. Create an investigation
        inv = Investigation.objects.create(
            query="Orders service CrashLoopBackOff",
            namespace="opspilot-demo",
            status=Investigation.Status.COMPLETED,
            ticket_approved=True,
            ticket_approved_by="guru-sre",
        )

        # 2. Record a tool call
        ToolCall.objects.create(
            investigation=inv,
            step_number=1,
            tool_name="list_pods",
            arguments={"namespace": "opspilot-demo"},
            output_summary="Found 1 pod",
            duration_ms=25.0,
        )

        # 3. Record SRE Feedback
        Feedback.objects.create(
            investigation=inv,
            is_correct=True,
            rating=5,
            comments="Perfect diagnosis",
        )

        # Query metrics endpoint
        resp = self.client.get(reverse("metrics"))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        body = resp.content.decode("utf-8")

        # Verify counters reflected
        self.assertIn('opspilot_investigations_total{status="COMPLETED"} 1', body)
        self.assertIn('opspilot_ticket_approvals_total 1', body)
        self.assertIn('opspilot_tool_calls_total{tool="list_pods"} 1', body)
        self.assertIn('opspilot_feedback_total{correct="true"} 1', body)
        self.assertIn('opspilot_feedback_total{correct="false"} 0', body)
