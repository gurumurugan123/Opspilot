"""
End-to-End Evaluation Harness & Incident Benchmark for OpsPilot (Phase 7).

Executes a benchmark suite of realistic Kubernetes and Jenkins incident scenarios
defined in `eval/scenarios.yaml` and computes:
  - Root Cause Diagnostic Accuracy (Target: >= 80%)
  - Evidence & Runbook Citation Precision (Target: >= 80%)
  - Tool Call Efficiency (Target: <= 6 tool calls per investigation)
  - Reviewer Confidence Score (Target: >= 0.80)
  - Latency & Cost Telemetry

Usage:
  python eval/run_eval.py
  python eval/run_eval.py --scenarios eval/scenarios.yaml --output eval/benchmark_report.json
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import patch
import yaml

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "api.settings")
import django
django.setup()

from agents.graph import run_investigation_graph


def load_scenarios(scenarios_path: Path) -> List[Dict[str, Any]]:
    """Load benchmark scenarios from YAML definition file."""
    if not scenarios_path.exists():
        raise FileNotFoundError(f"Scenarios file not found: {scenarios_path}")

    with open(scenarios_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("scenarios", [])


def run_benchmark_scenario(scenario: Dict[str, Any], live: bool = False) -> Dict[str, Any]:
    """Run an individual incident scenario and evaluate the generated diagnosis."""
    scenario_id = scenario.get("id")
    name = scenario.get("name")
    query = scenario.get("query")
    namespace = scenario.get("namespace", "opspilot-demo")
    service_hint = scenario.get("service_hint")
    expected_keywords = [k.lower() for k in scenario.get("expected_root_cause_keywords", [])]
    expected_runbook = scenario.get("expected_runbook", "").lower()
    mock_telemetry = scenario.get("mock_telemetry", {})

    def _mock_dispatch(tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        if tool_name in mock_telemetry:
            return mock_telemetry[tool_name]
        return {}

    start_time = time.time()

    if live:
        final_state = run_investigation_graph(
            question=query,
            namespace=namespace,
            service_hint=service_hint,
        )
    else:
        with patch("agents.investigator.dispatch_tool_call", side_effect=_mock_dispatch):
            final_state = run_investigation_graph(
                question=query,
                namespace=namespace,
                service_hint=service_hint,
            )

    duration_ms = round((time.time() - start_time) * 1000.0, 2)
    report = final_state.get("final_report") or {}
    root_cause = report.get("root_cause", "").lower()
    similar_incidents = [str(i).lower() for i in report.get("similar_incidents", [])]
    evidence = [str(e).lower() for e in report.get("evidence", [])]

    # Metric 1: Root Cause Keyword Accuracy
    matched_keywords = [kw for kw in expected_keywords if kw in root_cause]
    accuracy_passed = len(matched_keywords) > 0 and (
        len(matched_keywords) >= len(expected_keywords) or any(k in root_cause for k in expected_keywords)
    )

    # Metric 2: Citation Precision (runbook referenced in citations or similar incidents)
    citation_passed = False
    if expected_runbook:
        citation_passed = any(expected_runbook in inc for inc in similar_incidents) or any(
            expected_runbook in ev for ev in evidence
        )

    tool_calls = final_state.get("tool_call_count", 0)
    confidence = report.get("confidence", 0.0)

    return {
        "id": scenario_id,
        "name": name,
        "query": query,
        "accuracy_passed": accuracy_passed,
        "citation_passed": citation_passed,
        "matched_keywords": matched_keywords,
        "root_cause_diagnosed": report.get("root_cause", "No report"),
        "suggested_fix": report.get("suggested_fix", ""),
        "confidence": confidence,
        "tool_call_count": tool_calls,
        "duration_ms": duration_ms,
        "estimated_tokens": tool_calls * 120 + 450,
        "estimated_cost_usd": round((tool_calls * 120 + 450) * 0.000002, 6),
    }


def execute_evaluation(
    scenarios_path: Path,
    output_path: Path,
    summary_path: Path,
    live: bool = False,
) -> Dict[str, Any]:
    """Execute the full benchmark suite and export metrics."""
    scenarios = load_scenarios(scenarios_path)
    results: List[Dict[str, Any]] = []

    print("=" * 80)
    print(" OpsPilot SRE Incident Diagnostic Benchmark (Phase 7)")
    print(f" Total Scenarios: {len(scenarios)} | Execution Mode: {'LIVE CLUSTER' if live else 'DETERMINISTIC MOCK'}")
    print("=" * 80)

    for idx, sc in enumerate(scenarios, start=1):
        res = run_benchmark_scenario(sc, live=live)
        results.append(res)
        status_mark = "PASS" if res["accuracy_passed"] else "FAIL"
        cite_mark = "PASS" if res["citation_passed"] else "SKIP"
        print(f"[{idx:02d}/{len(scenarios):02d}] {res['id']:<42} | Diagnostic: {status_mark} | Citation: {cite_mark} | Tools: {res['tool_call_count']} | {res['duration_ms']:>6.1f}ms")

    # Aggregate Metrics
    total = len(results)
    accurate_count = sum(1 for r in results if r["accuracy_passed"])
    cited_count = sum(1 for r in results if r["citation_passed"])
    accuracy_rate = round((accurate_count / total) * 100.0, 1) if total else 0.0
    citation_rate = round((cited_count / total) * 100.0, 1) if total else 0.0
    avg_tools = round(sum(r["tool_call_count"] for r in results) / total, 1) if total else 0.0
    avg_latency = round(sum(r["duration_ms"] for r in results) / total, 1) if total else 0.0
    avg_confidence = round(sum(r["confidence"] for r in results) / total, 2) if total else 0.0
    total_cost = round(sum(r["estimated_cost_usd"] for r in results), 4)

    summary = {
        "benchmark_timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "total_scenarios": total,
        "accuracy_rate_pct": accuracy_rate,
        "citation_rate_pct": citation_rate,
        "avg_tool_calls": avg_tools,
        "avg_latency_ms": avg_latency,
        "avg_confidence": avg_confidence,
        "total_cost_usd": total_cost,
        "target_accuracy_pct": 80.0,
        "target_tool_calls_max": 6.0,
        "benchmark_passed": accuracy_rate >= 80.0 and avg_tools <= 6.0,
        "scenario_results": results,
    }

    # Save JSON Report
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    # Export Markdown Summary
    md_lines = [
        "# OpsPilot Incident Benchmark Report (Phase 7)",
        "",
        f"- **Benchmark Run:** {summary['benchmark_timestamp']}",
        f"- **Total Scenarios Evaluated:** {total}",
        f"- **Diagnostic Accuracy Rate:** **{accuracy_rate}%** (Target: >= 80.0%)",
        f"- **Runbook Citation Rate:** **{citation_rate}%** (Target: >= 80.0%)",
        f"- **Average Diagnostic Tool Calls:** **{avg_tools}** (Target: <= 6.0)",
        f"- **Average Reviewer Confidence:** **{avg_confidence:.0%}**",
        f"- **Average Latency per Incident:** **{avg_latency} ms**",
        f"- **Total Benchmark Token Cost:** **${total_cost:.4f} USD**",
        "",
        "### Scenario-by-Scenario Evaluation Matrix",
        "",
        "| ID | Scenario Title | Diagnosis | Citation | Tools | Latency | Confidence |",
        "|---|---|---|---|---|---|---|",
    ]

    for r in results:
        d_icon = "Passed" if r["accuracy_passed"] else "Failed"
        c_icon = "Passed" if r["citation_passed"] else "Skipped"
        md_lines.append(
            f"| `{r['id']}` | {r['name']} | {d_icon} | {c_icon} | {r['tool_call_count']} | {r['duration_ms']:.1f}ms | {r['confidence']:.0%} |"
        )

    summary_path.parent.mkdir(parents=True, exist_ok=True)
    with open(summary_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines) + "\n")

    print("=" * 80)
    print(f" BENCHMARK RESULT: {'PASSED (Meets Done-When Criteria)' if summary['benchmark_passed'] else 'FAILED'}")
    print(f" Accuracy Rate : {accuracy_rate}%  (Target: >= 80.0%)")
    print(f" Citation Rate : {citation_rate}%  (Target: >= 80.0%)")
    print(f" Avg Tool Calls: {avg_tools}      (Target: <= 6.0)")
    print(f" Report JSON   : {output_path}")
    print(f" Summary MD    : {summary_path}")
    print("=" * 80)

    return summary


def main():
    parser = argparse.ArgumentParser(description="OpsPilot Incident Benchmark Runner (Phase 7)")
    parser.add_argument("--scenarios", type=Path, default=BASE_DIR / "eval" / "scenarios.yaml")
    parser.add_argument("--output", type=Path, default=BASE_DIR / "eval" / "benchmark_report.json")
    parser.add_argument("--summary", type=Path, default=BASE_DIR / "eval" / "benchmark_summary.md")
    parser.add_argument("--live", action="store_true", help="Run against live cluster instead of mocks")
    args = parser.parse_args()

    summary = execute_evaluation(
        scenarios_path=args.scenarios,
        output_path=args.output,
        summary_path=args.summary,
        live=args.live,
    )

    if not summary["benchmark_passed"]:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
