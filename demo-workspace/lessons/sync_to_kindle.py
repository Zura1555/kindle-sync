#!/usr/bin/env python3
"""
Build PDF from all lessons, then send to Kindle.
Drop this into your /teach workspace's lessons/ directory.

Invoke: python3 lessons/sync_to_kindle.py
Or via AI agent: /kindle-sync
"""
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent

print("🔨 Building PDF...")
result = subprocess.run(
    [sys.executable, str(SCRIPTS / "build_kindle.py")],
    capture_output=True, text=True
)
print(result.stdout)
if result.returncode != 0:
    print(result.stderr)
    sys.exit(1)

print("📧 Sending to Kindle...")
result = subprocess.run(
    [sys.executable, str(SCRIPTS / "kindle-output" / "send_to_kindle.py")],
    capture_output=True, text=True
)
print(result.stdout)
if result.returncode != 0:
    print(result.stderr)
    sys.exit(1)

print("\n✅ Done! Your Kindle will have the latest lessons shortly.")
