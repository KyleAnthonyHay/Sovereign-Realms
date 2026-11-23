#!/usr/bin/env python3
"""The troop ship on L_RealmV2 in Play-In-Editor: board a platoon and the king at the west port, sail round the island,
land on the east port's quay, unload, and march the platoon inland (the editor open on L_RealmV2, no play session):

    python Tools/troopship_test.py [shots] [perf] [keep]

  shots   screenshots on the way: Saved/Screenshots/VL/troopship_*.png
  perf    vl.Perf before anyone is aboard, with everyone aboard at the quay, and under sail
  keep    leave the play session running at the end
What is checked (PASS / FAIL lines; exit code 1 if anything failed):
  - a ship lies at each port when the match starts, landed (its gangplank out), the player's with green cloth
  - a right click on the ship with troops selected sends them aboard (the click the player makes); 24 soldiers go
    aboard, the 25th and 26th stay ashore; the king boards and stands on the stern castle
  - aboard they stand on the deck (1.5 m above the sea, the castles higher), and ride with the ship as it sails
  - with the ship selected a right click on the water sails it there; it keeps to the water all the way
  - at sea nobody can be ordered off; an order to them is refused
  - at the quay it lands (the gangplank out); Unload puts everyone on the ground: each on a node of the path grid's
    main region, at the ground's height, idle or walking, none left attached to the ship
  - ordered inland they walk there (nobody stuck)
"""
import os
import re
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "Tools"))
import pie

LOG = pie.LOG
ARGS = sys.argv[1:]
SHOTS = "shots" in ARGS
PERF = "perf" in ARGS
fails = []
SEA = -600.0
QUAY = (-29850.0, 17600.0)              # the west port's quay (cm)
BEACH = (30300.0, -14500.0)             # the east port's quay
INLAND = (26800.0, -15000.0)


def log_tail(pattern, since):
    with open(LOG, errors="replace") as f:
        f.seek(since)
        return [re.sub(r"^\[[^\]]*\]\[[ \d]*\]LogSovereignRealms: ", "", l.rstrip()) for l in f if "LogSovereignRealms" in l and re.search(pattern, l)]


def cmd(cmds, pattern=None, wait=0.6):
    since = os.path.getsize(LOG)
    pie.run(cmds if isinstance(cmds, list) else [cmds])
    time.sleep(wait)
    return log_tail(pattern, since) if pattern else []


def check(text, ok, detail=""):
    print(("PASS  " if ok else "FAIL  ") + text + (("   [" + detail + "]") if detail else ""))
    if not ok:
        fails.append(text)
    return ok


def ships():
    out = []
    for l in cmd("vl.Ship state", r"ship #\d", 0.5):
        m = re.search(r"ship #(\d+) (\S+) team (\d) at V\(X=([-\d.]+), Y=([-\d.]+), Z=([-\d.]+)\) yaw ([-\d.]+): (.*); aboard (\d+) of (\d+), coming (\d+), landed (\d) at V\(X=([-\d.]+), Y=([-\d.]+), Z=([-\d.]+)\)", l)
        if m:
            g = m.groups()
            out.append(dict(i=int(g[0]), name=g[1], team=int(g[2]), x=float(g[3]), y=float(g[4]), z=float(g[5]), yaw=float(g[6]), state=g[7], aboard=int(g[8]), cap=int(g[9]),
                            coming=int(g[10]), landed=g[11] == "1", land=(float(g[12]), float(g[13]), float(g[14]))))
    return out


def mine():
    return [s for s in ships() if s["team"] == 0][0]


def units():
    out = {}
    for l in cmd("vl.Units", r": unit ", 0.6):
        m = re.match(r"unit (.+?)\s+at\s+(-?\d+)\s+(-?\d+)\s+(-?\d+)\s+(.*)$", l)
        if m:
            out[m.group(1).strip().replace(" ", "_")] = dict(x=float(m.group(2)), y=float(m.group(3)), z=float(m.group(4)), state=m.group(5))
    return out


def shot(name, settle=1.5, ui=False):
    if SHOTS:
        path = os.path.join(pie.SHOTS, name + ".png")
        if os.path.exists(path):
            os.remove(path)
        time.sleep(settle)
        pie.run(["vl.Shot " + name + (" ui" if ui else "")])
        end = time.time() + 15
        while not os.path.exists(path) and time.time() < end:
            time.sleep(0.1)
        print("      shot", path if os.path.exists(path) else "(not written)")


def perf(label):
    if PERF:
        time.sleep(8)
        l = cmd("vl.Perf", r"perf:", 0.8)
        print("PERF  %-34s %s" % (label, l[-1].replace("perf: ", "") if l else "?"))


def wait_for(what, test, timeout, every=1.5):
    end = time.time() + timeout
    while time.time() < end:
        v = test()
        if v:
            return v
        time.sleep(every)
    print("      (timed out waiting for %s)" % what)
    return None


def main():
    print(pie.mcp("StartPIE", {"options": {"bSimulate": False, "playMode": "PlayMode_InEditorFloating", "warmupSeconds": 2.0}})[:120])
    time.sleep(8)
    cmd(["vl.StartMatch 0"], wait=6)
    cmd(["vl.Mode overview"], wait=0.5)
    ss = wait_for("the ships", ships, 20)
    if not check("a troop ship at each port", bool(ss) and len(ss) == 2 and sorted(s["team"] for s in ss) == [0, 1], str([(s["name"], s["team"], round(s["x"]), round(s["y"])) for s in ss or []])):
        return
    s0 = mine()
    check("the player's is landed (its gangplank out)", s0["landed"], "at %.0f %.0f yaw %.0f, gangplank to %s" % (s0["x"], s0["y"], s0["yaw"], s0["land"]))
    # (the shore by its gangplank: a few metres inland of its foot)
    global QUAY
    dx, dy = s0["land"][0] - s0["x"], s0["land"][1] - s0["y"]
    n = (dx * dx + dy * dy) ** 0.5
    QUAY = (s0["land"][0] + dx / n * 900, s0["land"][1] + dy / n * 900)
    check("it floats on the sea", abs(s0["z"] - SEA) < 1.0, "z %.0f" % s0["z"])
    cmd(["vl.Look %.0f %.0f 0.34 -60" % (s0["x"], s0["y"])], wait=1.0)
    perf("west port, nobody aboard")
    shot("troopship_moored")

    # 26 soldiers on the quay (24 fit), the king with them
    cmd(["vl.Spawn Swordsman %.0f %.0f 16" % QUAY, "vl.Spawn Archer %.0f %.0f 10" % (QUAY[0] + dx / n * 500, QUAY[1] + dy / n * 500), "vl.Teleport %.0f %.0f %.0f" % (QUAY[0] + 400, QUAY[1], s0["land"][2] + 300)], wait=2.0)
    before = units()
    quay = [n for n, u in before.items() if abs(u["x"] - QUAY[0]) < 3000 and abs(u["y"] - QUAY[1]) < 4000]
    check("26 soldiers and the king stand on the quay", len(quay) >= 27, "%d there" % len(quay))
    shot("troopship_quay")
    # the click the player makes: the soldiers of the quay selected (a box over the view would take others too: by
    # name), then a right click on the ship
    cmd(["vl.SelectUnits none"] + ["vl.SelectUnits %s add" % n for n in quay if not n.lower().startswith("king")], wait=0.8)
    scr = cmd(["vl.Screen %.0f %.0f %.0f" % (s0["x"], s0["y"], SEA + 250)], r"screen|view", 0.6)
    m = re.search(r"([01]\.\d+)[ ,]+([01]\.\d+)", scr[-1]) if scr else None
    u, v = (float(m.group(1)), float(m.group(2))) if m else (0.5, 0.5)
    lines = cmd(["vl.RightClick %.3f %.3f" % (u, v)], r"ship:", 1.0)
    check("a right click on the ship orders them aboard", any("ordered aboard" in l for l in lines), lines[-1] if lines else "no ship line (click at %.2f %.2f)" % (u, v))
    s = wait_for("24 aboard", lambda: (lambda x: x if x["aboard"] >= 24 and x["coming"] == 0 else None)(mine()), 120)
    s = s or mine()
    check("24 soldiers aboard, 2 left ashore", s["aboard"] == 24, "aboard %d, coming %d" % (s["aboard"], s["coming"]))
    shot("troopship_boarding", 0.5)
    cmd(["vl.Ship board heroes"], wait=0.5)
    s = wait_for("the king aboard", lambda: (lambda x: x if x["aboard"] >= 25 else None)(mine()), 40) or mine()
    check("the king goes aboard too (he takes no soldier's place)", s["aboard"] == 25, "aboard %d" % s["aboard"])
    time.sleep(3)
    aboard = units()
    on = [n for n, u in aboard.items() if u["state"].startswith("on the tower") and u["z"] < SEA + 600 and not n.startswith("Tower")]
    zs = sorted(set(round(aboard[n]["z"] - SEA, -1) for n in on))
    check("everyone aboard stands on a deck (1.5 m, 3.1 m or 3.75 m above the sea)", len(on) == 25 and all(130 <= z <= 400 for z in zs), "heights above the sea %s" % zs)
    shot("troopship_aboard", 1.0)
    shot("troopship_aboard_ui", 0.5, ui=True)
    perf("west port, 24 soldiers and the king aboard")

    # sail: the ship selected, a right click on the water south-west of the port, then on to the beach
    cmd(["vl.Select Troop Ship", "vl.Look %.0f %.0f 0.3 -60" % (s0["x"] - dx / n * 4000, s0["y"] - dy / n * 4000)], wait=1.0)
    lines = cmd(["vl.RightClick 0.5 0.5"], r"ship:", 1.0)
    check("with the ship selected a right click on the water sails it there", any("sails to" in l for l in lines), lines[-1] if lines else "no ship line")
    shot("troopship_selected_ui", 1.0, ui=True)
    time.sleep(4)
    lines = cmd(["vl.SelectUnits %s" % on[0], "vl.Order selection %.0f %.0f" % QUAY, "vl.Select Troop Ship"], r"ship:", 1.0)
    u1 = units()
    check("at sea nobody can be ordered off the ship", u1[on[0]]["state"].startswith("on the tower"), u1[on[0]]["state"])
    lines = cmd(["vl.Ship sail %.0f %.0f" % BEACH], r"ship:", 0.8)
    check("it takes a course to the east port's quay", any("sails to" in l for l in lines), lines[-1] if lines else "")
    t0 = time.time()
    track = []
    wet = True
    shots = {12: "troopship_sailing", 45: "troopship_sailing_south"}
    perfed = False
    while time.time() - t0 < 420:
        s = mine()
        track.append((s["x"], s["y"], time.time()))
        wet = wet and abs(s["z"] - SEA) < 1.0
        if SHOTS:
            for t in list(shots):
                if time.time() - t0 > t:
                    cmd(["vl.Look %.0f %.0f 0.36 -40" % (s["x"], s["y"])], wait=0.4)
                    shot(shots.pop(t), 0.6)
        if PERF and not perfed and time.time() - t0 > 20:
            cmd(["vl.Look %.0f %.0f 0.36 -40" % (s["x"], s["y"])], wait=0.2)
            perf("under sail, 25 aboard")
            perfed = True
        if "Moored" in s["state"] or "At sea" in s["state"]:
            break
        time.sleep(2.0)
    s = mine()
    far = max(((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5 / max(b[2] - a[2], 0.5) for a, b in zip(track, track[1:])) if len(track) > 1 else 0
    check("it sails round the island to the east port (%.0f s, %d m from where it lay)" % (time.time() - t0, ((s["x"] - s0["x"]) ** 2 + (s["y"] - s0["y"]) ** 2) ** 0.5 / 100),
          abs(s["x"] - BEACH[0]) < 2500 and abs(s["y"] - BEACH[1]) < 2500 and wet, "at %.0f %.0f, %s" % (s["x"], s["y"], s["state"]))
    check("it never jumps (its greatest speed between two looks: %.1f m/s)" % (far / 100), far < 1300)
    check("it lands at the quay: the gangplank is out", s["landed"], "gangplank to %s" % (s["land"],))
    check("everyone is still aboard", s["aboard"] == 25, "aboard %d" % s["aboard"])
    cmd(["vl.Look %.0f %.0f 0.34 120" % (s["x"], s["y"])], wait=1.0)
    shot("troopship_landed")

    # unload
    lines = cmd(["vl.Ship unload"], r"ship:", 1.0)
    check("Unload sends them down the gangplank", any("unloads 25" in l for l in lines), lines[-1] if lines else "")
    shot("troopship_unloading", 3.0)
    s = wait_for("nobody aboard", lambda: (lambda x: x if x["aboard"] == 0 else None)(mine()), 60) or mine()
    check("nobody is left aboard", s["aboard"] == 0, "aboard %d" % s["aboard"])
    time.sleep(8)
    after = units()
    left = [n for n in on if n in after and after[n]["state"].startswith("on the tower")]
    check("none of them is still garrisoned", not left, str(left))
    ashore = [n for n in on if n in after and abs(after[n]["x"] - s["land"][0]) < 3000 and abs(after[n]["y"] - s["land"][1]) < 3000]
    check("all 25 stand on the shore by the gangplank", len(ashore) == 25, "%d of %d (%d alive)" % (len(ashore), len(on), len([n for n in on if n in after])))
    zs = [after[n]["z"] for n in ashore]
    check("on the ground there, not in the sea and not in the air", bool(zs) and min(zs) > SEA + 10 and max(zs) < SEA + 700, "feet %.0f .. %.0f cm (the sea %.0f)" % (min(zs or [0]), max(zs or [0]), SEA))
    shot("troopship_unloaded", 1.0)
    # inland: nobody stuck
    cmd(["vl.SelectUnits none"] + ["vl.SelectUnits %s add" % n for n in ashore], wait=0.8)
    cmd(["vl.Order selection %.0f %.0f" % INLAND], wait=1.0)
    done = wait_for("the march inland", lambda: (lambda u2: u2 if all(((u2[n]["x"] - INLAND[0]) ** 2 + (u2[n]["y"] - INLAND[1]) ** 2) ** 0.5 < 1500 for n in ashore if n in u2) else None)(units()), 90, 3.0)
    u2 = done or units()
    gone = [n for n in ashore if n in u2 and ((u2[n]["x"] - INLAND[0]) ** 2 + (u2[n]["y"] - INLAND[1]) ** 2) ** 0.5 >= 1500]
    check("ordered inland they all walk there (nobody stuck)", not gone, "short of it: %s" % gone[:6])
    cmd(["vl.Look %.0f %.0f 0.34 120" % INLAND], wait=1.0)
    shot("troopship_inland")
    perf("east port, everyone ashore")


if __name__ == "__main__":
    try:
        main()
    finally:
        if "keep" not in ARGS:
            print(pie.mcp("StopPIE")[:80])
    print("%d failure(s)" % len(fails))
    sys.exit(1 if fails else 0)
