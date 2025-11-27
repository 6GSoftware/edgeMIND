import csv
import os

def save(sa_result, cpu_values, ram_values, energy_joules, duration, run_id):
    sa_cpu_values = sa_result.get("cpu_values", [])
    sa_ram_values = sa_result.get("ram_values", [])
    sa_energy = sa_result.get("energy_joules", 0)
    sa_duration = sa_result.get("duration", 0)

    # Combine values from both services
    all_cpu_values = cpu_values + sa_cpu_values
    avg_cpu = sum(all_cpu_values) / len(all_cpu_values) if all_cpu_values else 0

    all_ram_values = ram_values + sa_ram_values
    avg_ram_mb = sum(all_ram_values) / len(all_ram_values) if all_ram_values else 0

    energy_total = energy_joules + sa_energy
    total_duration = duration + sa_duration

    print("------ MEASUREMENT DEBUG ------")
    print(f"len(sa_cpu_values): {len(sa_cpu_values)}")
    print(f"len(sa_ram_values): {len(sa_ram_values)}")
    print(f"len(cpu_values): {len(cpu_values)}")
    print(f"len(ram_values): {len(ram_values)}")
    print(f"avg_cpu: {avg_cpu:.2f}%")
    print(f"avg_ram: {avg_ram_mb:.2f} MB")
    print(f"energy_total: {energy_total:.6f} J")
    print(f"total_duration: {total_duration:.4f} s")
    print("--------------------------------")

    # Prepare the row for saving
    row = {
        "run_id": run_id,
        "duration_s": total_duration,
        "energy_joules": energy_total,
        "avg_cpu_percent": avg_cpu,
        "avg_ram_mb": avg_ram_mb,
    }

    # File path and headers
    csv_file_path = "/results/measurements.csv"
    fieldnames = [
    "run_id",
    "duration_s",
    "energy_joules",
    "avg_cpu_percent",
    "avg_ram_mb",
    "upload_bandwidth_mbps",
    "wifi_signal_dbm",
    "total_packets",
    "retransmissions",
    "lost_segments",
    "packet_loss_ratio",
    "response"
    ]

    # Create file if it doesn't exist and append data
    file_exists = os.path.isfile(csv_file_path)
    with open(csv_file_path, mode='a', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

        # Write header only once
        if not file_exists:
            writer.writeheader()

        # Write the measurement row
        writer.writerow(row)

    print(f"[SAVE] Measurement saved to {csv_file_path}")
