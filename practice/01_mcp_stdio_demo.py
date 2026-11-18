"""
Phase 0 Practice: Hello-World MCP Stdio Server & Client
Demonstrates the exact JSON-RPC 2.0 wire protocol used by Model Context Protocol (MCP).
"""

import sys
import json
import subprocess

# --- 1. MCP Server Implementation ---
def run_server():
    """Reads JSON-RPC requests from stdin and writes responses to stdout."""
    tools = [
        {
            "name": "check_service_health",
            "description": "Check if a service in Kubernetes is healthy.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "service_name": {"type": "string"}
                },
                "required": ["service_name"]
            }
        },
        {
            "name": "get_pod_status",
            "description": "Get pod status and restart count.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "pod_name": {"type": "string"}
                },
                "required": ["pod_name"]
            }
        }
    ]

    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            req = json.loads(line)
            req_id = req.get("id")
            method = req.get("method")
            params = req.get("params", {})

            if method == "tools/list":
                res = {"jsonrpc": "2.0", "id": req_id, "result": {"tools": tools}}
            elif method == "tools/call":
                tool_name = params.get("name")
                args = params.get("arguments", {})
                
                if tool_name == "check_service_health":
                    svc = args.get("service_name")
                    status = "DOWN (500)" if svc == "payments" else "UP (200)"
                    res = {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "result": {"content": [{"type": "text", "text": f"Service '{svc}' status: {status}"}]}
                    }
                elif tool_name == "get_pod_status":
                    pod = args.get("pod_name")
                    res = {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "result": {
                            "content": [{
                                "type": "text",
                                "text": json.dumps({"pod": pod, "phase": "CrashLoopBackOff", "restarts": 7})
                            }]
                        }
                    }
                else:
                    res = {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": f"Tool '{tool_name}' not found"}}
            else:
                res = {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": f"Method '{method}' not found"}}

            sys.stdout.write(json.dumps(res) + "\n")
            sys.stdout.flush()
        except Exception as e:
            err = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": str(e)}}
            sys.stdout.write(json.dumps(err) + "\n")
            sys.stdout.flush()

# --- 2. MCP Client Implementation ---
def run_client():
    print("=== Phase 0: Testing MCP Server & Client ===")
    server_process = subprocess.Popen(
        [sys.executable, __file__, "--server"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    def send_request(req):
        server_process.stdin.write(json.dumps(req) + "\n")
        server_process.stdin.flush()
        raw_resp = server_process.stdout.readline()
        return json.loads(raw_resp)

    # 1. Discover tools
    print("\n1. Calling 'tools/list'...")
    list_resp = send_request({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    print(f"Available MCP Tools ({len(list_resp['result']['tools'])}):")
    for tool in list_resp["result"]["tools"]:
        print(f"  - {tool['name']}: {tool['description']}")

    # 2. Invoke tool 'get_pod_status'
    print("\n2. Calling 'tools/call' for 'get_pod_status'...")
    call_resp = send_request({
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/call",
        "params": {
            "name": "get_pod_status",
            "arguments": {"pod_name": "payments-pod-99x"}
        }
    })
    print(f"MCP Response: {call_resp['result']['content'][0]['text']}")

    server_process.terminate()
    print("\nDone When Check: MCP server called by client and returned result successfully!")

if __name__ == "__main__":
    if "--server" in sys.argv:
        run_server()
    else:
        run_client()
