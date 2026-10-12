#!/bin/bash


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


USE_CASE="$1"
RAG_MODE="$2"
MODEL="$3"
PROCESSOR="$4"
PROMPT_MODE="$5"

echo "Running test with parameters:"
echo "Use case: $USE_CASE"
echo "RAG mode: $RAG_MODE"
echo "Model: $MODEL"
echo "Processor: $PROCESSOR"
echo "Prompt mode: $PROMPT_MODE"


##############################################
# PROMPT SELECTION BASED ON USE CASE + MODE
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

echo "Selected prompt: $QUESTION"


# STRICT ERROR HANDLING
set -e
sleep 1


#LLM_URL="http://xxx.xxx.xxx.xxx:30500/process_query"
IMG_FILE_PATH="/path/to/image.jpg"
CSV_FILE="./test_results/S2_load_balance_fault_recovery_construction.csv"

NODE1="usrname1@xxx.xxx.xxx.xxx"
NODE2="usrname2@xxx.xxx.xxx.xxx"

SSH_PASSWORD_1="passwrd1"
SSH_PASSWORD_2="passwrd2"

NODE1_IP="xxx.xxx.xxx.xxx"
NODE2_IP="xxx.xxx.xxx.xxx"

LLM_PORT=30500
IMAGE_PORT=30502
MEASUREMENT_DURATION=15


# ===================================
# CONFIGURATION
# ===================================
REQUESTED_GPU=100  # expected GPU utilization % for ETA calculation
CURL_PIDS=()
VALUES=()
#NODE1_VALUES=()  # node 1 readings only, for AVG/ETA
#NODE2_VALUES=()  # node 2 readings only (optional, for reference)

#REQUESTED_CPU=100  # percent
#NODE1_GPU=()
#NODE1_CPU=()
#NODE2_GPU=()
#NODE2_CPU=()


# ===================================
# SEND CURL REQUESTS ONCE (both nodes)
# ===================================
echo "Sending LLM request to both nodes..."
CURL_PIDS=()
if [ "${USE_CASE}" = "construction" ]; then
    curl --max-time 2 -s http://${NODE1_IP}:${IMAGE_PORT}/process_user_image \
        -F "file=@${IMG_FILE_PATH}" > /dev/null 2>&1 &
    CURL_PIDS+=($!)
    curl --max-time 2 -s http://${NODE2_IP}:${IMAGE_PORT}/process_user_image \
        -F "file=@${IMG_FILE_PATH}" > /dev/null 2>&1 &
    CURL_PIDS+=($!)
elif [ "${USE_CASE}" = "office" ]; then
    curl --max-time 2 -s http://${NODE1_IP}:${LLM_PORT}/process_query \
        -H "Content-Type: application/json" \
        -d "{\"question\": \"${QUESTION}\"}" > /dev/null 2>&1 &
    CURL_PIDS+=($!)
    curl --max-time 2 -s http://${NODE2_IP}:${LLM_PORT}/process_query \
        -H "Content-Type: application/json" \
        -d "{\"question\": \"${QUESTION}\"}" > /dev/null 2>&1 &
    CURL_PIDS+=($!)
fi

sleep 2

# ===================================
# MEASURE BOTH NODES IN PARALLEL (single pass)
# ===================================
echo "Starting GPU measurement for ${MEASUREMENT_DURATION} seconds..."

measure_node() {
    NODE=$1
    SSH_PASSWORD=$2
    sshpass -p "$SSH_PASSWORD" ssh -o ConnectTimeout=5 -o StrictHostKeyChecking=no "$NODE" "
        START=\$(date +%s)
        while [ \$((\$(date +%s) - START)) -lt ${MEASUREMENT_DURATION} ]; do
            TS=\$(date +%H:%M:%S)
            GPU=\$(nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader,nounits 2>/dev/null | awk '{sum+=\$1} END {printf \"%.0f\", sum}')
            echo \"\$TS \$GPU\"
            sleep 1
        done
    "
}


# Collect interleaved output from both nodes measured in parallel.
# measure_node NODE1 runs first in a subshell, then NODE2; both are
# backgrounded so they overlap in time. 'wait' ensures we capture all output.
while IFS= read -r line; do
    echo "$line"
    VALUE=$(echo "$line" | awk '{print $2}')
    if [ -n "$VALUE" ]; then
        VALUES+=("$VALUE")
    fi
done < <( (measure_node "$NODE1" "$SSH_PASSWORD_1" &) ; wait ) #(measure_node "$NODE2" "$SSH_PASSWORD_2" &) ; wait )

# Kill any still-running curl processes
for PID in "${CURL_PIDS[@]}"; do
    if ps -p "$PID" > /dev/null 2>&1; then
        echo "$PID is running. Killing it now."
        kill "$PID"
    fi
done

echo "GPU measurement finished."

# ===================================
# LOAD BALANCE CALCULATION (CoV)
# Pairs are (node1_sample_N, node2_sample_N), interleaved as even/odd indices
# ===================================
PAIR_COUNT=0
COV_SUM=0

for (( i=0; i<${#VALUES[@]}; i+=2 )); do
    VAL1=${VALUES[$i]}
    VAL2=${VALUES[$((i+1))]}

    # Skip if no second value (odd total)
    [ -z "$VAL2" ] && break

    MEAN=$(echo "scale=6; ($VAL1 + $VAL2) / 2" | bc)

    # Skip pair if mean is zero to avoid division by zero
    if [ "$(echo "$MEAN == 0" | bc)" -eq 1 ]; then
        continue
    fi

    DIFF1=$(echo "$VAL1 - $MEAN" | bc)
    DIFF2=$(echo "$VAL2 - $MEAN" | bc)
    VAR=$(echo "scale=6; (($DIFF1 * $DIFF1) + ($DIFF2 * $DIFF2)) / 2" | bc)
    STD=$(echo "scale=6; sqrt($VAR)" | bc)
    COV_PAIR=$(echo "scale=6; $STD / $MEAN" | bc)
    COV_SUM=$(echo "$COV_SUM + $COV_PAIR" | bc)
    PAIR_COUNT=$((PAIR_COUNT + 1))
done

if [ "$PAIR_COUNT" -eq 0 ]; then
    echo "Error: no valid pairs to compute CoV" >&2
    exit 1
fi

COV=$(echo "scale=6; $COV_SUM / $PAIR_COUNT" | bc)
COV_FORMATTED=$(printf "%.4f" "$COV")

# ===================================
# RESOURCE ALLOCATION EFFICIENCY (AVG_GPU + ETA)
# Uses node 1 samples (even indices: 0, 2, 4, ...)
# ===================================
NODE1_SAMPLE_COUNT=0
NODE1_GPU_SUM=0

for (( i=0; i<${#VALUES[@]}; i+=2 )); do
    VAL1=${VALUES[$i]}
    [ -z "$VAL1" ] && continue
    NODE1_GPU_SUM=$(echo "$NODE1_GPU_SUM + $VAL1" | bc)
    NODE1_SAMPLE_COUNT=$((NODE1_SAMPLE_COUNT + 1))
done

if [ "$NODE1_SAMPLE_COUNT" -eq 0 ]; then
    echo "Error: no node 1 samples to compute AVG_GPU" >&2
    exit 1
fi

AVG_GPU=$(echo "scale=6; $NODE1_GPU_SUM / $NODE1_SAMPLE_COUNT" | bc)
ETA_GPU=$(echo "scale=6; $AVG_GPU / $REQUESTED_GPU" | bc)

echo "Results:"
echo "  CoV (load balance):        $COV_FORMATTED"
echo "  AVG_GPU (node 1):          $(printf "%.2f" "$AVG_GPU")%"
echo "  ETA_GPU (allocation eff.): $(printf "%.4f" "$ETA_GPU")"
 
# ===============================
# FAULT RECOVERY TEST
# ===============================

echo "Deleting ALL LLM and Image pods..."

START_MS=$(date +%s%3N)

sudo kubectl delete pod -l app=llm-text-gen-service --grace-period=0 --force > /dev/null 2>&1
sudo kubectl delete pod -l app=image-service --grace-period=0 --force > /dev/null 2>&1

echo "Waiting for deployments to recover..."

sudo kubectl rollout status deployment/llm-text-gen-service --timeout=180s > /dev/null 2>&1
sudo kubectl rollout status deployment/image-service --timeout=180s > /dev/null 2>&1

END_MS=$(date +%s%3N)

RECOVERY_MS=$((END_MS - START_MS))
RECOVERY_SEC=$(echo "scale=3; $RECOVERY_MS/1000" | bc)

sleep 2

# FINAL RESULTS

echo ""
echo "=============================="
echo "FINAL RESULTS"
echo "=============================="
echo "Parameters:"
echo ""
echo "Use case=${USE_CASE}" 
echo "RAG mode=${RAG_MODE}"
echo "Model=${MODEL}"
echo "Processor=${PROCESSOR}"
echo "Prompt mode=${PROMPT_MODE}"
echo "------------------------------"
echo "Load balance, Coefficient of Variation: ${COV_FORMATTED} (GPU)"
echo ""
echo "Fault tolerance, recovery time: ${RECOVERY_MS}"
echo ""
echo "Avg GPU: ${AVG_GPU} %"
echo "GPU Resource Allocation Efficiency: GPU η = ${ETA_GPU}"
echo "=============================="


# ===============================
# SAVE RESULTS TO CSV
# ===============================

echo "Saving response to a csv file..."

# Create header with argument keys
if [[ ! -f "$CSV_FILE" ]]; then
  #echo "RESULTS: STAGE 3: TEST 1" > "$CSV_FILE"
  echo "timestamp#use_case#rag_mode#model#processor#load_balancing_gpu#fault_recovery_ms#avg_gpu#resource_allocation_gpu" > "$CSV_FILE"
fi

# Generate metadata
TIMESTAMP=$(date +"%Y-%m-%d %H:%M:%S")

# Append full row (latency, prompt, response, metadata)
echo "\"${TIMESTAMP}\"#\"${USE_CASE}\"#\"${RAG_MODE}\"#\"${MODEL}\"#\"${PROCESSOR}\"#\"${COV_FORMATTED}\"#\"${RECOVERY_MS}\"#\"${AVG_GPU}\"#\"${ETA_GPU}\"" >> "$CSV_FILE"

# Lastly, restart the image-service pods and print the pod info
sudo kubectl rollout restart deployment/image-service
sudo kubectl get pods -o wide