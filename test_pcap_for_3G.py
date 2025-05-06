#!/usr/bin/env python3
import subprocess
import argparse
import sys

def capture(interface: str, duration: int, output_file: str):
    cmd = [
        "tshark",
        "-i", interface,
        "-a", f"duration:{duration}",
        "-w", output_file
    ]
    print(f"[+] Capturing on {interface} for {duration}s → {output_file}")
    try:
        subprocess.run(cmd, check=True)
        print(f"[✓] Done. File saved as {output_file}")
    except subprocess.CalledProcessError as e:
        print(f"[✗] Error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Simple tshark capture")
    parser.add_argument("-i", "--interface", default="lo",
                        help="Network interface (default: lo)")
    parser.add_argument("-t", "--time", type=int, default=60,
                        help="Duration capture dalam detik (default: 300)")
    parser.add_argument("-o", "--output", default="test_3g.pcap",
                        help="Nama file output PCAP (default: test_3g.pcap)")
    args = parser.parse_args()

    capture(args.interface, args.time, args.output)
