set -eu

# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# IP address of the k3s node that exposes the services as NodePorts (required)
NODE_IP="${NODE_IP:?Set NODE_IP to the IP address of the k3s node, e.g. NODE_IP=192.0.2.10}"

# NodePorts of the services that expose a /health endpoint
HEALTH_PORTS=(30800 30501 30806 30500)

# NodePort of the image service, which receives the test upload
IMAGE_SERVICE_PORT="${IMAGE_SERVICE_PORT:-30806}"
UPLOAD_URL="http://${NODE_IP}:${IMAGE_SERVICE_PORT}/upload_image"

# Values of the "app" label of the pods whose traffic is captured
SERVICES=(image-service situational-awareness vector-db llm-text-gen-service)

# Sidecar container that runs tcpdump, and the capture file inside it
CAPTURE_CONTAINER="${CAPTURE_CONTAINER:-packet-capture}"
CAPTURE_FILE="${CAPTURE_FILE:-/captures/traffic.pcap}"

# Local files and directories
TEST_IMAGE="${TEST_IMAGE:-$SCRIPT_DIR/test_image.jpg}"        # image to upload
PCAP_ROOT="${PCAP_ROOT:-$SCRIPT_DIR/pcap_results}"            # one subfolder per run
CSV_FILE="${CSV_FILE:-$SCRIPT_DIR/results/measurements.csv}"  # shared results file

# Timing
HEALTH_TIMEOUT="${HEALTH_TIMEOUT:-300}"         # max seconds to wait for /health
POD_READY_TIMEOUT="${POD_READY_TIMEOUT:-60s}"   # passed to kubectl wait
SIGNAL_INTERVAL="${SIGNAL_INTERVAL:-3}"         # seconds between Wi-Fi samples

# Wi-Fi interface to sample; the first wireless interface is used if empty
WIFI_IFACE="${WIFI_IFACE:-}"

# --------------------------------------------------------------------------
# Pre-flight checks
# --------------------------------------------------------------------------

if [[ $EUID -ne 0 ]]; then
  echo "ERROR: Run this script as root (it restarts the k3s service)." >&2
  exit 1
fi

for cmd in systemctl kubectl curl iw tshark awk; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "ERROR: Required command '$cmd' not found." >&2
    exit 1
  fi
done

if [[ ! -f "$TEST_IMAGE" ]]; then
  echo "ERROR: Test image not found: $TEST_IMAGE (set TEST_IMAGE to override)." >&2
  exit 1
fi

if [[ -z "$WIFI_IFACE" ]]; then
  WIFI_IFACE=$(iw dev 2>/dev/null | awk '/Interface/ {print $2; exit}')
fi
if [[ -z "$WIFI_IFACE" ]]; then
  echo "WARNING: No Wi-Fi interface found; signal strength will be recorded as NA." >&2
fi

# Temporary files, removed on exit
SIGNAL_LOG=$(mktemp)
RESPONSE_BODY=$(mktemp)
MONITOR_PID=""

cleanup() {
  # Make sure the background signal monitor never outlives the script
  if [[ -n "$MONITOR_PID" ]]; then
    kill "$MONITOR_PID" 2>/dev/null || true
  fi
  rm -f "$SIGNAL_LOG" "$RESPONSE_BODY"
}
trap cleanup EXIT

# --------------------------------------------------------------------------
# 1. Restart k3s and wait for the services
# --------------------------------------------------------------------------

echo "Restarting k3s..."
systemctl restart k3s

echo "Waiting for all services to report ok (timeout ${HEALTH_TIMEOUT}s)..."
start_time=$SECONDS

while true; do
  all_ok=true

  for port in "${HEALTH_PORTS[@]}"; do
    url="http://${NODE_IP}:${port}/health"
    if curl -s --max-time 2 "$url" | grep -q '"ok"'; then
      echo "  $url ok"
    else
      echo "  $url not ready yet"
      all_ok=false
    fi
  done

  if $all_ok; then
    echo "All services are running!"
    break
  fi

  if (( SECONDS - start_time >= HEALTH_TIMEOUT )); then
    echo "ERROR: Services were not healthy within ${HEALTH_TIMEOUT}s." >&2
    exit 1
  fi

  echo "Retrying in 1 second..."
  sleep 1
done

# A healthy /health endpoint doesn't guarantee the pod is Ready, so wait for that too
for svc in "${SERVICES[@]}"; do
  kubectl wait --for=condition=Ready pod -l "app=$svc" --timeout="$POD_READY_TIMEOUT"
done

echo "Fetching pod names..."

declare -A PODS
missing=false
for svc in "${SERVICES[@]}"; do
  PODS["$svc"]=$(kubectl get pod -l "app=$svc" \
    -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)

  if [[ -z "${PODS[$svc]}" ]]; then
    echo "ERROR: No pod found with label app=$svc" >&2
    missing=true
  else
    echo "  $svc: ${PODS[$svc]}"
  fi
done

if $missing; then
  echo "Check pod labels with: kubectl get pods --show-labels" >&2
  exit 1
fi

# --------------------------------------------------------------------------
# 2. Start packet capture
# --------------------------------------------------------------------------

echo "Starting packet capture in all pods..."
for svc in "${SERVICES[@]}"; do
  # -U writes every packet straight to the file, so nothing is lost on stop
  kubectl exec "${PODS[$svc]}" -c "$CAPTURE_CONTAINER" -- \
    sh -c "nohup tcpdump -i eth0 -nn -U -w '$CAPTURE_FILE' >/dev/null 2>&1 &"
done
echo "Packet capture running!"

# --------------------------------------------------------------------------
# 3. Upload the test image while sampling Wi-Fi signal strength
# --------------------------------------------------------------------------

# Print the current signal level of the Wi-Fi link in dBm (empty if unavailable)
get_signal_strength() {
  [[ -n "$WIFI_IFACE" ]] || return 0
  iw dev "$WIFI_IFACE" link 2>/dev/null | awk '/signal:/ {print $2}'
}

# Append "HH:MM:SS <dBm|NA>" to $SIGNAL_LOG every $SIGNAL_INTERVAL seconds
signal_monitor() {
  set +e   # a failed sample must not stop the monitor
  local signal
  while true; do
    signal=$(get_signal_strength)
    echo "$(date +%H:%M:%S) ${signal:-NA}" >> "$SIGNAL_LOG"
    sleep "$SIGNAL_INTERVAL"
  done
}

echo "Starting background signal measurement..."
signal_monitor &
MONITOR_PID=$!

echo "Sending test image..."
# The response body goes to a file; stdout only receives the -w metrics
METRICS=$(curl -sS -o "$RESPONSE_BODY" \
  -w '%{http_code} %{time_total} %{size_upload}' \
  -F "file=@${TEST_IMAGE}" \
  "$UPLOAD_URL")

# Stop signal monitoring
kill "$MONITOR_PID" 2>/dev/null || true
wait "$MONITOR_PID" 2>/dev/null || true
MONITOR_PID=""

read -r HTTP_CODE TIME_TOTAL BYTES_SENT <<< "$METRICS"
IMAGE_RESPONSE=$(tr -d '\r' < "$RESPONSE_BODY")

echo ""
echo "Image-service response code: $HTTP_CODE"
echo "Response body: $IMAGE_RESPONSE"
echo "TIME_TOTAL=${TIME_TOTAL}s"
echo "BYTES_SENT=$BYTES_SENT"

# Flatten the body to one line and swap double quotes for single quotes
# so it fits in a single quoted CSV field
IMAGE_RESPONSE_CSV=$(printf '%s' "$IMAGE_RESPONSE" | tr '\n' ' ' | sed "s/\"/'/g")

# time_total covers the whole request (connection, upload, server-side
# processing and response), so this is effective throughput rather than
# raw link speed
BANDWIDTH_MBPS=$(awk -v bytes="$BYTES_SENT" -v time="$TIME_TOTAL" \
  'BEGIN { if (time > 0) printf "%.2f", (bytes * 8) / (time * 1000000); else print "NA" }')

echo "Upload bandwidth (external network): $BANDWIDTH_MBPS Mbps"

# --------------------------------------------------------------------------
# 4. Stop captures, collect the pcap files and analyse them
# --------------------------------------------------------------------------

echo "Stopping tcpdump processes..."
for svc in "${SERVICES[@]}"; do
  # SIGTERM lets tcpdump close the capture file cleanly
  timeout 5 kubectl exec "${PODS[$svc]}" -c "$CAPTURE_CONTAINER" -- \
    pkill -TERM tcpdump || true
done
sleep 1   # give tcpdump a moment to exit
echo "tcpdump processes stopped."

SAVE_DIR="$PCAP_ROOT/$(date +%Y%m%d_%H%M%S)"
echo "Saving capture files to $SAVE_DIR ..."
mkdir -p "$SAVE_DIR"

PCAPS=()
for svc in "${SERVICES[@]}"; do
  out="$SAVE_DIR/$svc.pcap"
  kubectl cp "${PODS[$svc]}:$CAPTURE_FILE" "$out" -c "$CAPTURE_CONTAINER"
  PCAPS+=("$out")
done
echo "Captures saved into: $SAVE_DIR"

echo "Calculating average signal strength..."
AVG_SIGNAL=$(awk '$2 != "NA" { sum += $2; n++ }
  END { if (n > 0) printf "%.2f", sum / n; else print "NA" }' "$SIGNAL_LOG")
echo "Average Wi-Fi signal: $AVG_SIGNAL dBm"

echo "Running packet-loss analysis..."
# Counts are summed over all captures, so a packet that passes through
# several captured pods is counted once per capture.
TOTAL=0
RETRANS=0
LOST=0

for p in "${PCAPS[@]}"; do
  echo "Analyzing $p ..."

  T=$(tshark -r "$p" -T fields -e frame.number 2>/dev/null | wc -l)
  R=$(tshark -r "$p" -Y "tcp.analysis.retransmission" 2>/dev/null | wc -l)
  L=$(tshark -r "$p" -Y "tcp.analysis.lost_segment" 2>/dev/null | wc -l)

  echo "  Packets: $T, Retransmissions: $R, Lost: $L"

  TOTAL=$((TOTAL + T))
  RETRANS=$((RETRANS + R))
  LOST=$((LOST + L))
done

echo "Combined results from all captures:"
echo "  Total packets:    $TOTAL"
echo "  Retransmissions:  $RETRANS"
echo "  Lost segments:    $LOST"

# Packet loss ratio = (retransmissions + lost segments) / total packets
PLR="NA"
if (( TOTAL > 0 )); then
  PLR=$(awk -v loss="$((RETRANS + LOST))" -v total="$TOTAL" \
    'BEGIN { printf "%.5f", loss / total }')
fi
echo "Packet loss ratio: $PLR"

# --------------------------------------------------------------------------
# 5. Write the results to the CSV file
# --------------------------------------------------------------------------
#
# The companion Python script writes a partial row with the first five
# columns (run_id ... avg_ram_mb) before this point. That row is replaced
# here with the complete row.

echo "Saving results to CSV..."

CSV_HEADER="run_id,duration_s,energy_joules,avg_cpu_percent,avg_ram_mb,upload_bandwidth_mbps,wifi_signal_dbm,total_packets,retransmissions,lost_segments,packet_loss_ratio,response"

mkdir -p "$(dirname "$CSV_FILE")"
[[ -s "$CSV_FILE" ]] || echo "$CSV_HEADER" > "$CSV_FILE"

LAST_LINE=$(tail -n 1 "$CSV_FILE")
FIELD_COUNT=$(awk -F',' '{ print NF }' <<< "$LAST_LINE")

if (( FIELD_COUNT > 0 && FIELD_COUNT < 12 )); then
  # Partial row from the Python script: keep its fields and replace the line
  PYTHON_FIELDS=$(cut -d',' -f1-5 <<< "$LAST_LINE")
  sed -i '$ d' "$CSV_FILE"
else
  # Last line is the header or an already complete row: don't overwrite it
  echo "WARNING: No partial row from the Python script found; its columns are left empty." >&2
  PYTHON_FIELDS=",,,,"
fi

echo "${PYTHON_FIELDS},${BANDWIDTH_MBPS},${AVG_SIGNAL},${TOTAL},${RETRANS},${LOST},${PLR},\"${IMAGE_RESPONSE_CSV}\"" >> "$CSV_FILE"

echo "Results saved to $CSV_FILE"
echo "All done!"
