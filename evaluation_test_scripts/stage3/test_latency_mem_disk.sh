#!/bin/bash
# =============================================================================
# Master node benchmark script to test EdgeMIND system latency, memory usage,
# disk I/O, and VRAM (n2 only) under load.
#
# Usage:
#   bash benchmark_master.sh <use_case> <rag_mode> <model> <processor> <prompt_mode>
# Example:
#   bash benchmark_master.sh construction ragsa llama gpu advanced
#
# Use cases   : office, construction
# RAG modes   : ragonly, ragsa
# Models      : llama, gemma, phi
# Processors  : cpu, gpu
# Prompt modes: simple, medium, advanced
# =============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# ARGUMENTS
# ---------------------------------------------------------------------------
if [[ $# -lt 5 ]]; then
  echo "Usage: $0 <use_case> <rag_mode> <model> <processor> <prompt_mode>"
  echo "Example: $0 construction ragsa llama gpu advanced"
  echo "--------------------------------"
  echo "Use cases   : office, construction"
  echo "RAG modes   : ragonly, ragsa"
  echo "Models      : llama, gemma, phi"
  echo "Processors  : cpu, gpu"
  echo "Prompt modes: simple, medium, advanced"
  exit 1
fi

echo "Running EdgeMIND tests (stages 3 and 4)."

USE_CASE="$1"
RAG_MODE="$2"
MODEL="$3"
PROCESSOR="$4"
PROMPT_MODE="$5"

# ---------------------------------------------------------------------------
# TEST CONFIGURATION
# ---------------------------------------------------------------------------
WORKER1_IP="xxx.xxx.xxx.xxx"
WORKER2_IP="xxx.xxx.xxx.xxx"
NODE1_USER="ursname1"
NODE2_USER="ursname2"
SSH_PASS="???"  # WARNING: INSECURE! Make sure this is only used in a safe testing environment.

LLM_URL="http://xxx.xxx.xxx.xxx:30500/process_query"  # LLM server URL (update IP if needed)
FILE_PATH="/path/to/image.jpg"

SAMPLE_INTERVAL=0.5   # seconds between samples

BASELINE_DURATION=20   # seconds of baseline sampling before request
#POST_DURATION=10       # seconds of post-request sampling after response

RESULTS_DIR="/path/to/results/directory"
mkdir -p "${RESULTS_DIR}"

# One CSV per node — named as requested
CSV_N1="${RESULTS_DIR}/S3_M5_mem_disk_node1.csv"
CSV_N2="${RESULTS_DIR}/S3_M5_mem_disk_node2.csv"
#CSV_N1="${RESULTS_DIR}/test_mem_disk_node1_GPU.csv"
#CSV_N2="${RESULTS_DIR}/test_mem_disk_vram_node2_GPU.csv"

AVAILABILITY_CSV="${RESULTS_DIR}/S4_M3_system_availability.csv"

# ---------------------------------------------------------------------------
# PROMPT SELECTION
# ---------------------------------------------------------------------------
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

# ---------------------------------------------------------------------------
# PRE-FLIGHT CHECKS
# ---------------------------------------------------------------------------
if [[ ! -f "${FILE_PATH}" ]]; then
  echo "[ERROR] Image file not found: ${FILE_PATH}"
  exit 1
fi

# ---------------------------------------------------------------------------
# CSV HEADERS — written only if the files do not exist yet
# ---------------------------------------------------------------------------

# n1: memory + disk I/O (no VRAM)
if [[ ! -f "${CSV_N1}" ]]; then
  echo "timestamp#use_case#rag_mode#model#processor#prompt_mode#node#measurement_type#mem_used_raw_mib#mem_used_effective_mib#mem_total_mib#mem_raw_%#mem_effective_%#disk_read_kb_s#disk_write_kb_s#disk_read_sectors_cumul#disk_write_sectors_cumul" \
    > "${CSV_N1}"
fi

# n2: memory + disk I/O + VRAM
if [[ ! -f "${CSV_N2}" ]]; then
  echo "timestamp#use_case#rag_mode#model#processor#prompt_mode#node#measurement_type#mem_used_raw_mib#mem_used_effective_mib#mem_total_mib#mem_raw_%#mem_effective_%#disk_read_kb_s#disk_write_kb_s#disk_read_sectors_cumul#disk_write_sectors_cumul" \
    > "${CSV_N2}"
fi

if [[ ! -f "${AVAILABILITY_CSV}" ]]; then
  echo "timestamp#use_case#rag_mode#model#processor#prompt_mode#duration_ms#system_status#available#availability_before#availability_after" \
    > "${AVAILABILITY_CSV}"
fi

# ---------------------------------------------------------------------------
# HELPER: run a command on a remote worker node via sshpass
# ---------------------------------------------------------------------------
remote() {
  local NODE_IP="$1"
  local NODE_USER="$2"
  shift 2
  sshpass -p "${SSH_PASS}" ssh \
    -o StrictHostKeyChecking=no \
    -o ConnectTimeout=5 \
    "${NODE_USER}@${NODE_IP}" "$@"
}

# ---------------------------------------------------------------------------
# HELPER: fetch cumulative sectors_read and sectors_written from /proc/diskstats
# on a remote node. Runs entirely in one SSH call to avoid quoting issues.
#
# /proc/diskstats columns used: 6=sectors_read, 10=sectors_written (512 B each)
# Handles plain partitions (sda1), NVMe partitions (nvme0n1p3), and LVM/dm paths.
#
# Prints: "<sectors_read> <sectors_written>"  or  "ERR_<reason>"
# ---------------------------------------------------------------------------
get_disk_sectors() {
  local NODE_IP="$1" NODE_USER="$2"
 
  local STATS
  STATS=$(remote "${NODE_IP}" "${NODE_USER}" bash << 'REMOTE'
set -uo pipefail
 
RAW=$(df "/" 2>/dev/null | awk 'NR==2{print $1}')
[[ -z "$RAW" ]] && { echo "ERR_NO_DF"; exit 0; }
 
# Resolve LVM/device-mapper paths to the underlying block device
if [[ "$RAW" == /dev/mapper/* ]]; then
  DM_NAME=$(basename "$RAW")
  SLAVE=$(dmsetup deps -o devname "$DM_NAME" 2>/dev/null | grep -oP '\(\K[^)]+' | head -1)
  if [[ -n "$SLAVE" ]]; then
    RAW="/dev/${SLAVE}"
  else
    DM_DEV=$(basename "$(readlink -f "$RAW" 2>/dev/null || echo "")")
    SLAVE=$(ls /sys/block/${DM_DEV}/slaves/ 2>/dev/null | head -1)
    [[ -n "$SLAVE" ]] && RAW="/dev/${SLAVE}"
  fi
fi
 
PART=$(basename "$RAW")
 
# Strip partition suffix to get the parent disk name
if   [[ "$PART" =~ ^(nvme[0-9]+n[0-9]+)p[0-9]+$ ]]; then DISK="${BASH_REMATCH[1]}"  # nvme0n1p3 -> nvme0n1
elif [[ "$PART" =~ ^([a-z]+[a-z])[0-9]+$         ]]; then DISK="${BASH_REMATCH[1]}"  # sda1 -> sda
else                                                        DISK="$PART"               # already a whole disk
fi
 
# Prefer the whole-disk entry; fall back to the partition entry
LINE=$(awk -v d="$DISK" '$3==d{print $6,$10; exit}' /proc/diskstats 2>/dev/null)
[[ -z "$LINE" ]] && LINE=$(awk -v d="$PART" '$3==d{print $6,$10; exit}' /proc/diskstats 2>/dev/null)
 
[[ -z "$LINE" ]] && { echo "ERR_NO_DISKSTATS:DISK=${DISK}:PART=${PART}"; exit 0; }
echo "$LINE"
REMOTE
  2>/dev/null) || { echo "ERR_SSH"; return; }
 
  if [[ "${STATS}" == ERR_* ]]; then
    echo "[WARN] disk_sectors ${NODE_IP}: ${STATS}" >&2
    echo "ERR"
    return
  fi
 
  echo "${STATS}"
}


##############################################
# HELPER: compute KB/s from two sector counts and a nanosecond time delta.
# Prints: "<read_kb_s> <write_kb_s>"
##############################################
calc_disk_rate() {
  local CUR_R="$1" CUR_W="$2" PREV_R="$3" PREV_W="$4" DELTA_NS="$5"
  awk "BEGIN {
    printf \"%.1f %.1f\n\",
      ((${CUR_R} - ${PREV_R}) / 2) / (${DELTA_NS} / 1000000000),
      ((${CUR_W} - ${PREV_W}) / 2) / (${DELTA_NS} / 1000000000)
  }"
}

##############################################
# AVAILABILITY CHECK HELPER
##############################################

# Returns "UP" if the deployment has at least 1 ready pod, "DOWN" otherwise.
check_pod_availability() {
  local DEPLOYMENT=$1
  READY=$(sudo kubectl get deployment "$DEPLOYMENT" \
    -o jsonpath='{.status.readyReplicas}' 2>/dev/null)
  if [[ "$READY" =~ ^[1-9][0-9]*$ ]]; then
    echo "UP"
  else
    echo "DOWN"
  fi
}

# Checks all deployments in the provided list and returns a combined status string.
# Format: "llm-text-gen-service=UP,vector-db=DOWN,..."
check_all_deployments() {
  local DEPLOYMENTS=("$@")
  local RESULTS=()
  for DEPLOYMENT in "${DEPLOYMENTS[@]}"; do
    STATUS=$(check_pod_availability "$DEPLOYMENT")
    RESULTS+=("${DEPLOYMENT}=${STATUS}")
  done
  echo "$(IFS=,; echo "${RESULTS[*]}")"
}

# Returns "CRASHED" if any deployment in the status string is DOWN, "OK" otherwise.
any_down() {
  local STATUS_STR=$1
  if echo "$STATUS_STR" | grep -q "=DOWN"; then
    echo "CRASHED"
  else
    echo "OK"
  fi
}
 
# ---------------------------------------------------------------------------
# SAMPLING LOOP
# Runs in the background, writing one CSV row per node per second.
# Stops when /tmp/benchmark_stop is created.
#
# Disk state (prev sector counts + timestamp) is kept as plain local variables
# here so it persists across iterations — $() subshells cannot do this.
# ---------------------------------------------------------------------------
sampling_loop() {
  local MEASUREMENT_TYPE="$1"
  local STOP_FILE="/tmp/benchmark_stop"
  rm -f "${STOP_FILE}"
 
  local PREV_READ_N1=0 PREV_WRITE_N1=0 PREV_TS_N1=0
  local PREV_READ_N2=0 PREV_WRITE_N2=0 PREV_TS_N2=0
  local FIRST_ITER=1
 
  while [[ ! -f "${STOP_FILE}" ]]; do
    local TS NOW
    TS=$(date +"%Y-%m-%dT%H:%M:%S")
    NOW=$(date +%s%N)
    local META="${USE_CASE}#${RAG_MODE}#${MODEL}#${PROCESSOR}#${PROMPT_MODE}"
 
    # ---- NODE 1 (n1) -------------------------------------------------------
    local MEM_N1
    MEM_N1=$(remote "${WORKER1_IP}" "${NODE1_USER}" \
      "free -m | awk '/^Mem:/ {
        t=\$2;
        ur=\$3;
        a=\$7;
        ue=t-a;
        pr=(t>0?ur/t*100:0);
        pe=(t>0?ue/t*100:0);
        printf \"%d %d %d %.1f %.1f\", ur, ue, t, pr, pe
      }'" \
      2>/dev/null) || MEM_N1="0 0 0 0 0"

    read -r \
      MEM_USED_RAW_N1 \
      MEM_USED_EFFECTIVE_N1 \
      MEM_TOTAL_N1 \
      MEM_PCT_RAW_N1 \
      MEM_PCT_EFFECTIVE_N1 \
    <<< "${MEM_N1}"
 
    local SECT_N1 CUR_READ_N1 CUR_WRITE_N1 DISK_R_N1 DISK_W_N1
    SECT_N1=$(get_disk_sectors "${WORKER1_IP}" "${NODE1_USER}")
    if [[ "${SECT_N1}" == ERR* || -z "${SECT_N1}" ]]; then
      CUR_READ_N1=$PREV_READ_N1; CUR_WRITE_N1=$PREV_WRITE_N1; DISK_R_N1=0; DISK_W_N1=0
    else
      read -r CUR_READ_N1 CUR_WRITE_N1 <<< "${SECT_N1}"
      if [[ $FIRST_ITER -eq 0 ]]; then
        read -r DISK_R_N1 DISK_W_N1 <<< "$(calc_disk_rate "${CUR_READ_N1}" "${CUR_WRITE_N1}" "${PREV_READ_N1}" "${PREV_WRITE_N1}" "$(( NOW - PREV_TS_N1 ))")"
      else
        DISK_R_N1=0; DISK_W_N1=0
      fi
    fi
    PREV_READ_N1=$CUR_READ_N1; PREV_WRITE_N1=$CUR_WRITE_N1; PREV_TS_N1=$NOW
 
    echo "${TS}#${META}#${NODE1_USER}#${MEASUREMENT_TYPE}#${MEM_USED_RAW_N1}#${MEM_USED_EFFECTIVE_N1}#${MEM_TOTAL_N1}#${MEM_PCT_RAW_N1}#${MEM_PCT_EFFECTIVE_N1}#${DISK_R_N1}#${DISK_W_N1}#${CUR_READ_N1}#${CUR_WRITE_N1}" \
      >> "${CSV_N1}"
 
    # ---- NODE 2 (n2) -------------------------------------------------------
    local MEM_N2
    MEM_N2=$(remote "${WORKER2_IP}" "${NODE2_USER}" \
      "free -m | awk '/^Mem:/ {
        t=\$2;
        ur=\$3;
        a=\$7;
        ue=t-a;
        pr=(t>0?ur/t*100:0);
        pe=(t>0?ue/t*100:0);
        printf \"%d %d %d %.1f %.1f\", ur, ue, t, pr, pe
      }'" \
      2>/dev/null) || MEM_N2="0 0 0 0 0"

    read -r \
      MEM_USED_RAW_N2 \
      MEM_USED_EFFECTIVE_N2 \
      MEM_TOTAL_N2 \
      MEM_PCT_RAW_N2 \
      MEM_PCT_EFFECTIVE_N2 \
    <<< "${MEM_N2}"

    local SECT_N2 CUR_READ_N2 CUR_WRITE_N2 DISK_R_N2 DISK_W_N2
    SECT_N2=$(get_disk_sectors "${WORKER2_IP}" "${NODE2_USER}")
    if [[ "${SECT_N2}" == ERR* || -z "${SECT_N2}" ]]; then
      CUR_READ_N2=$PREV_READ_N2; CUR_WRITE_N2=$PREV_WRITE_N2; DISK_R_N2=0; DISK_W_N2=0
    else
      read -r CUR_READ_N2 CUR_WRITE_N2 <<< "${SECT_N2}"
      if [[ $FIRST_ITER -eq 0 ]]; then
        read -r DISK_R_N2 DISK_W_N2 <<< "$(calc_disk_rate "${CUR_READ_N2}" "${CUR_WRITE_N2}" "${PREV_READ_N2}" "${PREV_WRITE_N2}" "$(( NOW - PREV_TS_N2 ))")"
      else
        DISK_R_N2=0; DISK_W_N2=0
      fi
    fi
    PREV_READ_N2=$CUR_READ_N2; PREV_WRITE_N2=$CUR_WRITE_N2; PREV_TS_N2=$NOW
 
#    local VRAM_N2
#    VRAM_N2=$(get_vram "${WORKER2_IP}" "${NODE2_USER}")
#    read -r VRAM_USED_N2 VRAM_TOTAL_N2 VRAM_PCT_N2 <<< "${VRAM_N2}"
 
    echo "${TS}#${META}#${NODE2_USER}#${MEASUREMENT_TYPE}#${MEM_USED_RAW_N2}#${MEM_USED_EFFECTIVE_N2}#${MEM_TOTAL_N2}#${MEM_PCT_RAW_N2}#${MEM_PCT_EFFECTIVE_N2}#${DISK_R_N2}#${DISK_W_N2}#${CUR_READ_N2}#${CUR_WRITE_N2}" \
      >> "${CSV_N2}"
 
    FIRST_ITER=0
    #sleep "${SAMPLE_INTERVAL}"
  done
}


##############################################
# CLEANUP TRAP
# Kills all background/child processes in this script's process group on exit.
##############################################

cleanup() {
  trap - EXIT INT TERM ERR   # disarm all traps first to prevent re-entry
  echo "[cleanup] Caught signal or error — killing background processes..." >&2
  touch "/tmp/benchmark_stop"
  kill -- -$$ 2>/dev/null || true
}
trap cleanup EXIT INT TERM ERR


##############################################
# SELECT DEPLOYMENTS FOR USE CASE
##############################################

if [ "$USE_CASE" == "office" ]; then
  DEPLOYMENTS=("llm-text-gen-service" "vector-db" "situational-awareness")
elif [ "$USE_CASE" == "construction" ]; then
  DEPLOYMENTS=("llm-text-gen-service" "image-service" "vector-db" "situational-awareness")
else
  echo "Error: Unknown use case '${USE_CASE}'. Use 'office' or 'construction'."
  exit 1
fi

 
##############################################
# HELPER: run sampling_loop as a background job for a fixed duration, then stop it.
##############################################

run_sampling_phase() {
  local PHASE="$1" DURATION="$2"
  echo "  [${PHASE}] Sampling for ${DURATION}s..."
  sampling_loop "${PHASE}" &
  local PID=$!
  sleep "${DURATION}"
  touch "/tmp/benchmark_stop"
  wait "${PID}" 2>/dev/null || true
  rm -f "/tmp/benchmark_stop"
  echo "  [${PHASE}] Done."
}


##############################################
# PRE-REQUEST AVAILABILITY CHECK
##############################################

AVAILABILITY_BEFORE=$(check_all_deployments "${DEPLOYMENTS[@]}")
echo "Pod availability before request: $AVAILABILITY_BEFORE"

 
##############################################
# PHASE 1 - Baseline
##############################################

echo ""
echo "=== Phase 1: Baseline (${BASELINE_DURATION}s) ==="
run_sampling_phase "baseline" "${BASELINE_DURATION}"
 
##############################################
# PHASE 2 - Workload: sampler starts, request is sent, sampler stops on response
##############################################

echo ""
echo "=== Phase 2: Workload ==="
echo "  Starting workload sampler..."
sampling_loop "workload" &
SAMPLER_PID=$!
 
echo "  Sending HTTP request..."
TMP_BODY=$(mktemp)
START_TS=$(date +"%Y-%m-%dT%H:%M:%S")
T0=$(date +%s%N)

if [ "$USE_CASE" == "office" ]; then
  METRICS=$(curl -s \
    -o "$TMP_BODY" \
    -w "%{http_code}\n%{time_total}" \
    -H "Content-Type: application/json" \
    -d "{\"question\": \"${QUESTION}\"}" \
    "$LLM_URL"
  ) || { echo "[ERROR] curl failed"; exit 1; }

elif [ "$USE_CASE" == "construction" ]; then
  METRICS=$(curl -s \
    -o "$TMP_BODY" \
    -w "%{http_code}\n%{time_total}" \
    -F "question=${QUESTION}" \
    -F "file=@${FILE_PATH};type=image/jpeg" \
    "$LLM_URL"
  ) || { echo "[ERROR] curl failed"; exit 1; }
fi
 
T1=$(date +%s%N)
END_TS=$(date +"%Y-%m-%dT%H:%M:%S")
DURATION_MS=$(( (T1 - T0) / 1000000 ))
 
touch "/tmp/benchmark_stop"
wait "${SAMPLER_PID}" 2>/dev/null || true
rm -f "/tmp/benchmark_stop"
echo "  Response received. Workload sampler stopped."


##############################################
# PHASE 3 - Post-request cooldown
##############################################
echo ""
echo "=== Phase 3: Post-request (${BASELINE_DURATION}s) ==="
run_sampling_phase "post" "${BASELINE_DURATION}"
 

##############################################
# POST-REQUEST AVAILABILITY CHECK
##############################################

AVAILABILITY_AFTER=$(check_all_deployments "${DEPLOYMENTS[@]}")
echo "Pod availability after request: $AVAILABILITY_AFTER"

##############################################
# DETERMINE SYSTEM STATUS
##############################################

mapfile -t METRIC_LINES <<< "$METRICS"
HTTP_CODE="${METRIC_LINES[0]}"
CURL_TIME="${METRIC_LINES[1]}"

if [[ "$(any_down "$AVAILABILITY_BEFORE")" == "CRASHED" ]]; then
  SYSTEM_STATUS="DOWN_BEFORE"
elif [[ "$HTTP_CODE" == "000" ]]; then
  SYSTEM_STATUS="CRASHED_NO_RESPONSE"
elif [[ "$(any_down "$AVAILABILITY_AFTER")" == "CRASHED" ]]; then
  SYSTEM_STATUS="CRASHED_AFTER"
elif [[ "$HTTP_CODE" != 2* ]]; then
  SYSTEM_STATUS="HTTP_ERROR_${HTTP_CODE}"
else
  SYSTEM_STATUS="OK"
fi

echo "System status: $SYSTEM_STATUS"

if [[ "$SYSTEM_STATUS" == "OK" ]]; then
  AVAILABLE="yes"
else
  AVAILABLE="no"
fi

##############################################
# PARSE RESPONSE
##############################################

echo "Extracting information from the response..."

LLM_RESPONSE=$(cat "$TMP_BODY")
rm "$TMP_BODY"

if [[ "$SYSTEM_STATUS" == "OK" ]] || [[ "$SYSTEM_STATUS" == HTTP_ERROR* ]]; then
  if ! jq empty <<< "$LLM_RESPONSE" 2>/dev/null; then
    echo "Invalid JSON from LLM server" >&2
    exit 1
  fi
  LLM_MESSAGE=$(jq -r '.message // ""' <<< "$LLM_RESPONSE")
  DB_RESULT=$(jq -r '.db_result // ""' <<< "$LLM_RESPONSE")
else
  LLM_MESSAGE=""
  DB_RESULT=""
fi

csv_escape() {
  echo "$1" | tr '\n' ' ' | sed 's/#/-/g'
}

LLM_MESSAGE_CSV=$(csv_escape "$LLM_MESSAGE")
DB_RESULT_CSV=$(csv_escape "$DB_RESULT")


##############################################
# SAVE TO CSV
##############################################

echo "Saving response to a csv file..."

PROMPT_SAFE=$(echo "$QUESTION" | sed "s/\"/'/g")

echo "\"${START_TS}\"#\"${USE_CASE}\"#\"${RAG_MODE}\"#\"${MODEL}\"#\"${PROCESSOR}\"#\"${PROMPT_MODE}\"#\"${DURATION_MS}\"#\"${SYSTEM_STATUS}\"#\"${AVAILABLE}\"#\"${AVAILABILITY_BEFORE}\"#\"${AVAILABILITY_AFTER}\"" >> "$AVAILABILITY_CSV"


##############################################
# SUMMARY
##############################################
echo ""
echo "=============================="
echo "  Test complete"
echo "=============================="
echo "  Use case     : ${USE_CASE}"
echo "  RAG mode     : ${RAG_MODE}"
echo "  Model        : ${MODEL}"
echo "  Processor    : ${PROCESSOR}"
echo "  Prompt mode  : ${PROMPT_MODE}"
echo "  Question     : ${QUESTION}"
echo "  HTTP status  : ${HTTP_CODE}"
echo "  Duration     : ${DURATION_MS} ms"
echo "  Response     : ${LLM_RESPONSE}"
echo "  DB result    : ${DB_RESULT}"
echo "  Available    : ${AVAILABLE}"
echo "=============================="