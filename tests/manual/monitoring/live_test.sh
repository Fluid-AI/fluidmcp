#!/usr/bin/env bash
# End-to-end live test of the MCP monitoring stack.
#
# Starts a real FluidMCP gateway, registers an MCP whose "database" can be
# broken on demand, and asserts that the monitoring API reports each failure
# class correctly — including the one no process-level check can see.
#
# Usage:  bash tests/manual/monitoring/live_test.sh [PORT]
set -u

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../../.." && pwd)"
PORT="${1:-8123}"
BASE="http://127.0.0.1:$PORT"
LOG="$(mktemp -t fmcp-live-XXXXXX.log)"
PASS=0; FAIL=0

ok()  { echo "  ✅ $1"; PASS=$((PASS+1)); }
bad() { echo "  ❌ $1"; [ -n "${2:-}" ] && echo "       got: $2"; FAIL=$((FAIL+1)); }
j()   { python3 -c "import sys,json;d=json.load(sys.stdin);print($1)" 2>/dev/null; }
srv() { curl -s "$BASE/api/monitoring/health" | python3 -c "
import sys,json
d=json.load(sys.stdin)
m=[s for s in d['servers'] if s['id']=='customer-sql']
print(json.dumps(m[0] if m else {}))" 2>/dev/null; }
call(){ curl -s -X POST "$BASE/customer-sql/mcp" -H 'Content-Type: application/json' \
        -d "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/call\",\"params\":{\"name\":\"$1\",\"arguments\":$2}}" >/dev/null 2>&1; }

rm -f /tmp/_fakesql_broken /tmp/_fakesql_authfail /tmp/_fakesql_crash

echo "▶ starting gateway on :$PORT (log: $LOG)"
cd "$REPO"
FMCP_HEALTH_CHECK_INTERVAL=3 \
FMCP_DEGRADED_MIN_SAMPLES=3 \
FMCP_GATEWAY_ID=live-test \
python3 -m fluidmcp.cli.server --host 127.0.0.1 --port "$PORT" --in-memory \
  > "$LOG" 2>&1 &
GW=$!
cleanup() {
  kill "$GW" 2>/dev/null
  rm -f /tmp/_fakesql_broken /tmp/_fakesql_authfail /tmp/_fakesql_crash
}
trap cleanup EXIT

for _ in $(seq 1 40); do curl -sf "$BASE/health" >/dev/null 2>&1 && break; sleep 1; done
curl -sf "$BASE/health" >/dev/null 2>&1 || { echo "❌ gateway never came up"; tail -25 "$LOG"; exit 1; }
echo "▶ gateway up"; echo

echo "── 1. Gateway self-monitoring ──"
H=$(curl -s "$BASE/health")
BOOT1=$(echo "$H" | j "d['boot_id']")
[ -n "$BOOT1" ] && ok "boot_id present ($BOOT1)" || bad "boot_id missing" "$H"
echo "$H" | j "d['config']" | grep -q . && ok "config block on unauthenticated /health" || bad "no config block" "$H"
curl -s "$BASE/health/ready" | j "d['ready']" | grep -q True && ok "/health/ready reports ready" || bad "not ready" "$(curl -s "$BASE/health/ready")"
G=$(curl -s "$BASE/api/monitoring/gateway")
echo "$G" | j "d['resources']['event_loop_lag_ms']" | grep -qE '^[0-9.]+$' && ok "event-loop lag reported" || bad "no lag metric" "$G"
echo "$G" | j "d['event_bus']['latest_seq']" | grep -qE '^[0-9]+$' && ok "event bus stats exposed" || bad "no bus stats" "$G"

echo; echo "── 2. Register + start the MCP ──"
curl -s -X POST "$BASE/api/servers" -H 'Content-Type: application/json' -d "{
  \"id\":\"customer-sql\",
  \"name\":\"Customer SQL MCP\",
  \"command\":\"python3\",
  \"args\":[\"$HERE/fake_sql_mcp.py\"],
  \"env\":{},
  \"working_dir\":\"/tmp\",
  \"install_path\":\"/tmp\"}" >/dev/null
curl -s -X POST "$BASE/api/servers/customer-sql/start" >/dev/null
sleep 4
echo "$(srv)" | j "d.get('state')" | grep -q running && ok "state=running in fleet rollup" || bad "not running" "$(srv)"

echo; echo "── 3. Healthy traffic ──"
for _ in 1 2 3 4; do call list_tables '{}'; done
sleep 1
R=$(srv | j "d.get('error_rate_5m')")
[ "$R" = "0.0" ] && ok "error_rate_5m = 0.0" || bad "unexpected error rate" "$R"

echo; echo "── 4. BREAK THE DATABASE (process stays alive) ──"
touch /tmp/_fakesql_broken
for _ in $(seq 1 6); do call execute_query '{"query":"SELECT 1"}'; done
sleep 6
S=$(srv)
echo "$S" | j "d.get('process_state')" | grep -q running && ok "process_state STILL running — PID alive, HTTP fine" || bad "process died" "$S"
echo "$S" | j "d.get('state')" | grep -q degraded          && ok "state = degraded" || bad "state not degraded" "$(echo "$S" | j "d.get('state')")"
echo "$S" | j "d.get('failure_category')" | grep -q db_connection_refused && ok "failure_category = db_connection_refused" || bad "wrong category" "$(echo "$S" | j "d.get('failure_category')")"
echo "$S" | j "d.get('failure_owner')" | grep -q customer  && ok "failure_owner = customer" || bad "wrong owner" "$(echo "$S" | j "d.get('failure_owner')")"
echo "$S" | j "d['failing_tools'][0]['tool']" | grep -q execute_query && ok "failing_tools names execute_query" || bad "failing_tools wrong" "$(echo "$S" | j "d.get('failing_tools')")"

echo; echo "── 5. Event emitted ──"
curl -s "$BASE/api/monitoring/events?severity=warning&limit=50" | grep -q server.degraded \
  && ok "server.degraded in event feed" || bad "no degraded event" "$(curl -s "$BASE/api/monitoring/events?limit=50" | j "[e['type'] for e in d['events']]")"

echo; echo "── 6. Diagnosis ──"
D=$(curl -s "$BASE/api/monitoring/servers/customer-sql/diagnosis")
echo "$D" | j "d['diagnosis']['failure_category']" | grep -q db_connection_refused && ok "diagnosis category" || bad "diagnosis wrong" "$D"
echo "$D" | j "d['diagnosis']['owner']" | grep -q customer && ok "diagnosis owner = customer" || bad "owner wrong" "$D"
echo "$D" | j "d['diagnosis']['is_dependency_failure']" | grep -q True && ok "flagged as dependency failure" || bad "not flagged" "$D"
echo "$D" | j "d['auto_restart']['would_help']" | grep -q False && ok "reports restart WON'T help (DB unreachable)" || bad "restart advice wrong" "$(echo "$D" | j "d['auto_restart']")"
SUM=$(echo "$D" | j "d['diagnosis']['summary']")
[ -n "$SUM" ] && ok "summary: ${SUM:0:70}..." || bad "no summary" "$D"
[ -n "$(echo "$D" | j "d['diagnosis']['remediation']")" ] && ok "remediation present" || bad "no remediation" "$D"

echo; echo "── 7. Recovery ──"
rm -f /tmp/_fakesql_broken
for _ in $(seq 1 45); do call execute_query '{"query":"SELECT 1"}'; done
sleep 6
RS=$(srv | j "d.get('state')")
[ "$RS" = "running" ] && ok "recovered to running" || bad "still $RS" "$RS"
curl -s "$BASE/api/monitoring/events?limit=200" | grep -q server.recovered && ok "server.recovered emitted" || bad "no recovered event"

echo; echo "── 8. Auth failure (JSON-RPC error path) ──"
touch /tmp/_fakesql_authfail
for _ in $(seq 1 8); do call execute_query '{"query":"SELECT 1"}'; done
sleep 6
A=$(curl -s "$BASE/api/monitoring/servers/customer-sql/diagnosis")
echo "$A" | j "d['diagnosis']['failure_category']" | grep -q db_auth_failed && ok "db_auth_failed detected" || bad "wrong category" "$(echo "$A" | j "d['diagnosis']['failure_category']")"
echo "$A" | j "d['auto_restart']['would_help']" | grep -q False && ok "correctly reports restart WON'T help" || bad "restart advice wrong" "$(echo "$A" | j "d['auto_restart']")"
rm -f /tmp/_fakesql_authfail

echo; echo "── 9. Real crash → classified + auto-restart ──"
echo 137 > /tmp/_fakesql_crash
call list_tables '{}'
rm -f /tmp/_fakesql_crash
sleep 14
C=$(curl -s "$BASE/api/monitoring/events?severity=critical&limit=50")
echo "$C" | grep -q server.crashed && ok "server.crashed emitted" || bad "no crash event" "$(echo "$C" | j "[e['type'] for e in d['events']]")"
echo "$C" | grep -q oom_killed && ok "exit 137 classified as oom_killed" || bad "exit label wrong" "$(echo "$C" | j "[e['data'].get('exit_label') for e in d['events'] if e['type']=='server.crashed']")"
curl -s "$BASE/api/servers/customer-sql/crashes" | grep -q exit_code && ok "crash persisted in /crashes" || bad "no crash record"

echo; echo "── 10. Cursor semantics ──"
E=$(curl -s "$BASE/api/monitoring/events?limit=500")
LATEST=$(echo "$E" | j "d['latest_seq']")
echo "$E" | python3 -c "
import sys,json
s=[e['seq'] for e in json.load(sys.stdin)['events']]
assert s==sorted(s), 'not ascending'
assert len(s)==len(set(s)), 'duplicates present'
print(len(s))" >/dev/null && ok "seq ascending & unique" || bad "seq ordering broken"
[ "$(curl -s "$BASE/api/monitoring/events?since=$LATEST" | j "d['returned']")" = "0" ] \
  && ok "since=latest_seq re-delivers nothing" || bad "cursor leaks events"
[ "$(curl -s "$BASE/api/monitoring/events" | j "d['boot_id']")" = "$BOOT1" ] \
  && ok "boot_id stable across calls" || bad "boot_id changed mid-process"

echo; echo "── 11. Uptime report ──"
U=$(curl -s "$BASE/api/monitoring/uptime?window=1h")
echo "$U" | j "d['fleet']['uptime_pct']" | grep -qE '^[0-9.]+$' && ok "fleet uptime_pct computed" || bad "no uptime" "$U"
echo "$U" | grep -q degraded_seconds && ok "degraded_seconds tracked separately from downtime" || bad "no degraded_seconds"

echo; echo "── 12. Webhook registration guards ──"
[ "$(curl -s -o /dev/null -w '%{http_code}' -X POST "$BASE/api/monitoring/webhooks" \
   -H 'Content-Type: application/json' -d '{"url":"http://169.254.169.254/","events":["server.crashed"]}')" = "400" ] \
  && ok "cloud-metadata URL rejected" || bad "SSRF guard failed"
[ "$(curl -s -o /dev/null -w '%{http_code}' -X POST "$BASE/api/monitoring/webhooks" \
   -H 'Content-Type: application/json' -d '{"url":"https://example.com/h","events":["server.exploded"]}')" = "422" ] \
  && ok "unknown event type rejected" || bad "event validation failed"

echo
echo "═══════════════════════════════════════"
printf "   PASSED: %-3s   FAILED: %s\n" "$PASS" "$FAIL"
echo "═══════════════════════════════════════"
[ "$FAIL" -eq 0 ] || { echo "gateway log: $LOG"; exit 1; }
