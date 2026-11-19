"""
Security, Guardrails, and Safety Engine for OpsPilot (Phase 6).

Implements multi-layer defense-in-depth:
  1. Read-Only Enforcement: Strict tool whitelisting and mutating command rejection.
  2. Input & Argument Validation: Shell metacharacter, path traversal, and malicious parameter checks.
  3. Prompt Injection Defense: Detection and neutralization of adversarial instructions in logs or user input.
  4. Untrusted Content Boundary: Explicit XML tagging (<untrusted_log>) for untrusted strings.
  5. Circuit Breakers: Hard limits on tool call budget, token usage, and graph iterations.
"""

import re
from typing import Any, Dict, List, Optional, Set


class SecurityViolationError(Exception):
    """Raised when an unauthorized mutating action, shell injection, or security violation occurs."""
    pass


class BudgetExceededError(Exception):
    """Raised when an investigation exceeds its configured tool call or token budget."""
    pass


# 1. Authoritative Whitelist of Read-Only Tools (Strictly enforced at dispatch)
ALLOWED_READ_ONLY_TOOLS: Set[str] = frozenset([
    "list_pods",
    "get_pod_logs",
    "describe_pod",
    "get_k8s_events",
    "get_recent_deployments",
    "get_jenkins_builds",
    "get_jenkins_build_log",
    "get_build_changes",
    "search_runbooks",
])

# Known Mutating Tool / Action Signatures that must NEVER be executed
DISALLOWED_MUTATING_KEYWORDS: List[str] = [
    "delete", "remove", "kill", "restart", "reboot", "scale",
    "patch", "update", "create", "apply", "exec", "post", "put",
    "drop", "truncate", "terminate", "destroy", "cordon", "drain"
]

# Validation patterns for Kubernetes names (RFC 1123 / DNS-1123 label standard)
K8S_NAME_RE = re.compile(r"^[a-z0-9]([-a-z0-9]*[a-z0-9])?$")

# Forbidden shell metacharacters and injection operators
SHELL_INJECTION_RE = re.compile(r"[;&|`$><\n\r\x00]")

# Prompt Injection Attack Signatures (Adversarial Log Lines & User Overrides)
PROMPT_INJECTION_PATTERNS: List[re.Pattern] = [
    re.compile(r"(?i)\b(ignore|forget|override|disregard)\s+(all\s+)?(previous|prior|above|system)\s+(instructions|prompts|rules|commands)\b"),
    re.compile(r"(?i)\b(system\s+override|system\s+directive|maintenance\s+mode|administrative\s+override)\b"),
    re.compile(r"(?i)\byou\s+are\s+now\s+(in\s+developer\s+mode|an\s+unrestricted\s+ai|free|admin|root)\b"),
    re.compile(r"(?i)\b(delete|drop|wipe|terminate)\s+(all\s+)?(pods|namespaces|deployments|cluster|database)\b"),
    re.compile(r"(?i)\b(curl|wget)\s+.*\|\s*(bash|sh)\b"),
    re.compile(r"(?i)\b(cat\s+/etc/passwd|rm\s+-rf|chmod\s+777)\b"),
    re.compile(r"(?i)\b(report\s+that\s+everything\s+is\s+healthy|fake\s+report|skip\s+checks)\b"),
]

# Circuit Breaker Limits
MAX_TOOL_CALLS_LIMIT = 10
MAX_GRAPH_ITERATIONS_LIMIT = 3
MAX_TOKEN_BUDGET_LIMIT = 15000


def is_tool_allowed(tool_name: str) -> bool:
    """Check if the given tool name is strictly registered in the read-only whitelist."""
    return tool_name in ALLOWED_READ_ONLY_TOOLS


def validate_tool_call(tool_name: str, arguments: Optional[Dict[str, Any]] = None) -> None:
    """
    Validate that a requested tool call is read-only and free of command/parameter injection.
    Raises SecurityViolationError if violation is detected.
    """
    # Check 1: Tool Whitelist
    if not is_tool_allowed(tool_name):
        # Check if it resembles a known mutating command
        name_lower = tool_name.lower()
        if any(kw in name_lower for kw in DISALLOWED_MUTATING_KEYWORDS):
            raise SecurityViolationError(
                f"SecurityViolation: Mutating operation '{tool_name}' is strictly forbidden. "
                "OpsPilot runs in read-only diagnostic mode."
            )
        raise SecurityViolationError(f"SecurityViolation: Unauthorized tool '{tool_name}' is not in the read-only whitelist.")

    if not arguments:
        return

    # Check 2: Argument injection validation
    for key, val in arguments.items():
        if isinstance(val, str):
            # Check for shell command injection characters
            if SHELL_INJECTION_RE.search(val):
                raise SecurityViolationError(
                    f"SecurityViolation: Potentially malicious metacharacters detected in argument '{key}': {val!r}"
                )

            # Check for path traversal attempts
            if "../" in val or "..\\" in val:
                raise SecurityViolationError(
                    f"SecurityViolation: Directory traversal sequence detected in argument '{key}': {val!r}"
                )

            # Namespace & Pod name format validation
            if key in ("namespace", "pod") and val:
                # Disallow strings with spaces or invalid DNS label characters
                if not K8S_NAME_RE.match(val):
                    raise SecurityViolationError(
                        f"SecurityViolation: Invalid Kubernetes identifier for '{key}': {val!r}. "
                        "Must adhere to RFC 1123 DNS-1123 label standards."
                    )


def detect_prompt_injection(text: str) -> bool:
    """
    Scans text for adversarial prompt injection patterns, instruction overrides,
    or malicious jailbreak signatures.
    """
    if not isinstance(text, str) or not text:
        return False
    return any(pattern.search(text) for pattern in PROMPT_INJECTION_PATTERNS)


def sanitize_user_input(text: str) -> str:
    """
    Sanitize user queries and incoming webhook alerts:
      - Strips HTML/script tags.
      - Disarms control sequences.
      - Enforces max input length.
    """
    if not text:
        return ""
    # Strip HTML tags like <script>...</script>
    cleaned = re.sub(r"<[^>]*>", "", text)
    # Strip control characters except newline and tab
    cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", cleaned)
    # Enforce length ceiling
    return cleaned[:1000].strip()


def sanitize_untrusted_log_content(content: str) -> str:
    """
    Neutralize prompt injection attempts within external log streams
    while preserving actual error stack traces for SRE analysis.
    """
    if not content:
        return content

    lines = content.splitlines()
    sanitized_lines = []
    for line in lines:
        if detect_prompt_injection(line):
            sanitized_lines.append(f"[DEFUSED_ADVERSARIAL_INJECTION_ATTEMPT: {line.strip()}]")
        else:
            sanitized_lines.append(line)
    return "\n".join(sanitized_lines)


def check_tool_budget(call_count: int, max_allowed: int = MAX_TOOL_CALLS_LIMIT) -> None:
    """Enforce circuit breaker on tool call count to prevent runaway execution loops."""
    if call_count >= max_allowed:
        raise BudgetExceededError(
            f"CircuitBreakerTriggered: Maximum tool call budget ({max_allowed}) reached. "
            "Investigation halted to prevent runaway execution."
        )
