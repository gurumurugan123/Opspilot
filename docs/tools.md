# OpsPilot MCP Tool Reference (Phase 2)

OpsPilot exposes **9 strictly read-only SRE diagnostic tools** through the Model Context Protocol (`mcp_server/server.py`).

No write, delete, or mutation tools exist anywhere in the MCP server.

---

## Tool Reference Table

| Tool Name | Category | Arguments | Purpose | Safety Processing |
| :--- | :--- | :--- | :--- | :--- |
| `list_pods` | Kubernetes | `namespace: str = "opspilot-demo"` | Lists pods with detailed status (`Running`, `CrashLoopBackOff`, `OOMKilled`, `Pending`), readiness (`0/1`), restarts, and age. | Read-only K8s RBAC + `redact_data` |
| `get_pod_logs` | Kubernetes | `pod: str`, `namespace: str`, `tail_lines: int = 100`, `since_minutes: int = 30` | Retrieves recent container logs for a specific pod. | `redact_text` $\to$ `truncate_logs` $\to$ `<untrusted_log>` wrapper |
| `describe_pod` | Kubernetes | `pod: str`, `namespace: str` | Returns waiting/terminated states, last termination reason & exit code (e.g., `137` for `OOMKilled`), CPU/memory requests & limits, and pod conditions. | Read-only K8s RBAC + `redact_data` |
| `get_k8s_events` | Kubernetes | `namespace: str`, `since_minutes: int = 30` | Fetches recent Warning and Normal Kubernetes events (e.g., `BackOff`, `FailedScheduling`, `Unhealthy`), sorted with Warnings first. | Read-only K8s RBAC + `redact_data` |
| `get_recent_deployments` | Kubernetes | `namespace: str` | Returns deployment rollout revision, active container images, desired vs. ready replicas, and rollout status conditions. | Read-only K8s RBAC + `redact_data` |
| `get_jenkins_builds` | Jenkins | `job: str`, `limit: int = 5` | Lists recent CI/CD build numbers, results (`SUCCESS`, `FAILURE`, `IN_PROGRESS`), duration, and timestamps. | HTTP `GET` only + `redact_data` |
| `get_jenkins_build_log` | Jenkins | `job: str`, `build_number: int` | Fetches console output for a specific build to inspect failing tests or Docker build errors. | `redact_text` $\to$ `truncate_logs` $\to$ `<untrusted_log>` wrapper |
| `get_build_changes` | Jenkins | `job: str`, `build_number: int` | Extracts Git commit IDs, authors, commit messages, and modified file paths included in a build. | HTTP `GET` only + `redact_data` |
| `search_runbooks` | Knowledge Base | `query: str`, `top_k: int = 3` | Searches internal SRE runbooks and past incident reports, returning ranked sections with source file citations. *(Upgrades to pgvector Hybrid RAG in Phase 4).* | Read-only + `redact_data` |

---

## Security & Reliability Layers

1. **Redaction (`mcp_server/redaction.py`):**  
   Scrubs database URL passwords, `Bearer`/`Basic` tokens, JWTs, API keys (`sk-...`, `ghp_...`, `AKIA...`), `password=`/`secret_key=` pairs, email addresses, and IPv4 addresses **before** any text reaches the LLM.
2. **Smart Log Truncation (`mcp_server/log_utils.py`):**  
   Protects token budgets by returning the last $N$ lines while scanning earlier lines for `ERROR`, `Exception`, `Traceback`, `FATAL`, `OOMKilled`, `OperationalError`, and `Connection refused` so critical failures are never clipped out.
3. **Prompt-Injection Defense (`wrap_untrusted_log`):**  
   Wraps external container and Jenkins logs in `<untrusted_log source="...">...</untrusted_log>` tags so the agent treats log output strictly as untrusted data.

---

## Running & Testing

```bash
# Run all 17 unit & end-to-end MCP stdio tests
.\.venv\Scripts\python.exe -m unittest discover -s tests -v

# Start the MCP server directly over stdio
.\.venv\Scripts\python.exe -m mcp_server.server
```
