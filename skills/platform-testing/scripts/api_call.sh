#!/usr/bin/env bash
# Make ONE API call with curl against the local server and record it as evidence.
#
# Records method, path, HTTP status, curl's client port, timing, the response body
# and a hash of every uploaded file in $RUN_DIR/calls.jsonl. verify_run.py later
# requires each recorded call to appear in the server's own access log with the
# same client port, method, path and status — so a call that never reached the
# server cannot pass as one that did.
#
# Usage: api_call.sh <label> <METHOD> <path?query> [extra curl args...]
#   api_call.sh convert-a POST "/api/fileOperations/convert/?dest_type=pdf" -F "file=@a/Report.pptx"
# NO_AUTH=1 sends no Authorization header (for 401 tests).
# Safe to run several in parallel with `&`.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"

if [ $# -lt 3 ]; then
    echo "Usage: api_call.sh <label> <METHOD> <path?query> [extra curl args...]" >&2
    exit 2
fi
label="$1"
method="$2"
path="$3"
shift 3

RUN_DIR="$(current_run_dir)"
call_id="$(date -u +%H%M%S)-$(od -An -N4 -tx1 /dev/urandom | tr -d ' \n')-${label//[^A-Za-z0-9_.-]/_}"
body_file="$RUN_DIR/calls/$call_id.body"

auth=()
if [ "${NO_AUTH:-}" != "1" ] && [ -f "$TOKEN_FILE" ]; then
    auth=(-H "Authorization: Bearer $(cat "$TOKEN_FILE")")
fi

started_at="$(date -u +%Y-%m-%dT%H:%M:%S.%3NZ)"
meta="$(curl -s -o "$body_file" -w '%{http_code} %{local_port} %{time_total}' \
    -X "$method" "${auth[@]}" "$BASE_URL$path" "$@" || true)"
read -r status local_port time_total <<< "$meta"

python3 -I - "$RUN_DIR/calls.jsonl" "$call_id" "$label" "$method" "$path" "${status:-000}" \
    "${local_port:-0}" "${time_total:-0}" "$started_at" "$body_file" "$@" <<'EOF'
import hashlib, json, os, sys

calls_file, call_id, label, method, path, status, port, seconds, started_at, body_file, *curl_args = sys.argv[1:]

def sha256(file_path):
    with open(file_path, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()

# Uploaded files appear in curl args as `name=@path[;type=...]` or `@path`.
inputs = []
for arg in curl_args:
    if "@" not in arg:
        continue
    candidate = arg.split("@", 1)[1].split(";", 1)[0]
    if os.path.isfile(candidate):
        inputs.append({"path": os.path.abspath(candidate), "bytes": os.path.getsize(candidate), "sha256": sha256(candidate)})

record = {
    "id": call_id, "label": label, "method": method, "path": path,
    "status": int(status), "local_port": int(port), "seconds": float(seconds),
    "started_at": started_at, "inputs": inputs,
    "body_file": body_file,
    "body_sha256": sha256(body_file) if os.path.exists(body_file) else None,
}
with open(calls_file, "a") as handle:
    handle.write(json.dumps(record) + "\n")
EOF

echo "$label: HTTP ${status:-000} in ${time_total:-?}s  body=$body_file"
