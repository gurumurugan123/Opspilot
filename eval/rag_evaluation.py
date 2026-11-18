"""
Phase 4 Evaluation Harness: Hybrid RAG Retrieval Benchmark (20 Questions).

Measures:
  - Top-1 Hit Rate
  - Top-3 Hit Rate (Goal: >= 80% to satisfy Phase 4 Done-When criteria)
  - Mean Reciprocal Rank (MRR)
"""

import os
import sys
from pathlib import Path

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Ensure Django environment is configured
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "api.settings")
import django
django.setup()

from rag.ingest import ingest_runbooks_sync
from rag.retrieval import hybrid_search

# 20 Realistic Production Incident Questions with Ground Truth Target Runbooks/Reports
RAG_TEST_CASES = [
    {
        "question": "Pod payments-service keeps crashing on startup with exit code 1 and KeyError.",
        "expected": ["runbook_crashloopbackoff.md"],
    },
    {
        "question": "Container terminated with Reason: OOMKilled and exit code 137.",
        "expected": ["runbook_oomkilled.md", "incident_report_002_oom_spike.md"],
    },
    {
        "question": "Why is pod stuck in ImagePullBackOff with manifest unknown error?",
        "expected": ["runbook_imagepullbackoff.md", "incident_report_003_bad_image_tag.md"],
    },
    {
        "question": "Django logs show OperationalError: could not translate host name for postgres.",
        "expected": ["runbook_bad_db_host.md", "incident_report_001_db_failure.md"],
    },
    {
        "question": "Readiness probe failed HTTP probe failed with statuscode 500 on health endpoint.",
        "expected": ["runbook_readiness_probe.md"],
    },
    {
        "question": "redis.exceptions.ConnectionError Error 111 connecting to redis Connection refused.",
        "expected": ["runbook_redis_connection.md"],
    },
    {
        "question": "Orders service getting requests.exceptions.ReadTimeout calling downstream payments.",
        "expected": ["runbook_downstream_timeout.md"],
    },
    {
        "question": "High response latency with elevated container_cpu_cfs_throttled_periods_total.",
        "expected": ["runbook_cpu_throttling.md"],
    },
    {
        "question": "What caused the historical outage INC-2026-001 in payments service?",
        "expected": ["incident_report_001_db_failure.md"],
    },
    {
        "question": "Tell me about incident INC-2026-002 where payments restarted 8 times.",
        "expected": ["incident_report_002_oom_spike.md"],
    },
    {
        "question": "What happened during incident INC-2026-003 after Jenkins build 48?",
        "expected": ["incident_report_003_bad_image_tag.md"],
    },
    {
        "question": "Missing DB_PASSWORD secret in configmap causing CrashLoopBackOff.",
        "expected": ["runbook_crashloopbackoff.md"],
    },
    {
        "question": "How do I fix container exceeded memory limit and raise limits.memory to 512Mi?",
        "expected": ["runbook_oomkilled.md", "incident_report_002_oom_spike.md"],
    },
    {
        "question": "Non-existent image tag deployed by CI/CD pipeline causing rollout to fail.",
        "expected": ["runbook_imagepullbackoff.md", "incident_report_003_bad_image_tag.md"],
    },
    {
        "question": "Postgres database connection pool refused port 5432 bad DB_HOST.",
        "expected": ["runbook_bad_db_host.md", "incident_report_001_db_failure.md"],
    },
    {
        "question": "Pod status is Running but Ready column is 0/1 not receiving user traffic.",
        "expected": ["runbook_readiness_probe.md"],
    },
    {
        "question": "DOWNSTREAM_TIMEOUT set to 0.001 causing gateway timeout 504 on orders.",
        "expected": ["runbook_downstream_timeout.md"],
    },
    {
        "question": "CPU limit too low 50m causing request queuing and slow execution.",
        "expected": ["runbook_cpu_throttling.md"],
    },
    {
        "question": "REDIS_HOST pointing to invalid hostname in inventory configmap.",
        "expected": ["runbook_redis_connection.md"],
    },
    {
        "question": "How to rollback deployment when new release causes CrashLoopBackOff or bad tag?",
        "expected": ["runbook_crashloopbackoff.md", "runbook_imagepullbackoff.md", "incident_report_003_bad_image_tag.md"],
    },
]


def run_benchmark():
    # Guarantee fresh indexing
    ingest_runbooks_sync()

    total_queries = len(RAG_TEST_CASES)
    top1_hits = 0
    top3_hits = 0
    reciprocal_ranks = []

    print("=" * 80)
    print(f"OpsPilot Phase 4 Evaluation: Evaluating Hybrid RAG on {total_queries} Test Queries")
    print("=" * 80)

    for idx, test in enumerate(RAG_TEST_CASES, start=1):
        q = test["question"]
        expected = test["expected"]

        res = hybrid_search(query=q, top_k=3)
        retrieved_files = [r["source_file"] for r in res.get("results", [])]

        # Check rankings
        hit_rank = 0
        for rank, filename in enumerate(retrieved_files, start=1):
            if filename in expected:
                hit_rank = rank
                break

        if hit_rank == 1:
            top1_hits += 1
            top3_hits += 1
            reciprocal_ranks.append(1.0)
            status_str = "PASS (Top-1)"
        elif 1 < hit_rank <= 3:
            top3_hits += 1
            reciprocal_ranks.append(1.0 / hit_rank)
            status_str = f"PASS (Top-{hit_rank})"
        else:
            reciprocal_ranks.append(0.0)
            status_str = "FAIL (Not in Top-3)"

        print(f"[{idx:02d}/20] {status_str}: '{q[:50]}...' -> Retrieved: {retrieved_files}")

    top1_rate = (top1_hits / total_queries) * 100.0
    top3_rate = (top3_hits / total_queries) * 100.0
    mrr = sum(reciprocal_ranks) / total_queries

    print("\n" + "=" * 80)
    print("OPSPILOT PHASE 4 HYBRID RAG BENCHMARK RESULTS")
    print("=" * 80)
    print(f"Total Test Cases      : {total_queries}")
    print(f"Top-1 Hit Rate        : {top1_rate:.1f}% ({top1_hits}/{total_queries})")
    print(f"Top-3 Hit Rate        : {top3_rate:.1f}% ({top3_hits}/{total_queries})")
    print(f"Mean Reciprocal Rank  : {mrr:.3f}")
    print("=" * 80)

    # Done-when criterion: top-3 hit rate >= 80%
    if top3_rate >= 80.0:
        print(f"[SUCCESS] Top-3 hit rate {top3_rate:.1f}% exceeds required threshold of 80.0%!")
        return True
    else:
        print(f"[FAILED] Top-3 hit rate {top3_rate:.1f}% is below required threshold of 80.0%.")
        return False


if __name__ == "__main__":
    success = run_benchmark()
    sys.exit(0 if success else 1)
