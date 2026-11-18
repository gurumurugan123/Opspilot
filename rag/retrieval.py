"""
Hybrid Retrieval Engine for OpsPilot RAG (Phase 4).

Combines:
  1. Dense vector semantic search (cosine similarity).
  2. Sparse keyword matching over titles, sections, tags, and content.
  3. Reciprocal Rank Fusion (RRF) with constant k=60 to merge candidate lists.
"""

import re
from typing import Any, Dict, List, Optional

from mcp_server.redaction import redact_data
from rag.embeddings import compute_dense_embedding, cosine_similarity
from rag.models import RunbookChunk

TOKEN_RE = re.compile(r"[a-z0-9_-]+")
STOPWORDS = {
    "the", "is", "in", "at", "of", "on", "to", "a", "an", "and", "or",
    "for", "with", "how", "why", "what", "are", "was", "be", "by", "from",
    "do", "does", "did", "this", "that", "these", "those",
}


def _tokenize(text: str) -> List[str]:
    return [t for t in TOKEN_RE.findall(text.lower()) if len(t) > 1 and t not in STOPWORDS]


def _sparse_score(query_tokens: List[str], chunk: RunbookChunk) -> float:
    """Calculate sparse keyword match score with weighted term frequencies."""
    if not query_tokens:
        return 0.0

    score = 0.0
    title_lower = chunk.title.lower()
    section_lower = chunk.section.lower()
    content_lower = chunk.content.lower()
    tags = [t.lower() for t in chunk.tags]

    for tok in query_tokens:
        if tok in title_lower:
            score += 3.0
        if tok in section_lower:
            score += 2.5
        if tok in tags:
            score += 2.0
        # Count occurrences in content
        matches = content_lower.count(tok)
        if matches:
            score += min(matches * 0.5, 3.0)

    return score


def hybrid_search(
    query: str,
    top_k: int = 3,
    service_filter: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Execute Hybrid Retrieval merging Dense Vector Search + Sparse Keyword Search
    using Reciprocal Rank Fusion (RRF).
    """
    chunks_qs = RunbookChunk.objects.all()
    if service_filter and service_filter != "general":
        chunks_qs = chunks_qs.filter(service__in=[service_filter, "general"])

    chunks = list(chunks_qs)
    if not chunks:
        # Fallback if DB not populated yet: attempt ingestion on-the-fly
        from rag.ingest import ingest_runbooks_sync
        ingest_runbooks_sync()
        chunks = list(RunbookChunk.objects.all())

    if not chunks:
        return {
            "query": query,
            "retrieval_mode": "hybrid_rrf",
            "result_count": 0,
            "results": [],
        }

    query_tokens = _tokenize(query)
    q_emb = compute_dense_embedding(query)

    # 1. Dense Scoring
    dense_scored = []
    for c in chunks:
        sim = cosine_similarity(q_emb, c.embedding)
        dense_scored.append((c, sim))
    dense_scored.sort(key=lambda x: x[1], reverse=True)

    # 2. Sparse Scoring
    sparse_scored = []
    for c in chunks:
        sp_score = _sparse_score(query_tokens, c)
        if sp_score > 0:
            sparse_scored.append((c, sp_score))
    sparse_scored.sort(key=lambda x: x[1], reverse=True)

    # 3. Reciprocal Rank Fusion (RRF) with standard constant k=60
    K_RRF = 60
    rrf_scores: Dict[str, float] = {}
    chunk_by_id = {c.id: c for c in chunks}

    for rank, (chunk, _) in enumerate(dense_scored, start=1):
        rrf_scores[chunk.id] = rrf_scores.get(chunk.id, 0.0) + (1.0 / (K_RRF + rank))

    for rank, (chunk, _) in enumerate(sparse_scored, start=1):
        rrf_scores[chunk.id] = rrf_scores.get(chunk.id, 0.0) + (1.0 / (K_RRF + rank))

    ranked_ids = sorted(rrf_scores.keys(), key=lambda cid: rrf_scores[cid], reverse=True)
    top_ids = ranked_ids[: max(1, min(int(top_k), 10))]

    results = []
    for cid in top_ids:
        chunk = chunk_by_id[cid]
        results.append(
            {
                "source_file": chunk.source_file,
                "doc_type": chunk.doc_type,
                "title": chunk.title,
                "section": chunk.section,
                "service": chunk.service,
                "score": round(rrf_scores[cid], 5),
                "content": chunk.content,
            }
        )

    return redact_data(
        {
            "query": query,
            "retrieval_mode": "hybrid_rrf",
            "result_count": len(results),
            "results": results,
        }
    )
