#!/usr/bin/env bash
#
# run_llm_tests.sh - benchmark an LLM endpoint with simple/medium/advanced prompts
#
# Usage:   ./run_llm_tests.sh <model> <url> <processor>
# Example: ./run_llm_tests.sh llama xxx.xxx.xxx.xxx:yyyy GPU
#
# Requires: bash >= 4.3, curl, jq

set -u

# ---------------------------------------------------------------------------
# Arguments
# ---------------------------------------------------------------------------
if [ $# -ne 3 ]; then
    echo "Usage: $0 <model> <url> <processor: GPU|CPU>" >&2
    exit 1
fi

MODEL="$1"
URL="$2"
PROCESSOR="${3^^}"   # normalise to upper case

if [ "$PROCESSOR" != "GPU" ] && [ "$PROCESSOR" != "CPU" ]; then
    echo "ERROR: processor must be GPU or CPU (got '$3')" >&2
    exit 1
fi

LLM_URL="http://${URL}/process_query"
REQUEST_TIMEOUT=250
REPETITIONS=5
OUTPUT_CSV="./session_persistence_results/results_${PROCESSOR}_${MODEL}.csv"

for cmd in curl jq; do
    command -v "$cmd" >/dev/null 2>&1 || { echo "ERROR: '$cmd' is required" >&2; exit 1; }
done

# ---------------------------------------------------------------------------
# Prompts: 4 per mode.
# ---------------------------------------------------------------------------

# Why are these simple? Because they are simple fact questions, no aggregation needed.
# In addition, all information can be found from one single text chunk.
SIMPLE_PROMPTS=(
    "How many illegal bonfires are there across Cork around June 23rd?"
    "Where are the bonfires most frequent?"
    "Where are the bonfires least frequent?"
    "What is the scale of the illegal bonfires?"
)

# Why are these medium? Because they require information from below multiple topics,
# and some aggregation of information from multiple text chunks.
MEDIUM_PROMPTS=(
    "How can dedicated dog parks help preserve green spaces?"
    "How can dedicated dog parks improve health and connection with other people?"
    "What are the main benefits of dedicated dog parks for the dogs?"
    "What are the main benefits of dog parks for the dog owners?"
)

# Why are these advanced? Because they require information from below multiple topics,
# and aggregation of information from multiple text chunks.
ADVANCED_PROMPTS=(
    "Does Cork city support older people?"
    "How does Cork city ensure that Cork is an age friendly city?"
    "What does the Cork city age friendly interdepartmental group do?"
    "What ensures the age friendliness of Cork city libraries?"
)

# Order of prompt modes for each repetition
declare -A PROMPT_MODE_ORDER=(
    [1]="simple medium advanced"
    [2]="medium advanced simple"
    [3]="advanced medium simple"
    [4]="medium simple advanced"
    [5]="advanced simple medium"
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Build the JSON request body. ADJUST the field name(s) to match your API.
build_payload() {
    jq -n --arg q "$1" '{question: $q}'
}

# Make a value safe for a '#'-delimited, unquoted CSV:
#  - any run of whitespace (spaces, tabs, \n, \r) becomes a single space,
#    so every record stays on exactly one line
#  - '#' inside the value is replaced with a space, since it is the delimiter
#  - leading/trailing whitespace is trimmed
csv_field() {
    local s="$1" d='#'
    s="${s//"$d"/ }"
    s="$(printf '%s' "$s" | tr -s '[:space:]' ' ')"
    s="${s#"${s%%[![:space:]]*}"}"   # trim leading
    s="${s%"${s##*[![:space:]]}"}"   # trim trailing
    printf '%s' "$s"
}

write_csv_row() {
    local out="" f
    for f in "$@"; do
        out+="$(csv_field "$f")#"
    done
    printf '%s\n' "${out%#}" >> "$OUTPUT_CSV"
}

run_query() {
    local question="$1"
    local tmp_body metrics curl_exit

    RQ_HTTP_CODE="ERR"; RQ_START_MS=""; RQ_END_MS=""
    RQ_LATENCY_MS="-1"; RQ_TIME_TOTAL="-1"
    RQ_LLM_MESSAGE=""; RQ_DB_RESULT=""

    tmp_body="$(mktemp)"

    RQ_START_MS="$(date +%s%3N)"

    metrics=$(curl -s \
        --max-time "$REQUEST_TIMEOUT" \
        -o "$tmp_body" \
        -w "%{http_code}\n%{time_total}" \
        -H "Content-Type: application/json" \
        -d "$(build_payload "$question")" \
        "$LLM_URL")
    curl_exit=$?

    RQ_END_MS="$(date +%s%3N)"

    if [ $curl_exit -ne 0 ]; then
        rm -f "$tmp_body"
        return 1
    fi

    RQ_LATENCY_MS=$(( RQ_END_MS - RQ_START_MS ))
    RQ_HTTP_CODE="$(sed -n 1p <<< "$metrics")"
    RQ_TIME_TOTAL="$(sed -n 2p <<< "$metrics")"

    # Validate JSON (do not abort the whole run on a bad response)
    if ! jq empty "$tmp_body" 2>/dev/null; then
        echo "    WARNING: invalid JSON from LLM server" >&2
        rm -f "$tmp_body"
        return 1
    fi

    # Extract fields (non-string values are serialised as JSON)
    RQ_LLM_MESSAGE="$(jq -r '(.message // "") | if type=="string" then . else tojson end' "$tmp_body")"
    RQ_DB_RESULT="$(jq -r '(.db_result // "") | if type=="string" then . else tojson end' "$tmp_body")"

    rm -f "$tmp_body"
    return 0
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

# CSV header (prompt_id, http_code and latency_ms are extras; remove if unwanted)
write_csv_row timestamp model processor prompt_mode prompt repetition \
              http_code latency_ms llm_response db_result

total=$(( REPETITIONS * 3 * 4 ))
count=0

echo "Model:     $MODEL"
echo "Processor: $PROCESSOR"
echo "Endpoint:  $LLM_URL"
echo "Output:    $OUTPUT_CSV"
echo "Total requests: $total"
echo

for rep in $(seq 1 "$REPETITIONS"); do
    echo "=== Repetition $rep (order: ${PROMPT_MODE_ORDER[$rep]}) ==="

    for mode in ${PROMPT_MODE_ORDER[$rep]}; do
        declare -n prompts="${mode^^}_PROMPTS"

        for i in "${!prompts[@]}"; do
            prompt_id=$(( i + 1 ))
            question="${prompts[$i]}"
            count=$(( count + 1 ))

            printf '[%d/%d] rep=%s mode=%s prompt=%s ... ' \
                   "$count" "$total" "$rep" "$mode" "$prompt_id"

            if run_query "$question"; then
                echo "HTTP $RQ_HTTP_CODE, ${RQ_LATENCY_MS} ms"
            else
                echo "FAILED (HTTP $RQ_HTTP_CODE)"
            fi

            write_csv_row "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$MODEL" "$PROCESSOR" \
                          "$mode" "$question" "$rep" \
                          "$RQ_HTTP_CODE" "$RQ_LATENCY_MS" \
                          "$RQ_LLM_MESSAGE" "$RQ_DB_RESULT"
        done
        unset -n prompts
    done
done

echo
echo "Done. Results written to $OUTPUT_CSV"