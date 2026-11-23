#!/usr/bin/env python3
"""Run Python inside the open Unreal editor (needs Tools/ue_py_bridge.py running there).

Usage:
  ue_py.py <script.py> [timeout_s]     # run a file
  ue_py.py -c "<code>" [timeout_s]     # run a snippet
Prints the script's stdout (or traceback); exit code 1 on error, 2 on timeout.
"""
import os, sys, time, uuid

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INBOX = os.path.join(ROOT, "Saved", "PyInbox")


def main(argv):
    if not argv:
        print(__doc__); return 0
    if argv[0] == "-c":
        src, rest = argv[1], argv[2:]
    else:
        with open(argv[0], encoding="utf-8") as f:
            src = f.read()
        rest = argv[1:]
    timeout = float(rest[0]) if rest else 600.0
    os.makedirs(INBOX, exist_ok=True)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")      # (a Windows console that is not UTF-8)
    base = os.path.join(INBOX, time.strftime("%H%M%S_") + uuid.uuid4().hex[:6])
    with open(base + ".tmp", "w", encoding="utf-8") as f:
        f.write(src)
    os.replace(base + ".tmp", base + ".py")
    end = time.time() + timeout
    while time.time() < end:
        if os.path.exists(base + ".out"):
            with open(base + ".out", encoding="utf-8", errors="replace") as f:
                status, _, body = f.read().partition("\n")
            os.remove(base + ".out")
            sys.stdout.write(body)
            return 0 if status == "OK" else 1
        time.sleep(0.1)
    print("timeout waiting for the editor (is ue_py_bridge.py running?)")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
