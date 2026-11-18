"""
Read-Only Jenkins CI/CD Diagnostic Tools for OpsPilot MCP Server.

Strictly read-only: only executes HTTP GET calls against the Jenkins REST API.
All outputs and console logs are redacted and truncated before reaching the LLM.
"""

import base64
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from mcp_server.log_utils import truncate_logs, wrap_untrusted_log
from mcp_server.redaction import redact_data, redact_text

JENKINS_URL = os.getenv("JENKINS_URL", "http://localhost:8080").rstrip("/")
JENKINS_USER = os.getenv("JENKINS_USER", "admin")
JENKINS_TOKEN = os.getenv("JENKINS_TOKEN", "")


def _default_http_get(url: str, timeout: float = 10.0) -> str:
    """Perform an authenticated HTTP GET request to Jenkins using stdlib urllib."""
    req = urllib.request.Request(url, method="GET")
    if JENKINS_USER and JENKINS_TOKEN:
        creds = f"{JENKINS_USER}:{JENKINS_TOKEN}".encode("utf-8")
        b64_creds = base64.b64encode(creds).decode("ascii")
        req.add_header("Authorization", f"Basic {b64_creds}")

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Jenkins API returned HTTP {exc.code} for {url}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Failed to connect to Jenkins at {url}: {exc.reason}") from exc


def _format_epoch_ms(ms: Optional[int]) -> str:
    if not ms:
        return "unknown"
    return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc).isoformat()


def get_jenkins_builds(
    job: str,
    limit: int = 5,
    base_url: Optional[str] = None,
    http_get: Optional[Callable[[str], str]] = None,
) -> Dict[str, Any]:
    """
    List the most recent builds for a Jenkins job with status, duration, and timestamp.
    """
    root = (base_url or os.getenv("JENKINS_URL", JENKINS_URL)).rstrip("/")
    fetcher = http_get or _default_http_get
    safe_job = urllib.parse.quote(job, safe="")
    max_builds = max(1, min(int(limit), 25))

    tree_query = f"builds[number,result,timestamp,duration,building,displayName]{{0,{max_builds}}}"
    url = f"{root}/job/{safe_job}/api/json?tree={urllib.parse.quote(tree_query, safe='[],{}')}"

    raw = fetcher(url)
    payload = json.loads(raw)

    builds: List[Dict[str, Any]] = []
    for b in payload.get("builds", [])[:max_builds]:
        status = "IN_PROGRESS" if b.get("building") else (b.get("result") or "UNKNOWN")
        builds.append(
            {
                "number": b.get("number"),
                "display_name": b.get("displayName", f"#{b.get('number')}"),
                "result": status,
                "duration_seconds": round((b.get("duration") or 0) / 1000.0, 2),
                "timestamp": _format_epoch_ms(b.get("timestamp")),
            }
        )

    return redact_data(
        {
            "job": job,
            "build_count": len(builds),
            "builds": builds,
        }
    )


def get_jenkins_build_log(
    job: str,
    build_number: int,
    base_url: Optional[str] = None,
    http_get: Optional[Callable[[str], str]] = None,
) -> Dict[str, Any]:
    """
    Fetch the console log of a Jenkins build, redact secrets/PII, truncate large logs
    preserving errors/tracebacks, and wrap in untrusted delimiters.
    """
    root = (base_url or os.getenv("JENKINS_URL", JENKINS_URL)).rstrip("/")
    fetcher = http_get or _default_http_get
    safe_job = urllib.parse.quote(job, safe="")

    url = f"{root}/job/{safe_job}/{int(build_number)}/consoleText"
    raw_log = fetcher(url)

    scrubbed = redact_text(raw_log)
    truncated = truncate_logs(scrubbed, max_tail_lines=80)
    safe_log = wrap_untrusted_log(truncated, source=f"jenkins:{job}#{build_number}")

    return {
        "job": job,
        "build_number": int(build_number),
        "console_log": safe_log,
    }


def get_build_changes(
    job: str,
    build_number: int,
    base_url: Optional[str] = None,
    http_get: Optional[Callable[[str], str]] = None,
) -> Dict[str, Any]:
    """
    Retrieve Git commit changes (commit ID, author, message, modified files)
    included in a specific Jenkins build.
    """
    root = (base_url or os.getenv("JENKINS_URL", JENKINS_URL)).rstrip("/")
    fetcher = http_get or _default_http_get
    safe_job = urllib.parse.quote(job, safe="")

    tree_query = (
        "number,result,timestamp,"
        "changeSets[items[commitId,msg,author[fullName],affectedPaths]],"
        "changeSet[items[commitId,msg,author[fullName],affectedPaths]]"
    )
    url = f"{root}/job/{safe_job}/{int(build_number)}/api/json?tree={urllib.parse.quote(tree_query, safe='[],')}"

    raw = fetcher(url)
    payload = json.loads(raw)

    # Jenkins Pipeline jobs use `changeSets` (list); Freestyle jobs use `changeSet` (dict)
    raw_items: List[Dict[str, Any]] = []
    for cs in payload.get("changeSets", []):
        raw_items.extend(cs.get("items", []))
    if not raw_items and isinstance(payload.get("changeSet"), dict):
        raw_items.extend(payload["changeSet"].get("items", []))

    changes: List[Dict[str, Any]] = []
    for item in raw_items:
        author = item.get("author") or {}
        changes.append(
            {
                "commit_id": (item.get("commitId") or "")[:10],
                "author": author.get("fullName", "unknown"),
                "message": (item.get("msg") or "").strip(),
                "affected_files": item.get("affectedPaths", []),
            }
        )

    return redact_data(
        {
            "job": job,
            "build_number": int(build_number),
            "result": payload.get("result", "UNKNOWN"),
            "timestamp": _format_epoch_ms(payload.get("timestamp")),
            "change_count": len(changes),
            "changes": changes,
        }
    )
