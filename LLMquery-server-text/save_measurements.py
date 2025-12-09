import csv
import os
import json

IN_K3S = os.path.exists("/var/run/secrets/kubernetes.io/serviceaccount/token")

EXTRAS_PATH = "/results2/query_extras.jsonl"

def save(image_result, cpu_values, ram_values, energy_joules, duration, run_id, prompt, mode, define_model, user_question, permanent_chunks):
    image_cpu_values = image_result.get("cpu_values", [])
    image_ram_values = image_result.get("ram_values", [])
    image_energy = image_result.get("energy_joules", 0)
    # image_duration = image_result.get("duration", 0)

    # Combine values from both services
    all_cpu_values = cpu_values + image_cpu_values
    avg_cpu = sum(all_cpu_values) / len(all_cpu_values) if all_cpu_values else 0

    all_ram_values = ram_values# + sa_ram_values
    avg_ram_mb = sum(all_ram_values) / len(ram_values) if ram_values else 0

    energy_total = energy_joules + image_energy
    total_duration = duration #+ image_duration

    print("------ MEASUREMENT DEBUG ------")
    print(f"len(image_cpu_values): {len(image_cpu_values)}")
    print(f"len(image_ram_values): {len(image_ram_values)}")
    print(f"len(cpu_values): {len(cpu_values)}")
    print(f"len(ram_values): {len(ram_values)}")
    print(f"avg_cpu: {avg_cpu:.2f}%")
    print(f"avg_ram: {avg_ram_mb:.2f} MB")
    print(f"energy_total: {energy_total:.6f} J")
    print(f"total_duration: {total_duration:.4f} s")
    print("--------------------------------")

    print("SAVEEEEEEE")
    print(f"user_question: {user_question}")
    print(f"permanent_chunks: {permanent_chunks}")


    permanent_chunks_str = json.dumps(permanent_chunks, ensure_ascii=False)

    user_question_safe = user_question.replace("\n", " ").replace('"', "'")

    # Prepare the row for saving
    row = {
        "run_id": run_id,
        "duration_s": total_duration,
        "energy_joules": energy_total,
        "avg_cpu_percent": avg_cpu,
        "avg_ram_mb": avg_ram_mb,
        "prompt": prompt,
        "mode": mode,
        "define_model": define_model,

        # Leave the rest empty for Bash:
    }

    # File path and headers
    csv_file_path = "/results2/query_measurements.csv"
    fieldnames = [
        "run_id",
        "duration_s",
        "energy_joules",
        "avg_cpu_percent",
        "avg_ram_mb",
        "prompt",
        "mode",
        "define_model",

        # Bash fills these:
        "wifi_signal_dbm",
        "total_packets",
        "total_retransmissions",
        "total_loss_percent",
        "initial_ram_usage_mb",
        "avg_ram_usage_bash_mb",
        "ram_growth_mb",
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


    save_query_extras(run_id, user_question, permanent_chunks)

def save_query_extras(run_id: str, user_question: str, permanent_chunks: list):
    """
    Saves user_question and permanent_chunks into a safe JSONL file.
    Each entry is one JSON per line.
    Never breaks CSV, and can store long text safely.

    :param run_id: Unique ID for the measurement (string)
    :param user_question: User's question text (string)
    :param permanent_chunks: List of chunk strings
    """

    record = {
        "run_id": run_id,
        "user_question": user_question,
        "permanent_chunks": permanent_chunks,
    }

    # Write as JSONL (one JSON per line)
    with open(EXTRAS_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

    print(f"[SAVE] Extra query info stored to {EXTRAS_PATH}")