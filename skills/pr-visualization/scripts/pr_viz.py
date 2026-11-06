#!/usr/bin/env python3
"""
PR visualization builder (stdlib only — runs with the system python3, no project virtualenv needed).

  collect  Fetch PR metadata + diff with `gh`, fetch the PR head commit with `git`, and write
           an outline of every changed Python file (functions/classes with line ranges, marked
           added/modified/unchanged). The outline gives the spec author exact `path:start-end`
           refs without having to read whole files.

  build    Validate the LLM-written spec.json against the diff and the head commit, resolve every
           code ref to a source snippet, and inline template + data into one self-contained HTML.

Usage:
  python3 pr_viz.py collect 913 [--workdir DIR] [--repo OWNER/NAME]
  python3 pr_viz.py build --workdir DIR [--spec DIR/spec.json] [--out FILE.html] [--artifact] [--strict]
"""
import argparse
import ast
import fnmatch
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE_DIR = os.path.join(SKILL_DIR, "template")
PR_FIELDS = ("number,title,author,url,state,isDraft,headRefName,baseRefName,headRefOid,"
             "additions,deletions,changedFiles,createdAt,updatedAt,body,files,commits")
REF_RE = re.compile(r"^(?P<path>[^:#\s]+):(?P<start>\d+)(?:-(?P<end>\d+))?$")
SNIPPET_MAX_LINES = 160      # refs longer than this are truncated (with a visible marker)
SNIPPET_CONTEXT = 20         # extra lines embedded around each ref, revealed by "Show surrounding code"


def run(cmd, cwd=None, check=True):
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if check and result.returncode != 0:
        sys.exit(f"Command failed: {' '.join(cmd)}\n{result.stderr.strip()}")
    return result


def default_workdir(number):
    return os.path.join(os.environ.get("TMPDIR", "/tmp"), "pr-viz", str(number))


# ── Diff parsing ─────────────────────────────────────────────────────────────

HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(.*)$")


def parse_unified_diff(text):
    """Parse `gh pr diff` output into [{path, oldPath, status, additions, deletions, binary, hunks}].
    Each hunk line is [type, old_no, new_no, text] with type one of '+', '-', ' '."""
    files, current, hunk = [], None, None
    old_no = new_no = 0
    for raw in text.splitlines():
        if raw.startswith("diff --git "):
            m = re.match(r"diff --git a/(.*) b/(.*)$", raw)
            current = {"path": m.group(2) if m else raw[11:], "oldPath": m.group(1) if m else None,
                       "status": "modified", "additions": 0, "deletions": 0, "binary": False, "hunks": []}
            files.append(current)
            hunk = None
            continue
        if current is None:
            continue
        if hunk is None:
            if raw.startswith("new file mode"):
                current["status"] = "added"
            elif raw.startswith("deleted file mode"):
                current["status"] = "removed"
            elif raw.startswith("rename to "):
                current["status"] = "renamed"
            elif raw.startswith("Binary files"):
                current["binary"] = True
        m = HUNK_RE.match(raw)
        if m:
            old_no, new_no = int(m.group(1)), int(m.group(3))
            hunk = {"header": raw, "context": m.group(5).strip(), "lines": []}
            current["hunks"].append(hunk)
            continue
        if hunk is None:
            continue
        if raw.startswith("+"):
            hunk["lines"].append(["+", None, new_no, raw[1:]])
            current["additions"] += 1
            new_no += 1
        elif raw.startswith("-"):
            hunk["lines"].append(["-", old_no, None, raw[1:]])
            current["deletions"] += 1
            old_no += 1
        elif raw.startswith("\\"):
            continue  # "\ No newline at end of file"
        else:
            hunk["lines"].append([" ", old_no, new_no, raw[1:] if raw.startswith(" ") else raw])
            old_no += 1
            new_no += 1
    return files


def added_lines_by_file(diff_files):
    return {f["path"]: {ln[2] for h in f["hunks"] for ln in h["lines"] if ln[0] == "+"} for f in diff_files}


def new_side_lines_by_file(diff_files):
    return {f["path"]: {ln[2] for h in f["hunks"] for ln in h["lines"] if ln[2] is not None} for f in diff_files}


# ── Source access at the PR head ─────────────────────────────────────────────

class HeadSource:
    def __init__(self, oid, cwd):
        self.oid, self.cwd, self._cache = oid, cwd, {}

    def lines(self, path):
        if path not in self._cache:
            result = run(["git", "show", f"{self.oid}:{path}"], cwd=self.cwd, check=False)
            self._cache[path] = result.stdout.splitlines() if result.returncode == 0 else None
        return self._cache[path]


def outline_python(path, lines, added):
    """Outline rows for a Python file: each def/class/assignment touched by the PR, with its line range."""
    try:
        tree = ast.parse("\n".join(lines))
    except SyntaxError as e:
        return [f"  !! could not parse: {e}"]
    rows = []

    def change_of(node):
        span = set(range(node.lineno, (node.end_lineno or node.lineno) + 1))
        hit = len(span & added)
        if hit == 0:
            return "unchanged"
        return "added" if hit >= len(span) * 0.9 else "modified"

    def visit(nodes, depth):
        for node in nodes:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                kind = {"FunctionDef": "def", "AsyncFunctionDef": "async def", "ClassDef": "class"}[type(node).__name__]
                change = change_of(node)
                if change != "unchanged":
                    rows.append(f"{'  ' * (depth + 1)}{path}:{node.lineno}-{node.end_lineno}  {kind} {node.name}  [{change}]")
                    if isinstance(node, ast.ClassDef):
                        visit(node.body, depth + 1)
            elif depth == 0 and isinstance(node, ast.Assign) and change_of(node) != "unchanged":
                names = [t.id for t in node.targets if isinstance(t, ast.Name)]
                if names:
                    rows.append(f"  {path}:{node.lineno}-{node.end_lineno}  const {', '.join(names)}  [{change_of(node)}]")

    visit(tree.body, 0)
    return rows or ["  (no changed defs — change is at module level)"]


# ── collect ──────────────────────────────────────────────────────────────────

def cmd_collect(args):
    workdir = os.path.abspath(args.workdir or default_workdir(args.number))
    os.makedirs(workdir, exist_ok=True)
    repo_flag = ["--repo", args.repo] if args.repo else []
    git_root = run(["git", "rev-parse", "--show-toplevel"]).stdout.strip()

    pr_json = run(["gh", "pr", "view", str(args.number), "--json", PR_FIELDS, *repo_flag]).stdout
    meta = json.loads(pr_json)
    if not meta.get("headRefOid"):
        sys.exit("gh returned no headRefOid for this PR")
    with open(os.path.join(workdir, "pr.json"), "w") as f:
        f.write(pr_json)
    diff_text = run(["gh", "pr", "diff", str(args.number), *repo_flag]).stdout
    with open(os.path.join(workdir, "pr.diff"), "w") as f:
        f.write(diff_text)

    run(["git", "fetch", "-q", "origin", f"pull/{args.number}/head:refs/pr-viz/{args.number}"], cwd=git_root)
    head = run(["git", "rev-parse", f"refs/pr-viz/{args.number}"], cwd=git_root).stdout.strip()
    if head != meta["headRefOid"]:
        print(f"warning: fetched head {head[:9]} differs from gh headRefOid {meta['headRefOid'][:9]}", file=sys.stderr)

    diff_files = parse_unified_diff(diff_text)
    added = added_lines_by_file(diff_files)
    source = HeadSource(head, git_root)
    out = [f"# PR #{meta['number']}: {meta['title']}",
           f"# head {head}  ({meta['headRefName']} -> {meta['baseRefName']})",
           "# Changed files with their touched defs at the PR head. Use these path:start-end values as `ref`s in spec.json.", ""]
    for f in diff_files:
        out.append(f"{f['path']}  [{f['status']}]  +{f['additions']} -{f['deletions']}")
        lines = source.lines(f["path"])
        if f["path"].endswith(".py") and lines is not None:
            out.extend(outline_python(f["path"], lines, added.get(f["path"], set())))
        ranges = []
        for h in f["hunks"]:
            new_nos = [ln[2] for ln in h["lines"] if ln[2]]
            if new_nos:
                ranges.append(f"{min(new_nos)}..{max(new_nos)}")
        out.append(f"  hunks (new-side lines): {', '.join(ranges) or '-'}")
        out.append("")
    with open(os.path.join(workdir, "outline.txt"), "w") as fh:
        fh.write("\n".join(out))
    with open(os.path.join(workdir, "head.json"), "w") as fh:
        json.dump({"oid": head, "gitRoot": git_root, "number": args.number}, fh)

    print(f"workdir: {workdir}")
    print(f"  pr.json, pr.diff ({len(diff_files)} files), outline.txt, head.json")
    print(f"Next: write {os.path.join(workdir, 'spec.json')} (see reference/spec-format.md), then run build.")


# ── build ────────────────────────────────────────────────────────────────────

def walk_refs(node, found):
    """Collect every code ref string in the spec (keys `ref` and `refs`)."""
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "ref" and isinstance(value, str):
                found.add(value)
            elif key == "refs" and isinstance(value, list):
                found.update(v for v in value if isinstance(v, str))
            else:
                walk_refs(value, found)
    elif isinstance(node, list):
        for item in node:
            walk_refs(item, found)


def iter_frames(frame):
    yield frame
    for child in frame.get("children") or []:
        yield from iter_frames(child)


def validate(spec, diff_files, source):
    """Return (errors, warnings, refs). Errors render wrong or missing; warnings are hints."""
    errors, warnings = [], []
    diff_paths = {f["path"] for f in diff_files}
    new_lines = new_side_lines_by_file(diff_files)

    layer_ids = {layer["id"] for layer in spec.get("layers") or []}
    symbols = {}
    for group in (spec.get("layout") or {}).get("groups") or []:
        if layer_ids and group.get("layer") not in layer_ids:
            errors.append(f"layout group uses unknown layer {group.get('layer')!r}")
        for file in group.get("files") or []:
            for sym in file.get("symbols") or []:
                if sym.get("id") in symbols:
                    errors.append(f"duplicate symbol id {sym.get('id')!r}")
                symbols[sym.get("id")] = sym
    for sym in symbols.values():
        for callee in sym.get("calls") or []:
            if callee not in symbols:
                warnings.append(f"symbol {sym['id']!r} calls unknown symbol {callee!r}")

    def check_symbol(value, where):
        if value and value not in symbols:
            errors.append(f"{where} references unknown symbol {value!r}")

    for entity in (spec.get("data_model") or {}).get("entities") or []:
        for sid in (entity.get("writers") or []) + (entity.get("readers") or []):
            check_symbol(sid, f"entity {entity.get('id')!r}")
    for ep in (spec.get("api") or {}).get("endpoints") or []:
        check_symbol(ep.get("handler"), f"endpoint {ep.get('path')!r}")
    for flow in spec.get("flows") or []:
        node_ids = {n["id"] for n in flow.get("nodes") or []} | {p["id"] for p in flow.get("participants") or []}
        for node in (flow.get("nodes") or []) + (flow.get("participants") or []):
            check_symbol(node.get("symbol"), f"flow {flow.get('id')!r} node {node.get('id')!r}")
            if layer_ids and node.get("layer") and node["layer"] not in layer_ids:
                errors.append(f"flow {flow.get('id')!r} node {node['id']!r} has unknown layer {node['layer']!r}")
        for edge in (flow.get("edges") or []) + (flow.get("messages") or []):
            check_symbol(edge.get("symbol"), f"flow {flow.get('id')!r} message {edge.get('label')!r}")
            for end in ("from", "to"):
                if edge.get(end) and edge[end] not in node_ids:
                    errors.append(f"flow {flow.get('id')!r}: {end}={edge[end]!r} is not a node/participant")
        for step in flow.get("steps") or []:
            check_symbol(step.get("symbol"), f"flow {flow.get('id')!r} step")
    for stack in spec.get("call_stacks") or []:
        for frame in iter_frames(stack.get("root") or {}):
            check_symbol(frame.get("symbol"), f"call stack {stack.get('id')!r}")
    for flow in spec.get("flows") or []:
        node_ids = {n["id"] for n in flow.get("nodes") or []}
        for group in flow.get("groups") or []:
            for end in ("from", "to"):
                if group.get(end) not in node_ids:
                    errors.append(f"flow {flow.get('id')!r} group {group.get('label')!r}: {end}={group.get(end)!r} is not a node")

    data_flow = spec.get("data_flow") or {}
    entity_ids = {e.get("id") for e in (spec.get("data_model") or {}).get("entities") or []}
    endpoint_ids = {ep.get("id") for ep in (spec.get("api") or {}).get("endpoints") or []}
    input_ids = {i.get("id") or i.get("name") for i in (spec.get("api") or {}).get("inputs") or []}
    column_ids = {c.get("id") for c in data_flow.get("columns") or []} or {"in", "process", "store", "out"}
    item_ids = set()
    for item in data_flow.get("items") or []:
        item_ids.add(item.get("id"))
        if item.get("column") not in column_ids:
            errors.append(f"data_flow item {item.get('id')!r} has unknown column {item.get('column')!r}")
        for key, known in (("entity", entity_ids), ("endpoint", endpoint_ids), ("input", input_ids)):
            if item.get(key) and item[key] not in known:
                errors.append(f"data_flow item {item.get('id')!r}: {key}={item[key]!r} does not exist")
        check_symbol(item.get("symbol"), f"data_flow item {item.get('id')!r}")
    for link in data_flow.get("links") or []:
        for end in ("from", "to"):
            if link.get(end) not in item_ids:
                errors.append(f"data_flow link {end}={link.get(end)!r} is not an item")

    lifecycle = (spec.get("data_model") or {}).get("lifecycle") or {}
    state_ids = {s["id"] for s in lifecycle.get("states") or []}
    for t in lifecycle.get("transitions") or []:
        for end in ("from", "to"):
            if t.get(end) not in state_ids:
                errors.append(f"lifecycle transition {end}={t.get(end)!r} is not a state")

    for ann in (spec.get("diff") or {}).get("annotations") or []:
        if ann.get("file") not in diff_paths:
            errors.append(f"diff annotation on {ann.get('file')!r}, which is not in the diff")
        elif ann.get("line") not in new_lines.get(ann["file"], set()):
            errors.append(f"diff annotation {ann['file']}:{ann.get('line')} is not a new-side line shown in the diff")

    refs = set()
    walk_refs(spec, refs)
    for ref in sorted(refs):
        m = REF_RE.match(ref)
        if not m:
            errors.append(f"bad ref {ref!r} (expected path:start-end)")
            continue
        lines = source.lines(m.group("path"))
        if lines is None:
            errors.append(f"ref {ref!r}: file not found at the PR head")
        elif int(m.group("end") or m.group("start")) > len(lines):
            errors.append(f"ref {ref!r}: past end of file ({len(lines)} lines)")
    return errors, warnings, refs


def resolve_sources(refs, source, diff_files):
    added = added_lines_by_file(diff_files)
    sources = {}
    for ref in refs:
        m = REF_RE.match(ref)
        if not m:
            continue
        path, start = m.group("path"), int(m.group("start"))
        end = int(m.group("end") or start)
        lines = source.lines(path)
        if lines is None:
            continue
        focus_start, focus_end = max(1, start), min(len(lines), end)
        truncated = focus_end - focus_start + 1 > SNIPPET_MAX_LINES
        if truncated:
            focus_end = focus_start + SNIPPET_MAX_LINES - 1
        lo, hi = max(1, focus_start - SNIPPET_CONTEXT), min(len(lines), focus_end + SNIPPET_CONTEXT)
        sources[ref] = {"path": path, "start": lo, "end": hi, "focusStart": focus_start, "focusEnd": focus_end,
                        "truncated": truncated, "lines": lines[lo - 1:hi],
                        "added": sorted(n for n in added.get(path, set()) if lo <= n <= hi)}
    return sources


def build_meta(pr):
    return {
        "number": pr.get("number"), "title": pr.get("title"), "url": pr.get("url"),
        "author": (pr.get("author") or {}).get("login"), "state": pr.get("state"), "isDraft": pr.get("isDraft"),
        "head": pr.get("headRefName"), "base": pr.get("baseRefName"), "headOid": pr.get("headRefOid"),
        "additions": pr.get("additions"), "deletions": pr.get("deletions"), "changedFiles": pr.get("changedFiles"),
        "createdAt": pr.get("createdAt"), "updatedAt": pr.get("updatedAt"),
        "commits": len(pr.get("commits") or []),
        "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    }


def apply_collapse(spec, diff_files):
    patterns = (spec.get("diff") or {}).get("collapse") or ["tests/*", "*.md"]
    for f in diff_files:
        f["collapsed"] = any(fnmatch.fnmatch(f["path"], p) for p in patterns)


def html_escape(text):
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def render_html(title, payload, artifact):
    def read(name):
        with open(os.path.join(TEMPLATE_DIR, name)) as fh:
            return fh.read()
    # "</" inside inline JSON would end the <script> tag early.
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str).replace("</", "<\\/")
    # Plain str.replace on the placeholders: no regex, so code and JSON pass through untouched.
    body = (read("index.html")
            .replace("{{TITLE}}", html_escape(title))
            .replace("/*{{STYLES}}*/", read("styles.css"))
            .replace("/*{{DATA}}*/", f"window.PR_DATA = {data};")
            .replace("/*{{APP}}*/", read("app.js")))
    if artifact:
        return body  # the Artifact publisher adds doctype/head/body itself
    return ("<!doctype html>\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">\n"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1, viewport-fit=cover\">\n"
            "</head>\n<body>\n" + body + "\n</body>\n</html>\n")


def cmd_build(args):
    workdir = os.path.abspath(args.workdir)
    spec_path = args.spec or os.path.join(workdir, "spec.json")
    with open(os.path.join(workdir, "pr.json")) as fh:
        pr = json.load(fh)
    with open(os.path.join(workdir, "pr.diff")) as fh:
        diff_files = parse_unified_diff(fh.read())
    with open(os.path.join(workdir, "head.json")) as fh:
        head = json.load(fh)
    try:
        with open(spec_path) as fh:
            spec = json.load(fh)
    except json.JSONDecodeError as e:
        sys.exit(f"{spec_path} is not valid JSON: {e}")

    source = HeadSource(head["oid"], head["gitRoot"])
    errors, warnings, refs = validate(spec, diff_files, source)
    for w in warnings:
        print(f"warning: {w}", file=sys.stderr)
    for e in errors:
        print(f"error: {e}", file=sys.stderr)
    if errors and args.strict:
        sys.exit(f"{len(errors)} spec error(s); fix them or drop --strict")

    apply_collapse(spec, diff_files)
    payload = {"meta": build_meta(pr), "spec": spec, "diff": diff_files,
               "sources": resolve_sources(refs, source, diff_files),
               "issues": {"errors": errors, "warnings": warnings}}
    short = (spec.get("summary") or {}).get("short_name") or pr.get("title")
    title = spec.get("title") or f"PR {pr.get('number')} {short}"
    out = args.out or os.path.join(workdir, f"pr-{pr.get('number')}.html")
    with open(out, "w") as fh:
        fh.write(render_html(title, payload, args.artifact))
    size_kb = os.path.getsize(out) / 1024
    print(f"wrote {out} ({size_kb:.0f} KB) — {len(errors)} error(s), {len(warnings)} warning(s)")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    c = sub.add_parser("collect", help="fetch PR data and write outline.txt")
    c.add_argument("number", type=int)
    c.add_argument("--workdir")
    c.add_argument("--repo")
    b = sub.add_parser("build", help="validate spec.json and render the HTML")
    b.add_argument("--workdir", required=True)
    b.add_argument("--spec")
    b.add_argument("--out")
    b.add_argument("--artifact", action="store_true", help="emit a body fragment for the Artifact publisher")
    b.add_argument("--strict", action="store_true", help="exit non-zero on spec errors")
    args = parser.parse_args()
    {"collect": cmd_collect, "build": cmd_build}[args.command](args)


if __name__ == "__main__":
    main()
