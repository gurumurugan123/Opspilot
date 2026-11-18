# OpsPilot 🚀
> **AI-Powered Incident Investigation for Kubernetes and Jenkins**  
> *Built with Django, Django REST Framework, LangGraph, Model Context Protocol (MCP), and Hybrid RAG*

OpsPilot investigates production incidents the way a junior SRE would. When an alert fires or a service begins failing, OpsPilot autonomously collects evidence across Kubernetes clusters and Jenkins CI/CD builds, performs hybrid RAG searches over runbooks and past incidents, synthesizes findings into a root-cause report, and drafts tickets for human review.

---

## ⚡ Key Highlights
* **Strictly Read-Only:** Safe by design. Inspects logs, events, and deployment rollouts; never applies changes without human approval.
* **Production Django Stack:** Built using Django, Django REST Framework, Celery, PostgreSQL (pgvector), and Redis.
* **Multi-Agent Orchestration:** Driven by LangGraph state machine (`Planner` → `Investigator` → `Reviewer` → `Reporter`).
* **MCP-Native Tools:** Kubernetes and Jenkins APIs exposed via the Model Context Protocol (Python SDK) with automated secret & PII redaction.
* **Hybrid RAG:** Vector search (pgvector) + PostgreSQL full-text keyword search merged via Reciprocal Rank Fusion (RRF).
* **Measurable Quality:** Benchmarked against 15–20 fault scenarios with automated evaluation comparing against a single-prompt LLM baseline.

---

## 📁 Repository Structure
```text
opspilot/
├── demo-env/        # Local mock infrastructure (Django microservices, k8s manifests, Jenkins, fault injection)
├── mcp_server/      # Read-only MCP tool server (Kubernetes, Jenkins, Runbooks, Redaction)
├── agents/          # LangGraph multi-agent workflows and prompts
├── api/             # Django / DRF backend with streaming investigation progress
├── workers/         # Celery async task workers (investigations & document ingestion)
├── rag/             # Chunking, pgvector embedding, and hybrid retrieval
├── runbooks/        # Runbooks and past incident reports (knowledge base)
├── eval/            # Automated evaluation harness and scenarios
├── deploy/          # Dockerfiles, docker-compose, and k8s deployment manifests
├── docs/            # Architecture diagrams, security design, and benchmarks
└── tests/           # Unit and integration test suites
```

---

## 🛠️ Quick Start (Development)
```bash
# 1. Activate virtual environment
.\.venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment
cp .env.example .env
```
