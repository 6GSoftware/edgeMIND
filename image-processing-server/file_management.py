import logging
import os
import signal
import sys
import time

IMAGE_DIR = "./Pictures"

DAYS_OLD = 1    # NOTE: Modify to your liking
SLEEP_INTERVAL = 86400


def remove_old_files():
    # Calculate time treshold again every time
    time_threshold = time.time() - (DAYS_OLD * 86400)  # 86400 seconds in a day
    logging.info(f"Cleaning up files older than {DAYS_OLD} days...")

    # Loop through all files in the folder
    for filename in os.listdir(IMAGE_DIR):
        file_path = os.path.join(IMAGE_DIR, filename)
        logging.info("File path: " + file_path)

        # Make sure it's a file (not a subdirectory)
        if os.path.isfile(file_path):
            # Get the last modified time
            file_mtime = os.path.getmtime(file_path)

            # Compare with threshold
            if file_mtime < time_threshold:
                try:
                    os.remove(file_path)
                    logging.info(f"Deleted: {file_path}")
                except Exception as e:
                    logging.error(f"Error deleting {file_path}: {e}")


def handle_exit(signum, frame):
    logging.info("Received shutdown signal. Exiting.")
    sys.exit(0)


if __name__ == "__main__":
    # Handle SIGTERM/SIGINT for Docker shutdown
    signal.signal(signal.SIGTERM, handle_exit)
    signal.signal(signal.SIGINT, handle_exit)

    while True:
        remove_old_files()
        logging.info(f"Sleeping for {SLEEP_INTERVAL} seconds...\n")
        time.sleep(SLEEP_INTERVAL)
