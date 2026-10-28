#!/usr/bin/env bash
#
# scalability_test_cpu.sh
#
# Sends ONE test request to the system's /process_query endpoint and appends
# one row of results to a shared CSV. No looping, no batching, no
# concurrency handling -- you call this once per test, with all parameters
# given on the command line.
#
# ---------------------------------------------------------------------------
# USAGE
#   ./scalability_test_cpu.sh MODEL PROCESSOR PROMPT_MODE TEST_REPETITION_NUMBER CONCURRENCY_NUMBER TERMINAL_NUMBER
#
# Example (terminal 2 of 4, testing Gemma/CPU/Medium, repetition 3):
#   ./scalability_test_cpu.sh Gemma CPU Medium 3 4 2
#
# PROMPT_MODE must be one of the keys defined in the PROMPTS map below
# (Simple / Medium / Advanced by default).
#
# All results are appended to the same CSV/log files across every terminal
# and every invocation (see OUTPUT_DIR below).
# ---------------------------------------------------------------------------

set -uo pipefail

# ============================== CONFIG ======================================

# Prompt mode -> actual question text sent to the API.
declare -A PROMPTS=(
  [Simple]="Give one reason why dog parks are needed."
  [Medium]="How do dedicated dog parks promote responsible dog ownership?"
  [Advanced]="How do dog parks enhance community engagement and responsible pet ownership?"
)

# Per-request timeout (seconds).
REQUEST_TIMEOUT=900

# --- Output -------------------------------------------------------------
# Fixed (not timestamped) so that every terminal/invocation appends to the
# same combined dataset.

OUTPUT_DIR="./scalability_results"
#RESULTS_CSV="${OUTPUT_DIR}/per_request_results_CPU.csv"
FAILURES_LOG="${OUTPUT_DIR}/failures.log"

# ============================ END CONFIG ====================================


fail() {
  echo "ERROR: $*" >&2
  exit 1
}

usage() {
  echo "Usage: $0 MODEL PROCESSOR PROMPT_MODE TEST_REPETITION_NUMBER CONCURRENCY_NUMBER TERMINAL_NUMBER LLM_URL" >&2
  echo "  PROMPT_MODE must be one of: ${!PROMPTS[*]}" >&2
  exit 1
}

[ $# -eq 7 ] || usage

MODEL="$1"
PROCESSOR="$2"
PROMPT_MODE="$3"
TEST_REPETITION_NUMBER="$4"
CONCURRENCY_NUMBER="$5"
TERMINAL_NUMBER="$6"
LLM_URL="$7"

RESULTS_CSV="${OUTPUT_DIR}/per_request_results_CPU_${MODEL}.csv"

[ -v "PROMPTS[$PROMPT_MODE]" ] || fail "Unknown PROMPT_MODE '$PROMPT_MODE'. Must be one of: ${!PROMPTS[*]}"

command -v curl >/dev/null 2>&1 || fail "Required command 'curl' not found."

# --- Request sender -------------------------------------------------------
# Prints a single JSON object on stdout with the fields:
#   message, db_result, duration, node_name, http_code, time_total
# Progress/warning messages go to stderr so they don't pollute the output.

send_request() {
  local question="$1" tmp_body payload metrics resp='{}'

  tmp_body=$(mktemp) || return 1
  trap 'rm -f "$tmp_body"; trap - RETURN' RETURN

  payload=$(jq -n --arg q "$question" '{question: $q}') || return 1

  metrics=$(curl -sS --max-time "$REQUEST_TIMEOUT" \
      -o "$tmp_body" \
      -w '%{http_code}\n%{time_total}' \
      -H "Content-Type: application/json" \
      -d "$payload" "$LLM_URL") || true   # keep going on timeout/curl error

  echo "Extracting information from the response..." >&2

  if jq -e 'type == "object"' "$tmp_body" >/dev/null 2>&1; then
    resp=$(<"$tmp_body")
  else
    echo "Warning: response was not a JSON object" >&2
  fi

  jq -n --argjson r "$resp" \
        --arg http_code  "${metrics%%$'\n'*}" \
        --arg time_total "${metrics##*$'\n'}" \
    '{message:    ($r.message    // ""),
      db_result:  ($r.db_result  // ""),
      duration:   ($r.duration   // "" | tostring),
      node_name:  ($r.node_name  // ""),
      http_code:  $http_code,
      time_total: $time_total}'
}

# --- Main -----------------------------------------------------------------

QUESTION="${PROMPTS[$PROMPT_MODE]}"
ts=$(date '+%Y-%m-%d %H:%M:%S')

OUT=$(send_request "$QUESTION") || fail "send_request failed unexpectedly."

LLM_MESSAGE="" DB_RESULT="" DURATION="" NODE_NAME="" HTTP_CODE="" TIME_TOTAL=""
{
  IFS= read -r -d '' LLM_MESSAGE
  IFS= read -r -d '' DB_RESULT
  IFS= read -r -d '' DURATION
  IFS= read -r -d '' NODE_NAME
  IFS= read -r -d '' HTTP_CODE
  IFS= read -r -d '' TIME_TOTAL
} < <(jq -j '[.message, .db_result, .duration, .node_name, .http_code, .time_total][] | tostring + "\u0000"' <<< "$OUT") || true

# Safety net: send_request should always yield these, even on timeout (000)
if [ -z "$TIME_TOTAL" ] || [ -z "$HTTP_CODE" ]; then
  printf '%s\n' "${ts},${MODEL},${PROCESSOR},${PROMPT_MODE},${TEST_REPETITION_NUMBER},${CONCURRENCY_NUMBER},${TERMINAL_NUMBER}: could not parse request metrics" >> "$FAILURES_LOG"
  fail "Could not parse request result. Logged to $FAILURES_LOG"
fi

if [[ "$HTTP_CODE" == "000" ]]; then
  printf '%s\n' "${ts},${MODEL},${PROCESSOR},${PROMPT_MODE},${TEST_REPETITION_NUMBER},${CONCURRENCY_NUMBER},${TERMINAL_NUMBER}: no response (timeout or curl error)" >> "$FAILURES_LOG"
elif [[ ! "$HTTP_CODE" =~ ^2 ]]; then
  printf '%s\n' "${ts},${MODEL},${PROCESSOR},${PROMPT_MODE},${TEST_REPETITION_NUMBER},${CONCURRENCY_NUMBER},${TERMINAL_NUMBER}: http_status=${HTTP_CODE}" >> "$FAILURES_LOG"
fi

printf '%s\n' "${ts}#${MODEL}#${PROCESSOR}#${PROMPT_MODE}#${TEST_REPETITION_NUMBER}#${CONCURRENCY_NUMBER}#${TERMINAL_NUMBER}#${NODE_NAME}#${TIME_TOTAL}#${DURATION}#${HTTP_CODE}" >> "$RESULTS_CSV"

printf '%s\n' "Result: curl_time=${TIME_TOTAL}s server_duration=${DURATION:-n/a}s http_status=${HTTP_CODE}"
#printf '%s\n' "  LLM response: ${LLM_MESSAGE}"
#printf '%s\n' "  Database results: ${DB_RESULT}"