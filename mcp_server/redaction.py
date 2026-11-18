"""
Secret, Credential, and PII Redaction Engine for OpsPilot MCP Server.

Every piece of text returned by Kubernetes, Jenkins, or Runbook tools passes
through this module BEFORE reaching the LLM context window.
"""

import re
from typing import Any, List, Tuple

# Ordered list of (pattern, replacement) tuples.
# More specific patterns (URLs, JWTs, API keys) run before generic patterns.
REDACTION_RULES: List[Tuple[re.Pattern, str]] = [
    # 1. Database / HTTP / Redis connection URLs with credentials: scheme://user:pass@host
    (
        re.compile(r"([a-zA-Z][a-zA-Z0-9+.-]*://[^:\s/@]*:)([^@\s]+)(@)"),
        r"\1[REDACTED_PASSWORD]\3",
    ),
    # 2. Bearer / Basic Authorization headers
    (
        re.compile(r"(?i)(Authorization\s*[:=]\s*(?:Bearer|Basic|Token)\s+)([^\s\"',;]+)"),
        r"\1[REDACTED_TOKEN]",
    ),
    (
        re.compile(r"(?i)(Bearer\s+)([A-Za-z0-9\-._~+/]+=*)"),
        r"\1[REDACTED_TOKEN]",
    ),
    # 3. JWT tokens (three base64url segments starting with eyJ)
    (
        re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"),
        "[REDACTED_JWT]",
    ),
    # 4. Well-known provider API keys (OpenAI, Anthropic, GitHub, AWS)
    (
        re.compile(r"\bsk-(?:ant-|proj-)?[A-Za-z0-9_-]{16,}\b"),
        "[REDACTED_API_KEY]",
    ),
    (
        re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}\b"),
        "[REDACTED_GITHUB_TOKEN]",
    ),
    (
        re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
        "[REDACTED_AWS_KEY]",
    ),
    # 5. Generic key=value or key: value secret assignments
    (
        re.compile(
            r"(?i)\b((?:db_)?password|passwd|pwd|secret(?:_key)?|api_?key|access_?token|auth_?token|private_?key|client_secret|jenkins_token)\b"
            r"(\s*[:=]\s*['\"]?)([^'\"\s,;}\]]+)(['\"]?)"
        ),
        r"\1\2[REDACTED_SECRET]\4",
    ),
    # 6. Email addresses (PII)
    (
        re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
        "[REDACTED_EMAIL]",
    ),
    # 7. IPv4 addresses (internal/external host IPs)
    (
        re.compile(r"\b(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)\b"),
        "[REDACTED_IP]",
    ),
]


def redact_text(text: str) -> str:
    """Scrub secrets, tokens, passwords, emails, and IP addresses from text."""
    if not isinstance(text, str) or not text:
        return text

    scrubbed = text
    for pattern, replacement in REDACTION_RULES:
        scrubbed = pattern.sub(replacement, scrubbed)
    return scrubbed


def redact_data(data: Any) -> Any:
    """Recursively redact all strings inside dicts, lists, and tuples."""
    if isinstance(data, str):
        return redact_text(data)
    if isinstance(data, list):
        return [redact_data(item) for item in data]
    if isinstance(data, tuple):
        return tuple(redact_data(item) for item in data)
    if isinstance(data, dict):
        return {k: redact_data(v) for k, v in data.items()}
    return data
