"""
In-Memory and Redis-Backed Event Progress Broadcaster for SSE streaming.
"""

import json
import time
from typing import Any, Dict, Generator


class ProgressEventStream:
    """Helper to format and stream Server-Sent Events (SSE)."""

    @staticmethod
    def format_sse(event_type: str, data: Dict[str, Any]) -> str:
        payload = json.dumps(data)
        return f"event: {event_type}\ndata: {payload}\n\n"

    @classmethod
    def generate_events(cls, investigation) -> Generator[str, None, None]:
        # Initial status event
        yield cls.format_sse(
            "status",
            {
                "investigation_id": str(investigation.id),
                "status": investigation.status,
                "query": investigation.query,
                "current_hypothesis": investigation.current_hypothesis,
            },
        )

        # Stream existing tool calls
        for tc in investigation.tool_calls.all():
            yield cls.format_sse(
                "tool_call",
                {
                    "step": tc.step_number,
                    "tool": tc.tool_name,
                    "summary": tc.output_summary,
                    "duration_ms": tc.duration_ms,
                    "is_error": tc.is_error,
                },
            )

        # If completed, stream final report
        if hasattr(investigation, "report") and investigation.report:
            rep = investigation.report
            yield cls.format_sse(
                "report",
                {
                    "root_cause": rep.root_cause,
                    "confidence": rep.confidence,
                    "suggested_fix": rep.suggested_fix,
                    "evidence": rep.evidence,
                    "similar_incidents": rep.similar_incidents,
                },
            )

        # Final end event
        yield cls.format_sse("complete", {"status": investigation.status})
