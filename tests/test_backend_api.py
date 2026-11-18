"""
Unit and Integration Tests for Phase 3: Django + DRF Backend Foundation.

Tests:
  - POST /api/investigations/ (triggers investigation + Celery worker task)
  - GET  /api/investigations/{id}/ (reads investigation status, audit tool calls, and report)
  - GET  /api/investigations/{id}/stream/ (SSE real-time event streaming)
  - POST /api/investigations/{id}/approve-ticket/ (Human-in-the-loop approval gate)
  - POST /api/investigations/{id}/feedback/ (SRE accuracy feedback recording)
  - POST /api/alerts/webhook/ (Alertmanager webhook ingestion)
  - Request ID structured JSON logging middleware
"""

import json
from unittest.mock import patch
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from api.models import Feedback, Investigation, InvestigationReport, ToolCall


class TestBackendAPI(TestCase):
    def setUp(self):
        self.client = APIClient()

    @patch("mcp_server.server.dispatch_tool_call")
    def test_create_and_run_investigation_end_to_end(self, mock_dispatch):
        mock_dispatch.side_effect = [
            {"namespace": "opspilot-demo", "pod_count": 3, "pods": []},
            {"namespace": "opspilot-demo", "event_count": 2, "events": []},
            {"query": "crash", "result_count": 1, "results": [{"source_file": "runbook_crashloopbackoff.md"}]},
        ]

        # 1. Trigger investigation via POST
        create_url = reverse("investigations-collection")
        resp = self.client.post(
            create_url,
            {"query": "Why is payments-service restarting?", "service_hint": "payments-service"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        inv_id = resp.data["id"]

        # 2. Retrieve investigation details via GET
        detail_url = reverse("investigation-detail", kwargs={"pk": inv_id})
        detail_resp = self.client.get(detail_url)
        self.assertEqual(detail_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(detail_resp.data["status"], "COMPLETED")
        self.assertEqual(detail_resp.data["tool_call_count"], 3)
        self.assertIsNotNone(detail_resp.data["report"])
        self.assertGreaterEqual(detail_resp.data["report"]["confidence"], 0.8)

        # 3. Stream progress via SSE GET
        stream_url = reverse("investigation-stream", kwargs={"pk": inv_id})
        stream_resp = self.client.get(stream_url)
        self.assertEqual(stream_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(stream_resp["Content-Type"], "text/event-stream")
        stream_body = b"".join(stream_resp.streaming_content).decode("utf-8")
        self.assertIn("event: status", stream_body)
        self.assertIn("event: tool_call", stream_body)
        self.assertIn("event: report", stream_body)
        self.assertIn("event: complete", stream_body)

        # 4. Human Approval Gate: Approve incident ticket
        approve_url = reverse("approve-ticket", kwargs={"pk": inv_id})
        approve_resp = self.client.post(approve_url)
        self.assertEqual(approve_resp.status_code, status.HTTP_200_OK)
        self.assertTrue(approve_resp.data["ticket_approved"])
        self.assertIn("github.com/gurumurugan123/Opspilot/issues/", approve_resp.data["ticket_url"])

        # 5. Record human accuracy feedback
        feedback_url = reverse("submit-feedback", kwargs={"pk": inv_id})
        fb_resp = self.client.post(feedback_url, {"is_correct": True, "rating": 5, "comments": "Accurate root cause"}, format="json")
        self.assertEqual(fb_resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Feedback.objects.filter(investigation_id=inv_id).count(), 1)

    def test_ticket_approval_blocked_without_report(self):
        inv = Investigation.objects.create(query="Test query without report")
        approve_url = reverse("approve-ticket", kwargs={"pk": inv.id})
        resp = self.client.post(approve_url)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("error", resp.data)

    @patch("workers.tasks.run_investigation_task.delay")
    def test_alertmanager_webhook_endpoint(self, mock_delay):
        url = reverse("alerts-webhook")
        payload = {
            "alertname": "PodCrashLooping",
            "summary": "Pod payments-service-78f99 is crashing repeatedly",
            "service": "payments-service",
        }
        resp = self.client.post(url, payload, format="json")
        self.assertEqual(resp.status_code, status.HTTP_202_ACCEPTED)
        self.assertIn("investigation_id", resp.data)
        mock_delay.assert_called_once()

    def test_structured_logging_middleware_attaches_request_id(self):
        url = reverse("investigations-collection")
        resp = self.client.get(url)
        self.assertIn("X-Request-ID", resp.headers)
        self.assertTrue(len(resp.headers["X-Request-ID"]) > 10)
