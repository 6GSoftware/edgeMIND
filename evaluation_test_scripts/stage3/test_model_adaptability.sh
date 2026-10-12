#!/usr/bin/env bash
#
# Sends test prompts to llm-text-gen-service and records the LLM response
# and the retrieved DB chunks in a '#'-delimited CSV file.
#
# Usage:   ./run_benchmark.sh <cpu|gpu> <llama|gemma|phi>
# Example: ./run_benchmark.sh gpu gemma
#
# Optional environment variables:
#   LLM_URL          Endpoint of llm-text-gen-service (default below)
#   REQUEST_TIMEOUT  Per-request timeout in seconds   (default 300)
#   OUTPUT_CSV       Output file                      (default results.csv)

set -uo pipefail

# ---------------------------------------------------------------- arguments
if [[ $# -ne 3 ]]; then
  echo "Usage: $0 <processor> <model> <url>" >&2
  exit 1
fi

PROCESSOR="$1"
MODEL="$2"
URL="$3"

case "$PROCESSOR" in
  cpu|gpu) ;;
  *) echo "Invalid processor '$1' (expected: cpu or gpu)" >&2; exit 1 ;;
esac

case "$MODEL" in
  llama|gemma|phi) ;;
  *) echo "Invalid model '$2' (expected: llama, gemma or phi)" >&2; exit 1 ;;
esac

command -v curl >/dev/null || { echo "curl is required" >&2; exit 1; }
command -v jq   >/dev/null || { echo "jq is required"   >&2; exit 1; }

# ------------------------------------------------------------------- config
LLM_URL="http://${URL}/process_query"
REQUEST_TIMEOUT=300
OUTPUT_CSV="./model_adaptability/results_${PROCESSOR}_${MODEL}.csv"

declare -A PROMPTS=(
  [simple]="Give one reason why dog parks are needed."
  [medium]="How do dedicated dog parks promote responsible dog ownership?"
  [advanced]="How do dog parks enhance community engagement and responsible pet ownership?"
)

declare -A PROMPT_MODE_ORDER=(
  [1]="simple medium advanced"
  [2]="medium advanced simple"
  [3]="advanced medium simple"
  [4]="medium simple advanced"
  [5]="advanced simple medium"
)

RETRIEVAL_COUNTS=(1 3 5)

# ---------------------------------------------------------------- functions

# Build the JSON request body.
# NOTE: adjust the field names to match what your service expects.
build_payload() {
  local question="$1" retrieval_n="$2"
  jq -n \
    --arg question "$question" \
    --argjson n "$retrieval_n" \
    '{question: $question, n: $n}'
}

# Make a value safe for a one-line, '#'-delimited CSV record:
# newlines/CRs -> spaces, double quotes doubled, whole value wrapped in quotes
# (so '#' characters inside the text don't break the columns).
csv_field() {
  local s
  s="$(printf '%s' "$1" | tr '\r\n' '  ' | sed 's/"/""/g')"
  printf '"%s"' "$s"
}

# Send one request. Sets RQ_HTTP_CODE, RQ_TIME, RQ_LLM_MESSAGE, RQ_DB_RESULT.
send_request() {
  local question="$1" retrieval_n="$2"
  local tmp_body metrics
  tmp_body="$(mktemp)"

  metrics=$(curl -s \
    --max-time "$REQUEST_TIMEOUT" \
    -o "$tmp_body" \
    -w "%{http_code}\n%{time_total}" \
    -H "Content-Type: application/json" \
    -d "$(build_payload "$question" "$retrieval_n")" \
    "$LLM_URL") || true

  RQ_HTTP_CODE="$(sed -n '1p' <<<"$metrics")"
  RQ_TIME="$(sed -n '2p' <<<"$metrics")"
  RQ_LLM_MESSAGE=""
  RQ_DB_RESULT=""

  if [[ "$RQ_HTTP_CODE" == "200" ]]; then
    RQ_LLM_MESSAGE="$(jq -r '(.message // "") | if type=="string" then . else tojson end' "$tmp_body" 2>/dev/null)"
    RQ_DB_RESULT="$(jq -r '(.db_result // "") | if type=="string" then . else tojson end' "$tmp_body" 2>/dev/null)"
  else
    RQ_LLM_MESSAGE="ERROR: HTTP ${RQ_HTTP_CODE:-000}"
  fi

  rm -f "$tmp_body"
}

# ------------------------------------------------------------------- main
if [[ ! -s "$OUTPUT_CSV" ]]; then
  echo "timestamp#processor#model#prompt_mode#repetition#prompt#retrieval_n#llm_response#db_result" > "$OUTPUT_CSV"
fi

total=$(( ${#PROMPT_MODE_ORDER[@]} * 3 * ${#RETRIEVAL_COUNTS[@]} ))
count=0

echo "Processor=$PROCESSOR  Model=$MODEL  URL=$LLM_URL  Output=$OUTPUT_CSV"

for repetition in 1 2 3 4 5; do
  for prompt_mode in ${PROMPT_MODE_ORDER[$repetition]}; do
    question="${PROMPTS[$prompt_mode]}"

    for retrieval_n in "${RETRIEVAL_COUNTS[@]}"; do
      count=$((count + 1))
      timestamp="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"

      send_request "$question" "$retrieval_n"

      printf '[%d/%d] rep=%s mode=%-8s n=%s -> HTTP %s in %ss\n' \
        "$count" "$total" "$repetition" "$prompt_mode" "$retrieval_n" \
        "${RQ_HTTP_CODE:-000}" "${RQ_TIME:-?}"

      {
        printf '%s#%s#%s#%s#%s#' \
          "$timestamp" "$PROCESSOR" "$MODEL" "$prompt_mode" "$repetition"
        csv_field "$question";        printf '#'
        printf '%s#' "$retrieval_n"
        csv_field "$RQ_LLM_MESSAGE";  printf '#'
        csv_field "$RQ_DB_RESULT";    printf '\n'
      } >> "$OUTPUT_CSV"
    done
  done
done

echo "Done. $count requests recorded in $OUTPUT_CSV"