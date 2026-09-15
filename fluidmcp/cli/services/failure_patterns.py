"""Failure pattern catalog for classifying MCP server errors.

Kept as data, separate from the matching logic in ``failure_classifier``, so
deployment-specific error strings can be added without touching code. Override
or extend with a JSON file via ``FMCP_FAILURE_PATTERNS_FILE``.

Each pattern is (regex, category, owner, remediation):

- ``category``    — machine-readable failure class
- ``owner``       — who has to act: ``customer`` | ``fluidmcp`` | ``external`` | ``unknown``
- ``remediation`` — human-readable next step, written to be pasted into a ticket

Order matters: the first match wins, so specific patterns must precede generic
ones (a bare "timeout" would otherwise shadow "connection pool timeout").
"""

from typing import List, Tuple

#: Who is responsible for fixing a failure class.
OWNER_CUSTOMER = "customer"
OWNER_FLUIDMCP = "fluidmcp"
OWNER_EXTERNAL = "external"
OWNER_UNKNOWN = "unknown"

PatternTuple = Tuple[str, str, str, str]

#: (regex, category, owner, remediation) — evaluated in order, first match wins.
DEFAULT_PATTERNS: List[PatternTuple] = [
    # ── Credentials / configuration (customer-actionable) ──────────────────
    (
        r"login failed for user|password authentication failed|access denied for user"
        r"|authentication failed|auth(?:entication)? error.*credential",
        "db_auth_failed",
        OWNER_CUSTOMER,
        "Database credentials were rejected. Update the DB username/password in this "
        "server's environment variables and restart it.",
    ),
    (
        r"invalid api key|incorrect api key|api key not (?:found|valid)"
        r"|unauthorized.*api.?key|missing api key",
        "upstream_auth_failed",
        OWNER_CUSTOMER,
        "The upstream API rejected the credentials. Verify and rotate the API key in "
        "this server's environment variables.",
    ),
    (
        r"\b401\b|\bunauthorized\b|\b403\b|\bforbidden\b",
        "upstream_auth_failed",
        OWNER_CUSTOMER,
        "The upstream service returned an authorization error. Check the API key or "
        "token and the permissions attached to it.",
    ),

    # ── Azure SQL / MSSQL specifics ────────────────────────────────────────
    # Placed before the generic connectivity rules: these carry numeric error
    # codes with precise meanings that a generic "connection refused" match
    # would otherwise swallow.
    (
        r"\b40613\b|is not currently available.*retry the connection"
        r"|database .* on server .* is not currently available",
        "db_unavailable",
        OWNER_EXTERNAL,
        "The Azure SQL database is not currently available — most often a "
        "serverless database that has auto-paused, or a failover in progress. It "
        "normally becomes available within a minute on retry. If it persists, "
        "check the database status in the Azure portal. Restarting the MCP does "
        "not help; the next request will succeed once the database resumes.",
    ),
    (
        r"\b40615\b|not allowed to access the server"
        r"|client with IP address .* is not allowed",
        "db_firewall_blocked",
        OWNER_CUSTOMER,
        "The Azure SQL firewall is rejecting this host's IP. Add the FluidMCP "
        "host's outbound IP to the server's firewall rules in the Azure portal.",
    ),
    (
        r"\b4060\b|cannot open database .* requested by the login",
        "db_not_accessible",
        OWNER_CUSTOMER,
        "The database exists but this login cannot open it. Check the database "
        "name and that the login is mapped to a user with access.",
    ),
    (
        r"\b(10928|10929|49918|49919|49920|40501)\b"
        r"|resource id ?: ?\d+.*limit|is currently busy",
        "db_resource_limit",
        OWNER_CUSTOMER,
        "The database hit a service-tier resource limit (DTU/vCore, sessions, or "
        "workers). Reduce concurrency or scale the database tier up.",
    ),
    (
        r"adaptive server is unavailable or does not exist|\b20009\b"
        r"|login timeout expired|unable to connect: adaptive server",
        "db_connection_refused",
        OWNER_CUSTOMER,
        "The MCP server could not reach the SQL server at all. Verify the host "
        "and port, that the server is running, and that network/firewall rules "
        "permit the connection from the FluidMCP host.",
    ),

    # ── Database / dependency connectivity (customer-actionable) ───────────
    (
        r"too many connections|connection pool (?:is )?(?:exhausted|full)"
        r"|queuepool limit|pool timeout|no available connection",
        "db_pool_exhausted",
        OWNER_CUSTOMER,
        "The database connection pool is exhausted. Increase the pool size, or fix "
        "connection leaks in the MCP server. Restarting the server clears it temporarily.",
    ),
    (
        r"econnrefused|connection refused|could not connect to server"
        r"|can'?t connect to (?:mysql|postgres|sql)|no pg_hba\.conf entry"
        r"|could not translate host name|getaddrinfo (?:enotfound|failed)|enotfound",
        "db_connection_refused",
        OWNER_CUSTOMER,
        "The MCP server cannot reach its database or upstream host. Verify the host is "
        "running and reachable from the FluidMCP host, and check firewall rules and the "
        "configured host/port.",
    ),
    (
        r"ssl.*(?:handshake|certificate).*(?:fail|expired|invalid)"
        r"|certificate (?:has expired|verify failed)|self.signed certificate",
        "tls_failure",
        OWNER_CUSTOMER,
        "TLS/certificate validation failed reaching the upstream. Check certificate "
        "validity and the trust store on the FluidMCP host.",
    ),

    # ── Upstream service problems (not ours, not the customer's) ───────────
    (
        r"\b429\b|rate limit|too many requests|quota exceeded",
        "rate_limited",
        OWNER_EXTERNAL,
        "The upstream service is rate-limiting requests. Reduce call volume, add "
        "backoff, or raise the account quota.",
    ),
    (
        r"\b50[0234]\b|bad gateway|service unavailable|gateway time.?out"
        r"|internal server error",
        "upstream_5xx",
        OWNER_EXTERNAL,
        "The upstream service is returning server errors. Check the provider's status "
        "page; this usually resolves without action on our side.",
    ),

    # ── FluidMCP / packaging problems (ours) ───────────────────────────────
    (
        r"module_not_found|modulenotfounderror|no module named|importerror"
        r"|cannot find module|err_module_not_found",
        "missing_dependency",
        OWNER_FLUIDMCP,
        "The MCP server package is missing a dependency. Reinstall the package or fix "
        "its dependency list.",
    ),
    (
        r"enoent|command not found|no such file or directory"
        r"|is not recognized as an internal or external command",
        "bad_command",
        OWNER_FLUIDMCP,
        "The configured command or a file it needs was not found. Verify the command "
        "exists on the FluidMCP host and that install paths are correct.",
    ),
    (
        r"eacces|permission denied|operation not permitted",
        "permission_denied",
        OWNER_FLUIDMCP,
        "The MCP server was denied filesystem or OS permissions. Check file modes and "
        "the user the FluidMCP process runs as.",
    ),
    (
        r"out of memory|cannot allocate memory|heap out of memory"
        r"|javascript heap out of memory|memoryerror",
        "oom",
        OWNER_FLUIDMCP,
        "The MCP server ran out of memory. Raise memory_limit_mb for this server or "
        "investigate the memory leak.",
    ),

    # ── Generic timeouts — last, so specific timeouts above win ────────────
    (
        r"etimedout|timed? ?out|timeout|esockettimedout",
        "upstream_timeout",
        OWNER_UNKNOWN,
        "Requests to the dependency are timing out. Check network latency and whether "
        "the upstream service is overloaded.",
    ),
]

#: Categories that indicate a dependency (not the process) is the problem.
#: Used to decide whether restarting the server could plausibly help.
DEPENDENCY_CATEGORIES = frozenset({
    "db_auth_failed",
    "db_unavailable",
    "db_firewall_blocked",
    "db_not_accessible",
    "db_resource_limit",
    "db_connection_refused",
    "db_pool_exhausted",
    "tls_failure",
    "upstream_auth_failed",
    "upstream_5xx",
    "upstream_timeout",
    "rate_limited",
})

#: Categories a restart will not fix — something outside the process must change.
#:
#: db_pool_exhausted is deliberately ABSENT: restarting genuinely clears a leaked
#: connection pool, so a restart is a legitimate (if temporary) remedy there.
#:
#: db_connection_refused, upstream_5xx and rate_limited ARE listed: if the
#: dependency is down or throttling us, restarting the MCP client changes
#: nothing, and a restart loop only hides the real fault and adds noise.
RESTART_WONT_HELP = frozenset({
    "db_auth_failed",
    "db_connection_refused",
    "db_unavailable",
    "db_firewall_blocked",
    "db_not_accessible",
    "db_resource_limit",
    "upstream_auth_failed",
    "upstream_5xx",
    "rate_limited",
    "missing_credentials",
    "invalid_config",
    "bad_command",
    "missing_dependency",
    "tls_failure",
})
