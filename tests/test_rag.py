"""
Unit and Integration Tests for Phase 4: Hybrid RAG Engine.

Tests:
  - Markdown heading chunking and metadata extraction (`rag/ingest.py`)
  - Normalized dense vector embeddings and cosine similarity (`rag/embeddings.py`)
  - Hybrid retrieval with Reciprocal Rank Fusion (`rag/retrieval.py`)
  - MCP `search_runbooks` tool integration with RAG citations
  - Benchmark evaluation verification (Top-3 Hit Rate >= 80%)
"""

from django.test import TestCase

from eval.rag_evaluation import RAG_TEST_CASES
from mcp_server.tools.runbooks import search_runbooks
from rag.embeddings import compute_dense_embedding, cosine_similarity
from rag.ingest import ingest_runbooks_sync
from rag.models import RunbookChunk
from rag.retrieval import hybrid_search


class TestHybridRAG(TestCase):
    @classmethod
    def setUpTestData(cls):
        # Ingest test runbooks into database
        cls.chunk_count = ingest_runbooks_sync()

    def test_runbook_ingestion_populates_database(self):
        self.assertGreater(self.chunk_count, 20)
        self.assertEqual(RunbookChunk.objects.count(), self.chunk_count)

        # Verify metadata extraction
        oom_chunk = RunbookChunk.objects.filter(source_file="runbook_oomkilled.md").first()
        self.assertIsNotNone(oom_chunk)
        self.assertIn("oom", oom_chunk.tags)
        self.assertEqual(len(oom_chunk.embedding), 128)

    def test_dense_embeddings_normalized_and_similar(self):
        emb_oom1 = compute_dense_embedding("Container OOMKilled exit code 137 memory exceeded")
        emb_oom2 = compute_dense_embedding("Out of memory OOM kill limit exceeded")
        emb_db = compute_dense_embedding("PostgreSQL database connection refused port 5432")

        sim_related = cosine_similarity(emb_oom1, emb_oom2)
        sim_unrelated = cosine_similarity(emb_oom1, emb_db)

        self.assertGreater(sim_related, sim_unrelated)

    def test_hybrid_search_ranks_relevant_runbook(self):
        res = hybrid_search("Pod payments in CrashLoopBackOff missing DB_PASSWORD", top_k=3)
        self.assertGreater(res["result_count"], 0)
        top_match = res["results"][0]
        self.assertEqual(top_match["source_file"], "runbook_crashloopbackoff.md")
        self.assertIn("score", top_match)
        self.assertIn("content", top_match)

    def test_mcp_tool_search_runbooks_integration(self):
        res = search_runbooks("Readiness probe failing HTTP 500", top_k=2)
        self.assertGreater(res["result_count"], 0)
        self.assertEqual(res["results"][0]["source_file"], "runbook_readiness_probe.md")

    def test_rag_retrieval_benchmark_meets_done_when_criteria(self):
        """Verify Top-3 retrieval hit rate on 20 test questions is >= 80%."""
        total = len(RAG_TEST_CASES)
        top3_hits = 0

        for test in RAG_TEST_CASES:
            res = hybrid_search(query=test["question"], top_k=3)
            retrieved = [r["source_file"] for r in res.get("results", [])]
            if any(f in test["expected"] for f in retrieved):
                top3_hits += 1

        hit_rate = (top3_hits / total) * 100.0
        self.assertGreaterEqual(hit_rate, 80.0, f"Hit rate {hit_rate:.1f}% below required 80%")
