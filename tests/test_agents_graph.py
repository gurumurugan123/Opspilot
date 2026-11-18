"""
Unit and Integration Tests for Phase 5: LangGraph Multi-Agent Workflow.

Tests:
  - Planner, Investigator, Reviewer, and Reporter nodes
  - Reviewer conditional loop and checkpointing
  - End-to-end diagnosis across 5 core SRE fault scenarios:
      1. CrashLoopBackOff (exit code 1 / KeyError)
      2. OOMKilled (exit code 137 / memory limit exceeded)
      3. ImagePullBackOff (invalid container image tag)
      4. Database connection error (bad DB_HOST / 500s)
      5. Redis connection refused (port 6379 unreachable)
"""

from unittest.mock import patch
from django.test import TestCase

from agents.graph import compile_investigation_graph, reviewer_decision, run_investigation_graph
from agents.planner import planner_node
from agents.reviewer import reviewer_node
from agents.state import IncidentState


class TestAgentsGraph(TestCase):
    def test_planner_formulates_ordered_steps(self):
        state: IncidentState = {
            "question": "Why is payment-service throwing 500s?",
            "namespace": "opspilot-demo",
            "service_hint": "payments-service",
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
            "investigation_id": None,
        }
        res = planner_node(state)
        self.assertGreaterEqual(len(res["plan"]), 4)
        self.assertIn("list_pods", res["plan"][0])
        self.assertEqual(res["iteration_count"], 1)

    def test_reviewer_rejects_unsupported_hypothesis(self):
        state: IncidentState = {
            "current_hypothesis": "Database host is corrupted and redis failed.",
            "evidence": [{"source": "k8s:pods", "finding": "All pods running normally."}],
            "iteration_count": 1,
        }
        review = reviewer_node(state)
        self.assertFalse(review["is_approved"])
        self.assertLess(review["confidence"], 0.80)
        self.assertGreater(len(review["recommended_checks"]), 0)
        self.assertEqual(reviewer_decision(dict(state, **review)), "investigator")

    def test_reviewer_approves_substantiated_hypothesis(self):
        state: IncidentState = {
            "current_hypothesis": "Pod payments-service terminated Reason: OOMKilled exit code 137.",
            "evidence": [{"source": "k8s:payments/describe", "finding": "Terminated Reason=OOMKilled exit_code=137 exceeded its memory limit"}],
            "iteration_count": 1,
        }
        review = reviewer_node(state)
        self.assertTrue(review["is_approved"])
        self.assertGreaterEqual(review["confidence"], 0.90)
        self.assertEqual(reviewer_decision(dict(state, **review)), "reporter")

    @patch("agents.investigator.dispatch_tool_call")
    def test_scenario_1_crashloopbackoff_diagnosis(self, mock_tool):
        # Mock tool responses for CrashLoopBackOff scenario
        mock_tool.side_effect = lambda tool_name, args: {
            "list_pods": {
                "pod_count": 3,
                "pods": [
                    {"name": "payments-service-1", "status": "CrashLoopBackOff", "ready": "0/1", "restarts": 12},
                    {"name": "orders-service-1", "status": "Running", "ready": "1/1", "restarts": 0},
                ],
            },
            "get_k8s_events": {
                "event_count": 1,
                "events": [{"type": "Warning", "reason": "BackOff", "object": "Pod/payments-service-1", "message": "Back-off restarting failed container"}],
            },
            "describe_pod": {
                "containers": [{"name": "payments-service", "last_termination": {"reason": "Error", "exit_code": 1, "message": "KeyError: 'DB_PASSWORD'"}}],
            },
            "get_pod_logs": {
                "logs": "2026-11-18 ERROR KeyError: 'DB_PASSWORD' environment variable is required but missing!\nProcess terminated with exit code 1",
            },
            "get_recent_deployments": {"deployments": []},
            "search_runbooks": {
                "results": [{"source_file": "runbook_crashloopbackoff.md", "section": "Remediation", "score": 0.035}],
            },
        }.get(tool_name, {})

        final_state = run_investigation_graph("Why is payments-service restarting in CrashLoopBackOff?")
        report = final_state.get("final_report")
        self.assertIsNotNone(report)
        self.assertIn("crashloop", report["root_cause"].lower())
        self.assertGreaterEqual(report["confidence"], 0.85)
        self.assertIn("runbook_crashloopbackoff.md", report["similar_incidents"])
        self.assertIn("environment variable", report["suggested_fix"].lower())

    @patch("agents.investigator.dispatch_tool_call")
    def test_scenario_2_oomkilled_diagnosis(self, mock_tool):
        mock_tool.side_effect = lambda tool_name, args: {
            "list_pods": {
                "pod_count": 2,
                "pods": [{"name": "payments-service-1", "status": "Running", "ready": "0/1", "restarts": 5}],
            },
            "get_k8s_events": {
                "events": [{"type": "Warning", "reason": "OOMKilling", "object": "Pod/payments-service-1", "message": "Container exceeded its memory limit"}],
            },
            "describe_pod": {
                "containers": [{"name": "payments-service", "last_termination": {"reason": "OOMKilled", "exit_code": 137, "message": "Out of memory"}}],
            },
            "get_pod_logs": {"logs": "Allocating memory buffers...\nTerminated by SIGKILL"},
            "get_recent_deployments": {"deployments": []},
            "search_runbooks": {"results": [{"source_file": "runbook_oomkilled.md", "score": 0.038}]},
        }.get(tool_name, {})

        final_state = run_investigation_graph("Why did payments-service restart with exit code 137?")
        report = final_state.get("final_report")
        self.assertIsNotNone(report)
        self.assertIn("oomkilled", report["root_cause"].lower())
        self.assertGreaterEqual(report["confidence"], 0.90)
        self.assertIn("memory limit", report["suggested_fix"].lower())

    @patch("agents.investigator.dispatch_tool_call")
    def test_scenario_3_imagepullbackoff_diagnosis(self, mock_tool):
        mock_tool.side_effect = lambda tool_name, args: {
            "list_pods": {
                "pod_count": 2,
                "pods": [{"name": "payments-service-1", "status": "ImagePullBackOff", "ready": "0/1", "restarts": 0}],
            },
            "get_k8s_events": {
                "events": [{"type": "Warning", "reason": "Failed", "object": "Pod/payments-service-1", "message": "Failed to pull image :v999-does-not-exist: manifest unknown"}],
            },
            "describe_pod": {
                "containers": [{"name": "payments-service", "current_state": {"reason": "ImagePullBackOff"}}],
            },
            "get_pod_logs": {"logs": ""},
            "get_recent_deployments": {"deployments": [{"name": "payments-service", "unavailable_replicas": 1}]},
            "search_runbooks": {"results": [{"source_file": "runbook_imagepullbackoff.md", "score": 0.037}]},
        }.get(tool_name, {})

        final_state = run_investigation_graph("Payments deployment is stuck after new release.")
        report = final_state.get("final_report")
        self.assertIsNotNone(report)
        self.assertIn("imagepullbackoff", report["root_cause"].lower())
        self.assertIn("image tag", report["suggested_fix"].lower())

    @patch("agents.investigator.dispatch_tool_call")
    def test_scenario_4_bad_db_host_diagnosis(self, mock_tool):
        mock_tool.side_effect = lambda tool_name, args: {
            "list_pods": {
                "pod_count": 2,
                "pods": [{"name": "payments-service-1", "status": "Running", "ready": "1/1", "restarts": 0}],
            },
            "get_k8s_events": {"events": []},
            "describe_pod": {"containers": [{"name": "payments-service"}]},
            "get_pod_logs": {
                "logs": "psycopg.OperationalError: could not translate host name 'postgres-wrong-address.internal' to address: Name or service not known",
            },
            "get_recent_deployments": {"deployments": []},
            "search_runbooks": {"results": [{"source_file": "runbook_bad_db_host.md", "score": 0.04}]},
        }.get(tool_name, {})

        final_state = run_investigation_graph("Checkout returning HTTP 500 errors on payments endpoint.")
        report = final_state.get("final_report")
        self.assertIsNotNone(report)
        self.assertIn("db_host", report["root_cause"].lower())
        self.assertIn("postgres", report["suggested_fix"].lower())

    @patch("agents.investigator.dispatch_tool_call")
    def test_scenario_5_redis_connection_refused_diagnosis(self, mock_tool):
        mock_tool.side_effect = lambda tool_name, args: {
            "list_pods": {
                "pod_count": 2,
                "pods": [{"name": "inventory-service-1", "status": "Running", "ready": "1/1", "restarts": 0}],
            },
            "get_k8s_events": {"events": []},
            "describe_pod": {"containers": [{"name": "inventory-service"}]},
            "get_pod_logs": {
                "logs": "redis.exceptions.ConnectionError: CRITICAL: Failed to connect to Redis at unreachable-redis.internal:6379 - Connection Refused",
            },
            "get_recent_deployments": {"deployments": []},
            "search_runbooks": {"results": [{"source_file": "runbook_redis_connection.md", "score": 0.04}]},
        }.get(tool_name, {})

        final_state = run_investigation_graph("Inventory service failing stock reservation calls.")
        report = final_state.get("final_report")
        self.assertIsNotNone(report)
        self.assertIn("redis", report["root_cause"].lower())
        self.assertIn("redis_host", report["suggested_fix"].lower())
