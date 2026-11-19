"""
URL Routing for OpsPilot Core Backend (Phase 3).
"""

from django.contrib import admin
from django.urls import path
from api.views import (
    alerts_webhook,
    approve_ticket,
    dashboard_view,
    investigation_detail,
    investigation_stream,
    investigations_collection,
    metrics_view,
    submit_feedback,
)

urlpatterns = [
    # SRE Incident Dashboard Web UI (Phase 8)
    path("", dashboard_view, name="dashboard"),
    path("dashboard/", dashboard_view, name="dashboard-alt"),
    # Prometheus Metrics Exposition
    path("api/metrics/", metrics_view, name="metrics"),
    path("admin/", admin.site.urls),
    # Investigations API
    path("api/investigations/", investigations_collection, name="investigations-collection"),
    path("api/investigations/<uuid:pk>/", investigation_detail, name="investigation-detail"),
    path("api/investigations/<uuid:pk>/stream/", investigation_stream, name="investigation-stream"),
    path("api/investigations/<uuid:pk>/approve-ticket/", approve_ticket, name="approve-ticket"),
    path("api/investigations/<uuid:pk>/feedback/", submit_feedback, name="submit-feedback"),
    # Alertmanager webhook endpoint
    path("api/alerts/webhook/", alerts_webhook, name="alerts-webhook"),
]
