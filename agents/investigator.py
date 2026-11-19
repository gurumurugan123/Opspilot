"""
Investigator Agent Node for OpsPilot LangGraph Workflow (Phase 5).

Executes MCP diagnostic tools in an evidence-driven loop:
  1. Checks pod health (list_pods).
  2. Inspects cluster warning events (get_k8s_events).
  3. Checks deployment rollout changes (get_recent_deployments).
  4. Inspects degraded pod termination state and limits (describe_pod).
  5. Retrieves error logs (get_pod_logs).
  6. Searches internal runbooks & past postmortems via RAG (search_runbooks).
"""

import time
from typing import Any, Dict, List

from agents.state import IncidentState
from mcp_server.security import detect_prompt_injection
from mcp_server.server import dispatch_tool_call


def _safe_call_tool(tool_name: str, arguments: Dict[str, Any], investigation_id: str = None) -> Dict[str, Any]:
    """Execute an MCP tool and log to Django ToolCall model if investigation_id exists."""
    start = time.time()
    try:
        result = dispatch_tool_call(tool_name, arguments)
        duration_ms = round((time.time() - start) * 1000.0, 2)
        is_error = False
    except Exception as exc:
        result = {"error": str(exc)}
        duration_ms = round((time.time() - start) * 1000.0, 2)
        is_error = True

    if investigation_id:
        try:
            from api.models import ToolCall
            ToolCall.objects.create(
                investigation_id=investigation_id,
                tool_name=tool_name,
                arguments=arguments,
                output_summary=str(result)[:300],
                raw_output=result,
                duration_ms=duration_ms,
                is_error=is_error,
            )
        except Exception:
            pass

    return result


def investigator_node(state: IncidentState) -> Dict[str, Any]:
    """
    Executes MCP diagnostic tools, gathers facts, performs RAG queries,
    and updates the active hypothesis.
    """
    namespace = state.get("namespace", "opspilot-demo")
    inv_id = state.get("investigation_id")
    tool_count = state.get("tool_call_count", 0)
    max_tool_budget = 10

    new_evidence: List[Dict[str, Any]] = []
    failing_pod = state.get("focus_pod")
    symptoms: List[str] = []

    # Check 1: Pod sweep (if not already done)
    if tool_count < max_tool_budget and not state.get("evidence"):
        pods_resp = _safe_call_tool("list_pods", {"namespace": namespace}, inv_id)
        tool_count += 1
        pods = pods_resp.get("pods", [])
        new_evidence.append({
            "source": f"k8s:{namespace}/pods",
            "finding": f"Inspected {len(pods)} pods in namespace '{namespace}'.",
        })

        for p in pods:
            status = p.get("status", "")
            ready = p.get("ready", "1/1")
            restarts = p.get("restarts", 0)
            if status not in ("Running", "Completed") or ready.startswith("0/") or restarts > 0:
                failing_pod = p.get("name")
                symptoms.append(f"Pod {failing_pod} status={status}, ready={ready}, restarts={restarts}")
                new_evidence.append({
                    "source": f"k8s:{namespace}/{failing_pod}",
                    "finding": f"Detected degraded pod: status={status}, ready={ready}, restarts={restarts}",
                })
                break

        # If all pods are superficially Running, infer focus pod from service_hint or question
        if not failing_pod:
            hint = (state.get("service_hint") or "").lower()
            q_text = state.get("question", "").lower()
            for p in pods:
                p_name = p.get("name", "").lower()
                base_name = p_name.split("-")[0]
                if (hint and hint in p_name) or (base_name and base_name in q_text):
                    failing_pod = p.get("name")
                    new_evidence.append({
                        "source": f"k8s:{namespace}/{failing_pod}",
                        "finding": f"Focusing log inspection on {failing_pod} based on incident query.",
                    })
                    break

    # Check 2: Recent cluster events
    if tool_count < max_tool_budget:
        events_resp = _safe_call_tool("get_k8s_events", {"namespace": namespace, "since_minutes": 30}, inv_id)
        tool_count += 1
        events = events_resp.get("events", [])
        warnings = [e for e in events if e.get("type") == "Warning"]
        if warnings:
            top_warn = warnings[0]
            warn_msg = f"Cluster Warning: {top_warn.get('reason')} on {top_warn.get('object')}: {top_warn.get('message')}"
            symptoms.append(warn_msg)
            new_evidence.append({"source": f"k8s:events/{top_warn.get('object')}", "finding": warn_msg})

    # Check 3: Detailed Pod Description (exit code, termination reasons, limits)
    if failing_pod and tool_count < max_tool_budget:
        desc_resp = _safe_call_tool("describe_pod", {"pod": failing_pod, "namespace": namespace}, inv_id)
        tool_count += 1
        containers = desc_resp.get("containers", [])
        if containers:
            c0 = containers[0]
            term = c0.get("last_termination")
            if term:
                term_msg = f"Last termination: Reason={term.get('reason')}, ExitCode={term.get('exit_code')}, Message={term.get('message')}"
                symptoms.append(term_msg)
                new_evidence.append({"source": f"k8s:{failing_pod}/termination", "finding": term_msg})
            waiting = c0.get("current_state", {}).get("reason")
            if waiting:
                symptoms.append(f"Container waiting state: {waiting}")
                new_evidence.append({"source": f"k8s:{failing_pod}/state", "finding": f"Container waiting: {waiting}"})

    # Check 4: Container Logs for the degraded pod
    if failing_pod and tool_count < max_tool_budget:
        logs_resp = _safe_call_tool("get_pod_logs", {"pod": failing_pod, "namespace": namespace, "tail_lines": 50}, inv_id)
        tool_count += 1
        raw_logs = logs_resp.get("logs", "")
        # Extract prominent error lines, neutralizing prompt injection payloads
        for line in raw_logs.splitlines():
            line_lower = line.lower()
            if detect_prompt_injection(line):
                new_evidence.append({
                    "source": f"k8s:{failing_pod}/security",
                    "finding": f"Adversarial prompt injection attempt detected and neutralized in container logs: {line.strip()[:100]}",
                })
                continue
            if any(err_kw in line_lower for err_kw in (
                "error", "exception", "keyerror", "connection refused", "connectionerror",
                "operationalerror", "fatal", "timeout", "critical", "fail"
            )):
                symptoms.append(line.strip())
                new_evidence.append({"source": f"k8s:{failing_pod}/logs", "finding": line.strip()})
                break

    # Check 5: Recent Deployments check
    if tool_count < max_tool_budget:
        dep_resp = _safe_call_tool("get_recent_deployments", {"namespace": namespace}, inv_id)
        tool_count += 1
        deps = dep_resp.get("deployments", [])
        for dep in deps:
            if dep.get("unavailable_replicas", 0) > 0:
                dep_msg = f"Deployment {dep.get('name')} revision {dep.get('revision')} has {dep.get('unavailable_replicas')} unavailable replicas."
                new_evidence.append({"source": f"k8s:deployment/{dep.get('name')}", "finding": dep_msg})

    # Check 6: Hybrid RAG Search over Runbooks & Past Postmortems
    symptom_query = " ".join(symptoms)[:200] or state.get("question", "")
    if tool_count < max_tool_budget:
        rag_resp = _safe_call_tool("search_runbooks", {"query": symptom_query, "top_k": 2}, inv_id)
        tool_count += 1
        results = rag_resp.get("results", [])
        if results:
            top_runbook = results[0]
            new_evidence.append({
                "source": f"rag:{top_runbook.get('source_file')}",
                "finding": f"Matching SRE runbook '{top_runbook.get('source_file')}' section '{top_runbook.get('section')}' (RRF score: {top_runbook.get('score')})",
            })

    # Formulate Hypothesis from Evidence
    evidence_text = " ".join([e["finding"] for e in new_evidence])
    ev_lower = evidence_text.lower()

    if "oomkilled" in ev_lower or "137" in ev_lower or ("exceeded" in ev_lower and "memory" in ev_lower):
        hypothesis = f"Pod {failing_pod or 'service'} was OOMKilled (exit code 137) after exceeding its configured memory limit."
    elif "crashloopbackoff" in ev_lower or "exit_code=1" in ev_lower or "keyerror" in ev_lower:
        hypothesis = f"Pod {failing_pod or 'service'} is crashing on startup in CrashLoopBackOff due to a missing environment variable or configuration error."
    elif "imagepullbackoff" in ev_lower or "errimagepull" in ev_lower or "manifest unknown" in ev_lower:
        hypothesis = f"Pod {failing_pod or 'service'} cannot start due to ImagePullBackOff (invalid or non-existent image tag)."
    elif "could not translate host name" in ev_lower or "operationalerror" in ev_lower or ("bad" in ev_lower and "db_host" in ev_lower):
        hypothesis = f"Service is failing with 500 errors because DB_HOST is invalid or PostgreSQL is unreachable."
    elif ("connection refused" in ev_lower or "connectionerror" in ev_lower) and "redis" in ev_lower:
        hypothesis = "Inventory service is experiencing failures because Redis connection was refused on port 6379."
    elif "readiness probe failed" in ev_lower or "0/1" in ev_lower:
        hypothesis = f"Pod {failing_pod or 'service'} is failing readiness probe checks on /health/ and has been removed from service endpoints."
    elif "timeout" in ev_lower or "504" in ev_lower:
        hypothesis = "Service is returning HTTP 504 Gateway Timeout due to downstream dependency call latency exceeding timeout window."
    elif "throttled" in ev_lower or ("cpu" in ev_lower and "limit" in ev_lower):
        hypothesis = "Service is suffering high latency and throttling due to container CPU limit configuration."
    else:
        hypothesis = f"Service instability detected on {failing_pod or 'target namespace'}; correlating observed events and logs."

    return {
        "evidence": new_evidence,
        "focus_pod": failing_pod,
        "current_hypothesis": hypothesis,
        "tool_call_count": tool_count,
    }
