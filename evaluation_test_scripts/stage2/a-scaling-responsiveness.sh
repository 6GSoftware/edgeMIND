#!/bin/bash
set -euo pipefail


if [[ $# -lt 4 ]]; then
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
#PROMPT_MODE="$5"

echo "Running test with parameters:"
echo "Use case: $USE_CASE"
echo "RAG mode: $RAG_MODE"
echo "Model: $MODEL"
echo "Processor: $PROCESSOR"
#echo "Prompt mode: $PROMPT_MODE"


# STRICT ERROR HANDLING
set -e
sleep 1


IMG_FILE_PATH="/path/to/image.jpg"
CSV_FILE="./test_results/S2_scaling_responsiveness_construction.csv"


#DEPLOYMENT="llm-text-gen-service"
#APP_LABEL="app=llm-text-gen-service"
DEPLOYMENT="image-service"
APP_LABEL="app=image-service"

NODE_IP="xxx.xxx.xxx.xxx"
LLM_PORT="30500"
IMG_PORT="30502"


echo "======================================"
echo "SCALING RESPONSIVENESS MEASUREMENT"
echo "======================================"

# Reset to single pod baseline
kubectl scale deployment llm-text-gen-service --replicas=1
sleep 3

# Clean up any stray pods
PODS_TO_DELETE=$(kubectl get pods -l "$APP_LABEL" \
  -o jsonpath='{range .items[*]}{.metadata.name}{"|"}{range .status.containerStatuses[*]}{.ready}{" "}{end}{"\n"}{end}' \
  | grep -v 'image-service=true' \
  | cut -d'|' -f1)

for pod in $PODS_TO_DELETE; do
  echo "Deleting pod: $pod"
  kubectl delete pod "$pod" --grace-period=0 --force
done

sleep 3

BASE_POD=$(kubectl get pods -l "$APP_LABEL" -o jsonpath='{.items[0].metadata.name}')
echo "[INFO] Base pod: $BASE_POD"

echo "Checking initial pod status..."
kubectl get pods -o wide -l "$APP_LABEL"

LOAD_START=$(date +%s%3N)
echo "[LOAD_START] $LOAD_START ms"
echo "[INFO] Starting GPU stress test on llm-text-gen-service..."

# GPU stress instead of CPU stress
kubectl exec $(kubectl get pod -l "$APP_LABEL" -o jsonpath='{.items[0].metadata.name}') \
  -c image-service -- sh -c \
  "python3 -c \"
import torch
t = torch.randn(10000, 10000, device='cuda')
while True:
    torch.mm(t, t)
\"" &
STRESS_PID=$!

echo "[INFO] Waiting for scaling to 2 Ready pods..."
while true; do
  READY_COUNT=$(kubectl get pods -l "$APP_LABEL" \
    --field-selector=status.phase=Running \
    -o jsonpath='{range .items[*]}{range .status.containerStatuses[*]}{.name}{"="}{.ready}{" "}{end}{"\n"}{end}' \
    | grep -c 'image-service=true')
  echo "Ready pods: $READY_COUNT"
  [[ "$READY_COUNT" -ge 2 ]] && break
  sleep 2
done

READY_TS=$(date +%s%3N)
LATENCY=$((READY_TS - LOAD_START))

echo ""
echo "======================================"
echo "RESULT"
echo "======================================"
echo "Scaling responsiveness (Ts): ${LATENCY} ms"
echo "======================================"

# Cleanup
kill $STRESS_PID 2>/dev/null || true
kubectl exec $(kubectl get pod -l "$APP_LABEL" -o jsonpath='{.items[0].metadata.name}') \
  -c image-service -- sh -c "pkill python3" 2>/dev/null || true


# ===============================
# SAVE RESULTS TO CSV
# ===============================

echo "Saving response to a csv file..."

# Create header with argument keys
if [[ ! -f "$CSV_FILE" ]]; then
  echo "timestamp#use_case#rag_mode#model#processor#scaling_responsiveness_ms" > "$CSV_FILE"
fi

# Generate metadata
TIMESTAMP=$(date +"%Y-%m-%d %H:%M:%S")

# Append full row (latency, prompt, response, metadata)
echo "\"${TIMESTAMP}\"#\"${USE_CASE}\"#\"${RAG_MODE}\"#\"${MODEL}\"#\"${PROCESSOR}\"#\"${LATENCY}\"" >> "$CSV_FILE"
