"""
Ingestion Pipeline for Markdown Runbooks and Incident Reports (Phase 4).

Loads markdown files from `runbooks/`, extracts metadata (tags, service, doc type),
splits into section-level chunks by headings, computes dense embeddings,
and indexes them into the `RunbookChunk` database table.
"""

from pathlib import Path
import re
from typing import Dict, List, Optional

from rag.embeddings import compute_dense_embedding
from rag.models import RunbookChunk

DEFAULT_RUNBOOKS_DIR = Path(__file__).resolve().parent.parent / "runbooks"

COMMON_TAGS = [
    "oom", "oomkilled", "137", "crashloop", "crashloopbackoff", "exit 1",
    "db_host", "database", "postgres", "redis", "connection refused",
    "readiness", "liveness", "probe", "500", "502", "504", "timeout",
    "imagepull", "imagepullbackoff", "secret", "password", "cpu", "throttling",
]


def _extract_tags(text: str) -> List[str]:
    """Identify relevant SRE incident tags from chunk content."""
    lower = text.lower()
    return [tag for tag in COMMON_TAGS if tag in lower]


def _detect_service(text: str, filename: str) -> str:
    """Detect whether a chunk is specific to payments, orders, or inventory."""
    combined = (filename + " " + text).lower()
    for svc in ("payments", "orders", "inventory", "redis", "postgres"):
        if svc in combined:
            return f"{svc}-service" if not svc.endswith("-service") else svc
    return "general"


def chunk_file(file_path: Path) -> List[Dict[str, str]]:
    """Split a Markdown document by heading (# or ##) into clean structured chunks."""
    text = file_path.read_text(encoding="utf-8")
    lines = text.splitlines()

    title = file_path.stem.replace("_", " ").title()
    chunks: List[Dict[str, str]] = []

    current_heading = "Overview"
    current_lines: List[str] = []

    for line in lines:
        if line.startswith("#"):
            if current_lines:
                content = "\n".join(current_lines).strip()
                if content:
                    chunks.append(
                        {
                            "title": title,
                            "section": current_heading,
                            "content": content,
                        }
                    )
            # Use top heading as doc title if available
            if line.startswith("# ") and title == file_path.stem.replace("_", " ").title():
                title = line.lstrip("# ").strip()
            current_heading = line.lstrip("#").strip()
            current_lines = []
        else:
            current_lines.append(line)

    if current_lines:
        content = "\n".join(current_lines).strip()
        if content:
            chunks.append(
                {
                    "title": title,
                    "section": current_heading,
                    "content": content,
                }
            )

    return chunks


def ingest_runbooks_sync(runbooks_dir: Optional[Path] = None) -> int:
    """
    Ingest all markdown runbooks and past incidents into the database.
    Idempotent: clears existing chunks and re-indexes.
    """
    target_dir = Path(runbooks_dir) if runbooks_dir else DEFAULT_RUNBOOKS_DIR
    if not target_dir.exists():
        return 0

    RunbookChunk.objects.all().delete()
    created_count = 0

    for md_file in sorted(target_dir.glob("*.md")):
        doc_type = (
            RunbookChunk.DocType.INCIDENT_REPORT
            if "incident" in md_file.name.lower()
            else RunbookChunk.DocType.RUNBOOK
        )
        file_chunks = chunk_file(md_file)

        for chunk_data in file_chunks:
            full_text = f"{chunk_data['title']} - {chunk_data['section']}\n{chunk_data['content']}"
            tags = _extract_tags(full_text)
            service = _detect_service(full_text, md_file.name)
            embedding = compute_dense_embedding(full_text)

            RunbookChunk.objects.create(
                source_file=md_file.name,
                doc_type=doc_type,
                title=chunk_data["title"],
                section=chunk_data["section"],
                content=chunk_data["content"],
                service=service,
                tags=tags,
                embedding=embedding,
            )
            created_count += 1

    return created_count
