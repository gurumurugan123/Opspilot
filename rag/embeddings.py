"""
Dense Vector Embedding Engine for OpsPilot RAG (Phase 4).

Supports:
  1. Built-in Semantic Hashing Embedder (128 dimensions, unit normalized, zero network latency).
  2. OpenAI text-embedding-3-small (when OPENAI_API_KEY is configured).
"""

import hashlib
import math
import os
import re
from typing import List

EMBEDDING_DIM = 128
TOKEN_RE = re.compile(r"[a-z0-9_-]+")


def _normalize_vector(vec: List[float]) -> List[float]:
    """Normalize vector to unit length (L2 norm = 1.0)."""
    norm = math.sqrt(sum(x * x for x in vec))
    if norm == 0.0:
        return [0.0] * len(vec)
    return [round(x / norm, 6) for x in vec]


def _hash_token_to_buckets(token: str, dim: int = EMBEDDING_DIM) -> List[tuple[int, float]]:
    """Hash token and its subword 3-grams into feature buckets with sign hashing."""
    features = []
    # Whole token
    h = int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16)
    idx = h % dim
    sign = 1.0 if ((h >> 16) & 1) else -1.0
    features.append((idx, sign * 2.0))

    # Subword character n-grams (captures prefixes/stems like 'oom', 'crash', 'timeout')
    for n in (3, 4):
        if len(token) >= n:
            for i in range(len(token) - n + 1):
                ngram = token[i : i + n]
                hn = int(hashlib.sha256(ngram.encode("utf-8")).hexdigest()[:8], 16)
                idx_n = hn % dim
                sign_n = 1.0 if (hn & 1) else -1.0
                features.append((idx_n, sign_n * 0.5))

    return features


def compute_dense_embedding(text: str, dim: int = EMBEDDING_DIM) -> List[float]:
    """
    Compute a normalized dense vector embedding for input text.
    If OPENAI_API_KEY is available and configured, calls OpenAI embeddings.
    Otherwise, uses deterministic semantic feature projection.
    """
    if not text:
        return [0.0] * dim

    api_key = os.getenv("OPENAI_API_KEY")
    provider = os.getenv("LLM_PROVIDER", "").lower()
    if api_key and provider == "openai":
        try:
            import urllib.request
            import json

            req = urllib.request.Request(
                "https://api.openai.com/v1/embeddings",
                data=json.dumps({"input": text[:8000], "model": "text-embedding-3-small"}).encode("utf-8"),
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data["data"][0]["embedding"][:dim]
        except Exception:
            # Gracefully fallback to deterministic local embedding on network errors
            pass

    # High-speed deterministic local embedding
    vec = [0.0] * dim
    tokens = TOKEN_RE.findall(text.lower())
    for token in tokens:
        for idx, val in _hash_token_to_buckets(token, dim):
            vec[idx] += val

    return _normalize_vector(vec)


def cosine_similarity(vec_a: List[float], vec_b: List[float]) -> float:
    """Compute cosine similarity between two vectors (dot product if unit-normalized)."""
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return 0.0
    return sum(a * b for a, b in zip(vec_a, vec_b))
