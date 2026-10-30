#!/usr/bin/env python3
"""Check native executable loading and usage contracts without model weights."""
from pathlib import Path
import subprocess
import sys

NAMES = ("yue-server", "yue-synth", "yue-plan", "yue-transcribe",
         "yue-tokenize", "neural-codec", "mp3-codec", "quantize")

def main():
    directory = Path(sys.argv[1])
    for name in NAMES:
        path = directory / (name + (".exe" if sys.platform == "win32" else ""))
        result = subprocess.run([str(path), "--help"], capture_output=True, text=True)
        output = result.stdout + result.stderr
        # Upstream uses exit 1 for usage; missing loaders/crashes must not pass.
        if result.returncode != 1 or "Usage:" not in output or "yue2.cpp" not in output:
            raise RuntimeError(f"{name} failed startup: exit {result.returncode}\n{output}")
        print(f"PASS {name}: native startup and usage")
    return 0

if __name__ == "__main__":
    sys.exit(main())
