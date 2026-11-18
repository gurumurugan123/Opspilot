"""
Phase 0 Practice: Tool-Calling Agent Loop
Demonstrates how an agent selects a tool, runs it, and interprets output.
"""

import json

# 1. Simulated Tool Registry (mirrors MCP tool endpoints)
def tool_list_pods(namespace: str = "default") -> dict:
    return {
        "namespace": namespace,
        "pods": [
            {"name": "orders-app-7b9c9f4d7b-1", "status": "Running", "restarts": 0},
            {"name": "payments-app-5d6f8f7c9b-1", "status": "CrashLoopBackOff", "restarts": 14},
            {"name": "inventory-app-6c8d7e9f1a-1", "status": "Running", "restarts": 0}
        ]
    }

def tool_get_pod_logs(pod_name: str, tail_lines: int = 10) -> dict:
    if "payments" in pod_name:
        return {
            "pod": pod_name,
            "logs": [
                "2026-11-16 22:15:01 INFO  Starting payment service...",
                "2026-11-16 22:15:02 ERROR Failed to connect to database at db.internal:5432",
                "2026-11-16 22:15:02 ERROR KeyError: 'DB_PASSWORD' environment variable is not set.",
                "2026-11-16 22:15:02 CRITICAL Process terminated with exit code 1"
            ]
        }
    return {"pod": pod_name, "logs": ["Service running normally."]}

AVAILABLE_TOOLS = {
    "list_pods": tool_list_pods,
    "get_pod_logs": tool_get_pod_logs
}

# 2. Agent Reasoning Loop
def run_agent_investigation(incident_query: str):
    print(f"=== Starting Investigation: '{incident_query}' ===")
    
    # Step 1: Agent decides which tool to call first
    print("\n[Agent Decision] Step 1: Inspect pod health across the namespace.")
    pods_result = AVAILABLE_TOOLS["list_pods"](namespace="default")
    print(f"[Tool Call list_pods] Result: {json.dumps(pods_result, indent=2)}")
    
    # Step 2: Agent identifies failing pod
    failing_pod = None
    for pod in pods_result["pods"]:
        if pod["status"] != "Running":
            failing_pod = pod["name"]
            break

    if not failing_pod:
        print("[Agent Conclusion] All pods are running healthy.")
        return

    # Step 3: Agent calls logs for the failing pod
    print(f"\n[Agent Decision] Step 2: Detected '{failing_pod}' in CrashLoopBackOff. Calling get_pod_logs.")
    logs_result = AVAILABLE_TOOLS["get_pod_logs"](pod_name=failing_pod, tail_lines=10)
    print(f"[Tool Call get_pod_logs] Result:\n" + "\n".join(f"  {line}" for line in logs_result["logs"]))
    
    # Step 4: Agent formulates root-cause conclusion
    print("\n[Agent Final Report]")
    print(f"Target Pod: {failing_pod}")
    print("Identified Root Cause: Missing configuration 'DB_PASSWORD' leading to database connection failure.")
    print("Confidence: 98%")
    print("Suggested Fix: Update the Kubernetes Secret or ConfigMap for payments-app with DB_PASSWORD and redeploy.")

if __name__ == "__main__":
    run_agent_investigation("Why is checkout returning HTTP 500?")
