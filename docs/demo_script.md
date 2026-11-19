# OpsPilot: 10-Minute Live Technical Interview Demo Script (Phase 10)

This script provides a step-by-step walkthrough to present **OpsPilot** during technical interviews, portfolio presentations, or live hiring manager demos.

---

## ⏱️ Demo Timeline Overview

| Minute | Stage | Talking Points |
|---|---|---|
| **0:00 – 2:00** | Problem & Architecture Overview | Introduce alert fatigue, MTTR reduction, and the 4-agent LangGraph topology |
| **2:00 – 4:00** | Fault Injection Demonstration | Trigger a realistic failure using the demo microservices |
| **4:00 – 6:30** | Live Dashboard & Real-Time SSE Stream | Show real-time diagnostic tool sweeps and evidence correlation |
| **6:30 – 8:00** | Root Cause Report & HITL Approval | Walk through evidence citations, remediation commands, and human ticket gate |
| **8:00 – 9:00** | Prometheus Metrics & Observability | Show live telemetry and counters on `/api/metrics/` |
| **9:00 – 10:00** | Evaluation Benchmark & CI Validation | Run `eval/run_eval.py` showing 100% diagnostic accuracy across 12 scenarios |

---

## 🎙️ Step-by-Step Presentation Script

### Minute 0:00 – 2:00 | Introduction & Problem Framing
1. **Open the Dashboard:** Open `http://localhost:8000/` in your browser.
2. **Opening Statement:**
   > *"Hi everyone. Today I'm demonstrating **OpsPilot**, an autonomous AI SRE Incident Investigation Agent designed for Kubernetes and Jenkins microservice environments.*  
   > *In production, when a critical service fails, SREs spend 30 to 60 minutes sifting through 10,000+ noisy log lines across multiple pods, checking events, and hunting down runbooks.*  
   > *OpsPilot autonomously executes this entire diagnostic sweep in under 30 seconds, operating strictly in read-only mode with full security guardrails, and presents an evidence-backed root cause report with human-in-the-loop approval."*

---

### Minute 2:00 – 4:00 | Triggering an Incident
1. **Highlight the Quick Presets:** Point to the left panel on the dashboard.
   > *"To demonstrate, we have 6 realistic failure modes in our demo environment: CrashLoopBackOff, OOMKilled exit code 137, ImagePullBackOff, bad database host resolution, Redis connection refused, and Jenkins CI failures.*  
   > *Let's click the **⚡ CrashLoopBackOff** preset for `orders-service`."*
2. **Review the Form:** Notice the query:  
   `"Orders service crashing in CrashLoopBackOff with missing DATABASE_URL."`
3. **Click "Launch AI Investigation":** The button transforms into a spinner, and the status changes to `IN_PROGRESS`.

---

### Minute 4:00 – 6:30 | Live Diagnostic Stream (SSE)
1. **Show the Real-Time Event Stream:**
   > *"Notice the middle timeline updating in real time via Server-Sent Events (SSE). OpsPilot's Celery worker is executing our 4-node LangGraph state machine:*  
   > *1. **Planner Node:** Decides on an ordered diagnostic strategy.*  
   > *2. **Investigator Node:** Communicates with our FastMCP server over standard I/O to sweep pods (`list_pods`), inspect warning events (`get_k8s_events`), and fetch redacted container logs (`get_pod_logs`).*  
   > *3. **Hybrid RAG Query:** It extracts the error symptom and queries our vector store using Reciprocal Rank Fusion ($k=60$) over SRE runbooks (`search_runbooks`).*  
   > *4. **Reviewer Quality Gate:** The Reviewer cross-checks the findings against hard citations before approving the report."*
2. **Point out the MCP Badges:** Mention that each tool call (`list_pods`, `get_k8s_events`, `describe_pod`) displays execution latency in milliseconds and that secrets are redacted automatically.

---

### Minute 6:30 – 8:00 | Verified Root-Cause Diagnosis & Human Gate
1. **Review the Diagnosis Card:**
   > *"The investigation has completed with **95% Reviewer Confidence**.*  
   > *- **Root Cause:** Identifies that `orders-service-1` is in CrashLoopBackOff due to a missing `DATABASE_URL` environment variable.*  
   > *- **Suggested Fix:** Gives the exact copyable remediation command: `Verify required environment variables in Secret/ConfigMap...`*  
   > *- **Evidence Citations:** Shows the exact pod event and container log lines cited by the agent.*  
   > *- **Ruled-Out Causes:** Clarifies that hardware nodes and network interfaces were tested and ruled out.*  
   > *- **Runbooks:** Links to `runbook_crashloopbackoff.md`."*
2. **Demonstrate the Human-in-the-Loop Approval:**
   > *"Under our security model, the agent can NEVER autonomously open external tickets or execute remediation. An on-call engineer must review and approve.*  
   > *I click **'Approve & Create Ticket'** — the backend verifies the report, records an audit log of who approved it and when, and dispatches the incident issue."*

---

### Minute 8:00 – 9:00 | Observability & Prometheus Metrics
1. **Open the Metrics Endpoint:** Open `http://localhost:8000/api/metrics/` in a new tab.
2. **Explain the Telemetry:**
   > *"OpsPilot is instrumented for production observability. Our `/api/metrics/` endpoint exports standard Prometheus exposition format:*  
   > *- `opspilot_investigations_total{status="COMPLETED"}` tracks completed runs.*  
   > *- `opspilot_tool_calls_total` tracks individual tool usage.*  
   > *- `opspilot_ticket_approvals_total` tracks authorized escalations.*  
   > *This allows SRE teams to integrate OpsPilot directly into Grafana and Datadog."*

---

### Minute 9:00 – 10:00 | Benchmark Evaluation Harness & Q&A
1. **Switch to Terminal:** Run:
   ```bash
   python eval/run_eval.py
   ```
2. **Show Benchmark Output:**
   > *"To validate that OpsPilot operates reliably and doesn't hallucinate, we engineered an end-to-end evaluation harness benchmarking 12 diverse Kubernetes and Jenkins incident scenarios.*  
   > *As you can see on the screen, OpsPilot achieved:*  
   > *- **100.0% Diagnostic Accuracy** (Target: $\ge 80\%$)*  
   > *- **100.0% Runbook Citation Rate** (Target: $\ge 80\%$)*  
   > *- **5.7 Average Tool Calls** per incident (Target: $\le 6.0$)*  
   > *The entire system is backed by **62 automated tests** and a single-command `docker compose up -d` deployment.*  
   > *I'd be glad to dive into any architectural questions about LangGraph, our FastMCP protocol, or our Hybrid RAG retrieval engine!"*
