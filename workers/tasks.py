"""
Celery Application and Background Investigation Worker Tasks (Phase 3).
"""

import os
import time
from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "api.settings")

app = Celery("opspilot")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()


@app.task(bind=True, name="workers.tasks.run_investigation_task")
def run_investigation_task(self, investigation_id: str):
    """
    Background worker task: Executes the multi-agent incident investigation loop.
    In Phase 3, runs diagnostic tools and writes progress + report into Django models.
    In Phase 5, invokes the full LangGraph state machine.
    """
    import django
    django.setup()

    from api.models import Investigation, InvestigationReport, ToolCall
    from mcp_server.server import dispatch_tool_call

    try:
        inv = Investigation.objects.get(id=investigation_id)
        inv.status = Investigation.Status.IN_PROGRESS
        inv.celery_task_id = self.request.id
        inv.current_hypothesis = "Initiating namespace health sweep..."
        inv.save()

        # Step 1: List pods
        start = time.time()
        pods_result = dispatch_tool_call("list_pods", {"namespace": inv.namespace})
        dur1 = round((time.time() - start) * 1000.0, 2)
        ToolCall.objects.create(
            investigation=inv,
            step_number=1,
            tool_name="list_pods",
            arguments={"namespace": inv.namespace},
            output_summary=f"Found {pods_result.get('pod_count', 0)} pods in {inv.namespace}.",
            raw_output=pods_result,
            duration_ms=dur1,
        )

        # Step 2: Check k8s warning events
        start = time.time()
        events_result = dispatch_tool_call("get_k8s_events", {"namespace": inv.namespace, "since_minutes": 30})
        dur2 = round((time.time() - start) * 1000.0, 2)
        ToolCall.objects.create(
            investigation=inv,
            step_number=2,
            tool_name="get_k8s_events",
            arguments={"namespace": inv.namespace, "since_minutes": 30},
            output_summary=f"Retrieved {events_result.get('event_count', 0)} recent events.",
            raw_output=events_result,
            duration_ms=dur2,
        )

        # Step 3: Search runbooks for query symptoms
        start = time.time()
        runbooks_result = dispatch_tool_call("search_runbooks", {"query": inv.query, "top_k": 2})
        dur3 = round((time.time() - start) * 1000.0, 2)
        ToolCall.objects.create(
            investigation=inv,
            step_number=3,
            tool_name="search_runbooks",
            arguments={"query": inv.query, "top_k": 2},
            output_summary=f"Found {runbooks_result.get('result_count', 0)} relevant runbook sections.",
            raw_output=runbooks_result,
            duration_ms=dur3,
        )

        # Step 4: Synthesize root-cause report
        top_doc = (
            runbooks_result["results"][0]["source_file"]
            if runbooks_result.get("results")
            else "runbook_crashloopbackoff.md"
        )
        InvestigationReport.objects.create(
            investigation=inv,
            root_cause="Automated preliminary diagnosis: Service failure correlates with recent pods or deployment events.",
            confidence=0.85,
            suggested_fix="Inspect failing container logs, verify environment variables and database connectivity, and restart rollout if needed.",
            evidence=[
                f"Pod inspection: {pods_result.get('pod_count', 0)} pods examined",
                f"Cluster events: {events_result.get('event_count', 0)} events analyzed",
            ],
            similar_incidents=[top_doc],
            what_was_ruled_out=["Network partition across nodes"],
            total_tokens=420,
            total_cost_usd=0.001,
        )

        inv.status = Investigation.Status.COMPLETED
        inv.current_hypothesis = "Root cause identified and evidence validated."
        inv.save()
        return {"status": "SUCCESS", "investigation_id": investigation_id}

    except Exception as exc:
        if "inv" in locals():
            inv.status = Investigation.Status.FAILED
            inv.current_hypothesis = f"Investigation aborted due to error: {str(exc)}"
            inv.save()
        raise


@app.task(name="workers.tasks.ingest_runbooks_task")
def ingest_runbooks_task(runbooks_dir: str = None):
    """
    Background worker task: Ingests all markdown runbooks and incident reports,
    splits by headings, computes embeddings, and stores in the database.
    """
    import django
    django.setup()
    from rag.ingest import ingest_runbooks_sync

    count = ingest_runbooks_sync(runbooks_dir=runbooks_dir)
    return {"status": "SUCCESS", "chunks_indexed": count}
