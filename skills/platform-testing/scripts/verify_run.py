#!/usr/bin/env python3
"""
Independently verify a platform-testing run and print its report.

Run it yourself on the RUN_DIR an agent reports — don't rely on output the agent
pasted. It trusts nothing the agent typed; every claim is checked against
something the agent did not write:

  1. The server really ran: the uvicorn log in the run dir must show the same
     process id that start_local_server.sh recorded, listening on the recorded
     port, with startup completed.
  2. Every call really reached that server: each entry in calls.jsonl (written by
     api_call.sh from curl's own output) must match an access-log line written
     by the server, on client port + method + path + status.
  3. Evidence was not edited afterwards: response bodies and uploaded inputs must
     still hash to what was recorded at call time.
  4. Results were checked, not asserted: there must be at least one check, and
     PASS is recomputed here from the recorded expected and actual values.

Exit code 0 only when everything holds. Usage:
    python3 verify_run.py [RUN_DIR]     # default: the current run on PORT (8010)
"""
import hashlib
import json
import os
import re
import subprocess
import sys
from collections import Counter
from datetime import datetime

ANSI = re.compile(r"\x1b\[[0-9;]*m")
ACCESS_LINE = re.compile(r'127\.0\.0\.1:(\d+) - "([A-Z]+) (\S+) HTTP/[\d.]+" (\d{3})')


def default_run_dir():
    port = os.getenv("PORT", "8010")
    pointer = os.path.join(os.getenv("TMPDIR", "/tmp"), f"fluidgpt-local-server-{port}", "current_run")
    if not os.path.isfile(pointer):
        sys.exit(f"No RUN_DIR given and no current run at {pointer}")
    return open(pointer).read().strip()


def read_jsonl(path):
    if not os.path.isfile(path):
        return []
    with open(path) as handle:
        return [json.loads(line) for line in handle if line.strip()]


def sha256(path):
    with open(path, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


def main():
    run_dir = sys.argv[1] if len(sys.argv) > 1 else default_run_dir()
    problems = []
    warnings = []

    run_file = os.path.join(run_dir, "run.json")
    log_file = os.path.join(run_dir, "server.log")
    if not (os.path.isfile(run_file) and os.path.isfile(log_file)):
        print(f"NOT VERIFIED: {run_dir} has no run.json/server.log — start_local_server.sh never ran here.")
        return 1
    run = json.load(open(run_file))
    log = ANSI.sub("", open(log_file, errors="replace").read())

    # 1. The server process recorded at start is the one that wrote this log.
    if f"Started server process [{run['pid']}]" not in log:
        problems.append(f"server.log has no 'Started server process [{run['pid']}]' — not the recorded server")
    if f"Uvicorn running on http://127.0.0.1:{run['port']}" not in log:
        problems.append(f"server.log does not show uvicorn listening on port {run['port']}")
    if "Application startup complete" not in log:
        problems.append("server.log never reached 'Application startup complete'")

    # 2. Each recorded call appears in the server's access log.
    served = Counter(ACCESS_LINE.findall(log))
    calls = read_jsonl(os.path.join(run_dir, "calls.jsonl"))
    if not calls:
        problems.append("no API calls recorded (calls.jsonl missing or empty)")
    for call in calls:
        key = (str(call["local_port"]), call["method"], call["path"], str(call["status"]))
        if served[key] > 0:
            served[key] -= 1
            call["seen_by_server"] = True
        else:
            call["seen_by_server"] = False
            problems.append(f"call '{call['label']}' ({call['method']} {call['path']} -> {call['status']}) is not in the server access log")

        # 3. Evidence still matches what was recorded.
        if call.get("body_sha256") and (not os.path.isfile(call["body_file"]) or sha256(call["body_file"]) != call["body_sha256"]):
            problems.append(f"response body of '{call['label']}' was changed or removed after the call")
        for item in call.get("inputs", []):
            if not os.path.isfile(item["path"]):
                warnings.append(f"input {item['path']} of '{call['label']}' no longer exists (hash not re-checked)")
            elif sha256(item["path"]) != item["sha256"]:
                problems.append(f"input {item['path']} of '{call['label']}' changed after it was sent")

    # 4. Checks: recompute, don't trust the stored flag.
    checks = read_jsonl(os.path.join(run_dir, "checks.jsonl"))
    if not checks:
        problems.append("no checks recorded — status codes alone don't show the output was correct")
    for check in checks:
        check["passed"] = check["expected"].strip() == check["actual"].strip()
        if not check["passed"]:
            problems.append(f"check failed: {check['label']}")

    # Which code was tested.
    try:
        head = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True,
                              cwd=os.path.dirname(os.path.abspath(__file__))).stdout.strip()
        if head and head != run["commit"]:
            warnings.append(f"this checkout is now at {head[:9]}; the run tested {run['commit'][:9]}")
    except OSError:
        pass
    if run.get("uncommitted_changes"):
        warnings.append("the server ran with uncommitted changes in the checkout")

    # Report.
    print(f"Run:     {run_dir}")
    print(f"Code:    {run['branch']} @ {run['commit'][:9]}  (server pid {run['pid']}, port {run['port']}, started {run['started_at']})")
    print(f"Deps:    {run.get('dependencies', 'not recorded')}")
    print()
    print(f"API calls ({len(calls)}):")
    for call in calls:
        mark = "✓" if call["seen_by_server"] else "✗ NOT IN SERVER LOG"
        print(f"  {mark:<3} {call['status']}  {call['seconds']:>6.2f}s  {call['method']} {call['path']}  [{call['label']}]")
    print()
    print(f"Checks ({len(checks)}):")
    for check in checks:
        print(f"  {'PASS' if check['passed'] else 'FAIL'}  {check['label']}: expected {check['expected'].strip()!r}, got {check['actual'].strip()[:120]!r}")
    print()
    for warning in warnings:
        print(f"WARNING: {warning}")
    if problems:
        print("NOT VERIFIED:")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    passed = sum(check["passed"] for check in checks)
    print(f"VERIFIED: {len(calls)}/{len(calls)} calls seen by the server, {passed}/{len(checks)} checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
