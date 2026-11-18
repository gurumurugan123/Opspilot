"""
Runbook and Past Incident Search Tool for OpsPilot MCP Server (Phase 4).

Connects to the Hybrid RAG engine (Dense Vector + Keyword Search with RRF)
when Django models are available, with seamless fallback to direct markdown
parsing when run in standalone mode.
"""

import os
from pathlib import Path
import re
from typing import Any, Dict, List, Optional

from mcp_server.redaction import redact_data

DEFAULT_RUNBOOKS_DIR = Path(__file__).resolve().parent.parent.parent / "runbooks"
TOKEN_RE = re.compile(r"[a-z0-9_-]+")


def _ensure_django() -> bool:
    """Ensure Django app registry is loaded if Django is available."""
    try:
        import django
        os.environ.setdefault("DJANGO_SETTINGS_MODULE", "api.settings")
        django.setup()
        return True
    except Exception:
        return False


def _chunk_markdown_file(file_path: Path) -> List[Dict[str, str]]:
    """Standalone markdown chunker with zero external dependencies."""
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
                    chunks.append({"title": title, "section": current_heading, "content": content})
            if line.startswith("# ") and title == file_path.stem.replace("_", " ").title():
                title = line.lstrip("# ").strip()
            current_heading = line.lstrip("#").strip()
            current_lines = []
        else:
            current_lines.append(line)

    if current_lines:
        content = "\n".join(current_lines).strip()
        if content:
            chunks.append({"title": title, "section": current_heading, "content": content})

    return chunks


def search_runbooks(
    query: str,
    top_k: int = 3,
    runbooks_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Search markdown runbooks and past incident reports for troubleshooting steps
    and similar historical outages. Returns ranked sections with file citations.
    """
    if _ensure_django():
        try:
            from rag.retrieval import hybrid_search
            return hybrid_search(query=query, top_k=top_k)
        except Exception:
            pass

    # Fallback to direct markdown search for standalone environments
    kb_dir = Path(runbooks_dir) if runbooks_dir else DEFAULT_RUNBOOKS_DIR
    if not kb_dir.exists():
        return {"query": query, "result_count": 0, "results": []}

    query_tokens = set(TOKEN_RE.findall(query.lower()))
    if not query_tokens:
        return {"query": query, "result_count": 0, "results": []}

    scored = []
    for md_file in sorted(kb_dir.glob("*.md")):
        for chunk in _chunk_markdown_file(md_file):
            haystack = f"{chunk['title']} {chunk['section']} {chunk['content']}".lower()
            matches = sum(1 for tok in query_tokens if tok in haystack)
            if matches > 0:
                scored.append(
                    {
                        "source_file": md_file.name,
                        "doc_type": "Incident Report" if "incident" in md_file.name else "Runbook",
                        "title": chunk["title"],
                        "section": chunk["section"],
                        "score": round(matches / max(len(query_tokens), 1), 4),
                        "content": chunk["content"],
                    }
                )

    scored.sort(key=lambda r: r["score"], reverse=True)
    top_results = scored[: max(1, min(int(top_k), 10))]

    return redact_data(
        {
            "query": query,
            "retrieval_mode": "fallback_markdown_search",
            "result_count": len(top_results),
            "results": top_results,
        }
    )
