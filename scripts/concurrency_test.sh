#!/usr/bin/env bash
# Concurrency test — can target FluidMCP gateway (8099) or FastMCP directly (8500)
# Set MODE=direct to bypass the gateway and hit FastMCP on 8500 directly.
# In direct mode each user gets its own session (recommended for true concurrency).

# ── Config ────────────────────────────────────────────────────────────────────
CONCURRENT_USERS=100          # Change this to increase load

# MODE: "gateway"    → hit FluidMCP on 8099
#       "direct"    → hit FastMCP on 8500 directly (each user gets own session)
#       "stateless" → hit FastMCP on 8500 directly, no session init, plain JSON
MODE="gateway"  # Change this to "gateway", "direct", or "stateless"

GATEWAY_URL="http://localhost:8099/addition-mcp/mcp"
DIRECT_URL="http://localhost:8500/mcp"

OUTPUT_FILE="concurrency_results_$(date +%Y%m%d_%H%M%S).txt"
TMPDIR_PREFIX="/tmp/fmcp_concurrency_$$"
# ─────────────────────────────────────────────────────────────────────────────

if [[ "${MODE}" == "direct" || "${MODE}" == "stateless" ]]; then
    ENDPOINT="${DIRECT_URL}"
else
    ENDPOINT="${GATEWAY_URL}"
fi

mkdir -p "${TMPDIR_PREFIX}"

echo "FluidMCP Concurrency Test"
echo "  Mode       : ${MODE}"
echo "  Endpoint   : ${ENDPOINT}"
echo "  Users      : ${CONCURRENT_USERS}"
echo "  Output     : ${OUTPUT_FILE}"
echo ""

# ── Helper: initialize a fresh MCP session, return session ID ────────────────
init_session() {
    local resp
    resp=$(curl -si -X POST "${DIRECT_URL}" \
        -H "Content-Type: application/json" \
        -H "Accept: application/json, text/event-stream" \
        -d '{"jsonrpc":"2.0","id":0,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}' \
        2>/dev/null)
    # Extract mcp-session-id from response headers (case-insensitive)
    echo "${resp}" | grep -i "mcp-session-id" | awk '{print $2}' | tr -d '\r'
}

# Fire all requests in parallel, one background job per user
for i in $(seq 1 "${CONCURRENT_USERS}"); do
    # Each user gets unique inputs so we can verify correct routing
    A=$((i * 10))
    B=$((i * 3))

    RESULT_FILE="${TMPDIR_PREFIX}/user_${i}.json"
    TIMING_FILE="${TMPDIR_PREFIX}/user_${i}.time"

    (
        # In direct mode: each user initializes their own session first
        SESSION_HEADER=""
        START=$(date +%s%N)

        if [[ "${MODE}" == "direct" ]]; then
            SESSION_ID=$(init_session)
            if [[ -n "${SESSION_ID}" ]]; then
                SESSION_HEADER="-H \"mcp-session-id: ${SESSION_ID}\""
            fi
        fi

        PAYLOAD="{\"jsonrpc\":\"2.0\",\"id\":${i},\"method\":\"tools/call\",\"params\":{\"name\":\"add_numbers\",\"arguments\":{\"a\":${A},\"b\":${B}}}}"

        if [[ "${MODE}" == "stateless" ]]; then
            HTTP_STATUS=$(curl -s -o "${RESULT_FILE}" -w "%{http_code}" \
                -X POST "${ENDPOINT}" \
                -H "Content-Type: application/json" \
                -H "Accept: application/json, text/event-stream" \
                -d "${PAYLOAD}")
        elif [[ "${MODE}" == "direct" && -n "${SESSION_ID}" ]]; then
            HTTP_STATUS=$(curl -s -o "${RESULT_FILE}" -w "%{http_code}" \
                -X POST "${ENDPOINT}" \
                -H "Content-Type: application/json" \
                -H "Accept: application/json, text/event-stream" \
                -H "mcp-session-id: ${SESSION_ID}" \
                -d "${PAYLOAD}")
        else
            HTTP_STATUS=$(curl -s -o "${RESULT_FILE}" -w "%{http_code}" \
                -X POST "${ENDPOINT}" \
                -H "Content-Type: application/json" \
                -H "Accept: application/json, text/event-stream" \
                -d "${PAYLOAD}")
        fi

        END=$(date +%s%N)
        ELAPSED_MS=$(( (END - START) / 1000000 ))

        echo "${ELAPSED_MS} ${HTTP_STATUS} ${A} ${B}" > "${TIMING_FILE}"
    ) &
done

# Wait for all background jobs to finish
wait

# ── Collect results and write report ─────────────────────────────────────────
{
    echo "========================================"
    echo "  FluidMCP Concurrency Test Report"
    echo "  Date     : $(date '+%Y-%m-%d %H:%M:%S')"
    echo "  Mode     : ${MODE}"
    echo "  Endpoint : ${ENDPOINT}"
    echo "  Users    : ${CONCURRENT_USERS}"
    echo "========================================"
    echo ""

    TOTAL_MS=0
    MIN_MS=999999999
    MAX_MS=0
    PASS=0
    FAIL=0

    for i in $(seq 1 "${CONCURRENT_USERS}"); do
        TIMING_FILE="${TMPDIR_PREFIX}/user_${i}.time"
        RESULT_FILE="${TMPDIR_PREFIX}/user_${i}.json"

        if [[ ! -f "${TIMING_FILE}" ]]; then
            echo "User ${i} | ERROR: no timing data"
            FAIL=$((FAIL + 1))
            continue
        fi

        read -r ELAPSED_MS HTTP_STATUS A B < "${TIMING_FILE}"
        EXPECTED=$(( A + B ))

        # Parse the actual returned value from the JSON response
        if [[ -f "${RESULT_FILE}" ]]; then
            ACTUAL=$(python3 -c "
import json
try:
    d = json.load(open('${RESULT_FILE}'))
    content = d.get('result', {}).get('content', [])
    print(content[0].get('text', 'N/A') if content else 'N/A')
except Exception as e:
    print(f'parse_error: {e}')
" 2>/dev/null)
            RAW_JSON=$(cat "${RESULT_FILE}")
        else
            ACTUAL="no_response"
            RAW_JSON=""
        fi

        # Determine pass/fail
        if [[ "${HTTP_STATUS}" == "200" ]]; then
            STATUS_LABEL="OK"
            PASS=$((PASS + 1))
        else
            STATUS_LABEL="FAIL (HTTP ${HTTP_STATUS})"
            FAIL=$((FAIL + 1))
        fi

        # Update aggregates
        TOTAL_MS=$((TOTAL_MS + ELAPSED_MS))
        (( ELAPSED_MS < MIN_MS )) && MIN_MS=${ELAPSED_MS}
        (( ELAPSED_MS > MAX_MS )) && MAX_MS=${ELAPSED_MS}

        echo "----------------------------------------"
        printf "  User %-3s | Input: %s + %s  |  Expected: %s\n" "${i}" "${A}" "${B}" "${EXPECTED}"
        printf "            | Response time : %s ms\n" "${ELAPSED_MS}"
        printf "            | HTTP status   : %s\n" "${STATUS_LABEL}"
        printf "            | Actual result : %s\n" "${ACTUAL}"
        echo "            | Raw JSON:"
        echo "${RAW_JSON}" | python3 -m json.tool 2>/dev/null | sed 's/^/              /'
        echo ""
    done

    AVG_MS=$(( TOTAL_MS / CONCURRENT_USERS ))

    echo "========================================"
    echo "  Summary"
    echo "----------------------------------------"
    printf "  Total users  : %s\n"    "${CONCURRENT_USERS}"
    printf "  Passed       : %s\n"    "${PASS}"
    printf "  Failed       : %s\n"    "${FAIL}"
    printf "  Fastest      : %s ms\n" "${MIN_MS}"
    printf "  Slowest      : %s ms\n" "${MAX_MS}"
    printf "  Average      : %s ms\n" "${AVG_MS}"
    printf "  Wall clock   : %s ms\n" "${MAX_MS}"
    echo "========================================"

} | tee "${OUTPUT_FILE}"

rm -rf "${TMPDIR_PREFIX}"

echo ""
echo "Results saved to: ${OUTPUT_FILE}"
