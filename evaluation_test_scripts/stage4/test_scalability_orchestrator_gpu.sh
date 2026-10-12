#!/usr/bin/env bash
#
# run_scalability_tests.sh
#
# Orchestrates the full CPU scalability test sweep by launching
# scalability_test_cpu.sh (the single-request worker script) as background
# jobs -- as many at once as the concurrency level being tested calls for.
# This replaces manually opening N terminals: the orchestrator IS the N
# terminals, just running in the background.
#
# What it does:
#   - Iterates over every (Model x Processor x Prompt mode) combination.
#   - For each combination, runs REPETITIONS full passes.
#   - In each pass, tests every value in CONCURRENCY_LEVELS, in a randomized
#     order (reshuffled every pass).
#   - For each concurrency value N, launches N copies of the worker script
#     in the background at (as close to) the same moment, waits for all N to
#     finish, and records:
#       * batch wall-clock time (from launch to last completion)
#       * throughput = N / wall-clock time
#       * how many of the N succeeded / failed
#   - Per-request latency is still recorded by the worker script itself, in
#     the same shared per_request_results.csv as before.
#
# Requirements: bash, the worker script (scalability_test_cpu.sh) in the
# same directory (or set WORKER_SCRIPT below), shuf, bc.
#
# ---------------------------------------------------------------------------
# USAGE
#   ./run_scalability_tests.sh <model>
#
# Edit the CONFIG section below before running.
# ---------------------------------------------------------------------------

set -uo pipefail

# ============================== CONFIG ======================================

MODEL="$1"
PROCESSOR=GPU
PROMPT_MODES=(Simple Medium Advanced)   # Simple Medium Advanced, must match keys used in the worker script

# Concurrency levels to test in each pass.
CONCURRENCY_LEVELS=(1 2 4)

# Fixed concurrency order per repetition (1-indexed to match REPETITIONS below).
declare -A CONCURRENCY_ORDER=(
  [1]="4 1 2"
  [2]="2 4 1"
  [3]="1 2 4"
  [4]="4 2 1"
  [5]="1 4 2"
)

# How many full passes.
REPETITIONS=5

# Path to the worker script.
WORKER_SCRIPT="./test_scalability_gpu.sh"

URLS=(
  "http://<llm-text-server-gpu-node-url-1>:30503/process_query"
  "http://<llm-text-server-gpu-node-url-2>:30503/process_query"
)

# --- Output -------------------------------------------------------------
# Same directory the worker script writes per_request_results.csv into, so
# everything from a sweep ends up together.

OUTPUT_DIR="./scalability_results"
BATCH_CSV="${OUTPUT_DIR}/throughput_results_GPU_${MODEL}.csv"
RESULTS_CSV="${OUTPUT_DIR}/per_request_results_GPU_${MODEL}.csv"
FAILURES_LOG="${OUTPUT_DIR}/failures_GPU.log"

# ============================ END CONFIG ====================================

# ---------------------------------------------------------------------------
# Argument validation
# ---------------------------------------------------------------------------

if [ -z "$MODEL" ]; then
    echo "Usage: $0 <model_name>" >&2
    echo "  e.g. $0 llama" >&2
    echo "  (model_name is just a label for the results - it must match whichever" >&2
    echo "  model is currently deployed in the k3s cluster)" >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# Dependency checks
# ---------------------------------------------------------------------------

fail() {
  echo "ERROR: $*" >&2
  exit 1
}

check_deps() {
  for cmd in bc; do
    command -v "$cmd" >/dev/null 2>&1 || fail "Required command '$cmd' not found."
  done
  [ -x "$WORKER_SCRIPT" ] || fail "Worker script not found or not executable: $WORKER_SCRIPT"
}

init_output() {
  mkdir -p "$OUTPUT_DIR"
  if [ ! -f "$BATCH_CSV" ]; then
    echo "timestamp,model,processor,prompt_mode,repetition,concurrency,batch_wall_time_sec,throughput_req_per_sec,successful_requests,failed_requests" > "$BATCH_CSV"
  fi

  mkdir -p "$OUTPUT_DIR"
  if [ ! -f "$RESULTS_CSV" ]; then
    echo "timestamp#model#processor#prompt_mode#repetition#concurrency_number#terminal_number#node_name#latency_curl#latency_manual#http_status" > "$RESULTS_CSV"
  fi
  touch "$FAILURES_LOG"
}

# --- Core batch runner --------------------------------------------------
# Launches $concurrency copies of the worker script in parallel, one per
# "terminal", waits for all of them, and records batch-level throughput.

run_batch() {
  local MODEL="$1" PROCESSOR="$2" PROMPT_MODE="$3" repetition="$4" concurrency="$5"

  local start_time end_time wall_time
  start_time=$(date +%s.%N)

  local pids=()
  local url
  for ((terminal = 1; terminal <= concurrency; terminal++)); do
    # terminal is 1-based, arrays are 0-based, so subtract 1 before the modulo
    url="${URLS[(terminal - 1) % ${#URLS[@]}]}"

    "$WORKER_SCRIPT" "$MODEL" "$PROCESSOR" "$PROMPT_MODE" "$repetition" "$concurrency" "$terminal" "$url" \
      >>"${OUTPUT_DIR}/worker_stdout.log" 2>&1 &
    pids+=($!)
  done

  local success_count=0
  local fail_count=0
  for pid in "${pids[@]}"; do
    if wait "$pid"; then
      success_count=$((success_count + 1))
    else
      fail_count=$((fail_count + 1))
    fi
  done

  end_time=$(date +%s.%N)
  wall_time=$(echo "$end_time - $start_time" | bc)

  local throughput
  throughput=$(echo "scale=6; ${concurrency} / ${wall_time}" | bc)

  local ts
  ts=$(date '+%Y-%m-%d %H:%M:%S')
  echo "${ts},${MODEL},${PROCESSOR},${PROMPT_MODE},${repetition},${concurrency},${wall_time},${throughput},${success_count},${fail_count}" >> "$BATCH_CSV"
}


# --- Main sweep -----------------------------------------------------------

main() {
  check_deps
  init_output

  for PROMPT_MODE in "${PROMPT_MODES[@]}"; do
    for ((rep = 1; rep <= REPETITIONS; rep++)); do
      for concurrency in ${CONCURRENCY_ORDER[$rep]}; do
        run_batch "$MODEL" "$PROCESSOR" "$PROMPT_MODE" "$rep" "$concurrency"
      done
      sleep 15
    done
    sleep 15
  done

  echo "Done."
  echo "Per-request latencies: ${OUTPUT_DIR}/per_request_results.csv"
  echo "Batch/throughput summary: $BATCH_CSV"
  echo "Failures (if any): ${OUTPUT_DIR}/failures.log"
}

main "$@"