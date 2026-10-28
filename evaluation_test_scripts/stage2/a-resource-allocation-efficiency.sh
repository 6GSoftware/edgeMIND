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
CSV_FILE="./test_results/S2_load_balance_fault_recovery.csv"


NODE_IP="xxx.xxx.xxx.xxx"
NODE_USER="nodeusrname"
LOGFILE="llm_node_realtime.log"

#REQUESTED_CPU=500     # milliCPU
REQUESTED_GPU=100     # percentage of GPU utilization (adjust based on your model and workload)


echo "Sending request..."

curl -X POST http://$NODE_IP:30500/process_query \
  -F "file=@${IMG_FILE_PATH}" \
  -F "question=${QUESTION}"

sleep 2

echo "Starting GPU measurement for 20 seconds..."

GPU_VALUES=()

while IFS= read -r line; do
  GPU_VALUES+=("$line")
done < <(ssh -t ${NODE_USER}@${NODE_IP} "
timeout 20 bash -c '
while true; do
  echo -n \"\$(date +%H:%M:%S) \"
  nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader,nounits
  sleep 1
done
'")

echo "Calculating GPU averages and allocation efficiency..."

read AVG_GPU ETA_GPU < <(printf '%s\n' "${GPU_VALUES[@]}" | awk '{
  gpu += $2
  n++
} END {
  avg_gpu = gpu / n
  eta_gpu = avg_gpu / '"$REQUESTED_GPU"'
  print avg_gpu, eta_gpu
}')


# ================================
# FINAL RESULTS
# ===============================

echo ""
echo "=============================="
echo "Avg GPU: ${AVG_GPU} %"
echo "GPU Resource Allocation Efficiency: GPU η = ${ETA_GPU}"