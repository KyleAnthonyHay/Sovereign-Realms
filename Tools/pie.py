#!/usr/bin/env python3
"""Drive a Play-In-Editor session of the voxel sandbox from the shell (editor open, MCP server on port 8000).

  pie.py start [wait]                start PIE in a floating window
  pie.py stop
  pie.py run "<cmd>" ["<cmd>" ...]   console commands (vl.* and any engine command); the game polls Saved/VLCommands.txt
  pie.py shot <name> [settle]        save Saved/Screenshots/VL/<name>.png (after `settle` seconds, default 2.5)
  pie.py log [pattern] [n]           last n (default 40) LogSovereignRealms lines of the editor log
vl.View follow|postcard|free X Y Z Pitch Yaw [FOV] | vl.Teleport X Y Z [Yaw] | vl.Walk X Y [run] | vl.Orbit Yaw Pitch Dist | vl.Where
"""
import json
import os
import re
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INBOX = os.path.join(ROOT, "Saved", "VLCommands.txt")
SHOTS = os.path.join(ROOT, "Saved", "Screenshots", "VL")
LOG = os.path.expanduser("~/Library/Logs/Unreal Engine/SovereignRealmsEditor/SovereignRealms.log")
MCP = [sys.executable, os.path.join(ROOT, "Tools", "ue_mcp.py"), "call", "EditorToolset.EditorAppToolset"]


def mcp(tool, args=None):
    return subprocess.run(MCP + [tool, json.dumps(args or {})], capture_output=True, text=True).stdout.strip()


def run(cmds, timeout=20.0):
    tmp = INBOX + ".tmp"
    with open(tmp, "w") as f:
        f.write("\n".join(cmds) + "\n")
    os.replace(tmp, INBOX)
    end = time.time() + timeout
    while os.path.exists(INBOX) and time.time() < end:
        time.sleep(0.05)
    if os.path.exists(INBOX):
        print("commands were not picked up (is PIE running?)")
        return False
    return True


def log(pattern="", n=40):
    if not os.path.exists(LOG):
        print("no log at", LOG)
        return
    with open(LOG, errors="replace") as f:
        lines = [l.rstrip() for l in f if "LogSovereignRealms" in l and (not pattern or re.search(pattern, l))]
    for l in lines[-n:]:
        print(re.sub(r"^\[[^\]]*\]\[[ \d]*\]", "", l))


def main(a):
    if not a:
        print(__doc__)
        return 0
    if a[0] == "start":
        print(mcp("StartPIE", {"options": {"bSimulate": False, "playMode": "PlayMode_InEditorFloating", "warmupSeconds": 2.0}})[:300])
        time.sleep(float(a[1]) if len(a) > 1 else 4.0)
    elif a[0] == "stop":
        print(mcp("StopPIE")[:200])
    elif a[0] == "run":
        return 0 if run(a[1:]) else 1
    elif a[0] == "shot":
        name = a[1]
        path = os.path.join(SHOTS, name + ".png")
        if os.path.exists(path):
            os.remove(path)
        time.sleep(float(a[2]) if len(a) > 2 else 2.5)
        run(["vl.Shot " + name])
        end = time.time() + 15
        while not os.path.exists(path) and time.time() < end:
            time.sleep(0.1)
        time.sleep(0.3)
        print(path if os.path.exists(path) else "no screenshot written")
    elif a[0] == "log":
        log(a[1] if len(a) > 1 else "", int(a[2]) if len(a) > 2 else 40)
    else:
        print(__doc__)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
