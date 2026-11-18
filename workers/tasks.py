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
    Background worker task: Executes the multi-agent incident investigation loop
    via the compiled LangGraph state machine.
    """
    import django
    django.setup()

    from api.models import Investigation
    from agents.graph import run_investigation_graph

    try:
        inv = Investigation.objects.get(id=investigation_id)
        inv.status = Investigation.Status.IN_PROGRESS
        inv.celery_task_id = getattr(self.request, "id", None) or f"sync-{str(investigation_id)[:8]}"
        inv.current_hypothesis = "Initiating multi-agent LangGraph workflow..."
        inv.save()

        # Run LangGraph multi-agent workflow (Planner -> Investigator -> Reviewer -> Reporter)
        final_state = run_investigation_graph(
            question=inv.query,
            namespace=inv.namespace,
            service_hint=inv.service_hint,
            investigation_id=str(inv.id),
        )

        inv.refresh_from_db()
        return {
            "status": "SUCCESS",
            "investigation_id": investigation_id,
            "confidence": final_state.get("confidence", 0.0),
        }

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
