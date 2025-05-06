#!/usr/bin/env python3
import asyncio
import signal
import sys
import os
import subprocess
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime

# --- Konfigurasi (dapat diatur melalui environment variables) ---
BASE_CHECK_INTERVAL = float(os.getenv("BASE_CHECK_INTERVAL", "1"))
STABLE_CHECKS = int(os.getenv("STABLE_CHECKS", "5"))
LOOP_DELAY = float(os.getenv("LOOP_DELAY", "3"))
DETACH_COOLDOWN = float(os.getenv("DETACH_COOLDOWN", "60"))
PID_FILE = os.getenv("PID_FILE", "/tmp/detach_watchdog.pid")
LOG_FILE = os.getenv("LOG_FILE", "/tmp/detach_watchdog.log")

# --- Setup Logging dengan RotatingFileHandler ---
logger = logging.getLogger("detach_watchdog")
logger.setLevel(logging.INFO)
formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

file_handler = RotatingFileHandler(LOG_FILE, maxBytes=1 * 1024 * 1024, backupCount=3)
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

# --- Variabel Global ---
last_locked_plmn = None
last_detach_time = 0
running = True

def check_adb():
    """Pastikan adb tersedia di PATH."""
    try:
        subprocess.check_output(["adb", "version"], timeout=5)
    except Exception as e:
        logger.error(f"adb not found or error: {e}")
        sys.exit(1)

def write_pid():
    try:
        pid = os.getpid()
        with open(PID_FILE, "w") as f:
            f.write(str(pid))
        logger.info(f"detach_watchdog started. PID: {pid}")
    except Exception as e:
        logger.error(f"Failed to write PID file: {e}")

def remove_pid():
    try:
        if os.path.exists(PID_FILE):
            os.remove(PID_FILE)
    except Exception as e:
        logger.error(f"Failed to remove PID file: {e}")

def get_plmn() -> str:
    try:
        output = subprocess.check_output(["adb", "shell", "getprop", "gsm.operator.numeric"], timeout=5)
        return output.decode().strip().replace(",", "")
    except subprocess.TimeoutExpired:
        logger.error("Timeout when trying to get PLMN.")
        return ""
    except subprocess.CalledProcessError as e:
        logger.error(f"Error getting PLMN: {e}")
        return ""
    except FileNotFoundError:
        logger.error("adb not found. Ensure adb is installed and in PATH.")
        sys.exit(1)

async def detach_network(plmn: str):
    logger.info("Detaching from persistent network...")
    try:
        subprocess.call(["adb", "shell", "service", "call", "phone", "101", "i32", "1"])
        subprocess.call(["adb", "shell", "settings", "put", "global", "airplane_mode_on", "1"])
        subprocess.call(["adb", "shell", "cmd", "connectivity", "airplane-mode", "enable"])
        await asyncio.sleep(5)
        subprocess.call(["adb", "shell", "settings", "put", "global", "airplane_mode_on", "0"])
        subprocess.call(["adb", "shell", "cmd", "connectivity", "airplane-mode", "disable"])
        logger.info("✓ Detach complete.")
    except Exception as e:
        logger.error(f"Error during detach: {e}")

def handle_exit(signum, frame):
    logger.info("Exiting detach_watchdog gracefully...")
    global running
    running = False
    remove_pid()
    sys.exit(0)

async def poll_plmn(num_checks: int, interval: float) -> str:
    readings = []
    for _ in range(num_checks):
        reading = get_plmn()
        readings.append(reading)
        await asyncio.sleep(interval)
    if readings[0] and all(r == readings[0] for r in readings):
        logger.info("[*] Network readings are stable.")
        return readings[0]
    else:
        logger.info("[*] Network readings are unstable.")
        return ""

async def main_loop():
    global last_locked_plmn, last_detach_time, running
    logger.info("Starting asynchronous network monitoring...")
    while running:
        persistent_plmn = await poll_plmn(STABLE_CHECKS, BASE_CHECK_INTERVAL)
        if persistent_plmn:
            now = asyncio.get_event_loop().time()
            if persistent_plmn != last_locked_plmn or (now - last_detach_time) > DETACH_COOLDOWN:
                logger.info("Persistent network detected.")
                await detach_network(persistent_plmn)
                last_locked_plmn = persistent_plmn
                last_detach_time = now
            else:
                logger.info("Persistent network already detached recently. Skipping detach.")
        else:
            logger.info("No persistent network detected, skipping...")
        await asyncio.sleep(LOOP_DELAY)

async def main():
    signal.signal(signal.SIGINT, handle_exit)
    signal.signal(signal.SIGTERM, handle_exit)
    write_pid()
    await main_loop()

if __name__ == "__main__":
    check_adb()
    try:
        asyncio.run(main())
    except Exception as e:
        logger.error(f"Unhandled exception: {e}")
        remove_pid()