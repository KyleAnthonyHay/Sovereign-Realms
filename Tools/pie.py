#!/usr/bin/env python3
"""Drive a Play-In-Editor session from the shell (needs the editor open with its MCP server).

  pie.py start [wait] [--menu]       start PIE in a floating window and start a match (sr.StartMatch); with --menu
                                     stay on the main menu instead
  pie.py stop
  pie.py run "<cmd>" ["<cmd>" ...]   write console commands to Saved/SRCommands.txt (the game polls it), wait for pickup
  pie.py shot <name> [X Y [zoom]]    optionally move the camera, let the image settle, save Saved/Screenshots/SR/<name>.png
  pie.py log [pattern] [n]           last n (default 40) LogSovereign lines of the editor log matching pattern
  pie.py wait <seconds>
Commands are the sr.* console commands (Source/SovereignRealms/Battle/SRDebugCommands.cpp).
"""
import glob
import json
import os
import re
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INBOX = os.path.join(ROOT, "Saved", "SRCommands.txt")
SHOTS = os.path.join(ROOT, "Saved", "Screenshots", "SR")
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
        return
    with open(LOG, errors="replace") as f:
        lines = [l.rstrip() for l in f if "LogSovereign" in l and (not pattern or re.search(pattern, l))]
    for l in lines[-n:]:
        print(re.sub(r"^\[[^\]]*\]\[[ \d]*\]", "", l))


def main(a):
    if not a:
        print(__doc__)
        return 0
    if a[0] == "start":
        print(mcp("StartPIE", {"options": {"bSimulate": False, "playMode": "PlayMode_InEditorFloating", "warmupSeconds": 2.0}})[:300])
        rest = [x for x in a[1:] if x != "--menu"]
        time.sleep(float(rest[0]) if rest else 4.0)
        if "--menu" not in a:                    # the game opens on its main menu: tests want the battle
            run(["sr.StartMatch"])
            time.sleep(1.0)
    elif a[0] == "stop":
        print(mcp("StopPIE")[:200])
    elif a[0] == "run":
        return 0 if run(a[1:]) else 1
    elif a[0] == "wait":
        time.sleep(float(a[1]))
    elif a[0] == "shot":
        name = a[1]
        path = os.path.join(SHOTS, name + ".png")
        if os.path.exists(path):
            os.remove(path)
        if len(a) >= 4:
            run(["sr.Camera %s %s%s" % (a[2], a[3], (" " + a[4]) if len(a) > 4 else "")])
            time.sleep(3.0)                      # temporal AA, Lumen and depth of field settle after a camera jump
        run(["sr.Shot " + name])
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
