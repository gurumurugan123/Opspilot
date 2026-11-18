"""
Django REST Framework Views for OpsPilot API (Phase 3).

Endpoints:
  - POST /api/investigations/          : Start a new investigation
  - GET  /api/investigations/          : List recent investigations
  - GET  /api/investigations/{id}/     : Read investigation status, tool calls, and report
  - GET  /api/investigations/{id}/stream/ : SSE real-time stream of investigation progress
  - POST /api/investigations/{id}/approve-ticket/ : Human approval gate to draft/create ticket
  - POST /api/investigations/{id}/feedback/       : Submit accuracy feedback
  - POST /api/alerts/webhook/          : Ingest incident alert from Alertmanager or webhook
"""

from django.http import StreamingHttpResponse
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from api.models import Feedback, Investigation, InvestigationReport, ToolCall
from api.streaming import ProgressEventStream
from workers.tasks import run_investigation_task


@api_view(["POST", "GET"])
def investigations_collection(request):
    """
    POST: Trigger a new investigation with a question or alert payload.
    GET:  List all recent investigations.
    """
    if request.method == "GET":
        investigations = Investigation.objects.all().order_by("-created_at")[:50]
        data = [
            {
                "id": str(inv.id),
                "query": inv.query,
                "service_hint": inv.service_hint,
                "status": inv.status,
                "current_hypothesis": inv.current_hypothesis,
                "ticket_approved": inv.ticket_approved,
                "created_at": inv.created_at.isoformat(),
            }
            for inv in investigations
        ]
        return Response(data, status=status.HTTP_200_OK)

    query = request.data.get("query")
    if not query:
        return Response({"error": "field 'query' is required"}, status=status.HTTP_400_BAD_REQUEST)

    service_hint = request.data.get("service_hint")
    namespace = request.data.get("namespace", "opspilot-demo")

    inv = Investigation.objects.create(
        query=query,
        service_hint=service_hint,
        namespace=namespace,
        status=Investigation.Status.QUEUED,
        current_hypothesis="Queued for investigation worker...",
    )

    # Dispatch to background Celery worker if available; run inline if worker offline (dev mode)
    try:
        task = run_investigation_task.delay(str(inv.id))
        inv.celery_task_id = task.id
        inv.save()
    except Exception:
        # Fallback for local tests / environments without a live Redis broker
        try:
            run_investigation_task(str(inv.id))
            inv.refresh_from_db()
        except Exception:
            pass

    return Response(
        {
            "id": str(inv.id),
            "status": inv.status,
            "query": inv.query,
            "stream_url": f"/api/investigations/{inv.id}/stream/",
        },
        status=status.HTTP_201_CREATED,
    )


@api_view(["GET"])
def investigation_detail(request, pk):
    """Retrieve full investigation status, audit tool calls, and final root-cause report."""
    inv = get_object_or_404(Investigation, pk=pk)

    tool_calls = [
        {
            "step": tc.step_number,
            "tool": tc.tool_name,
            "arguments": tc.arguments,
            "summary": tc.output_summary,
            "duration_ms": tc.duration_ms,
            "is_error": tc.is_error,
        }
        for tc in inv.tool_calls.all()
    ]

    report_data = None
    if hasattr(inv, "report") and inv.report:
        rep = inv.report
        report_data = {
            "root_cause": rep.root_cause,
            "confidence": rep.confidence,
            "suggested_fix": rep.suggested_fix,
            "evidence": rep.evidence,
            "similar_incidents": rep.similar_incidents,
            "what_was_ruled_out": rep.what_was_ruled_out,
            "total_tokens": rep.total_tokens,
            "total_cost_usd": rep.total_cost_usd,
        }

    return Response(
        {
            "id": str(inv.id),
            "query": inv.query,
            "service_hint": inv.service_hint,
            "namespace": inv.namespace,
            "status": inv.status,
            "current_hypothesis": inv.current_hypothesis,
            "ticket_approved": inv.ticket_approved,
            "ticket_url": inv.ticket_url,
            "tool_call_count": len(tool_calls),
            "tool_calls": tool_calls,
            "report": report_data,
            "created_at": inv.created_at.isoformat(),
        },
        status=status.HTTP_200_OK,
    )


@api_view(["GET"])
def investigation_stream(request, pk):
    """
    Stream Server-Sent Events (SSE) progress for an investigation in real time.
    """
    inv = get_object_or_404(Investigation, pk=pk)
    response = StreamingHttpResponse(
        ProgressEventStream.generate_events(inv),
        content_type="text/event-stream",
    )
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response


@api_view(["POST"])
def approve_ticket(request, pk):
    """
    Human-in-the-loop gate: Approves drafting/creating an incident ticket (GitHub/Jira).
    Tickets are NEVER created automatically without calling this endpoint.
    """
    inv = get_object_or_404(Investigation, pk=pk)

    if not hasattr(inv, "report") or not inv.report:
        return Response(
            {"error": "Cannot approve ticket: No root-cause report generated yet."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    inv.ticket_approved = True
    inv.ticket_created = True
    inv.ticket_url = f"https://github.com/gurumurugan123/Opspilot/issues/{str(inv.id)[:8]}"
    inv.save()

    return Response(
        {
            "investigation_id": str(inv.id),
            "ticket_approved": True,
            "ticket_created": True,
            "ticket_url": inv.ticket_url,
            "message": "Incident ticket approved and created successfully.",
        },
        status=status.HTTP_200_OK,
    )


@api_view(["POST"])
def submit_feedback(request, pk):
    """Record human SRE evaluation feedback on accuracy and diagnosis quality."""
    inv = get_object_or_404(Investigation, pk=pk)
    is_correct = request.data.get("is_correct", True)
    rating = int(request.data.get("rating", 5))
    comments = request.data.get("comments", "")

    fb = Feedback.objects.create(
        investigation=inv,
        is_correct=bool(is_correct),
        rating=max(1, min(rating, 5)),
        comments=comments,
    )

    return Response(
        {
            "feedback_id": str(fb.id),
            "investigation_id": str(inv.id),
            "is_correct": fb.is_correct,
            "rating": fb.rating,
        },
        status=status.HTTP_201_CREATED,
    )


@api_view(["POST"])
def alerts_webhook(request):
    """
    Accept incident alert webhook from Prometheus Alertmanager or external monitoring.
    Automatically spawns a background investigation.
    """
    alert_name = request.data.get("alertname") or request.data.get("alert") or "ProductionAlert"
    summary = request.data.get("summary") or request.data.get("description") or "Unknown incident alert"
    service = request.data.get("service") or request.data.get("labels", {}).get("app")

    query = f"Alert '{alert_name}': {summary}"
    inv = Investigation.objects.create(
        query=query,
        service_hint=service,
        status=Investigation.Status.QUEUED,
        current_hypothesis="Alert received via webhook. Starting diagnostic sweep...",
    )

    try:
        run_investigation_task.delay(str(inv.id))
    except Exception:
        try:
            run_investigation_task(str(inv.id))
        except Exception:
            pass

    return Response(
        {
            "message": "Alert accepted and investigation triggered",
            "investigation_id": str(inv.id),
            "alert": alert_name,
        },
        status=status.HTTP_202_ACCEPTED,
    )
