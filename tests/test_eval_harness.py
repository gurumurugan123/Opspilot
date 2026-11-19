"""
Unit and Integration Tests for Phase 7: End-to-End Evaluation Harness & Incident Benchmark.

Tests:
  - Scenarios schema validation (YAML formatting, required fields, minimum scenario count).
  - Single scenario benchmark execution.
  - End-to-end evaluation runner execution, accuracy calculation, and Done-When criteria verification.
"""

from pathlib import Path
import tempfile
import yaml
from django.test import TestCase

from eval.run_eval import (
    execute_evaluation,
    load_scenarios,
    run_benchmark_scenario,
)


class TestEvalHarness(TestCase):
    """Verify evaluation harness loading, schema conformance, and benchmark metrics."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.scenarios_file = Path(__file__).resolve().parent.parent / "eval" / "scenarios.yaml"

    def test_scenarios_yaml_exists_and_schema_valid(self):
        """Confirm scenarios.yaml exists, parses cleanly, and contains at least 10 scenarios."""
        self.assertTrue(self.scenarios_file.exists(), f"Missing scenarios.yaml at {self.scenarios_file}")

        with open(self.scenarios_file, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        self.assertIn("scenarios", data)
        scenarios = data["scenarios"]
        self.assertGreaterEqual(len(scenarios), 10, "Evaluation benchmark must include at least 10 scenarios")

        required_keys = {
            "id",
            "name",
            "namespace",
            "service_hint",
            "query",
            "expected_root_cause_keywords",
            "expected_runbook",
            "mock_telemetry",
        }

        for idx, sc in enumerate(scenarios, start=1):
            missing = required_keys - set(sc.keys())
            self.assertEqual(
                len(missing),
                0,
                f"Scenario {idx} ({sc.get('id', 'unknown')}) is missing required keys: {missing}",
            )
            self.assertGreater(len(sc["expected_root_cause_keywords"]), 0)
            self.assertTrue(isinstance(sc["mock_telemetry"], dict))

    def test_run_single_benchmark_scenario(self):
        """Execute a single scenario benchmark and verify computed metrics structure."""
        scenarios = load_scenarios(self.scenarios_file)
        first_sc = scenarios[0]

        result = run_benchmark_scenario(first_sc, live=False)
        self.assertEqual(result["id"], first_sc["id"])
        self.assertTrue(result["accuracy_passed"])
        self.assertTrue(result["citation_passed"])
        self.assertGreaterEqual(result["confidence"], 0.80)
        self.assertLessEqual(result["tool_call_count"], 10)
        self.assertGreater(result["duration_ms"], 0)

    def test_end_to_end_benchmark_satisfies_done_when_criteria(self):
        """
        Run the complete evaluation suite across all 12 scenarios and verify
        that accuracy >= 80%, citation rate >= 80%, and average tool calls <= 6.
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            out_json = Path(tmp_dir) / "test_report.json"
            out_md = Path(tmp_dir) / "test_summary.md"

            summary = execute_evaluation(
                scenarios_path=self.scenarios_file,
                output_path=out_json,
                summary_path=out_md,
                live=False,
            )

            self.assertTrue(summary["benchmark_passed"])
            self.assertGreaterEqual(summary["accuracy_rate_pct"], 80.0)
            self.assertGreaterEqual(summary["citation_rate_pct"], 80.0)
            self.assertLessEqual(summary["avg_tool_calls"], 6.0)
            self.assertTrue(out_json.exists())
            self.assertTrue(out_md.exists())
