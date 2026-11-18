"""
Read-Only Kubernetes Diagnostic Tools for OpsPilot MCP Server.

Strictly read-only: only invokes list/read/get endpoints using the configured
kubeconfig (or read-only ServiceAccount inside the cluster).
All outputs pass through `redact_data` before returning to the LLM.
"""

import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from mcp_server.log_utils import truncate_logs, wrap_untrusted_log
from mcp_server.redaction import redact_data, redact_text

DEFAULT_NAMESPACE = os.getenv("K8S_NAMESPACE", "opspilot-demo")


def _load_k8s_clients():
    """Load Kubernetes CoreV1Api and AppsV1Api lazily."""
    try:
        from kubernetes import client, config
    except ImportError as exc:
        raise RuntimeError(
            "The 'kubernetes' package is not installed. Run `pip install kubernetes`."
        ) from exc

    kubeconfig_path = os.getenv("KUBECONFIG_PATH")
    try:
        if kubeconfig_path:
            config.load_kube_config(config_file=os.path.expanduser(kubeconfig_path))
        else:
            try:
                config.load_kube_config()
            except Exception:
                config.load_incluster_config()
    except Exception as exc:
        raise RuntimeError(f"Failed to load Kubernetes configuration: {exc}") from exc

    return client.CoreV1Api(), client.AppsV1Api()


def _format_age(creation_timestamp: Optional[datetime]) -> str:
    """Convert a UTC timestamp into a human-readable age string like '12m' or '2h'."""
    if not creation_timestamp:
        return "unknown"
    now = datetime.now(timezone.utc)
    if creation_timestamp.tzinfo is None:
        creation_timestamp = creation_timestamp.replace(tzinfo=timezone.utc)
    delta = now - creation_timestamp
    seconds = max(0, int(delta.total_seconds()))
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m"
    if seconds < 86400:
        return f"{seconds // 3600}h"
    return f"{seconds // 86400}d"


def _extract_pod_status(pod: Any) -> Dict[str, Any]:
    """Extract readable status, restart count, and readiness summary from a K8s Pod object."""
    phase = getattr(pod.status, "phase", "Unknown") or "Unknown"
    container_statuses = getattr(pod.status, "container_statuses", None) or []

    restarts = 0
    ready_count = 0
    detailed_status = phase

    for cs in container_statuses:
        restarts += getattr(cs, "restart_count", 0) or 0
        if getattr(cs, "ready", False):
            ready_count += 1

        state = getattr(cs, "state", None)
        if state:
            if getattr(state, "waiting", None) and getattr(state.waiting, "reason", None):
                detailed_status = state.waiting.reason
            elif getattr(state, "terminated", None) and getattr(state.terminated, "reason", None):
                detailed_status = state.terminated.reason

    total_containers = len(getattr(pod.spec, "containers", None) or []) or len(container_statuses)

    return {
        "name": pod.metadata.name,
        "namespace": pod.metadata.namespace,
        "status": detailed_status,
        "phase": phase,
        "ready": f"{ready_count}/{total_containers}",
        "restarts": restarts,
        "age": _format_age(getattr(pod.metadata, "creation_timestamp", None)),
    }


def list_pods(
    namespace: str = DEFAULT_NAMESPACE,
    core_v1: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    List all pods in a Kubernetes namespace with status, restarts, readiness, and age.
    """
    if core_v1 is None:
        core_v1, _ = _load_k8s_clients()

    pod_list = core_v1.list_namespaced_pod(namespace=namespace)
    pods = [_extract_pod_status(pod) for pod in getattr(pod_list, "items", [])]

    return redact_data(
        {
            "namespace": namespace,
            "pod_count": len(pods),
            "pods": pods,
        }
    )


def get_pod_logs(
    pod: str,
    namespace: str = DEFAULT_NAMESPACE,
    tail_lines: int = 100,
    since_minutes: int = 30,
    core_v1: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Fetch recent logs from a specific pod, redact secrets/PII, truncate large outputs
    while keeping ERROR/Exception/Traceback lines, and wrap as untrusted data.
    """
    if core_v1 is None:
        core_v1, _ = _load_k8s_clients()

    since_seconds = max(60, int(since_minutes) * 60)
    raw_logs = core_v1.read_namespaced_pod_log(
        name=pod,
        namespace=namespace,
        tail_lines=max(1, min(int(tail_lines), 1000)),
        since_seconds=since_seconds,
    )

    # 1. Redact secrets FIRST so nothing sensitive survives truncation
    scrubbed = redact_text(raw_logs or "")
    # 2. Smartly truncate large logs while keeping error/traceback lines
    truncated = truncate_logs(scrubbed, max_tail_lines=min(tail_lines, 80))
    # 3. Wrap in untrusted delimiters for prompt-injection protection
    safe_logs = wrap_untrusted_log(truncated, source=f"k8s:{namespace}/{pod}")

    return {
        "pod": pod,
        "namespace": namespace,
        "since_minutes": since_minutes,
        "logs": safe_logs,
    }


def describe_pod(
    pod: str,
    namespace: str = DEFAULT_NAMESPACE,
    core_v1: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Inspect detailed pod state: container statuses, last termination reason & exit code,
    resource requests/limits, probes, and pod conditions.
    """
    if core_v1 is None:
        core_v1, _ = _load_k8s_clients()

    pod_obj = core_v1.read_namespaced_pod(name=pod, namespace=namespace)
    status_obj = pod_obj.status
    spec_obj = pod_obj.spec

    # Map container specs for resource requests/limits and image info
    spec_by_name = {c.name: c for c in (getattr(spec_obj, "containers", None) or [])}
    containers_info: List[Dict[str, Any]] = []

    for cs in (getattr(status_obj, "container_statuses", None) or []):
        c_spec = spec_by_name.get(cs.name)
        resources = getattr(c_spec, "resources", None) if c_spec else None

        current_state = {}
        if getattr(cs, "state", None):
            if getattr(cs.state, "running", None):
                current_state = {"state": "Running", "started_at": str(cs.state.running.started_at)}
            elif getattr(cs.state, "waiting", None):
                current_state = {
                    "state": "Waiting",
                    "reason": cs.state.waiting.reason,
                    "message": cs.state.waiting.message,
                }
            elif getattr(cs.state, "terminated", None):
                current_state = {
                    "state": "Terminated",
                    "reason": cs.state.terminated.reason,
                    "exit_code": cs.state.terminated.exit_code,
                    "message": cs.state.terminated.message,
                }

        last_termination = None
        last_state = getattr(cs, "last_state", None)
        if last_state and getattr(last_state, "terminated", None):
            term = last_state.terminated
            last_termination = {
                "reason": term.reason,
                "exit_code": term.exit_code,
                "message": term.message,
                "finished_at": str(term.finished_at),
            }

        containers_info.append(
            {
                "name": cs.name,
                "image": getattr(cs, "image", None) or (getattr(c_spec, "image", None) if c_spec else None),
                "ready": bool(getattr(cs, "ready", False)),
                "restart_count": getattr(cs, "restart_count", 0) or 0,
                "current_state": current_state,
                "last_termination": last_termination,
                "resources": {
                    "requests": getattr(resources, "requests", None) or {},
                    "limits": getattr(resources, "limits", None) or {},
                },
            }
        )

    # Also include container specs if pod is Pending (no container_statuses yet)
    if not containers_info:
        for c in (getattr(spec_obj, "containers", None) or []):
            resources = getattr(c, "resources", None)
            containers_info.append(
                {
                    "name": c.name,
                    "image": c.image,
                    "ready": False,
                    "restart_count": 0,
                    "current_state": {"state": "Pending"},
                    "last_termination": None,
                    "resources": {
                        "requests": getattr(resources, "requests", None) or {},
                        "limits": getattr(resources, "limits", None) or {},
                    },
                }
            )

    conditions = []
    for cond in (getattr(status_obj, "conditions", None) or []):
        conditions.append(
            {
                "type": cond.type,
                "status": cond.status,
                "reason": getattr(cond, "reason", None),
                "message": getattr(cond, "message", None),
            }
        )

    return redact_data(
        {
            "pod": pod_obj.metadata.name,
            "namespace": pod_obj.metadata.namespace,
            "phase": getattr(status_obj, "phase", "Unknown"),
            "node_name": getattr(spec_obj, "node_name", None),
            "age": _format_age(getattr(pod_obj.metadata, "creation_timestamp", None)),
            "containers": containers_info,
            "conditions": conditions,
        }
    )


def get_k8s_events(
    namespace: str = DEFAULT_NAMESPACE,
    since_minutes: int = 30,
    core_v1: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Fetch Kubernetes events (especially Warnings like BackOff, FailedScheduling, Unhealthy)
    from the last `since_minutes` minutes.
    """
    if core_v1 is None:
        core_v1, _ = _load_k8s_clients()

    event_list = core_v1.list_namespaced_event(namespace=namespace)
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=max(1, int(since_minutes)))

    events: List[Dict[str, Any]] = []
    for ev in getattr(event_list, "items", []):
        ts = getattr(ev, "last_timestamp", None) or getattr(ev, "event_time", None) or getattr(ev.metadata, "creation_timestamp", None)
        if ts:
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            if ts < cutoff:
                continue

        involved = getattr(ev, "involved_object", None)
        events.append(
            {
                "type": getattr(ev, "type", "Normal"),
                "reason": getattr(ev, "reason", ""),
                "object": f"{getattr(involved, 'kind', '')}/{getattr(involved, 'name', '')}" if involved else "",
                "message": getattr(ev, "message", ""),
                "count": getattr(ev, "count", 1) or 1,
                "last_seen": ts.isoformat() if ts else "unknown",
            }
        )

    # Sort warnings first, then most recent
    events.sort(key=lambda e: (0 if e["type"] == "Warning" else 1, e["last_seen"]), reverse=False)

    return redact_data(
        {
            "namespace": namespace,
            "since_minutes": since_minutes,
            "event_count": len(events),
            "events": events,
        }
    )


def get_recent_deployments(
    namespace: str = DEFAULT_NAMESPACE,
    apps_v1: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    List deployments in a namespace with rollout revisions, container images,
    desired vs ready replicas, and rollout status conditions.
    """
    if apps_v1 is None:
        _, apps_v1 = _load_k8s_clients()

    dep_list = apps_v1.list_namespaced_deployment(namespace=namespace)
    deployments: List[Dict[str, Any]] = []

    for dep in getattr(dep_list, "items", []):
        annotations = getattr(dep.metadata, "annotations", None) or {}
        containers = getattr(dep.spec.template.spec, "containers", None) or []
        images = [f"{c.name}={c.image}" for c in containers]

        conditions = []
        for cond in (getattr(dep.status, "conditions", None) or []):
            conditions.append(
                {
                    "type": cond.type,
                    "status": cond.status,
                    "reason": getattr(cond, "reason", None),
                    "message": getattr(cond, "message", None),
                }
            )

        deployments.append(
            {
                "name": dep.metadata.name,
                "namespace": dep.metadata.namespace,
                "revision": annotations.get("deployment.kubernetes.io/revision", "unknown"),
                "images": images,
                "desired_replicas": getattr(dep.spec, "replicas", 0) or 0,
                "ready_replicas": getattr(dep.status, "ready_replicas", 0) or 0,
                "unavailable_replicas": getattr(dep.status, "unavailable_replicas", 0) or 0,
                "age": _format_age(getattr(dep.metadata, "creation_timestamp", None)),
                "conditions": conditions,
            }
        )

    return redact_data(
        {
            "namespace": namespace,
            "deployment_count": len(deployments),
            "deployments": deployments,
        }
    )
