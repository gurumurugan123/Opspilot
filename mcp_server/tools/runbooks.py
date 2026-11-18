"""
Runbook and Past Incident Search Tool for OpsPilot MCP Server.

Phase 2 provides a clean section-level keyword search directly over `runbooks/*.md`.
In Phase 4, this tool upgrades seamlessly to Hybrid RAG (pgvector + PostgreSQL full-text RRF)
while preserving the exact same MCP tool name, arguments, and citation output schema.
"""

import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from mcp_server.redaction import redact_data

DEFAULT_RUNBOOKS_DIR = Path(__file__).resolve().parent.parent.parent / "runbooks"
TOKEN_RE = re.compile(r"[a-z0-9_]+")
STOPWORDS = {
    "the", "is", "in", "at", "of", "on", "to", "a", "an", "and", "or",
    "for", "with", "how", "why", "what", "are", "was", "be", "by", "from",
}


def _tokenize(text: str) -> List[str]:
    return [t for t in TOKEN_RE.findall(text.lower()) if len(t) > 1 and t not in STOPWORDS]


def _chunk_markdown_by_heading(file_path: Path) -> List[Dict[str, str]]:
    """Split a Markdown file into heading-based chunks with source file and section titles."""
    text = file_path.read_text(encoding="utf-8")
    chunks: List[Dict[str, str]] = []
    current_heading = file_path.stem
    current_lines: List[str] = []

    for line in text.splitlines():
        if line.startswith("#"):
            if current_lines:
                content = "\n".join(current_lines).strip()
                if content:
                    chunks.append(
                        {
                            "source_file": file_path.name,
                            "section": current_heading,
                            "content": content,
                        }
                    )
            current_heading = line.lstrip("#").strip()
            current_lines = []
        else:
            current_lines.append(line)

    if current_lines:
        content = "\n".join(current_lines).strip()
        if content:
            chunks.append(
                {
                    "source_file": file_path.name,
                    "section": current_heading,
                    "content": content,
                }
            )
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
    kb_dir = Path(runbooks_dir) if runbooks_dir else DEFAULT_RUNBOOKS_DIR
    if not kb_dir.exists():
        return {"query": query, "result_count": 0, "results": []}

    query_tokens = set(_tokenize(query))
    if not query_tokens:
        return {"query": query, "result_count": 0, "results": []}

    scored: List[Dict[str, Any]] = []
    for md_file in sorted(kb_dir.glob("*.md")):
        for chunk in _chunk_markdown_by_heading(md_file):
            haystack_tokens = _tokenize(f"{chunk['source_file']} {chunk['section']} {chunk['content']}")
            if not haystack_tokens:
                continue
            matches = sum(1 for tok in haystack_tokens if tok in query_tokens)
            unique_matches = len(query_tokens.intersection(haystack_tokens))
            if unique_matches == 0:
                continue

            # Weighted score rewarding coverage of distinct query terms + frequency
            score = round((unique_matches / len(query_tokens)) * 0.7 + min(matches / 10.0, 0.3), 4)
            scored.append(
                {
                    "source_file": chunk["source_file"],
                    "section": chunk["section"],
                    "score": score,
                    "content": chunk["content"],
                }
            )

    scored.sort(key=lambda r: r["score"], reverse=True)
    top_results = scored[: max(1, min(int(top_k), 10))]

    return redact_data(
        {
            "query": query,
            "retrieval_mode": "keyword_fallback_phase2",
            "result_count": len(top_results),
            "results": top_results,
        }
    )
