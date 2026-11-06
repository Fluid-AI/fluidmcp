---
name: pr-visualization
description: Turns a FluidMCP GitHub PR into one interactive HTML page — data-model changes, API/router changes and other new inputs, code-flow diagrams, the program layout, expandable call stacks, the full diff with inline review notes, and review findings. The LLM writes only a compact JSON spec per PR; a fixed template and a stdlib Python builder render it and pull code snippets and the diff straight from git. Use when the user wants to visualize, explain, walk through, or review a PR or spec as HTML.
---

# PR Visualization

This repository keeps the skill in `skills/pr-visualization/`. Work from the FluidMCP checkout; PRs normally target `development`. Confirm the actual PR base and head before describing changes.

One page per PR, built from two parts:

| Part | Who makes it | Where |
|------|--------------|-------|
| Renderer (HTML shell, CSS, JS components: graph + sequence diagrams, state lifecycle, field tables, endpoint cards, call-stack trees, diff viewer, symbol drawer, search) | Fixed, reused for every PR | `template/` |
| PR data: metadata, diff, source snippets | `pr_viz.py` from `gh` + `git` — **never typed by the LLM** | workdir |
| PR understanding: what changed, how it flows, what is risky | **The LLM, fresh per PR** | `spec.json` |

The spec only holds structure and prose plus `path:start-end` refs. Code is never pasted into it: the builder resolves every ref against the PR head commit and embeds the snippet, and the full diff comes from `gh pr diff`. That keeps generation cheap (a spec is typically 15–35 KB) while the page stays detailed.

**Starter:** `examples/http-routing.spec.json` illustrates FluidMCP request-ID routing for PR #913. Read it for structure; expand sections and resolve fresh refs for the PR under review. It is not a complete review or evidence of tests run.
**Field reference:** `reference/spec-format.md`.

## Workflow

### 1. Find the PR
```bash
gh pr list --state open --search "<words from the user>" --json number,title,author,headRefName
```
If the user's description (author, title) doesn't match exactly, say what you found and which PR you used.

### 2. Collect
Run from inside a checkout of the repo (any worktree):
```bash
python3 skills/pr-visualization/scripts/pr_viz.py collect <PR> --workdir <scratch>/pr-viz/<PR>
```
Writes `pr.json`, `pr.diff`, `head.json` and **`outline.txt`**: every changed file with the defs it touches, their exact line ranges at the PR head, and added/modified flags. Use those ranges as refs. Do not count lines yourself.

### 3. Understand the PR
Read in this order, and stop when you can explain it:
1. `outline.txt`: the shape of the change.
2. The PR body in `pr.json`: the author's intent.
3. `pr.diff` for non-test files: the actual change.
4. Targeted `git show <head>:<path>` reads for unchanged code the change depends on (auth on the router, helpers it calls, where config is loaded, how the thing is scheduled). `head.json` has the oid.

Verify claims before writing them. A finding needs a ref, and anything you could not verify says so ("likely", "needs a real upstream server").

### 4. Write `spec.json`
Write `<workdir>/spec.json` following `reference/spec-format.md`. Section by section:

| Section | Answers | Keep it to |
|---|---|---|
| `summary` | What does this PR do, and why? | Headline ≤ 35 words, 3–6 `what` bullets, 3–6 `impact` rows |
| `layers` | Which architectural layers does it touch? | 5–8 layers, ordered top-down |
| `data_flow` | **The picture readers look at first:** what comes in → what processes it → where it is stored → what goes out | 6–12 cards in four columns, each with its key fields; arrows labelled with the data that moves. Separate paths (write path / read path) go on separate rows. |
| `data_model` | Details behind the data cards: every **persisted** shape (backend records, server settings, persisted configuration) with all fields, plus stored data the PR newly reads | One entity per stored shape. Add `lifecycle` when a status field drives behaviour. Shown in the side panel and a collapsed Reference list. |
| `api` | Details behind the HTTP/input cards: endpoint contracts, plus `inputs` for schedulers, webhooks, settings, env vars and external reads | Request/response fields from the Pydantic models |
| `flows` | How does it run? | 2–4 tabs. For the main process give **both** a `flowchart` (steps, yes/no decisions, outcomes to the side, loop boxes) and a `graph` call graph (≤ 14 nodes, coloured by layer, numbered steps) of the same run. Add `sequence` diagrams (≤ 16 messages) for request/response or backend calls. |
| `call_stacks` | Who calls what, under which condition, ending in which outcome? | One tree per entry point (CLI command, HTTP route, startup, transport reader) |
| `layout` | Where does the code live? | Every added/modified symbol, plus the unchanged symbols the flows/stacks reference. External systems as a pseudo-file. |
| `diff.annotations` | What should a reviewer notice on a given line? | 6–15 notes, mixing `risk`, `question`, `note` and `praise` |
| `review` | Verdict, findings, tests, gaps, deployment steps | Findings ranked by severity, each with refs and a suggestion |

Write `data_flow` and the main `flowchart` in plain product language ("Match the upstream response to the waiting caller"), with the code name as the `sub` line. They are the parts non-authors read.

Rules that keep the page correct:
- Symbol ids are short and unique (`r.ep`, `s.chat`, `x.mongo`). Every `symbol`, `handler`, `writers`, `readers` and `calls` entry must name one.
- Refs are `path:start-end` at the PR head (single line: `path:42-42`). Get them from `outline.txt` or `grep -n` on `git show <head>:<path>`.
- Diff annotations anchor to a **new-side** line that appears in the diff (an added or context line).
- Prose fields accept `` `code` `` and `**bold**` only.
- Write for a reviewer who has not seen the PR: plain sentences, the real names from the code, no filler.
- Use `skills/production-coding-tenets/SKILL.md` for repository review principles. Check secure-mode dependencies, per-server ownership, event-loop blocking, bounded concurrency, response matching, pending-request cleanup, session lifecycle, and subprocess shutdown where affected.
- Start code tracing at `fluidmcp/cli/cli.py`, `fluidmcp/cli/services/run_servers.py`, `fluidmcp/cli/services/server_manager.py`, and the actual transport implementation. Do not assume all three transports share request matching.
- For routing changes, show `POST /{server}/mcp` and `POST /{server}/mcp/tools/call` separately. Label caller JSON-RPC ID, gateway ID, upstream ID, and session ID at each hop; show restoration on the return path. Notifications have no response ID. Echo markers in tests are separate from protocol IDs and authentication.
- Distinguish `run --file --start-server` from management `serve` mode. Show the real backend and bearer-token checks; do not invent GPT Engine tenant/JWT/database conventions.
- Describe `tests/` and `tests_e2e/` coverage separately. Existing load tests cover Streamable HTTP; do not claim stdio or SSE coverage unless exercised. Test counts in the page describe the code, not execution evidence; record actual commands/results and gaps.

### 5. Build
```bash
python3 skills/pr-visualization/scripts/pr_viz.py build --workdir <workdir> --strict \
  --out <workdir>/pr-<PR>.html
```
`--strict` fails on any spec error: unknown symbol, bad ref, an annotation off the diff, an unknown layer. Fix the spec and rebuild until it reports `0 error(s)`. Without `--strict`, errors still print and also appear as a red banner at the top of the page, so they are never hidden.

### 6. Check once (optional, recommended for a first spec)
If installed, headless Chromium may be in `~/.cache/ms-playwright/chromium-*/chrome-linux64/chrome`. `--screenshot` does not capture after a JS scroll, so to view one section, write a copy that hides the others:
```bash
sed 's|</style>|.section:not(#flows){display:none!important}</style>|' pr-<PR>.html > /tmp/flows.html
chrome --headless=new --no-sandbox --hide-scrollbars --window-size=1440,1600 \
  --virtual-time-budget=3000 --screenshot=/tmp/flows.png file:///tmp/flows.html
```
Section ids: `overview data flows stacks layout diff review`. To screenshot the side panel, append a script that clicks a card or node after load, e.g. `setTimeout(()=>document.querySelector('.dmap-card').click(),400)`.

### 7. Share
- **File:** the default build is a standalone HTML file that opens offline. Link the generated file in your response. Do not commit generated PR data or HTML unless requested.
- Publish only through an available sharing tool when requested. `--artifact` emits a body fragment for a compatible renderer; it does not publish anything by itself.

## What the page gives the reader

Sections, in order:
- **Overview:** headline, bullets, why, changed lines by layer, impact table, and finding counts.
- **Data flow:** a four-column map (Comes in → Processed by → Stored in → Goes out) of cards with their key fields, joined by labelled arrows. Hover to trace a card's data; click for every field, the endpoint contract or the code. Below it are the status lifecycle diagram and a collapsed Reference list (all stored shapes, endpoint contracts, other inputs). At phone width the map becomes a list where each card says where its data goes.
- **Code flow:** tabs of flowcharts (spine of steps, yes/no diamonds, coloured outcomes, dashed loop boxes, coloured by layer) and sequence diagrams.
- **Call stacks:** expandable trees with branch pills, outcome boxes and I/O tags (`sync-io`, `thread`, `network`, `db`).
- **Program layout:** a band per layer with file tiles, then filterable, expandable files with their symbols, signatures and call chips.
- **Diff:** every file, syntax-highlighted, with review notes inline. Tests and docs start collapsed, with a filter for files that have notes.
- **Review:** verdict, severity-ranked findings with refs, tests table, gaps and deployment steps.

**Side panel:** clicking any card, node, symbol or ref opens it. On screens 1000px and wider it docks to the right and the page shrinks beside it, so the diagram stays visible. Drag its left edge to resize, or use the widen button; the width is remembered. It shows the signature, summary, callers/callees and the real source at the PR head (added lines highlighted), with **Show surrounding code** for 20 extra lines either side, and **Show in diff**. On phones it overlays the page.

Global search covers symbols, files and fields. Light/dark/system theme.

## Changing the renderer

Template changes apply to every PR, so keep them generic: PR-specific content belongs in the spec. After editing `template/app.js`, run `node --check template/app.js`, collect FluidMCP PR #913 and rebuild with `--spec skills/pr-visualization/examples/http-routing.spec.json` and look at the affected section. If you add a spec field, document it in `reference/spec-format.md` and, if it references symbols or refs, teach `validate()` in `pr_viz.py` about it.
