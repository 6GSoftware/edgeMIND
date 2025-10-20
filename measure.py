from flask import Flask, request, jsonify
import time
import logging
import csv
import os
from collections import defaultdict

logging.basicConfig(level=logging.INFO)
app = Flask(__name__)
TAG = "measure_service: "

CSV_FILE = "measurements.csv"

# CSV columns
CSV_COLUMNS = [
    "run_id",
    "service",
    "duration_s",
    "start_time",
    "end_time",
    "energy_joules",
    "energy_pkg",
    "energy_dram",
    "avg_cpu",
    "avg_mem",
    "received_at",
]

# All services that must be completed before calculating totals
EXPECTED_SERVICES = {"image_service", "sa", "vector_db"}

# In-memory cache of measurements (keyed by run_id)
measurements_cache = defaultdict(list)


def format_energy(val):
    """Convert list or scalar energy value to float."""
    if val is None:
        return None
    if isinstance(val, list):
        try:
            return sum(float(v) for v in val)
        except Exception:
            return None
    try:
        return float(val)
    except Exception:
        return None


def ensure_csv_exists():
    """Create CSV file with headers if not already existing."""
    if not os.path.exists(CSV_FILE):
        with open(CSV_FILE, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
            writer.writeheader()


def append_to_csv(row: dict):
    """Append one row to CSV."""
    with open(CSV_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writerow(row)


def calculate_and_store_total(run_id):
    """Compute total duration and energy for a run_id, then append a total row."""
    all_entries = measurements_cache[run_id]

    durations = [e.get("duration_s") for e in all_entries if e.get("duration_s") is not None]
    energies = [e.get("energy_joules") for e in all_entries if e.get("energy_joules") is not None]

    if len(durations) < len(EXPECTED_SERVICES) or len(energies) < len(EXPECTED_SERVICES):
        return  # not all services reported yet

    total_duration = sum(durations)
    total_energy = sum(energies)

    total_row = {
        "run_id": run_id,
        "service": "total",
        "duration_s": total_duration,
        "start_time": "",
        "end_time": "",
        "energy_joules": total_energy,
        "energy_pkg": "",
        "energy_dram": "",
        "avg_cpu": "",
        "avg_mem": "",
        "received_at": time.time(),
    }

    append_to_csv(total_row)
    logging.info(f"✅ Total row added for {run_id}: duration={total_duration:.4f}s, energy={total_energy:.6f}J")


@app.route("/measure", methods=["POST"])
def measure():
    """Receive measurement data and store it as one row in the CSV file."""
    data = request.get_json(force=True)

    run_id = data.get("run_id")
    service = data.get("service")
    duration = data.get("duration")
    start_time = data.get("start_time")
    end_time = data.get("end_time")

    energy_total = format_energy(data.get("energy_joules"))
    energy_pkg = format_energy(data.get("energy_pkg"))
    energy_dram = format_energy(data.get("energy_dram"))

    avg_cpu = data.get("avg_cpu")
    avg_mem = data.get("avg_mem")

    logging.info(f"{TAG} Measurement received:")
    logging.info(f"  Run ID: {run_id}")
    logging.info(f"  Service: {service}")
    logging.info(f"  Duration: {duration:.4f} s" if duration else "  Duration: (not provided)")
    logging.info(f"  Energy total: {energy_total:.6f} J" if energy_total else "  Energy: (not provided)")
    if avg_cpu is not None and avg_mem is not None:
        logging.info(f"  Avg CPU: {avg_cpu:.2f}% | Avg MEM: {avg_mem:.2f}%")
    logging.info("-" * 60)

    ensure_csv_exists()

    # Create and store row
    row = {
        "run_id": run_id,
        "service": service,
        "duration_s": duration,
        "start_time": start_time,
        "end_time": end_time,
        "energy_joules": energy_total,
        "energy_pkg": energy_pkg,
        "energy_dram": energy_dram,
        "avg_cpu": avg_cpu,
        "avg_mem": avg_mem,
        "received_at": time.time(),
    }

    append_to_csv(row)

    # Add to in-memory cache for total calculation
    measurements_cache[run_id].append(row)

    # If all services have reported → compute total
    reported_services = {r["service"] for r in measurements_cache[run_id]}
    if EXPECTED_SERVICES.issubset(reported_services):
        calculate_and_store_total(run_id)

    return jsonify({"status": "ok"}), 200


@app.route("/health", methods=["GET"])
def health():
    """Simple health check endpoint."""
    return jsonify({"status": "ok"}), 200


if __name__ == "__main__":
    ensure_csv_exists()
    app.run(host="0.0.0.0", port=5030, debug=False)

