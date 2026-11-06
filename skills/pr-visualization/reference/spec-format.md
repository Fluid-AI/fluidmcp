# spec.json format (version 1)

One JSON object. Every top-level section is optional; a section with no content is not rendered and has no nav entry. PR metadata (title, author, branches, stats, commits, dates) and the diff come from `gh` and are **not** part of the spec.

Conventions used below:
- `ref`: `"path:start-end"` at the PR head commit, e.g. `"fluidmcp/cli/services/run_servers.py:30-41"`. A single line is `"path:42-42"`. The builder validates it and embeds the snippet. Any object may carry `ref`; a list field named `refs` holds several.
- `symbol`: the id of a symbol declared in `layout` (see below). Clicking it opens the code drawer.
- `change`: one of `added`, `modified`, `removed`, `renamed`, `unchanged`, `existing`.
- *prose*: plain text with `` `code` `` and `**bold**` allowed. No other markup.

```jsonc
{
  "version": 1,
  "title": "optional <title> override; default 'PR <n> <summary.short_name>'",
  "summary": { ... },
  "layers": [ ... ],
  "data_flow": { ... },
  "data_model": { ... },
  "api": { ... },
  "flows_title": "…", "flows_intro": "prose", "flows": [ ... ],
  "layout": { ... },
  "call_stacks_title": "…", "call_stacks_intro": "prose", "call_stacks": [ ... ],
  "diff": { ... },
  "review": { ... }
}
```

## summary
| Field | Type | Notes |
|---|---|---|
| `short_name` | str | Feature name for the header and page title, 2–4 words (e.g. "Request ID Isolation"). |
| `ticket` | str | Jira key, if any. |
| `headline` | prose | One sentence: what the PR does for the product. |
| `what` | prose[] | 3–6 bullets: the concrete changes. |
| `why` | prose | The problem it solves. |
| `tags` | str[] | Short topic tags. |
| `impact` | `{label, level: high\|medium\|low, text: prose}`[] | Deployment, data, auth, performance and dependency impact. `level` colours the dot. |

## layers
`[{id, label, color}]`, ordered from the top of the stack to the bottom. `color` is one of `blue teal violet amber rose green slate orange`. Ids are used by `layout.groups[].layer`, flow nodes and the footprint bar. If omitted, the defaults are `model, api, service, repository, infra, external, tests`.

Typical set for this repo: `cli` (teal), `api` (blue), `transport` (amber), `service` (violet), plus feature-specific ones (`cli`, `transport`, `process`…), `infra` (slate), `external` (rose), `tests` (green).

## data_flow
The first diagram readers see. Cards sit in columns; `row`/`span` line them up so arrows stay short and the write path and read path read as separate bands.
```jsonc
{ "title": "What data moves where", "intro": "prose",
  "columns": [{ "id": "in", "label": "Comes in" }, { "id": "process", "label": "Processed by" },
              { "id": "store", "label": "Stored in" }, { "id": "out", "label": "Goes out" }],   // this is the default
  "items": [{
    "id": "cls", "column": "process", "row": 1, "span": 4,   // grid placement; rows start at 1
    "kind": "scheduler|setting|env|request|response|endpoint|mailbox|external|existing-data|function|collection|embedded|file|queue",
    "badge": "POST",                       // optional override of the kind's badge text
    "title": "prose", "sub": "prose", "change": "added|modified|existing",
    "fields": ["name", { "name": "FMCP_SECURE_MODE", "note": "true · false" }],   // default: the linked entity's field names
    "max_fields": 6, "bullets": ["prose"],
    // what clicking opens (first match wins):
    "entity": "data_model entity id", "endpoint": "api endpoint id", "input": "api input id or name",
    "symbol": "symbol id", "ref": "path:a-b"
  }],
  "links": [{ "from": "item id", "to": "item id", "label": "the data that moves", "kind": "data|write|call|config|trigger|external" }]
}
```
- Label every link with **what** moves ("tool arguments + upstream request ID"), not how.
- Link kinds: `data` (teal), `write` (amber), `external` (rose), `config` (dotted amber), `trigger` (dashed violet), `call` (grey).
- Each endpoint in `api.endpoints` needs an `id` for `endpoint` to point at it. The same endpoint can back both a request card and a response card.

## data_model
```jsonc
{
  "title": "…", "intro": "prose",
  "entities": [{
    "id": "serverConfig",               // anchor for search
    "name": "chats.emailMetadata.serverConfig",
    "kind": "mongo-embedded",              // mongo-collection | mongo-embedded | mongo-field | setting | env | vector | pydantic-api …
    "store": "Configuration file · mcpServers",
    "change": "added",
    "summary": "prose",
    "fields": [ FIELD ],
    "writers": ["symbol"], "readers": ["symbol"],
    "notes": ["prose"],
    "example": { },                        // any JSON; shown collapsed
    "example_label": "Example document",
    "ref": "path:a-b"
  }],
  "lifecycle": {                           // optional state machine, drawn left-to-right
    "title": "…", "description": "prose", "direction": "LR",
    "states": [{ "id", "label", "kind": "initial|process|retry|final|terminal-error", "desc": "prose", "col": 2 }],
    "transitions": [{ "from", "to", "label", "kind": "retry" }]
  }
}
```
`FIELD` = `{ name, type, change, required: bool, desc: prose, values: [str], default, example }`. The same shape is used for API request/response fields.

Put here only what is **stored** (backend records, server settings, configuration files). Request/response models go under `api`. Include an `existing` entity for stored fields the PR newly *reads*, because reviewers need to see that dependency.

## api
```jsonc
{
  "title": "…", "intro": "prose",
  "endpoints": [{
    "method": "POST", "path": "/{server}/mcp", "change": "added",
    "router": "fluidmcp/cli/services/run_servers.py", "handler": "symbol",
    "auth": "prose: validator and where it comes from (router-level vs endpoint)",
    "summary": "prose",
    "request":  { "model": "Name", "ref": "fluidmcp/cli/models/server.py:a-b", "fields": [FIELD], "example": {} },
    "response": { "model": "Name", "ref": "…", "fields": [FIELD], "example": {} },
    "errors": [{ "status": 422, "when": "prose" }],
    "notes": ["prose"]
  }],
  "inputs_title": "…", "inputs_intro": "prose",
  "inputs": [{ "kind": "scheduler|webhook|consumer|setting|env|external-read|file", "name", "change", "default", "desc": "prose", "ref" }]
}
```
`inputs` is for everything that brings data or configuration into the platform without being a new HTTP route.

## flows
Each flow is one tab. Three kinds:

**Flowchart** (`"kind": "flowchart"`): the default for "how does this run":
```jsonc
{ "id", "title", "kind": "flowchart", "description": "prose",
  "nodes": [{ "id", "kind": "start|step|decision|end", "label": "prose (plain language)", "sub": "code name / file",
              "layer": "layer id", "symbol": "id", "ref": "…", "change": "added",
              "side": "right|left",          // omit for the main spine; set for outcomes and early exits
              "tone": "good|bad|warn" }],     // colours end nodes: verdicts, errors, retryable states
  "edges": [{ "from", "to", "label": "yes|no|…", "kind": "retry" }],
  "groups": [{ "label": "for each server · one at a time", "from": "first spine node id", "to": "last spine node id" }] }
```
- Spine nodes are drawn top-down **in the order listed**. A side node sits on the row of the node that branches to it.
- An edge back up the spine (e.g. "next server") is routed down the left margin; mark it `"kind": "retry"`.
- Decision labels are questions. Label their exits `yes` / `no` (coloured green and red).

**Graph** (`"kind": "graph"`), laid out top-down by default (`"direction": "LR"` for left-to-right swimlanes):
```jsonc
{ "id", "title", "kind": "graph", "description": "prose",
  "nodes": [{ "id", "label", "sub": "small second line", "layer": "layer id", "symbol": "id",
              "ref": "…", "shape": "box|pill|db", "change": "added|modified|existing", "tip": "hover text", "col": 3 }],
  "edges": [{ "from", "to", "label", "kind": "call|data|write|async|external|return|retry", "step": 1 }],
  "steps": [{ "text": "prose", "symbol": "id", "ref": "…" }] }
```
- Ranks come from the edges (longest path); cycles are detected and drawn as return arcs. `col` pins a node's rank.
- Keep labels short (≤ 22 chars) and sub-lines ≤ 28 chars; long names can be abbreviated with `…`.
- `step` numbers the main path. `steps` repeats it as numbered prose under the diagram.
- `shape: "db"` for stores and external systems, `pill` for triggers.

**Sequence** (`"kind": "sequence"`):
```jsonc
{ "id", "title", "kind": "sequence", "description": "prose",
  "participants": [{ "id", "label", "sub", "layer", "symbol" }],
  "messages": [
    { "from", "to", "label", "kind": "call|return|async|external", "symbol": "id", "ref": "…", "tip": "…" },
    { "kind": "divider", "label": "branch / phase title" },
    { "kind": "note", "from", "to", "label": "prose" }
  ] }
```
A message from a participant to itself draws a self-loop. Messages are numbered automatically.

## layout
The symbol registry and the L2 program layout.
```jsonc
{ "title": "…", "intro": "prose",
  "groups": [{
    "layer": "layer id", "summary": "prose",
    "files": [{
      "path": "fluidmcp/cli/services/run_servers.py",             // use a pseudo path like "(external systems)" for non-code nodes
      "change": "added|modified|existing", "summary": "prose",
      "symbols": [{
        "id": "s.route",                    // unique, short
        "name": "route_request",
        "kind": "function|async function|method|class|model|route|constant|settings|test class|database|REST API …",
        "change": "added|modified|unchanged|existing",
        "signature": "one or two lines, real code",
        "summary": "prose",
        "tags": ["sync-io", "db", "network", "thread", "async", "blocking", "per-worker", "import-time"],
        "calls": ["symbol ids"],
        "notes": ["prose"],
        "ref": "path:a-b"
      }]
    }]
  }]
}
```
- Include every added/modified function, class or constant from `outline.txt`, plus unchanged symbols that flows or stacks reference (shared helpers, the router object, config loaders), and external systems.
- `calls` builds the callee/caller lists in the drawer, so keep it to the calls that matter for understanding.
- Tags with built-in colours: `blocking`/`sync-io` (red), `thread`/`async` (blue), `io`/`network`/`db` (amber).

## call_stacks
```jsonc
{ "id", "title", "trigger": "POST /{server}/mcp | CLI | startup", "description": "prose",
  "expand_depth": 3,
  "root": FRAME }
```
`FRAME` = `{ symbol | label, ref, tags: [], note: prose, branch: "condition text", outcome: true, children: [FRAME] }`
- `symbol` renders a clickable chip (its ref comes from the symbol); `label` renders plain mono text (use it for loops, library calls and inline expressions).
- `branch` shows an amber pill: the condition under which this frame runs.
- `outcome: true` marks a leaf that is a result (status written, response returned, early exit).

## diff
```jsonc
{ "intro": "prose",
  "collapse": ["tests/*", "*.md"],          // fnmatch globs that start collapsed (default shown)
  "order": ["fluidmcp/cli/…", "tests_e2e/…"],       // file order; unlisted files follow layout order, then the rest
  "annotations": [{ "file", "line": 256, "kind": "risk|question|note|praise", "text": "prose" }] }
```
`line` is the **new-side** line number and must be visible in the diff (an added or context line). The builder rejects anything else.

## review
```jsonc
{ "title": "…", "intro": "prose",
  "verdict": "prose", "verdict_level": "approve|comment|changes",
  "findings": [{ "id", "severity": "high|medium|low|info", "category": "correctness|concurrency|security|…",
                 "title": "prose", "detail": "prose", "suggestion": "prose", "refs": ["path:a-b"] }],
  "tests": [{ "file", "what": "prose", "count": 20 }],
  "untested": ["prose"],
  "deployment": ["prose"] }
```
Severity guide: **high**: wrong results or data loss in normal use; **medium**: wrong under specific but realistic conditions, or an operational trap; **low**: maintainability, debuggability, minor inefficiency; **info**: context.
