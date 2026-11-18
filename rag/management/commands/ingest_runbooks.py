"""
Django Management Command: Ingest runbooks and incident reports into RAG database.

Usage:
  python manage.py ingest_runbooks
"""

from django.core.management.base import BaseCommand
from rag.ingest import ingest_runbooks_sync


class Command(BaseCommand):
    help = "Ingest markdown runbooks and past incident reports into RAG database"

    def add_arguments(self, parser):
        parser.add_argument("--dir", type=str, default=None, help="Custom runbooks directory")

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("Ingesting runbooks and past incident reports..."))
        count = ingest_runbooks_sync(runbooks_dir=options.get("dir"))
        self.stdout.write(self.style.SUCCESS(f"Successfully ingested and indexed {count} runbook chunks!"))
