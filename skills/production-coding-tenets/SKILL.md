---
name: production-coding-tenets
description: Apply Fluid AI's production coding principles when implementing or reviewing platform changes, including minimal diffs, product reuse, readability, concurrency, and tenant isolation.
---

# Production Coding Tenets

## Minimal Changes and Production Safety

- Change only what the requirement needs. Preserve working structure; keep unrelated cleanup, renaming, formatting, and refactoring separate.
- On-premises deployments can break in ways tests and reviews miss. Avoid unnecessary dependencies, configuration changes, and infrastructure; preserve existing defaults and compatibility.
- Minimize behavioral risk, not just line count. A few clear lines are preferable to a clever one-liner.
- Touch as few files as practical, expanding only when architecture or maintainability requires it.

## Maintainability and Human Readability of the Code

- Write straightforward code with descriptive names and explicit conditions. Avoid clever logic, hidden mutations, unnecessary helpers, and abstractions that obscure simple behavior.
- Express intent directly: to skip a tenant comparison, guard the existing rejection conditions with a named flag; do not overwrite the decoded tenant to make validation pass.
- Keep comments short and explain why a choice is necessary.

## Product Fit and Reuse

- Treat the platform as a shared product for many customers. Represent customer differences through configuration rather than hardcoded customer branches.
- Inspect existing code, UI, and workflows before adding functionality. Extend established product capabilities where they fit.
- Example: add HTTP triggering and any required timing options to DataLoaderSync's existing scheduling, management, and Temporal execution paths instead of creating a separate scheduler and management system.

## Architecture and Scalability

- Think through ownership, data flow, failure handling, and future maintenance before editing. Choose the smallest coherent extension to the existing architecture.
- Reuse existing services, workers, and persistence patterns. Add a new subsystem only when existing capabilities cannot reasonably meet the requirement.

## Concurrency and Event Loop Lag

- Design for many simultaneous users. Never block the event loop with synchronous network, database, filesystem, or CPU-heavy work.
- Use async APIs where available; offload blocking work and suitable CPU-heavy operations to the existing threadpool. For sustained Python CPU work, use existing process/background workers where thread contention would still cause lag.
- Bound concurrency, queues, retries, and timeouts. Avoid shared mutable request state and unbounded task creation; consider cancellation and worker capacity.

## Tenant Isolation

- The environment variable is `TENANT`. JWT authorization reads `fluidai_app_metadata.tenant` (a string or list), not `tenant_id`, and checks deployment membership in `services/authorization/authorization_provider.py`. Preserve this request-level boundary.
- MongoDB uses `tenantId`; reuse `Repository` with tenant checking enabled. Verify reads, writes, and aggregations stay scoped; never let caller-supplied tenant values override the authorized deployment scope.
- MinIO/S3 object paths use tenant names. Preserve tenant prefixes through existing storage flows and validate access; low-level storage helpers do not necessarily enforce isolation themselves.
- Carry tenant scope into background jobs, caches, and shared state. Never mix tenants or mutate identity claims to bypass authorization.

## Reviewer Experience and Verification

- Keep the diff focused and easy to trace. Explain the concrete behavior change, why it is needed, and any deployment impact.
- Run checks appropriate to the risk, covering unchanged defaults and affected behavior. For auth, tenant isolation, and concurrency changes, verify those boundaries explicitly; report what remains untested.
