import os
import time
import json
import signal


def is_samsung_connected():
    try:
        result = os.popen("lsusb").read()
        return any("Qualcomm" in line for line in result.split('\n'))
    except Exception as e:
        print(f"Error checking USB connection: {e}")
        return False

def kill_process_from_pid_file(pid_file):
    if os.path.exists(pid_file):
        try:
            with open(pid_file, "r") as f:
                pid = int(f.read().strip())
            os.kill(pid, signal.SIGTERM)
            print(f"Process with PID {pid} has been terminated.")
            os.remove(pid_file)
        except Exception as e:
            print(f"Error terminating process: {e}")
    else:
        print("PID file not found.")

def main():
    json_file = "pancashiki.json"
    pid_file = "pancashiki.pid"

    while True:
        samsung_status = is_samsung_connected()

        with open(json_file, "w") as f:
            json.dump({"is_samsung_connected": samsung_status}, f)

        if samsung_status:
            print("Samsung device connected.")
        else:
            print("Samsung device not connected. Killing process from PID file.")
            kill_process_from_pid_file(pid_file)

        time.sleep(2)

if __name__ == "__main__":
    main()
