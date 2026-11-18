"""
Unit and Integration Tests for Phase 2: OpsPilot Read-Only MCP Server & Tools.

Tests:
  - Secret/PII redaction engine (`redaction.py`)
  - Smart log truncation & delimiter wrapping (`log_utils.py`)
  - All 5 Kubernetes read-only tools (using mocked K8s API objects)
  - All 3 Jenkins read-only tools (using mocked HTTP responses)
  - Runbook search over real markdown runbooks
  - End-to-end MCP client <-> server stdio JSON-RPC 2.0 communication
"""

import json
import subprocess
import sys
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from mcp_server.log_utils import truncate_logs, wrap_untrusted_log
from mcp_server.redaction import redact_data, redact_text
from mcp_server.server import list_tool_schemas
from mcp_server.tools.jenkins import (
    get_build_changes,
    get_jenkins_build_log,
    get_jenkins_builds,
)
from mcp_server.tools.k8s import (
    describe_pod,
    get_k8s_events,
    get_pod_logs,
    get_recent_deployments,
    list_pods,
)
from mcp_server.tools.runbooks import search_runbooks


class TestRedaction(unittest.TestCase):
    def test_redacts_database_url_and_ip(self):
        raw = "Connecting to postgres://opspilot:SuperSecret99@10.244.0.15:5432/opspilot"
        scrubbed = redact_text(raw)
        self.assertNotIn("SuperSecret99", scrubbed)
        self.assertNotIn("10.244.0.15", scrubbed)
        self.assertIn("[REDACTED_PASSWORD]", scrubbed)
        self.assertIn("[REDACTED_IP]", scrubbed)

    def test_redacts_tokens_keys_and_emails(self):
        raw = (
            "Authorization: Bearer abc123xyz987token "
            "OPENAI_API_KEY=sk-proj-1234567890abcdefghijklmnop "
            "DB_PASSWORD='my_db_password' "
            "AWS_KEY=AKIAIOSFODNN7EXAMPLE "
            "Contact: sre.lead@example.com "
            "JWT=eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3OCJ9.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
        )
        scrubbed = redact_text(raw)
        for leaked in [
            "abc123xyz987token",
            "sk-proj-1234567890abcdefghijklmnop",
            "my_db_password",
            "AKIAIOSFODNN7EXAMPLE",
            "sre.lead@example.com",
            "SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c",
        ]:
            self.assertNotIn(leaked, scrubbed)

    def test_recursive_redact_data(self):
        payload = {
            "msg": "Failed login for dev@example.com from 192.168.1.45",
            "nested": [{"secret_key": "secret_key=topsecretval"}],
        }
        result = redact_data(payload)
        self.assertIn("[REDACTED_EMAIL]", result["msg"])
        self.assertIn("[REDACTED_IP]", result["msg"])
        self.assertNotIn("topsecretval", result["nested"][0]["secret_key"])


class TestLogUtils(unittest.TestCase):
    def test_truncate_preserves_earlier_errors_and_tail(self):
        lines = [f"2026-11-18 INFO heartbeat tick {i}" for i in range(1, 201)]
        lines[14] = "2026-11-18 ERROR KeyError: 'DB_PASSWORD' is missing"
        raw = "\n".join(lines)

        truncated = truncate_logs(raw, max_tail_lines=10, max_error_lines=5)
        self.assertIn("[L15] 2026-11-18 ERROR KeyError: 'DB_PASSWORD' is missing", truncated)
        self.assertIn("heartbeat tick 200", truncated)
        self.assertNotIn("heartbeat tick 50", truncated)

    def test_wrap_untrusted_log(self):
        wrapped = wrap_untrusted_log("line1", source="k8s:opspilot-demo/payments-1")
        self.assertTrue(wrapped.startswith('<untrusted_log source="k8s:opspilot-demo/payments-1">'))
        self.assertTrue(wrapped.endswith("</untrusted_log>"))


class TestKubernetesTools(unittest.TestCase):
    def _mock_core_v1(self):
        now = datetime.now(timezone.utc)
        healthy_pod = SimpleNamespace(
            metadata=SimpleNamespace(name="orders-service-1", namespace="opspilot-demo", creation_timestamp=now - timedelta(minutes=20)),
            spec=SimpleNamespace(node_name="kind-worker-1", containers=[SimpleNamespace(name="orders-service", image="opspilot/orders:v1", resources=None)]),
            status=SimpleNamespace(
                phase="Running",
                container_statuses=[
                    SimpleNamespace(
                        name="orders-service",
                        image="opspilot/orders:v1",
                        ready=True,
                        restart_count=0,
                        state=SimpleNamespace(running=SimpleNamespace(started_at=now), waiting=None, terminated=None),
                        last_state=None,
                    )
                ],
                conditions=[],
            ),
        )
        oom_pod = SimpleNamespace(
            metadata=SimpleNamespace(name="payments-service-1", namespace="opspilot-demo", creation_timestamp=now - timedelta(minutes=5)),
            spec=SimpleNamespace(
                node_name="kind-worker-1",
                containers=[
                    SimpleNamespace(
                        name="payments-service",
                        image="opspilot/payments:v2",
                        resources=SimpleNamespace(requests={"memory": "128Mi"}, limits={"memory": "10Mi"}),
                    )
                ],
            ),
            status=SimpleNamespace(
                phase="Running",
                container_statuses=[
                    SimpleNamespace(
                        name="payments-service",
                        image="opspilot/payments:v2",
                        ready=False,
                        restart_count=6,
                        state=SimpleNamespace(
                            running=None,
                            waiting=SimpleNamespace(reason="CrashLoopBackOff", message="Back-off restarting failed container"),
                            terminated=None,
                        ),
                        last_state=SimpleNamespace(
                            terminated=SimpleNamespace(reason="OOMKilled", exit_code=137, message="Out of memory", finished_at=now)
                        ),
                    )
                ],
                conditions=[SimpleNamespace(type="Ready", status="False", reason="ContainersNotReady", message="containers with unready status")],
            ),
        )

        recent_warning = SimpleNamespace(
            type="Warning",
            reason="BackOff",
            involved_object=SimpleNamespace(kind="Pod", name="payments-service-1"),
            message="Back-off restarting failed container at 10.244.0.99",
            count=5,
            last_timestamp=now - timedelta(minutes=2),
            event_time=None,
            metadata=SimpleNamespace(creation_timestamp=now - timedelta(minutes=2)),
        )
        old_normal = SimpleNamespace(
            type="Normal",
            reason="Scheduled",
            involved_object=SimpleNamespace(kind="Pod", name="orders-service-1"),
            message="Successfully assigned pod",
            count=1,
            last_timestamp=now - timedelta(minutes=90),
            event_time=None,
            metadata=SimpleNamespace(creation_timestamp=now - timedelta(minutes=90)),
        )

        class MockCoreV1:
            def list_namespaced_pod(self, namespace):
                return SimpleNamespace(items=[healthy_pod, oom_pod])

            def read_namespaced_pod(self, name, namespace):
                return oom_pod

            def read_namespaced_pod_log(self, name, namespace, tail_lines, since_seconds):
                return (
                    "2026-11-18 INFO Booting Django payments-service\n"
                    "2026-11-18 ERROR Failed connecting to postgres://opspilot:TopSecret123@10.244.0.12:5432/opspilot\n"
                )

            def list_namespaced_event(self, namespace):
                return SimpleNamespace(items=[old_normal, recent_warning])

        return MockCoreV1()

    def _mock_apps_v1(self):
        now = datetime.now(timezone.utc)
        dep = SimpleNamespace(
            metadata=SimpleNamespace(
                name="payments-service",
                namespace="opspilot-demo",
                annotations={"deployment.kubernetes.io/revision": "4"},
                creation_timestamp=now - timedelta(hours=2),
            ),
            spec=SimpleNamespace(
                replicas=2,
                template=SimpleNamespace(
                    spec=SimpleNamespace(containers=[SimpleNamespace(name="payments-service", image="opspilot/payments:v2")])
                ),
            ),
            status=SimpleNamespace(
                ready_replicas=0,
                unavailable_replicas=2,
                conditions=[SimpleNamespace(type="Available", status="False", reason="MinimumReplicasUnavailable", message="Deployment does not have minimum availability.")],
            ),
        )

        class MockAppsV1:
            def list_namespaced_deployment(self, namespace):
                return SimpleNamespace(items=[dep])

        return MockAppsV1()

    def test_list_pods(self):
        res = list_pods(namespace="opspilot-demo", core_v1=self._mock_core_v1())
        self.assertEqual(res["pod_count"], 2)
        payments = [p for p in res["pods"] if p["name"] == "payments-service-1"][0]
        self.assertEqual(payments["status"], "CrashLoopBackOff")
        self.assertEqual(payments["restarts"], 6)
        self.assertEqual(payments["ready"], "0/1")

    def test_get_pod_logs_redacted_and_wrapped(self):
        res = get_pod_logs(pod="payments-service-1", namespace="opspilot-demo", core_v1=self._mock_core_v1())
        self.assertNotIn("TopSecret123", res["logs"])
        self.assertNotIn("10.244.0.12", res["logs"])
        self.assertIn("[REDACTED_PASSWORD]", res["logs"])
        self.assertIn("<untrusted_log", res["logs"])

    def test_describe_pod_extracts_oomkilled(self):
        res = describe_pod(pod="payments-service-1", namespace="opspilot-demo", core_v1=self._mock_core_v1())
        container = res["containers"][0]
        self.assertEqual(container["last_termination"]["reason"], "OOMKilled")
        self.assertEqual(container["last_termination"]["exit_code"], 137)
        self.assertEqual(container["resources"]["limits"]["memory"], "10Mi")

    def test_get_k8s_events_filters_and_redacts(self):
        res = get_k8s_events(namespace="opspilot-demo", since_minutes=30, core_v1=self._mock_core_v1())
        self.assertEqual(res["event_count"], 1)
        self.assertEqual(res["events"][0]["reason"], "BackOff")
        self.assertNotIn("10.244.0.99", res["events"][0]["message"])

    def test_get_recent_deployments(self):
        res = get_recent_deployments(namespace="opspilot-demo", apps_v1=self._mock_apps_v1())
        self.assertEqual(res["deployment_count"], 1)
        dep = res["deployments"][0]
        self.assertEqual(dep["revision"], "4")
        self.assertEqual(dep["unavailable_replicas"], 2)
        self.assertIn("payments-service=opspilot/payments:v2", dep["images"])


class TestJenkinsTools(unittest.TestCase):
    def test_get_jenkins_builds(self):
        mock_json = json.dumps(
            {
                "builds": [
                    {"number": 42, "result": "FAILURE", "timestamp": 1763400000000, "duration": 18500, "building": False},
                    {"number": 41, "result": "SUCCESS", "timestamp": 1763390000000, "duration": 21000, "building": False},
                ]
            }
        )
        res = get_jenkins_builds("payments-service", limit=5, http_get=lambda _url: mock_json)
        self.assertEqual(res["build_count"], 2)
        self.assertEqual(res["builds"][0]["number"], 42)
        self.assertEqual(res["builds"][0]["result"], "FAILURE")
        self.assertEqual(res["builds"][0]["duration_seconds"], 18.5)

    def test_get_jenkins_build_log_redacts_secrets(self):
        mock_log = (
            "Started by user dev@example.com\n"
            "Exporting API_KEY=sk-1234567890abcdefghijklmnop\n"
            "ERROR: pytest failed in tests/test_payments.py\n"
        )
        res = get_jenkins_build_log("payments-service", 42, http_get=lambda _url: mock_log)
        self.assertNotIn("sk-1234567890abcdefghijklmnop", res["console_log"])
        self.assertNotIn("dev@example.com", res["console_log"])
        self.assertIn("ERROR: pytest failed", res["console_log"])

    def test_get_build_changes(self):
        mock_json = json.dumps(
            {
                "number": 42,
                "result": "FAILURE",
                "timestamp": 1763400000000,
                "changeSets": [
                    {
                        "items": [
                            {
                                "commitId": "abcdef1234567890",
                                "msg": "Update DB_HOST in payments.yaml",
                                "author": {"fullName": "Alex Dev"},
                                "affectedPaths": ["demo-env/k8s/payments.yaml"],
                            }
                        ]
                    }
                ],
            }
        )
        res = get_build_changes("payments-service", 42, http_get=lambda _url: mock_json)
        self.assertEqual(res["change_count"], 1)
        self.assertEqual(res["changes"][0]["commit_id"], "abcdef1234")
        self.assertEqual(res["changes"][0]["affected_files"], ["demo-env/k8s/payments.yaml"])


class TestRunbookSearch(unittest.TestCase):
    def test_finds_oomkilled_runbook(self):
        res = search_runbooks("OOMKilled exit code 137 memory limit")
        self.assertGreater(res["result_count"], 0)
        self.assertEqual(res["results"][0]["source_file"], "runbook_oomkilled.md")

    def test_finds_db_host_runbook_and_incident(self):
        res = search_runbooks("OperationalError could not translate host name DB_HOST")
        sources = {item["source_file"] for item in res["results"]}
        self.assertTrue(
            "runbook_bad_db_host.md" in sources or "incident_report_001_db_failure.md" in sources
        )


class TestMCPServerEndToEnd(unittest.TestCase):
    def test_all_nine_tools_registered(self):
        names = [t["name"] for t in list_tool_schemas()]
        expected = {
            "list_pods",
            "get_pod_logs",
            "describe_pod",
            "get_k8s_events",
            "get_recent_deployments",
            "get_jenkins_builds",
            "get_jenkins_build_log",
            "get_build_changes",
            "search_runbooks",
        }
        self.assertEqual(set(names), expected)

    def test_mcp_stdio_client_server_roundtrip(self):
        proc = subprocess.Popen(
            [sys.executable, "-m", "mcp_server.server", "--stdio-fallback"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            def rpc(payload):
                proc.stdin.write(json.dumps(payload) + "\n")
                proc.stdin.flush()
                return json.loads(proc.stdout.readline())

            # 1. Initialize handshake
            init_res = rpc({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
            self.assertEqual(init_res["result"]["serverInfo"]["name"], "opspilot-mcp")

            # 2. List tools
            list_res = rpc({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
            self.assertEqual(len(list_res["result"]["tools"]), 9)

            # 3. Call search_runbooks tool over live stdio pipe
            call_res = rpc(
                {
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {
                        "name": "search_runbooks",
                        "arguments": {"query": "CrashLoopBackOff exit code 1", "top_k": 2},
                    },
                }
            )
            self.assertFalse(call_res["result"]["isError"])
            tool_payload = json.loads(call_res["result"]["content"][0]["text"])
            self.assertEqual(tool_payload["results"][0]["source_file"], "runbook_crashloopbackoff.md")

            # 4. Unknown tool returns clean JSON-RPC error
            err_res = rpc(
                {
                    "jsonrpc": "2.0",
                    "id": 4,
                    "method": "tools/call",
                    "params": {"name": "delete_pod", "arguments": {"pod": "payments-1"}},
                }
            )
            self.assertIn("error", err_res)
            self.assertEqual(err_res["error"]["code"], -32601)
        finally:
            proc.terminate()
            proc.wait(timeout=5)
            for stream in (proc.stdin, proc.stdout, proc.stderr):
                if stream:
                    stream.close()


if __name__ == "__main__":
    unittest.main()
