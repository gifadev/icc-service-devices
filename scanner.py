#!/usr/bin/env python3

import os
import sys
import subprocess
import time
import signal
import threading
import socket
import getpass
import uuid


allowed_devices = [
    {
        "hostname": "me",
        "username": ["me", "root"],
        "serial_number": "RR8R303RQEP"
    },
]

def print_header():
    print("=" * 50)
    print("           PANCASHIKI QUALCOMM RUNNER TOOL")
    print("=" * 50)

def write_to_log(log_message):
    with open("pancashiki.log", "a") as log_file:
        log_file.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} - {log_message}\n")

def run_adb_commands():
    if os.geteuid() != 0:
        print("Please run this script as root (use sudo).")
        sys.exit(1)
    try:
        subprocess.run(["adb", "kill-server"], check=True)
        subprocess.run(["adb", "start-server"], check=True)
        adb_input = "su\nsetprop sys.usb.config diag,adb\n"
        subprocess.run(["adb", "shell"], input=adb_input.encode('utf-8'), check=True)
        write_to_log("ADB commands executed successfully.")
    except subprocess.CalledProcessError as e:
        error_msg = f"ADB command failed: {e}"
        print(error_msg)
        write_to_log(error_msg)

def get_adb_device_serial():
    max_attempts = 5
    delay = 2  # detik
    attempt = 0
    while attempt < max_attempts:
        output = os.popen("adb devices").read()
        lines = output.strip().splitlines()
        if len(lines) > 1:
            for line in lines[1:]:
                parts = line.split()
                if len(parts) >= 2 and parts[1] == "device":
                    serial = parts[0]
                    write_to_log(f"ADB device detected with serial: {serial}")
                    return serial
        attempt += 1
        time.sleep(delay)
    write_to_log("No adb devices found after multiple attempts.")
    return None

def get_qualcomm_device_serial():
    try:
        result = subprocess.check_output(['lsusb']).decode('utf-8')
        qualcomm_devices = [line for line in result.splitlines() if "Qualcomm" in line]
        if qualcomm_devices:
            parts = qualcomm_devices[0].split()
            usb_serial = parts[1] + ":" + parts[3].strip(':')
            write_to_log(f"USB device detected with address: {usb_serial}")
            return usb_serial
        else:
            print("No Qualcomm device detected via lsusb.")
            write_to_log("No Qualcomm device detected via lsusb.")
            return None
    except subprocess.CalledProcessError as e:
        write_to_log(f"Failed to run lsusb command: {e}")
        return None

def check_pancashiki_installed():
    try:
        subprocess.check_call(
            ['pip3', 'show', 'pancashiki'],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        write_to_log("Pancashiki package is installed.")
        return True
    except subprocess.CalledProcessError:
        write_to_log("Pancashiki package is not installed.")
        return False

def save_pid(pid):
    with open("pancashiki.pid", "w") as pid_file:
        pid_file.write(str(pid))

def get_mac_address():
    mac_int = uuid.getnode()
    mac_hex = ':'.join(('%012X' % mac_int)[i:i+2] for i in range(0, 12, 2))
    return mac_hex.lower()

def get_hostname():
    return socket.gethostname()

def get_username():
    return getpass.getuser()

def get_device_info(adb_serial):
    return {
        "hostname": get_hostname(),
        "username": get_username(),
        "serial_number": adb_serial
    }

def verify_device_info(device_info, allowed_devices):
    for allowed in allowed_devices:
        if (device_info['hostname'] == allowed.get('hostname') and
            (device_info['username'] in allowed.get('username')) and
            device_info['serial_number'] == allowed.get('serial_number')):
            write_to_log("Device verification successful.")
            return True
    write_to_log("Device verification failed. Device not allowed.")
    return False

def run_pancashiki_command(usb_serial):
    if usb_serial is None:
        write_to_log("USB device serial not found. Command not executed.")
        return

    command = [
        'sudo',
        'python3',
        '-m',
        'pancashiki',
        '-t', 'qc',
        '-u',
        '-a', usb_serial,
        '-i', '0'
        #'--gsmtapv3', '--msgs', '--cacombos', '--disable-crc-check', '--trace', '--ilm', '--all-items', '--events'
    ]

    print("Running pancashiki command...")
    print("=" * 50)

    pid = None
    def loading_animation():
        animation = ["|", "/", "-", "\\"]
        idx = 0
        while True:
            print(f"\rRunning... {animation[idx % len(animation)]}", end="", flush=True)
            idx += 1
            time.sleep(0.2)

    try:
        with open("pancashiki.log", "a") as log_file:
            process = subprocess.Popen(command, stdout=log_file, stderr=log_file)
        pid = process.pid
        save_pid(pid)
        print(f"\nProcess PID: {pid}")
        write_to_log(f"Started pancashiki process with PID: {pid}")

        animation_thread = threading.Thread(target=loading_animation, daemon=True)
        animation_thread.start()

        process.wait()
        animation_thread.join(timeout=0)

        if process.returncode == 0:
            print("\nCommand executed successfully.")
            write_to_log("Command executed successfully.")
        else:
            print("\nCommand failed.")
            write_to_log("Command failed.")
    except Exception as e:
        error_msg = f"Failed to run pancashiki command: {e}"
        print(f"\n{error_msg}")
        write_to_log(error_msg)
    finally:
        if pid:
            if os.path.exists("pancashiki.pid"):
                os.remove("pancashiki.pid")
            print("PID file removed.")
            write_to_log("PID file removed.")

def main():
    print_header()
    run_adb_commands()

    adb_serial = get_adb_device_serial()
    if not adb_serial:
        print("Tidak dapat menemukan adb device, proses tidak dijalankan.\n")
        return

    device_info = get_device_info(adb_serial)
    if not verify_device_info(device_info, allowed_devices):
        print("Verifikasi perangkat gagal. Proses dihentikan.\n")
        return

    if not check_pancashiki_installed():
        print("Please install pancashiki\n")
        return

    usb_serial = get_qualcomm_device_serial()
    if not usb_serial:
        print("Tidak dapat memperoleh alamat USB device (lsusb), proses tidak dijalankan.\n")
        return

    run_pancashiki_command(usb_serial)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nProcess interrupted by user.")
        write_to_log("Process interrupted by user.")
        if os.path.exists("pancashiki.pid"):
            try:
                with open("pancashiki.pid", "r") as pid_file:
                    pid = int(pid_file.read())
                os.kill(pid, signal.SIGTERM)
                print(f"Process with PID {pid} terminated.")
                write_to_log(f"Process with PID {pid} terminated.")
            except Exception as e:
                print(f"Error terminating process: {e}")
                write_to_log(f"Error terminating process: {e}")
        else:
            print("No PID file found. Cannot terminate process.")
            write_to_log("No PID file found. Cannot terminate process.")
