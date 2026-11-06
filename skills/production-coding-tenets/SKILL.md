---
name: production-coding-tenets
description: Apply FluidMCP's production coding principles when implementing or reviewing platform changes, including minimal diffs, product reuse, readability, concurrency, and request isolation and authentication.
---

# Production Coding Tenets

## Minimal Changes and Production Safety

- Change only what the requirement needs. Preserve working structure; keep unrelated cleanup, renaming, formatting, and refactoring separate.
- On-premises deployments can break in ways tests and reviews miss. Avoid unnecessary dependencies, configuration changes, and infrastructure; preserve existing defaults and compatibility.
- Minimize behavioral risk, not just line count. A few clear lines are preferable to a clever one-liner.
- Touch as few files as practical, expanding only when architecture or maintainability requires it.

## Maintainability and Human Readability of the Code

- Write straightforward code with descriptive names and explicit conditions. Avoid clever logic, hidden mutations, unnecessary helpers, and abstractions that obscure simple behavior.
- Express intent directly: guard optional validation with a named flag; do not rewrite request identity to make authorization pass.
- Keep comments short and explain why a choice is necessary.

## Product Fit and Reuse

- Treat the platform as a shared product for many customers. Represent customer differences through configuration rather than hardcoded customer branches.
- Inspect existing code, UI, and workflows before adding functionality. Extend established product capabilities where they fit.
- Follow the existing CLI (`fluidmcp/cli/cli.py`), gateway (`services/run_servers.py`), and server lifecycle (`services/server_manager.py`) paths before adding another launcher or proxy. Service paths are relative to `fluidmcp/cli/`.

## Architecture and Scalability

- Think through ownership, data flow, failure handling, and future maintenance before editing. Choose the smallest coherent extension to the existing architecture.
- Reuse existing services, workers, and persistence patterns. Add a new subsystem only when existing capabilities cannot reasonably meet the requirement.

## Concurrency and Event Loop Lag

- Design for many simultaneous users. Never block the event loop with synchronous network, database, filesystem, or CPU-heavy work.
- Use async APIs where available; offload blocking work and suitable CPU-heavy operations to the existing threadpool. For sustained Python CPU work, use existing process/background workers where thread contention would still cause lag.
- Bound concurrency, queues, retries, and timeouts. Avoid shared mutable request state and unbounded task creation; consider cancellation and worker capacity.

## Request Isolation and Authentication

- Check `fluidmcp/cli/auth.py` and the affected route dependencies. Secure mode uses `FMCP_SECURE_MODE` and `FMCP_BEARER_TOKEN`; do not assume GPT Engine JWT claims or tenant repositories exist here. Keep tokens and server environment secrets out of logs and responses.
- Trace both `POST /{server}/mcp` (JSON-RPC) and `POST /{server}/mcp/tools/call` (name/arguments). Distinguish caller JSON-RPC IDs, gateway-generated IDs, upstream IDs, and MCP session IDs. None is an authenticated user identity.
- Shared transport clients must correlate each response to the correct pending request even when callers reuse IDs. Preserve original IDs in downstream responses; remove pending state on success, errors, timeout, cancellation, and shutdown.
- Treat stdio, SSE, and Streamable HTTP as distinct transport implementations. A fix or test for one does not establish coverage for another. Preserve notifications without response IDs and handle upstream errors without crossing request boundaries.
- Keep per-server configuration, processes, sessions, and backend records scoped to the correct server. Inspect the actual backend and authorization path before claiming isolation guarantees.

## Reviewer Experience and Verification

- Keep the diff focused and easy to trace. Explain the concrete behavior change, why it is needed, and any deployment impact.
- Run checks appropriate to the risk, covering unchanged defaults and affected behavior. For auth, request isolation, and concurrency changes, verify those boundaries explicitly; report what remains untested.
