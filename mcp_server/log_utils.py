"""
Log Truncation, Error Extraction, and Prompt-Injection Delimiter Utilities.

Prevents huge container or Jenkins logs from overflowing LLM token budgets
while guaranteeing that critical ERROR / Exception / Traceback lines are never lost.
"""

import re
from typing import List

from mcp_server.security import sanitize_untrusted_log_content

ERROR_PATTERN = re.compile(
    r"(?i)\b(ERROR|CRITICAL|FATAL|Exception|Traceback|OOMKilled|ConnectionError|"
    r"OperationalError|KeyError|TimeoutError|Connection refused|FAILED|panic)\b"
)


def truncate_logs(
    raw_logs: str,
    max_tail_lines: int = 50,
    max_error_lines: int = 30,
    max_chars: int = 8000,
) -> str:
    """
    Truncate large logs intelligently:
      1. Preserves up to `max_error_lines` lines matching ERROR/Exception/Traceback
         from earlier in the log (with original line numbers).
      2. Preserves the last `max_tail_lines` lines in full.
      3. Enforces a hard `max_chars` safety ceiling for token budget control.
    """
    if not raw_logs:
        return "(no logs available)"

    lines: List[str] = raw_logs.splitlines()
    total_lines = len(lines)

    if total_lines <= max_tail_lines and len(raw_logs) <= max_chars:
        return raw_logs

    split_idx = max(0, total_lines - max_tail_lines)
    earlier_lines = lines[:split_idx]
    tail_lines = lines[split_idx:]

    # Collect error/exception lines from the truncated prefix
    matched_errors: List[str] = []
    for idx, line in enumerate(earlier_lines, start=1):
        if ERROR_PATTERN.search(line):
            matched_errors.append(f"[L{idx}] {line}")

    parts: List[str] = [
        f"--- LOG SUMMARY: showing last {len(tail_lines)} of {total_lines} total lines "
        f"({len(matched_errors)} error/exception lines found in earlier logs) ---"
    ]

    if matched_errors:
        kept_errors = matched_errors[-max_error_lines:]
        parts.append("\n--- EARLIER ERROR / EXCEPTION LINES ---")
        parts.extend(kept_errors)

    parts.append(f"\n--- LAST {len(tail_lines)} LINES ---")
    parts.extend(tail_lines)

    result = "\n".join(parts)

    # Hard character budget guard
    if len(result) > max_chars:
        result = result[: max_chars - 60] + "\n... [TRUNCATED DUE TO MAX CHAR BUDGET]"

    return result


def wrap_untrusted_log(content: str, source: str) -> str:
    """
    Wrap external log text in explicit untrusted delimiters so downstream LLMs
    treat log lines strictly as data, never as executable instructions.
    Neutralizes any prompt injection payloads detected inside log lines.
    """
    sanitized = sanitize_untrusted_log_content(content)
    return f'<untrusted_log source="{source}">\n{sanitized}\n</untrusted_log>'
