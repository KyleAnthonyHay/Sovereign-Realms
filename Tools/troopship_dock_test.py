#!/usr/bin/env python3
"""The troop ship's docking, its course and its patrol, in Play-In-Editor (the editor open, no play session):

    python Tools/troopship_dock_test.py realmv3|realmv2 [shots] [keep]

What is checked (PASS / FAIL lines; exit code 1 if anything failed):
  dock      sailed to open water within 30 m of a berth, the dock button shows (over the berth and in the panel); a
            click on it and the ship swings its side to the land and slides in, in 1 to 1.5 s, and is landed; troops
            board and unload there and stand on the ground. A right click on the other dock's quay sails there and
            docks the same way (Realm v3: both docks; Realm v2: the east port, the only quay units can walk to)
  minimap   with the ship selected a right click on the minimap sails it to that point of the map
  course    three points (the second and third queued, as Shift + right click queues them), the last on a quay: it
            sails them in order and docks at the end
  patrol    P and a click on the water, one more point added: it loops round its points (two laps watched), keeps to
            the water, and a dock order ends the patrol
  lap       the open sea round the island (owner, 2026-11-23: "more room to travel"): the map reaches MAP_EDGE m from
            the middle every way (the minimap's world box says so), and a course of eight points on a ring between the
            coast and that edge, back to where it began, is sailed all the way round, afloat throughout
shots: Saved/Screenshots/VL/troopship_dock_icon.png, troopship_docking_*.png (the move, every sixth of a second),
troopship_gangplank_walk.png, troopship_course.png, troopship_patrol.png, troopship_minimap.png, troopship_lap.png
(the overview all the way out, the minimap with it) (with <map>_ before the name on Realm v2).
"""
import glob
import os
import re
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "Tools"))
import pie

LOG = pie.LOG
ARGS = sys.argv[1:]
MAP = ARGS[0] if ARGS and ARGS[0] in ("realmv2", "realmv3") else "realmv3"
SHOTS = "shots" in ARGS
PRE = "" if MAP == "realmv3" else "realmv2_"
fails = []
SEA = -600.0
# (cm) near: open water about 25 m off the first dock; quay2: the other dock's quay; a, b: two points of open water
PLAN = dict(
    realmv3=dict(near=(-27000, -13300), far=(-27300, -6600), quay1=(-23800, -13400), quay2=(23600, 13300), a=(-27200, -10600), b=(-27200, -16100), spawn=(-23600, -13500)),
    realmv2=dict(near=(32900, -14300), far=(34000, -9000), quay1=(30300, -14500), quay2=None, a=(33600, -11000), b=(33900, -8500), spawn=(30100, -14600)),
)[MAP]
# (m) the map's extent (MAP_EDGE in Tools/ue/build_<map>.py) and the ring the lap is sailed on: between the coast (Realm
# v3 230 m from the middle at most, Realm v2 309 m) and that edge
EDGE, RING = dict(realmv3=(310.0, 270.0), realmv2=(390.0, 350.0))[MAP]


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


def ship():
    for l in cmd("vl.Ship state", r"ship #\d", 0.5):
        m = re.search(r"ship #(\d+) (\S+) team 0 at V\(X=([-\d.]+), Y=([-\d.]+), Z=([-\d.]+)\) yaw ([-\d.]+): (.*); aboard (\d+) of (\d+), coming (\d+), landed (\d) at V\(X=([-\d.]+), Y=([-\d.]+), Z=([-\d.]+)\).*can dock (\d) at V\(([^)]*)\), last dock ([\d.]+) s", l)
        if m:
            g = m.groups()
            return dict(x=float(g[2]), y=float(g[3]), z=float(g[4]), yaw=float(g[5]), state=g[6], aboard=int(g[7]), coming=int(g[9]), landed=g[10] == "1",
                        land=(float(g[11]), float(g[12]), float(g[13])), can=g[14] == "1", dock=tuple(float(v) for v in re.findall(r"=(-?[\d.]+)", g[15])) or (0.0, 0.0, 0.0), took=float(g[16]))
    return None


def units():
    out = {}
    for l in cmd("vl.Units", r": unit ", 0.6):
        m = re.match(r"unit (.+?)\s+at\s+(-?\d+)\s+(-?\d+)\s+(-?\d+)\s+(.*)$", l)
        if m:
            out[m.group(1).strip().replace(" ", "_")] = dict(x=float(m.group(2)), y=float(m.group(3)), z=float(m.group(4)), state=m.group(5))
    return out


def shot(name, settle=1.0, ui=True):
    if SHOTS:
        path = os.path.join(pie.SHOTS, PRE + name + ".png")
        if os.path.exists(path):
            os.remove(path)
        time.sleep(settle)
        pie.run(["vl.Shot " + PRE + name + (" ui" if ui else "")])
        end = time.time() + 15
        while not os.path.exists(path) and time.time() < end:
            time.sleep(0.1)
        print("      shot", path if os.path.exists(path) else "(not written)")


def wait_for(what, test, timeout, every=1.0):
    end = time.time() + timeout
    while time.time() < end:
        v = test()
        if v:
            return v
        time.sleep(every)
    print("      (timed out waiting for %s)" % what)
    return None


def still(s):
    return s and ("Moored" in s["state"] or "At sea" in s["state"])


def hud_button(ident):
    for l in cmd("vl.HUD", r"hud button %d " % ident, 0.6):
        m = re.search(r"hud button %d at ([\d.]+) ([\d.]+)" % ident, l)
        if m:
            return float(m.group(1)), float(m.group(2))
    return None


def look(s, zoom=0.36, yaw=-60):
    """A free camera on that point of the sea (the middle of the view is the point itself), from the south-west."""
    k = zoom / 0.36
    cmd(["vl.View free %.0f %.0f %.0f -42.4 -34.4 60" % (s["x"] - 3800 * k, s["y"] + 2600 * k, SEA + 4200 * k)], wait=0.8)


def main():
    print(pie.mcp("StartPIE", {"options": {"bSimulate": False, "playMode": "PlayMode_InEditorFloating", "warmupSeconds": 2.0}})[:60])
    time.sleep(8)
    if MAP == "realmv3":
        cmd(["vl.Map realmv3"], wait=40)
    cmd(["vl.StartMatch 0"], wait=7)
    cmd(["vl.Mode overview"], wait=0.5)
    s = wait_for("the ship", ship, 20)
    if not check("the player's troop ship is there", bool(s), str(s)):
        return
    cmd(["vl.Select Troop Ship"], wait=0.3)

    # ---- dock: to open water near the first dock, the button, the click, the move
    cmd(["vl.Ship sail %d %d" % PLAN["far"]], wait=0.5)
    s = wait_for("it to lie off the shore", lambda: (lambda x: x if still(x) else None)(ship()), 240)
    cmd(["vl.Ship sail %d %d" % PLAN["near"]], wait=0.5)
    s = wait_for("it to lie near the dock", lambda: (lambda x: x if still(x) else None)(ship()), 240)
    time.sleep(1.0)
    s = ship()
    d = ((s["x"] - s["dock"][0]) ** 2 + (s["y"] - s["dock"][1]) ** 2) ** 0.5 / 100
    check("off the dock, not landed, a berth in reach: the dock button shows", s["can"] and not s["landed"], "%s; the berth's gangplank foot %.0f m from the ship" % (s["state"], d))
    look(s, 0.34)
    b = hud_button(501)
    check("the dock button is drawn over the berth", bool(b), "at %s of the view" % (b,))
    shot("troopship_dock_icon")
    yaw0 = s["yaw"]
    since = os.path.getsize(LOG)
    if b:
        if SHOTS:
            for f in glob.glob(os.path.join(pie.SHOTS, PRE + "troopship_docking_*.png")):
                os.remove(f)
            cmd(["vl.Record %stroopship_docking 60 30" % PRE, "vl.UIClick %.3f %.3f" % b], wait=0.5)
        else:
            cmd(["vl.UIClick %.3f %.3f" % b], wait=0.5)
    lines = wait_for("the dock", lambda: log_tail(r"ship: \S+ docked in", since)[-1:], 60) or []
    m = re.search(r"docked in ([\d.]+) s .*yaw (-?[\d.]+): (.*)", lines[-1]) if lines else None
    took = float(m.group(1)) if m else 0
    check("a click on it docks the ship in one move of 1 to 1.5 s", bool(m) and 0.95 <= took <= 1.6, lines[-1] if lines else "no dock")
    time.sleep(1.0)
    s = ship()
    check("docked: landed, the gangplank out", s["landed"], "%s; it turned %.0f degrees; gangplank to %s" % (s["state"], abs((s["yaw"] - yaw0 + 180) % 360 - 180), s["land"]))
    check("the dock button is gone", not s["can"])
    if SHOTS:
        time.sleep(18)           # (the recording runs at a fixed step, slower than the clock)
        frames = sorted(glob.glob(os.path.join(pie.SHOTS, PRE + "troopship_docking_*.png")))
        for i, f in enumerate(frames):
            if i % 5 != 0 or i > 50:
                os.remove(f)
        print("      shots %s (every sixth of a second of the move: %d kept)" % (os.path.join(pie.SHOTS, PRE + "troopship_docking_*.png"), len(glob.glob(os.path.join(pie.SHOTS, PRE + "troopship_docking_*.png")))))
    shot("troopship_docked")

    # ---- board and unload at this dock: they walk the gangplank
    cmd(["vl.Spawn Swordsman %d %d 6" % PLAN["spawn"], "vl.Spawn Archer %d %d 4" % (PLAN["spawn"][0], PLAN["spawn"][1] - 300)], wait=2.0)
    cmd(["vl.Ship board near 40"], wait=0.5)
    look(s, 0.3)
    wait_for("the first aboard", lambda: (lambda x: x if x["aboard"] >= 2 else None)(ship()), 60, 0.3)
    shot("troopship_gangplank_walk", 0.0)
    s = wait_for("ten aboard", lambda: (lambda x: x if x["aboard"] >= 10 and x["coming"] == 0 else None)(ship()), 90) or ship()
    check("ten soldiers walk aboard", s["aboard"] == 10, "aboard %d, coming %d" % (s["aboard"], s["coming"]))
    time.sleep(4)
    on = [n for n, u in units().items() if u["state"].startswith("on the tower") and u["z"] < SEA + 600 and not n.startswith("Tower")]
    cmd(["vl.Ship unload"], wait=1.5)
    shot("troopship_gangplank_down", 0.0)
    s = wait_for("nobody aboard", lambda: (lambda x: x if x["aboard"] == 0 else None)(ship()), 60) or ship()
    time.sleep(6)
    after = units()
    ashore = [n for n in on if n in after and not after[n]["state"].startswith("on the tower") and after[n]["z"] > SEA + 10]       # (at the enemy's port they go for its archers: anywhere on the ground)
    check("they walk down it again and stand on the ground (nobody stuck aboard or in the sea)", s["aboard"] == 0 and len(on) == 10 and len(ashore) == len([n for n in on if n in after]) >= 7, "%d of %d ashore, feet %s" % (len(ashore), len(on), sorted(set(int(after[n]["z"]) for n in ashore))))

    # ---- the minimap: a right click on it sails the ship there
    cmd(["vl.Select Troop Ship"], wait=0.3)
    info = cmd("vl.HUD", r"hud: minimap at", 0.6)
    m = re.search(r"minimap at ([\d.]+) ([\d.]+) \.\. ([\d.]+) ([\d.]+), world (-?[\d.]+) (-?[\d.]+) \.\. (-?[\d.]+) (-?[\d.]+), up yaw (-?[\d.]+)", info[-1]) if info else None
    if check("the minimap is drawn", bool(m), info[-1][:120] if info else ""):
        u0, v0, u1, v1, wx0, wy0, wx1, wy1, up = [float(g) for g in m.groups()]
        # (the click's own world point is read back from the log: the map may be turned)
        import math
        tx, ty = PLAN["a"]
        dx, dy = tx - (wx0 + wx1) / 2, ty - (wy0 + wy1) / 2
        ux, uy = math.cos(math.radians(up)), math.sin(math.radians(up))
        cu = u0 + (u1 - u0) * (0.5 + (dx * -uy + dy * ux) / (wx1 - wx0))
        cv = v0 + (v1 - v0) * (0.5 - (dx * ux + dy * uy) / (wx1 - wx0))
        cu, cv = min(max(cu, u0 + 0.004), u1 - 0.004), min(max(cv, v0 + 0.006), v1 - 0.006)      # (a point off the map: its edge)
        lines = cmd(["vl.UIClick %.4f %.4f right" % (cu, cv)], r"minimap: the ship sent to|ship: \S+ sails to", 1.0)
        sent = re.search(r"minimap: the ship sent to (-?\d+) (-?\d+)", " ".join(lines))
        check("a right click on the minimap sails the ship to that point of the map", bool(sent) and any("sails to" in l for l in lines), " | ".join(lines)[:200])
        shot("troopship_minimap", 1.5)
        s = wait_for("it to arrive", lambda: (lambda x: x if still(x) else None)(ship()), 240)
        if sent and s:
            gx, gy = float(sent.group(1)), float(sent.group(2))
            check("it lies where the map was clicked (or the nearest water to it)", ((s["x"] - gx) ** 2 + (s["y"] - gy) ** 2) ** 0.5 < 6000, "clicked %.0f %.0f, lies at %.0f %.0f: %s" % (gx, gy, s["x"], s["y"], s["state"]))

    # ---- a course of three points, the last on the quay: sailed in order, docked at the end
    since = os.path.getsize(LOG)
    cmd(["vl.Ship sail %d %d" % PLAN["b"], "vl.Ship sail %d %d queue" % PLAN["a"], "vl.Ship sail %d %d queue" % PLAN["quay1"]], wait=1.0)
    s = ship()
    check("three points queued", "2 more points" in s["state"], s["state"])
    look(dict(x=(PLAN["a"][0] + PLAN["quay1"][0]) / 2, y=(PLAN["a"][1] + PLAN["b"][1]) / 2), 0.5)
    shot("troopship_course", 1.0)
    s = wait_for("the course's end", lambda: (lambda x: x if still(x) else None)(ship()), 300)
    legs = log_tail(r"ship: \S+: the next point of its course|ship: \S+ docked in", since)
    check("it sails them in order and docks at the last", len(legs) == 3 and "docks there" in legs[1] and "docked in" in legs[2] and s and s["landed"], " | ".join(l[:90] for l in legs))
    if s:
        check("that docking move too takes 1 to 1.5 s", 0.95 <= s["took"] <= 1.6, "%.2f s" % s["took"])

    # ---- patrol: P, a click on the water; one more point; two laps; a dock order ends it
    since = os.path.getsize(LOG)
    cmd(["vl.Select Troop Ship"], wait=0.3)
    look(dict(x=PLAN["a"][0], y=PLAN["a"][1]), 0.45)
    lines = cmd(["vl.Input key P"], None, 0.6)
    lines = cmd(["vl.Click 0.5 0.5"], r"ship: \S+ patrols between", 1.0)
    check("P, then a click on the water: it patrols between where it lies and there", bool(lines), lines[-1] if lines else "no patrol")
    cmd(["vl.Ship patrol %d %d add" % PLAN["b"]], wait=0.5)
    s = ship()
    check("one more point: a loop of three", "On patrol (3 points)" in s["state"], s["state"])
    track = []
    t0 = time.time()
    laps = []
    shot_done = False
    while time.time() - t0 < 420:
        s = ship()
        track.append(s)
        laps = log_tail(r"on patrol: on to point", since)
        if SHOTS and not shot_done and len(laps) >= 2:
            cmd(["vl.Select Troop Ship"], wait=0.2)
            look(dict(x=(PLAN["a"][0] + PLAN["b"][0]) / 2, y=(PLAN["a"][1] + PLAN["b"][1]) / 2), 0.6)
            shot("troopship_patrol", 0.8)
            shot_done = True
        if len(laps) >= 6:
            break
        time.sleep(2.0)
    check("it loops round its points (two laps: six points reached in %.0f s)" % (time.time() - t0), len(laps) >= 6, "%d reached" % len(laps))
    check("on patrol it keeps to the water and never lands", all(abs(x["z"] - SEA) < 1 and not x["landed"] for x in track), "%d looks" % len(track))
    cmd(["vl.Ship sail %d %d" % PLAN["near"]], wait=0.5)
    s = wait_for("it to lie near the dock", lambda: (lambda x: x if still(x) else None)(ship()), 240)
    lines = cmd(["vl.Ship dock"], r"ship: dock", 1.0)
    s = wait_for("the dock", lambda: (lambda x: x if x["landed"] else None)(ship()), 20) or ship()
    check("another order ends the patrol, and it docks", s["landed"] and "patrol" not in s["state"].lower(), "%s; %.2f s" % (s["state"], s["took"]))

    # ---- the lap: the map's extent, then a course of eight points round the island on the open sea
    info = cmd("vl.HUD", r"hud: minimap at", 0.6)
    m = re.search(r"world (-?[\d.]+) (-?[\d.]+) \.\. (-?[\d.]+) (-?[\d.]+)", info[-1]) if info else None
    if m:
        wx0, wy0, wx1, wy1 = [float(g) / 100.0 for g in m.groups()]
        check("the map (the minimap's world) reaches %.0f m from the middle every way" % EDGE, min(-wx0, -wy0, wx1, wy1) >= EDGE - 2.0, "world %.0f %.0f .. %.0f %.0f m" % (wx0, wy0, wx1, wy1))
    else:
        check("the minimap's world box is reported", False)
    import math
    ring = []
    for k in range(8):
        a = math.radians(180.0 - 45.0 * k)          # (from the west, round by the north: clockwise seen from above)
        c, sn = math.cos(a), math.sin(a)
        f = RING / max(abs(c), abs(sn))             # (a square ring: the corners as far out as the sides)
        ring.append((f * c * 100.0, -f * sn * 100.0))
    ring.append(ring[0])
    since = os.path.getsize(LOG)
    cmd(["vl.Select Troop Ship", "vl.Ship sail %d %d" % ring[0]], wait=0.5)
    s = wait_for("the lap's start", lambda: (lambda x: x if still(x) else None)(ship()), 400, 2.0)
    since = os.path.getsize(LOG)
    cmd(["vl.Ship sail %d %d" % ring[1]] + ["vl.Ship sail %d %d queue" % p for p in ring[2:]], wait=1.0)
    t0, track, turned, last = time.time(), [], 0.0, None
    while time.time() - t0 < 1200:
        s = ship()
        if s:
            track.append(s)
            ang = math.atan2(-s["y"], s["x"])
            if last is not None:
                d = ang - last
                turned += (d + math.pi) % (2 * math.pi) - math.pi
            last = ang
            if still(s) and time.time() - t0 > 10:
                break
        time.sleep(2.0)
    legs = log_tail(r"ship: \S+: the next point of its course", since)
    far = max(max(abs(x["x"]), abs(x["y"])) for x in track) / 100.0 if track else 0.0
    check("a lap round the island: eight points sailed in order, back where it began (%.0f s)" % (time.time() - t0),
          bool(s) and len(legs) >= 7 and ((s["x"] - ring[-1][0]) ** 2 + (s["y"] - ring[-1][1]) ** 2) ** 0.5 < 3000, "%d legs; lies at %.0f %.0f" % (len(legs), s["x"] if s else 0, s["y"] if s else 0))
    check("all the way round (%.0f degrees about the middle), out to %.0f m from it" % (abs(math.degrees(turned)), far), abs(math.degrees(turned)) > 330.0 and far > RING - 15.0)
    check("on the lap it keeps to the water and never lands", all(abs(x["z"] - SEA) < 1 and not x["landed"] for x in track), "%d looks" % len(track))
    if SHOTS:
        cmd(["vl.Mode overview", "vl.Look 0 0 1 -62"], wait=3.0)
        shot("troopship_lap", 2.0)

    # ---- the other dock: a right click on its quay sails there and docks
    if PLAN["quay2"]:
        since = os.path.getsize(LOG)
        cmd(["vl.Select Troop Ship", "vl.Ship sail %d %d" % PLAN["quay2"]], wait=1.0)
        s = wait_for("the other dock", lambda: (lambda x: x if still(x) else None)(ship()), 400, 2.0) or ship()
        lines = log_tail(r"ship: \S+ docked in", since)
        check("sent to the other dock's quay it sails there and docks (%s)" % (lines[-1][lines[-1].find("docked in"):lines[-1].find(" at V")] if lines else "no dock"),
              bool(lines) and s["landed"] and ((s["x"] - PLAN["quay2"][0]) ** 2 + (s["y"] - PLAN["quay2"][1]) ** 2) ** 0.5 < 4000, lines[-1][-110:] if lines else s["state"])
        look(s, 0.34, 120)
        shot("troopship_docked_other")


if __name__ == "__main__":
    try:
        main()
    finally:
        if "keep" not in ARGS:
            print(pie.mcp("StopPIE")[:60])
    print("%d failure(s)" % len(fails))
    sys.exit(1 if fails else 0)
