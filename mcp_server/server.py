"""
OpsPilot Read-Only MCP Server (Phase 2).

Exposes 9 read-only SRE diagnostic tools over the Model Context Protocol (MCP):
  Kubernetes:
    - list_pods
    - get_pod_logs
    - describe_pod
    - get_k8s_events
    - get_recent_deployments
  Jenkins:
    - get_jenkins_builds
    - get_jenkins_build_log
    - get_build_changes
  Knowledge Base (RAG):
    - search_runbooks

Uses the official `mcp.server.fastmcp.FastMCP` SDK when installed, and includes
a compliant JSON-RPC 2.0 stdio fallback so it can also run and be tested with
zero external dependencies.
"""

import json
import sys
from typing import Any, Callable, Dict, List

from mcp_server.redaction import redact_data, redact_text
from mcp_server.tools.jenkins import (
    get_build_changes,
    get_jenkins_build_log,
    get_jenkins_builds,
)
from mcp_server.tools.k8s import (
    DEFAULT_NAMESPACE,
    describe_pod,
    get_k8s_events,
    get_pod_logs,
    get_recent_deployments,
    list_pods,
)
from mcp_server.tools.runbooks import search_runbooks

SERVER_NAME = "opspilot-mcp"
SERVER_VERSION = "0.2.0"

# Authoritative registry of all read-only diagnostic tools
TOOL_SPECS: List[Dict[str, Any]] = [
    {
        "name": "list_pods",
        "description": (
            "List all Kubernetes pods in a namespace with their status (Running, CrashLoopBackOff, "
            "OOMKilled, Pending, ImagePullBackOff), ready count, restart count, and age. "
            "Call this first to identify which pods are unhealthy."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "namespace": {
                    "type": "string",
                    "description": "Kubernetes namespace to inspect.",
                    "default": DEFAULT_NAMESPACE,
                }
            },
            "required": [],
        },
        "handler": list_pods,
    },
    {
        "name": "get_pod_logs",
        "description": (
            "Fetch recent container logs for a specific Kubernetes pod. Secrets and PII are "
            "automatically redacted, large logs are truncated while keeping ERROR/Exception/Traceback lines."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "pod": {"type": "string", "description": "Exact pod name from list_pods."},
                "namespace": {"type": "string", "default": DEFAULT_NAMESPACE},
                "tail_lines": {"type": "integer", "default": 100, "description": "Number of recent lines to fetch."},
                "since_minutes": {"type": "integer", "default": 30, "description": "Lookback window in minutes."},
            },
            "required": ["pod"],
        },
        "handler": get_pod_logs,
    },
    {
        "name": "describe_pod",
        "description": (
            "Inspect detailed pod state including container waiting/terminated reasons, "
            "last termination exit code (e.g., 137 for OOMKilled, 1 for app crash), "
            "CPU/memory requests & limits, and pod scheduling conditions."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "pod": {"type": "string", "description": "Exact pod name to inspect."},
                "namespace": {"type": "string", "default": DEFAULT_NAMESPACE},
            },
            "required": ["pod"],
        },
        "handler": describe_pod,
    },
    {
        "name": "get_k8s_events",
        "description": (
            "Fetch recent Kubernetes cluster events (Warnings such as BackOff, Unhealthy, "
            "FailedScheduling, ErrImagePull) in a namespace."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "namespace": {"type": "string", "default": DEFAULT_NAMESPACE},
                "since_minutes": {"type": "integer", "default": 30},
            },
            "required": [],
        },
        "handler": get_k8s_events,
    },
    {
        "name": "get_recent_deployments",
        "description": (
            "List Kubernetes deployments with current rollout revision, container images, "
            "desired vs ready replicas, and rollout status conditions to spot recent bad releases."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "namespace": {"type": "string", "default": DEFAULT_NAMESPACE},
            },
            "required": [],
        },
        "handler": get_recent_deployments,
    },
    {
        "name": "get_jenkins_builds",
        "description": (
            "List recent Jenkins CI/CD builds for a job with build number, result "
            "(SUCCESS, FAILURE, IN_PROGRESS), duration, and timestamp."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "job": {"type": "string", "description": "Jenkins job name (e.g., payments-service)."},
                "limit": {"type": "integer", "default": 5, "description": "Max recent builds to return."},
            },
            "required": ["job"],
        },
        "handler": get_jenkins_builds,
    },
    {
        "name": "get_jenkins_build_log",
        "description": (
            "Fetch redacted and truncated console output for a specific Jenkins build number "
            "to diagnose failing tests, missing dependencies, or Docker build errors."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "job": {"type": "string", "description": "Jenkins job name."},
                "build_number": {"type": "integer", "description": "Jenkins build number."},
            },
            "required": ["job", "build_number"],
        },
        "handler": get_jenkins_build_log,
    },
    {
        "name": "get_build_changes",
        "description": (
            "Retrieve Git commits, authors, commit messages, and modified file paths "
            "included in a specific Jenkins build to correlate a failure with recent code/config changes."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "job": {"type": "string", "description": "Jenkins job name."},
                "build_number": {"type": "integer", "description": "Jenkins build number."},
            },
            "required": ["job", "build_number"],
        },
        "handler": get_build_changes,
    },
    {
        "name": "search_runbooks",
        "description": (
            "Search internal SRE runbooks and past incident reports for troubleshooting "
            "procedures and known fixes matching observed error symptoms."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Symptoms or error keywords to search for."},
                "top_k": {"type": "integer", "default": 3, "description": "Number of top sections to return."},
            },
            "required": ["query"],
        },
        "handler": search_runbooks,
    },
]

TOOL_HANDLERS: Dict[str, Callable[..., Any]] = {spec["name"]: spec["handler"] for spec in TOOL_SPECS}


def list_tool_schemas() -> List[Dict[str, Any]]:
    """Return MCP-compliant tool definitions (without internal Python function references)."""
    return [
        {
            "name": spec["name"],
            "description": spec["description"],
            "inputSchema": spec["inputSchema"],
        }
        for spec in TOOL_SPECS
    ]


def dispatch_tool_call(tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Execute a registered read-only tool safely with argument validation and redaction."""
    handler = TOOL_HANDLERS.get(tool_name)
    if handler is None:
        raise KeyError(f"Unknown tool: {tool_name}")

    result = handler(**(arguments or {}))
    return redact_data(result)


def _handle_jsonrpc_message(req: Dict[str, Any]) -> Dict[str, Any] | None:
    """Process a single JSON-RPC 2.0 MCP message and return a response dict (or None for notifications)."""
    req_id = req.get("id")
    method = req.get("method")
    params = req.get("params") or {}

    # JSON-RPC notifications have no `id` and expect no response
    if method == "notifications/initialized" or (req_id is None and method and method.startswith("notifications/")):
        return None

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            },
        }

    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {"tools": list_tool_schemas()},
        }

    if method == "tools/call":
        tool_name = params.get("name")
        args = params.get("arguments") or {}
        try:
            output = dispatch_tool_call(tool_name, args)
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": json.dumps(output, indent=2)}],
                    "isError": False,
                },
            }
        except KeyError as exc:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32601, "message": redact_text(str(exc))},
            }
        except TypeError as exc:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32602, "message": f"Invalid tool arguments: {redact_text(str(exc))}"},
            }
        except Exception as exc:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": f"Tool execution error: {redact_text(str(exc))}"}],
                    "isError": True,
                },
            }

    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {"code": -32601, "message": f"Method not found: {method}"},
    }


def run_stdio_server() -> None:
    """Run the built-in JSON-RPC 2.0 MCP server over stdin/stdout."""
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            req = json.loads(line)
            resp = _handle_jsonrpc_message(req)
        except Exception as exc:
            resp = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": redact_text(str(exc))},
            }
        if resp is not None:
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()


def build_fastmcp_server():
    """Build an official FastMCP server instance when the `mcp` SDK is installed."""
    from mcp.server.fastmcp import FastMCP

    mcp = FastMCP(SERVER_NAME)

    @mcp.tool(name="list_pods")
    def _list_pods(namespace: str = DEFAULT_NAMESPACE) -> Dict[str, Any]:
        """List Kubernetes pods with status, readiness, restarts, and age."""
        return list_pods(namespace=namespace)

    @mcp.tool(name="get_pod_logs")
    def _get_pod_logs(
        pod: str,
        namespace: str = DEFAULT_NAMESPACE,
        tail_lines: int = 100,
        since_minutes: int = 30,
    ) -> Dict[str, Any]:
        """Fetch redacted, truncated logs for a Kubernetes pod."""
        return get_pod_logs(pod=pod, namespace=namespace, tail_lines=tail_lines, since_minutes=since_minutes)

    @mcp.tool(name="describe_pod")
    def _describe_pod(pod: str, namespace: str = DEFAULT_NAMESPACE) -> Dict[str, Any]:
        """Describe pod state, last termination exit code, resource limits, and conditions."""
        return describe_pod(pod=pod, namespace=namespace)

    @mcp.tool(name="get_k8s_events")
    def _get_k8s_events(namespace: str = DEFAULT_NAMESPACE, since_minutes: int = 30) -> Dict[str, Any]:
        """Fetch recent Kubernetes cluster Warning and Normal events."""
        return get_k8s_events(namespace=namespace, since_minutes=since_minutes)

    @mcp.tool(name="get_recent_deployments")
    def _get_recent_deployments(namespace: str = DEFAULT_NAMESPACE) -> Dict[str, Any]:
        """List deployments with rollout revisions, container images, and replica counts."""
        return get_recent_deployments(namespace=namespace)

    @mcp.tool(name="get_jenkins_builds")
    def _get_jenkins_builds(job: str, limit: int = 5) -> Dict[str, Any]:
        """List recent Jenkins builds for a CI/CD job."""
        return get_jenkins_builds(job=job, limit=limit)

    @mcp.tool(name="get_jenkins_build_log")
    def _get_jenkins_build_log(job: str, build_number: int) -> Dict[str, Any]:
        """Fetch redacted, truncated Jenkins console output for a specific build."""
        return get_jenkins_build_log(job=job, build_number=build_number)

    @mcp.tool(name="get_build_changes")
    def _get_build_changes(job: str, build_number: int) -> Dict[str, Any]:
        """Get Git commits, authors, and changed files for a specific Jenkins build."""
        return get_build_changes(job=job, build_number=build_number)

    @mcp.tool(name="search_runbooks")
    def _search_runbooks(query: str, top_k: int = 3) -> Dict[str, Any]:
        """Search SRE runbooks and past incident reports for similar symptoms and fixes."""
        return search_runbooks(query=query, top_k=top_k)

    return mcp


if __name__ == "__main__":
    if "--stdio-fallback" in sys.argv:
        run_stdio_server()
    else:
        try:
            server = build_fastmcp_server()
            server.run(transport="stdio")
        except ImportError:
            run_stdio_server()
