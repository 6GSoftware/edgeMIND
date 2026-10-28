#!/usr/bin/env bash

CURRENT_MODEL="$1"
PROCESSOR="$2"
URL="$3"

LLM_URL="http://${URL}/process_query"

PROMPT_MODES=("simple" "medium" "advanced")   # used for the summary order

REQUEST_TIMEOUT=250   # seconds, passed to curl --max-time

declare -A PROMPT_MODE_ORDER=(
  [1]="simple medium advanced"
  [2]="medium advanced simple"
  [3]="advanced medium simple"
  [4]="medium simple advanced"
  [5]="advanced simple medium"
)

# One full pass over every prompt-mode order = one repetition per prompt mode
REPETITIONS=${#PROMPT_MODE_ORDER[@]}

OUTPUT_DIR="./latency_ground_sim_results"
CSV_FILE="${OUTPUT_DIR}/latency_grounding_similarity_results_${PROCESSOR}_${CURRENT_MODEL}.csv"
SUMMARY_FILE="${OUTPUT_DIR}/latency_summary_grounding_similarity_${PROCESSOR}_${CURRENT_MODEL}.csv"

# One representative question per prompt mode.
declare -A PROMPTS=(
  [simple]="Give one reason why dog parks are needed."
  [medium]="How do dedicated dog parks promote responsible dog ownership?"
  [advanced]="How do dog parks enhance community engagement and responsible pet ownership?"
)

# ---------------------------------------------------------------------------
# Argument validation
# ---------------------------------------------------------------------------

if [ -z "$CURRENT_MODEL" ] || [ -z "$PROCESSOR" ]; then
    echo "Usage: $0 <model_name> <processor> <ip:port>" >&2
    echo "  (model_name is just a label for the results - it must match whichever" >&2
    echo "  model is currently deployed in the k3s cluster)" >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# Dependency checks
# ---------------------------------------------------------------------------

for cmd in curl awk date jq mktemp seq; do
    if ! command -v "$cmd" >/dev/null 2>&1; then
        echo "ERROR: required command '$cmd' not found in PATH." >&2
        exit 1
    fi
done

mkdir -p "$OUTPUT_DIR"

# Per-mode temp files holding successful latencies (for the summary stats)
LAT_DIR="$(mktemp -d)"
trap 'rm -rf "$LAT_DIR"' EXIT

# ---------------------------------------------------------------------------
# CSV headers
# ---------------------------------------------------------------------------

echo "timestamp#model#prompt_mode#repetition#http_code#inference_start_time#inference_end_time#latency_ms#curl_time_total_s#question#llm_response#db_result#" > "$CSV_FILE"
echo "model#prompt_mode#repetitions#mean_latency_ms#stddev_latency_ms" > "$SUMMARY_FILE"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Build the JSON payload safely (handles quotes etc. in the question).
build_payload() {
    jq -n --arg question "$1" '{question: $question}'
}

# Make a free-text value safe for a '#'-delimited, one-line CSV field.
csv_field() {
    local v="$1"
    v="${v//$'\r'/ }"
    v="${v//$'\n'/ }"
    v="${v//#/ }"
    v="${v//\"/\"\"}"
    printf '"%s"' "$v"
}

# ---------------------------------------------------------------------------
# Fire a single query against the LLM endpoint.
# Results are returned via global variables (no subshell, so nothing is lost):
#   RQ_HTTP_CODE RQ_START_MS RQ_END_MS RQ_LATENCY_MS RQ_TIME_TOTAL
#   RQ_LLM_MESSAGE RQ_DB_RESULT
# Returns non-zero if curl failed or the response was not valid JSON.
# ---------------------------------------------------------------------------

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
# Compute mean and population stddev (ms) for a list of latencies via awk.
# ---------------------------------------------------------------------------

compute_stats() {
    awk '
        { sum += $1; vals[NR] = $1; n++ }
        END {
            if (n == 0) { print "0,0"; exit }
            mean = sum / n
            sq_diff_sum = 0
            for (i = 1; i <= n; i++) {
                diff = vals[i] - mean
                sq_diff_sum += diff * diff
            }
            stddev = sqrt(sq_diff_sum / n)
            printf "%.3f,%.3f\n", mean, stddev
        }
    '
}

# ---------------------------------------------------------------------------
# Banner
# ---------------------------------------------------------------------------

echo "==================================================================="
echo " LLM Latency Test ($PROCESSOR) - $(date)"
echo " Endpoint : $LLM_URL"
echo " Model    : $CURRENT_MODEL  (must match what's deployed in k3s right now)"
echo " Modes    : ${PROMPT_MODES[*]}"
echo " Orders   : $REPETITIONS (each order runs every mode once)"
echo " Results  : $CSV_FILE"
echo " Summary  : $SUMMARY_FILE"
echo "==================================================================="

# ---------------------------------------------------------------------------
# Warm-up query: ONCE, before all measurements (discarded)
# ---------------------------------------------------------------------------

echo ""
echo "Warm-up query (once)..."
if run_query "${PROMPTS[simple]}"; then
    echo "  Warm-up done."
else
    echo "  WARNING: warm-up query failed (continuing anyway)."
fi

# ---------------------------------------------------------------------------
# Main test loop: outer = prompt-mode orders, inner = modes within the order
# ---------------------------------------------------------------------------

for rep in $(seq 1 "$REPETITIONS"); do
    order="${PROMPT_MODE_ORDER[$rep]}"

    echo ""
    echo "[order $rep/$REPETITIONS] model=$CURRENT_MODEL order: $order"

    for mode in $order; do
        question="${PROMPTS[$mode]}"

        run_query "$question"
        rc=$?

        row_ts="$(date -Iseconds)"

        # Same file, same '#' delimiter as the header. cosine_similarity is not
        # computed by this script, so that column is left empty.
        printf '%s#%s#%s#%s#%s#%s#%s#%s#%s#"%s"#%s#%s#\n' \
            "$row_ts" "$CURRENT_MODEL" "$mode" "$rep" \
            "$RQ_HTTP_CODE" "$RQ_START_MS" "$RQ_END_MS" \
            "$RQ_LATENCY_MS" "$RQ_TIME_TOTAL" "$question" \
            "$(csv_field "$RQ_LLM_MESSAGE")" "$(csv_field "$RQ_DB_RESULT")" \
            >> "$CSV_FILE"

        if [ $rc -ne 0 ] || [ "$RQ_HTTP_CODE" != "200" ]; then
            echo "    $mode: FAILED (http_code=$RQ_HTTP_CODE)"
        else
            echo "    $mode: ${RQ_LATENCY_MS} ms (http $RQ_HTTP_CODE, curl ${RQ_TIME_TOTAL} s)"
            echo "$RQ_LATENCY_MS" >> "${LAT_DIR}/${mode}.txt"
        fi

        sleep 5 # Give the machines some time to cool down in between
    done
done

# ---------------------------------------------------------------------------
# Stats per prompt mode (successful runs only)
# ---------------------------------------------------------------------------

echo ""
for mode in "${PROMPT_MODES[@]}"; do
    latencies_file="${LAT_DIR}/${mode}.txt"

    if [ -s "$latencies_file" ]; then
        stats="$(compute_stats < "$latencies_file")"
        mean_ms="$(echo "$stats" | cut -d',' -f1)"
        stddev_ms="$(echo "$stats" | cut -d',' -f2)"
        n_success=$(wc -l < "$latencies_file")
    else
        mean_ms="NaN"
        stddev_ms="NaN"
        n_success=0
    fi

    echo "$CURRENT_MODEL,$mode,$n_success,$mean_ms,$stddev_ms" >> "$SUMMARY_FILE"
    echo "$mode --> mean=${mean_ms} ms, stddev=${stddev_ms} ms (n=${n_success}/${REPETITIONS} successful)"
done

echo ""
echo "==================================================================="
echo "Done. Detailed results: $CSV_FILE"
echo "      Summary:          $SUMMARY_FILE"
echo "==================================================================="