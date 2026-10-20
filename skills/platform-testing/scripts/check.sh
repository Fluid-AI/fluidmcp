#!/usr/bin/env bash
# Record ONE assertion about the test results: runs a command, compares its output
# to what was expected, and logs expected, actual and the command itself to
# $RUN_DIR/checks.jsonl. PASS/FAIL is computed here, never typed by hand.
#
# Usage: check.sh <label> <expected> '<shell command printing the actual value>'
#   check.sh "health status" "healthy" 'jq -r .status "$RUN_DIR"/calls/*health.body'
# The command runs with RUN_DIR, BASE_URL and TOKEN_FILE exported.
# Output is compared after trimming surrounding whitespace. Exits 1 on FAIL.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"

if [ $# -ne 3 ]; then
    echo "Usage: check.sh <label> <expected> '<command>'" >&2
    exit 2
fi
label="$1"
expected="$2"
command="$3"

RUN_DIR="$(current_run_dir)"
export RUN_DIR BASE_URL TOKEN_FILE

exit_code=0
actual="$(bash -c "$command" 2>&1)" || exit_code=$?

python3 -I - "$RUN_DIR/checks.jsonl" "$label" "$expected" "$actual" "$command" "$exit_code" <<'EOF'
import json, sys
from datetime import datetime, timezone

checks_file, label, expected, actual, command, exit_code = sys.argv[1:]
passed = int(exit_code) == 0 and expected.strip() == actual.strip()
with open(checks_file, "a") as handle:
    handle.write(json.dumps({
        "label": label, "expected": expected, "actual": actual, "command": command,
        "passed": passed, "exit_code": int(exit_code), "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }) + "\n")
print(f"{'PASS' if passed else 'FAIL'}: {label}  (expected {expected.strip()!r}, got {actual.strip()[:200]!r})")
sys.exit(0 if passed else 1)
EOF
