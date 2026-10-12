#!/bin/bash

##############################################
# ARGUMENTS
##############################################

if [[ $# -lt 5 ]]; then
    echo "Usage: $0 <use_case> <rag_mode> <model> <processor> <prompt_mode>"
    echo "Example: $0 construction ragsa llama cpu advanced"
    echo "--------------------------------"
    echo "Use cases: office, construction"
    echo "RAG modes: ragonly, ragsa"
    echo "Models: llama, gemma, phi"
    echo "Processors: cpu, gpu"
    echo "Prompt modes: simple, medium, advanced"
    exit 1
fi

echo "Running EdgeMIND tests (stages 3 and 4)."

USE_CASE="$1"
RAG_MODE="$2"
MODEL="$3"
PROCESSOR="$4"
PROMPT_MODE="$5"

##############################################
# TEST CONFIGURATION
##############################################

TEST_DURATION=300   # 5 minutes

LLM_URL="http://xxx.xxx.xxx.xxx:30500/process_query"
FILE_PATH="/path/to/image.jpg"

##############################################
# PROMPT SELECTION
##############################################

case "$USE_CASE" in
  office)
    case "$PROMPT_MODE" in
      simple)   QUESTION="Give one reason why dog parks are needed." ;;
      medium)   QUESTION="How do dedicated dog parks promote responsible dog ownership?" ;;
      advanced) QUESTION="How do dog parks enhance community engagement and responsible pet ownership?" ;;
      *) echo "Unknown prompt mode: ${PROMPT_MODE}"; exit 1 ;;
    esac
    ;;
  construction)
    case "$PROMPT_MODE" in
      simple)   QUESTION="What is the crane doing?" ;;
      medium)   QUESTION="What is the crane doing and what is in the background?" ;;
      advanced) QUESTION="What is the crane doing and what does it indicate about construction status?" ;;
      *) echo "Unknown prompt mode: ${PROMPT_MODE}"; exit 1 ;;
    esac
    ;;
  *)
    echo "Unknown use case: ${USE_CASE}"
    exit 1
    ;;
esac

# STRICT ERROR HANDLING
set -e
sleep 1

##############################################
# RUN THROUGHPUT TEST
##############################################


echo "Starting throughput test (5 minutes)..."

START_TIME=$(date +%s)
END_TIME=$((START_TIME + TEST_DURATION))

TOTAL_SENT=0
TOTAL_SUCCESS=0
TOTAL_FAILED=0

while [[ $(date +%s) -lt $END_TIME ]]
do

    TMP_BODY=$(mktemp)


    if [ "$USE_CASE" == "office" ]; then
      METRICS=$(curl -s \
        -o "$TMP_BODY" \
        -w "%{http_code}" \
        -H "Content-Type: application/json" \
        -d "{\"question\": \"${QUESTION}\"}" \
        "$LLM_URL"
      )

    elif [ "$USE_CASE" == "construction" ]; then
      METRICS=$(curl -s \
        -o "$TMP_BODY" \
        -w "%{http_code}" \
        -F "question=${QUESTION}" \
        -F "file=@${FILE_PATH};type=image/jpeg" \
        "$LLM_URL"
      )

    else
      echo "Error: Unknown use case '${USE_CASE}'. Use 'office' or 'construction'."
      exit 1
    fi

    ((TOTAL_SENT++))

    if [[ "$RESPONSE" == "200" ]]; then
        ((TOTAL_SUCCESS++))
        echo "Request $TOTAL_SENT succeeded (HTTP $RESPONSE). Successful so far: $TOTAL_SUCCESS"
    else
        ((TOTAL_FAILED++))
        echo "Request $TOTAL_SENT failed (HTTP $RESPONSE). Failures so far: $TOTAL_FAILED"
    fi

    rm -f "$TMP_BODY"

done

TOTAL_TIME=$(( $(date +%s) - START_TIME ))

if [[ $TOTAL_TIME -gt 0 ]]; then
    THROUGHPUT=$(echo "scale=4; $TOTAL_SUCCESS / $TOTAL_TIME" | bc)
else
    THROUGHPUT="N/A"
fi

echo ""
echo "========================================="
echo "           THROUGHPUT TEST RESULTS"
echo "========================================="
echo "Total requests sent:        $TOTAL_SENT"
echo "Successful requests:        $TOTAL_SUCCESS"
echo "Failed requests:            $TOTAL_FAILED"
echo "Total time (seconds):       $TOTAL_TIME"
echo "Throughput (req/sec):       $THROUGHPUT"
echo "========================================="

##############################################
# SAVE TO CSV
##############################################

if [[ ! -f "$CSV_FILE" ]]; then
    echo "timestamp,use_case,rag_mode,model,processor,prompt_mode,test_duration_sec,total_sent,total_success,total_failed,total_time_sec,throughput_req_per_sec" > "$CSV_FILE"
fi

TIMESTAMP=$(date +"%Y-%m-%d %H:%M:%S")

echo "\"$TIMESTAMP\",\"$USE_CASE\",\"$RAG_MODE\",\"$MODEL\",\"$PROCESSOR\",\"$PROMPT_MODE\",\"$TEST_DURATION\",\"$TOTAL_SENT\",\"$TOTAL_SUCCESS\",\"$TOTAL_FAILED\",\"$TOTAL_TIME\",\"$THROUGHPUT\"" >> "$CSV_FILE"

echo "Results saved to $CSV_FILE"