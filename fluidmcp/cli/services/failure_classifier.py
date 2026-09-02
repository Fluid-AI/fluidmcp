"""Classify MCP server failures into an actionable category + owner.

Two entry points:

- :func:`classify_text`     — match stderr output or a tool error message
- :func:`classify_exit`     — map a process exit code (wraps ``classify_exit_code``)
- :func:`diagnose`          — combine both plus evidence into a single verdict

The ``owner`` field is the point of the whole module: it separates "the customer
must rotate a password" from "we shipped a bad build", which is what makes a
failure report actionable rather than a finger-pointing exercise.
"""

import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger

from .failure_patterns import (
    DEFAULT_PATTERNS,
    DEPENDENCY_CATEGORIES,
    OWNER_CUSTOMER,
    OWNER_FLUIDMCP,
    OWNER_UNKNOWN,
    RESTART_WONT_HELP,
)

#: Compiled (regex, category, owner, remediation), built once at import.
_COMPILED: List[Tuple[Any, str, str, str]] = []

#: Maps exit-code labels from classify_exit_code() to classifier categories.
_EXIT_LABEL_TO_CATEGORY = {
    "oom_killed": ("oom", OWNER_FLUIDMCP,
                   "The OS killed the server for using too much memory. Raise "
                   "memory_limit_mb or investigate the memory leak."),
    "segfault": ("segfault", OWNER_FLUIDMCP,
                 "The MCP server crashed with a segmentation fault — likely a bug in "
                 "the server or a native dependency."),
    "command_not_found": ("bad_command", OWNER_FLUIDMCP,
                          "The configured command was not found on the FluidMCP host. "
                          "Verify the command and install path."),
    "permission_denied": ("permission_denied", OWNER_FLUIDMCP,
                          "The command is not executable. Check file permissions."),
    "killed_by_fluidmcp": ("resource_kill", OWNER_FLUIDMCP,
                           "FluidMCP's resource monitor killed the server for exceeding "
                           "its memory or CPU budget."),
    "sigkill": ("resource_kill", OWNER_UNKNOWN,
                "The server was force-killed (SIGKILL). If unexpected, check for an "
                "external process manager or OOM killer."),
}


def _load_patterns() -> None:
    """Compile the default catalog, then apply any file-based overrides.

    Override file format (JSON):
        {"patterns": [{"regex": "...", "category": "...",
                       "owner": "customer", "remediation": "..."}],
         "replace": false}

    ``replace: true`` discards the built-in catalog entirely; otherwise custom
    patterns are prepended so they take precedence over the defaults.
    """
    global _COMPILED
    patterns = list(DEFAULT_PATTERNS)

    path = os.getenv("FMCP_FAILURE_PATTERNS_FILE")
    if path:
        try:
            with open(path, "r", encoding="utf-8") as f:
                spec = json.load(f)
            custom = [
                (p["regex"], p["category"], p.get("owner", OWNER_UNKNOWN),
                 p.get("remediation", ""))
                for p in spec.get("patterns", [])
            ]
            patterns = custom if spec.get("replace") else custom + patterns
            logger.info(
                f"Loaded {len(custom)} custom failure patterns from {path} "
                f"(replace={bool(spec.get('replace'))})"
            )
        except Exception as e:
            # A bad override file must never break classification.
            logger.error(f"Failed to load FMCP_FAILURE_PATTERNS_FILE={path}: {e}")

    compiled = []
    for regex, category, owner, remediation in patterns:
        try:
            compiled.append((re.compile(regex, re.IGNORECASE), category, owner, remediation))
        except re.error as e:
            logger.error(f"Skipping invalid failure pattern {regex!r}: {e}")
    _COMPILED = compiled


_load_patterns()


def reload_patterns() -> int:
    """Re-read the pattern catalog. Returns the number of active patterns."""
    _load_patterns()
    return len(_COMPILED)


def classify_text(text: Optional[str]) -> Optional[Dict[str, str]]:
    """Classify a stderr blob or error message.

    Args:
        text: Raw error text. May be None or empty.

    Returns:
        ``{"failure_category", "failure_owner", "remediation", "matched"}`` or
        None if nothing matched.
    """
    if not text:
        return None

    for pattern, category, owner, remediation in _COMPILED:
        match = pattern.search(text)
        if match:
            return {
                "failure_category": category,
                "failure_owner": owner,
                "remediation": remediation,
                "matched": match.group(0)[:200],
            }
    return None


def classify_exit(exit_code: Optional[int]) -> Optional[Dict[str, str]]:
    """Classify a process exit code into a failure category + owner."""
    if exit_code is None:
        return None

    # Imported lazily: server_manager imports this module, so a top-level import
    # would be circular.
    from .server_manager import classify_exit_code

    info = classify_exit_code(exit_code)
    label = info["label"]

    if label in ("clean_exit", "sigterm", "sigterm_container"):
        return None  # Intentional shutdown — not a failure.

    category, owner, remediation = _EXIT_LABEL_TO_CATEGORY.get(
        label, (label, OWNER_UNKNOWN, info["description"])
    )
    return {
        "failure_category": category,
        "failure_owner": owner,
        "remediation": remediation,
        "exit_label": label,
        "exit_category": info["category"],
        "exit_description": info["description"],
    }


def diagnose(
    exit_code: Optional[int] = None,
    stderr: Optional[str] = None,
    tool_errors: Optional[List[str]] = None,
    config_issues: Optional[Dict[str, List[str]]] = None,
) -> Dict[str, Any]:
    """Produce a single verdict from all available signals.

    Precedence is deliberate, strongest evidence first:

    1. **Config issues** — a missing credential explains everything downstream,
       and is the cheapest thing for a human to fix.
    2. **Tool errors** — the server is running, so the error text is about the
       dependency, not the process. Most specific signal available.
    3. **stderr** — may be stale or contain unrelated warnings.
    4. **Exit code** — coarsest; "exit 1" says nothing about why.

    Returns a dict with failure_category, owner, confidence, summary,
    remediation, restart_would_help, and the evidence it was drawn from.
    """
    evidence: List[Dict[str, Any]] = []
    verdict: Optional[Dict[str, str]] = None
    confidence = "low"

    # 1. Configuration problems
    if config_issues:
        missing = config_issues.get("missing_env") or []
        placeholder = config_issues.get("placeholder_env") or []
        unresolved = config_issues.get("unresolved_env") or []
        if missing or placeholder or unresolved:
            parts = []
            if missing:
                parts.append(f"missing: {', '.join(missing)}")
            if placeholder:
                parts.append(f"placeholder values: {', '.join(placeholder)}")
            if unresolved:
                parts.append(f"unresolved references: {', '.join(unresolved)}")
            verdict = {
                "failure_category": "missing_credentials",
                "failure_owner": OWNER_CUSTOMER,
                "remediation": (
                    "Set the following environment variables for this server via "
                    f"PUT /api/servers/{{id}}/instance/env — {'; '.join(parts)}."
                ),
            }
            confidence = "high"
            evidence.append({
                "source": "config",
                "missing_env": missing,
                "placeholder_env": placeholder,
                "unresolved_env": unresolved,
            })

    # 2. Tool-call errors — strongest runtime signal
    if verdict is None and tool_errors:
        for message in tool_errors:
            hit = classify_text(message)
            if hit:
                verdict = hit
                confidence = "high"
                evidence.append({
                    "source": "tool_error",
                    "sample": message[:500],
                    "matched": hit["matched"],
                })
                break
        if verdict is None:
            # Unclassified but definitely failing.
            evidence.append({"source": "tool_error", "sample": tool_errors[0][:500]})

    # 3. stderr
    if verdict is None and stderr:
        hit = classify_text(stderr)
        if hit:
            verdict = hit
            confidence = "medium"
            evidence.append({
                "source": "stderr",
                "sample": _last_matching_line(stderr, hit["matched"]),
                "matched": hit["matched"],
            })

    # 4. Exit code — coarsest
    if verdict is None and exit_code is not None:
        hit = classify_exit(exit_code)
        if hit:
            verdict = hit
            # An exit code alone is only a strong signal when it is specific.
            confidence = (
                "medium" if hit["failure_category"] not in ("generic_error", "unknown")
                else "low"
            )
            evidence.append({
                "source": "exit_code",
                "exit_code": exit_code,
                "exit_label": hit.get("exit_label"),
            })

    if verdict is None:
        return {
            "failure_category": "unknown",
            "failure_owner": OWNER_UNKNOWN,
            "confidence": "low",
            "summary": "No recognised failure signature. Inspect stderr and recent tool calls.",
            "remediation": (
                "Check GET /api/servers/{id}/stderr and GET /api/servers/{id}/crashes "
                "for details."
            ),
            "restart_would_help": None,
            "evidence": evidence,
        }

    category = verdict["failure_category"]
    return {
        "failure_category": category,
        "failure_owner": verdict["failure_owner"],
        "confidence": confidence,
        "summary": _summarize(category, verdict, tool_errors, exit_code),
        "remediation": verdict.get("remediation", ""),
        "restart_would_help": category not in RESTART_WONT_HELP,
        "is_dependency_failure": category in DEPENDENCY_CATEGORIES,
        "evidence": evidence,
    }


def _last_matching_line(text: str, needle: str) -> str:
    """Return the last stderr line containing ``needle`` (most recent occurrence)."""
    if not needle:
        return text[-500:]
    for line in reversed(text.splitlines()):
        if needle.lower() in line.lower():
            return line.strip()[:500]
    return text[-500:]


def _summarize(
    category: str,
    verdict: Dict[str, str],
    tool_errors: Optional[List[str]],
    exit_code: Optional[int],
) -> str:
    """One human sentence describing the failure, safe to paste into a ticket."""
    running_but_failing = bool(tool_errors)

    templates = {
        "missing_credentials":
            "The server is missing required configuration, so it cannot authenticate "
            "to its dependencies.",
        "db_connection_refused":
            "The MCP process is healthy but cannot reach its database or upstream host — "
            "every call fails at connection time."
            if running_but_failing else
            "The MCP server could not reach its database or upstream host.",
        "db_auth_failed":
            "The MCP process is healthy but its database credentials are being rejected.",
        "db_pool_exhausted":
            "The MCP server has exhausted its database connection pool and is refusing "
            "new work.",
        "db_unavailable":
            "The database is temporarily unavailable — most likely an auto-paused "
            "serverless database or a failover. This usually clears itself within a "
            "minute.",
        "db_firewall_blocked":
            "The database firewall is rejecting connections from this host's IP address.",
        "db_not_accessible":
            "The database exists but this login cannot open it — wrong database name "
            "or a login without access.",
        "db_resource_limit":
            "The database hit a service-tier resource limit and is refusing new "
            "requests.",
        "upstream_auth_failed":
            "The MCP process is healthy but the upstream API is rejecting its credentials.",
        "upstream_5xx":
            "The upstream service the MCP server depends on is returning server errors.",
        "upstream_timeout":
            "Calls from the MCP server to its dependency are timing out.",
        "rate_limited":
            "The MCP server is being rate-limited by its upstream service.",
        "tls_failure":
            "TLS/certificate validation is failing between the MCP server and its upstream.",
        "oom":
            "The MCP server was killed for exceeding its memory budget.",
        "segfault":
            "The MCP server crashed with a segmentation fault.",
        "bad_command":
            "The MCP server could not start because its command or a required file "
            "was not found.",
        "missing_dependency":
            "The MCP server could not start because a package dependency is missing.",
        "permission_denied":
            "The MCP server was denied permission to run or access a file.",
        "resource_kill":
            "FluidMCP killed the MCP server for exceeding its resource budget.",
    }

    summary = templates.get(category)
    if summary:
        return summary
    if exit_code is not None:
        return f"The MCP server exited with code {exit_code} ({category})."
    return f"The MCP server reported a {category} failure."
