"""
Phase 0 Practice: Hello-World MCP Server
Demonstrates how Model Context Protocol (MCP) exposes tools to AI agents.
"""

from mcp.server.fastmcp import FastMCP

# Initialize FastMCP Server named "OpsPilot-Hello"
mcp = FastMCP("OpsPilot-Hello")

@mcp.tool()
def check_health(service_name: str) -> str:
    """Check the operational health of a specified service."""
    mock_status = {
        "payment-service": "DOWN - HTTP 500 internal server error",
        "order-service": "UP - Operational",
        "inventory-service": "UP - Operational"
    }
    return mock_status.get(service_name.lower(), f"UNKNOWN - Service '{service_name}' not found")

@mcp.tool()
def get_pod_restarts(namespace: str, pod_name: str) -> dict:
    """Retrieve restart count and status for a Kubernetes pod."""
    return {
        "namespace": namespace,
        "pod": pod_name,
        "restart_count": 5,
        "status": "CrashLoopBackOff",
        "last_exit_code": 1
    }

if __name__ == "__main__":
    # Runs the MCP server over standard input/output (stdio)
    mcp.run(transport="stdio")
