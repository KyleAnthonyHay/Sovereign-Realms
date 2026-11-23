#!/usr/bin/env python3
"""Tests of L_Realm in Play-In-Editor (the editor open on L_Realm, PIE running: python3 Tools/pie.py start):

    Tools/.venv/bin/python Tools/realm_test.py [routes] [barriers] [dock] [trees] [march]

  routes    the path grid's routes between the plan's key points (vl.Path), next to the plan's own measure
  barriers  the king is put beside every kind of water's edge and runs straight at it with the keys held (vl.Move: no
            route, just the push): he must stop on dry ground outside the plan's hazard map; and straight over the
            two bridges and along the dock, which he must cross
  trees     the instanced forest (AVLForest): the plan's count, none against a building, and vl.ClearTrees on the
            thickest wood of the player's bank: trunks and crowns gone, the path grid walkable there, a route through
  march     three swordsmen and two archers go from the player's plaza to the enemy's (and three back), at a run;
            an archer goes up the player's watch tower
Reads SourceArt/realm.json and realm_terrain.npz. Prints PASS / FAIL lines; exit code 1 if anything failed.
"""
import json
import math
import os
import re
import sys
import time

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "Tools"))
import pie

LOG = pie.LOG
J = json.load(open(os.path.join(ROOT, "SourceArt", "realm.json")))
Z = np.load(os.path.join(ROOT, "SourceArt", "realm_terrain.npz"))
H, HZ = Z["h"], Z["hazard"]
HALF, CELL = J["terrain"]["half"], J["terrain"]["cell"]
G = J["gates"]
fails = []


def cell(x, y):
    n = H.shape[0]
    return min(n - 1, max(0, int((x + HALF) / CELL))), min(n - 1, max(0, int((y + HALF) / CELL)))


def ground(x, y):
    return float(H[cell(x, y)])


def log_tail(pattern, since):
    with open(LOG, errors="replace") as f:
        f.seek(since)
        return [l.rstrip() for l in f if "LogSovereignRealms" in l and re.search(pattern, l)]


def run(cmds, pattern=None, wait=0.6):
    since = os.path.getsize(LOG)
    pie.run(cmds)
    time.sleep(wait)
    return log_tail(pattern, since) if pattern else []


def check(ok, text):
    print(("PASS  " if ok else "FAIL  ") + text)
    if not ok:
        fails.append(text)


def routes():
    b = J["balance"] or {}
    we, ee = J["places"]["bridge_west_end"], J["places"]["bridge_east_end"]
    bw, be = (we[0] - 1.0, we[1]), (ee[0] + 1.0, ee[1])
    rows = [("player castle -> bridge", G["castle0"], bw, b.get("player", {}).get("bridge")),
            ("enemy castle -> bridge", G["castle1"], be, b.get("enemy", {}).get("bridge")),
            ("over the crossing", bw, be, None),
            ("bridge -> the island's middle", bw, (0.0, we[1] + 4.0), None),
            ("player castle -> own mine", G["castle0"], G["mine0"], b.get("player", {}).get("own_mine")),
            ("enemy castle -> own mine", G["castle1"], G["mine1"], b.get("enemy", {}).get("own_mine")),
            ("player castle -> tower (by its mine)", G["castle0"], G["tower0"], b.get("player", {}).get("tower")),
            ("enemy castle -> tower", G["castle1"], G["tower1"], b.get("enemy", {}).get("tower")),
            ("player castle -> neutral mine (west bank)", G["castle0"], G["mine_w"], b.get("player", {}).get("neutral_mine_own_bank")),
            ("enemy castle -> neutral mine (east bank)", G["castle1"], G["mine_e"], b.get("enemy", {}).get("neutral_mine_own_bank")),
            ("player castle -> neutral mine (east bank)", G["castle0"], G["mine_e"], b.get("player", {}).get("neutral_mine_far_bank")),
            ("enemy castle -> neutral mine (west bank)", G["castle1"], G["mine_w"], b.get("enemy", {}).get("neutral_mine_far_bank")),
            ("player castle -> the terrace (the old archery ground)", G["castle0"], (-148.0, -52.0), None),
            ("enemy castle -> the old archery ground in the north", G["castle1"], (124.0, 160.0), None),
            ("player castle -> its islet (over the sea bridge)", G["castle0"], (-72.0, -185.0), None),
            ("enemy castle -> its islet (over the sea bridge)", G["castle1"], (161.0, -154.0), None),
            ("bridge -> the island's north lobe", bw, (0.0, 50.0), None),
            ("bridge -> the island's south lobe", bw, (0.0, -26.0), None),
            ("castle -> castle", G["castle0"], G["castle1"], b.get("player", {}).get("enemy_castle")),
            ("castle -> castle, back", G["castle1"], G["castle0"], b.get("enemy", {}).get("enemy_castle")),
            ("player castle -> dock head", G["castle0"], (J["places"]["dock"][0] - 11.0, J["places"]["dock"][1]), None)]
    out = {}
    print("%-48s %9s %9s" % ("route (path grid, in the game)", "grid m", "plan m"))
    for name, a, c, plan in rows:
        lines = run(["vl.Path %.0f %.0f %.0f %.0f" % (a[0] * 100, -a[1] * 100, c[0] * 100, -c[1] * 100)], r"path:", 0.8)
        m = re.search(r"path: (\w+), (\d+) corners, ([\d.]+) m", lines[-1]) if lines else None
        ok = bool(m) and m.group(1) == "found"
        length = float(m.group(3)) if m else None
        out[name] = length
        print("%-48s %9s %9s" % (name, length, plan))
        check(ok, "route found: " + name)
    return out


def where():
    lines = run(["vl.Where"], r"King at", 0.5)
    for l in reversed(lines):
        m = re.search(r"X=(-?[\d.]+) Y=(-?[\d.]+) Z=(-?[\d.]+)", l)
        if m:
            return float(m.group(1)) / 100.0, -float(m.group(2)) / 100.0, float(m.group(3)) / 100.0
    return None


def probe(name, a, b, seconds=5.0, cross=False, floor=None):
    floor = ground(*a) if floor is None else floor
    z = floor + 1.3
    yaw = math.degrees(math.atan2(-(b[1] - a[1]), b[0] - a[0]))            # Unreal's yaw of the way to walk
    if not cross:                                                          # no tree between him and the edge (this play only)
        half = math.hypot(b[0] - a[0], b[1] - a[1]) / 2.0 + 2.0
        run(["vl.ClearTrees %.0f %.0f %.0f" % ((a[0] + b[0]) * 50, -(a[1] + b[1]) * 50, half * 100)], None, 0.3)
    run(["vl.Move 0 0 0.1", "vl.Teleport %.0f %.0f %.0f %.0f" % (a[0] * 100, -a[1] * 100, z * 100, yaw), "vl.Orbit %.0f -35 900" % yaw], None, 1.2)
    p = where()
    if p is None or math.hypot(p[0] - a[0], p[1] - a[1]) > 1.0:
        check(False, name + ": he did not land where he was put (%s)" % (p,))
        return
    # the keys held towards the water (straight ahead in the view), at a run: no route, no grid, just the push
    run(["vl.Move 1 0 %.1f run" % (seconds if cross else max(seconds - 1.0, 3.0))], None, seconds + 0.5)
    p = where()
    if p is None:
        check(False, name + ": no position logged")
        return
    x, y, zz = p
    haz = bool(HZ[cell(x, y)])
    left = math.hypot(x - b[0], y - b[1])
    if cross:
        check(left < 2.5 or math.hypot(x - a[0], y - a[1]) > math.hypot(b[0] - a[0], b[1] - a[1]) - 1.0, "%s: crossed, ended %.1f m from the far end at (%.1f, %.1f, %.1f)" % (name, left, x, y, zz))
    else:
        # the capsule's middle is about 0.9 m over his feet: he must stand on the ground he started from, outside the hazard map
        dry = zz - 0.9 > floor - 0.8
        check(not haz and dry, "%s: stopped at (%.1f, %.1f, %.1f), %.1f m short of the water point%s%s" % (
            name, x, y, zz, left, "" if not haz else "  INSIDE THE HAZARD MAP", "" if dry else "  FELL"))


def barriers(only_dock=False):
    d = J["places"]["dock"]
    by = J["places"]["bridge_west_end"][1]
    f2 = J["places"]["fall2"]
    run(["vl.Mode hero"], None, 1.0)                                       # (the keys move him only in the hero view)
    if only_dock:
        for (n, p, q) in (("the dock: off the walkway's side", (d[0] - 5.0, d[1]), (d[0] - 5.0, d[1] + 8.0)), ("the dock: off the head's end", (d[0] - 10.5, d[1]), (d[0] - 18.0, d[1])),
                          ("the dock: off the head's corner", (d[0] - 10.5, d[1] + 2.0), (d[0] - 16.0, d[1] + 8.0)), ("the dock: off the walkway's other side", (d[0] - 4.0, d[1]), (d[0] - 4.0, d[1] - 8.0))):
            probe(n, p, q, 4.0, floor=J["terrain"]["sea"] + 1.0)
        return
    for (n, p, q) in BANKS(by, f2):
        probe(n, p, q)
    probe("the dock: off the walkway's side", (d[0] - 5.0, d[1]), (d[0] - 5.0, d[1] + 8.0), 4.0, floor=J["terrain"]["sea"] + 1.0)
    probe("the dock: off the head's end", (d[0] - 10.5, d[1]), (d[0] - 18.0, d[1]), 4.0, floor=J["terrain"]["sea"] + 1.0)
    probe("the dock: off the head's corner", (d[0] - 10.5, d[1] + 2.0), (d[0] - 16.0, d[1] + 8.0), 4.0, floor=J["terrain"]["sea"] + 1.0)
    probe("the dock: along the walkway to the head", (d[0] + 2.0, d[1]), (d[0] - 10.5, d[1]), 6.0, cross=True)
    probe("the west bridge, west to east", (-12.0, by), (-2.0, by), 5.0, cross=True)
    probe("the east bridge, west to east", (-2.0, by), (12.0, by), 6.0, cross=True)
    probe("both bridges, east to west", (12.0, by), (-12.0, by), 9.0, cross=True)
    probe("the player's islet bridge, out onto the islet", (-72.0, -159.0), (-72.0, -177.0), 6.0, cross=True)
    probe("the enemy's islet bridge, out onto the islet", (161.0, -128.0), (161.0, -146.0), 6.0, cross=True)


def BANKS(by, f2):
    """Where he is put, and the point in the water (or over the cliff) he runs at: one of every kind of edge."""
    return [("west bank, west channel (north of the bridge)", (-28.0, 40.0), (-17.0, 40.0)),
            ("west bank, west channel (south of the bridge)", (-24.0, -14.0), (-14.0, -14.0)),
            ("east bank, east channel", (24.0, -14.0), (14.0, -14.0)),
            ("east bank, beside the bridge's rail", (11.0, by + 3.2), (6.5, by + 3.2)),
            ("the island, towards its north point", (0.0, by + 48.0), (0.0, by + 76.0)),
            ("the island, towards its south point", (0.0, by - 40.0), (0.0, by - 60.0)),
            ("the island, off its west side", (0.0, by + 4.0), (-6.5, by + 4.0)),
            ("the gorge above the island (west bank)", (-34.0, 120.0), (-10.0, 120.0)),
            ("the gorge above the island (east bank)", (16.0, 120.0), (-8.0, 120.0)),
            ("under the first fall (west bank)", (-40.0, 178.0), (-19.5, 178.0)),
            ("the top of the second fall (west bank)", (f2[0] - 16.5, f2[1] - 1.5), (f2[0] - 2.5, f2[1] + 3.5)),
            ("the top of the second fall (east bank)", (f2[0] + 9.5, f2[1] + 10.5), (f2[0] - 2.5, f2[1] + 3.5)),
            ("the lower gorge (south bank)", (51.2, -122.2), (58.0, -110.0)),
            ("the lower gorge (north bank)", (64.8, -97.8), (58.0, -110.0)),
            ("the river's mouth (the third fall)", (100.0, -146.0), (112.0, -142.0)),
            ("the south cliff", (-60.0, -160.0), (-60.0, -190.0)),
            ("the south cliff by the farm", (0.0, -158.0), (4.0, -190.0)),
            ("the west cliff (the west terrace)", (-170.0, -60.0), (-200.0, -60.0)),
            ("the west cliff (the north-west meadow)", (-170.0, 0.0), (-200.0, 0.0)),
            ("the enemy's south coast", (175.0, -116.0), (175.0, -150.0)),
            ("the player's islet, off its far side", (-72.0, -186.0), (-72.0, -206.0)),
            ("the enemy's islet, off its far side", (161.0, -154.0), (161.0, -175.0))]


def trees():
    """The forest: its count, nothing against a building, and clearing a footprint in the thick of the woods."""
    T = J.get("trees", {})
    want = sum(T.get("count", {}).values())
    lines = run(["vl.ClearTrees"], r"TREES: ", 0.8)
    m = re.search(r"TREES: (\d+) tree", lines[-1]) if lines else None
    check(bool(m) and int(m.group(1)) == want, "the level's forest has the plan's %d trees (%s)" % (want, m.group(1) if m else "no answer"))
    lines = run(["vl.ClearTrees buildings %d count" % round(T.get("margin", 1.5) * 100)], r"TREES counted round", 1.5)
    m = re.search(r"round (\d+) building\(s\).*: (\d+) tree", lines[-1]) if lines else None
    check(bool(m) and int(m.group(1)) > 8 and int(m.group(2)) == 0, "no tree stands in or against a building: %s" % (lines[-1].split("TREES ")[-1] if lines else "no answer"))
    # the thickest 16 m square of trunks on the player's bank
    trunks = [(i["pos"][0], i["pos"][1]) for i in J["instances"] if i["mesh"].startswith("SM_Tree2") and i["mesh"].endswith("_Trunk") and i.get("group") != "wild"]     # (not the wild woods: nobody walks there)
    best, at = 0, None
    for (x, y) in trunks:
        if x < -20:
            n = sum(1 for (a, b) in trunks if abs(a - x) <= 8.0 and abs(b - y) <= 8.0)
            if n > best:
                best, at = n, (x, y)
    X, Y = at[0] * 100, -at[1] * 100
    lines = run(["vl.ClearTrees %.0f %.0f 800 count" % (X, Y)], r"TREES counted", 0.8)
    m = re.search(r"counted: (\d+) tree", lines[-1]) if lines else None
    n0 = int(m.group(1)) if m else -1
    check(n0 >= best, "%d trees stand in a 16 m square at (%.0f, %.0f) (the plan: %d)" % (n0, at[0], at[1], best))
    lines = run(["vl.ClearTrees %.0f %.0f 800" % (X, Y)], r"TREES cleared|GRID area", 1.0)
    for l in lines:
        print("      " + l.split("LogSovereignRealms: ")[-1])
    m = re.search(r"cleared: (\d+) tree\(s\) \((\d+) crown.*grid: (\d+) cell.*where (\d+) trunk", lines[-1]) if lines else None
    check(bool(m) and int(m.group(1)) == n0 and int(m.group(2)) == n0, "cleared them, trunk and crown: %s" % (m.groups() if m else "no answer",))
    check(bool(m) and int(m.group(3)) > 0 and int(m.group(4)) >= n0 - 1, "the path grid was sampled again there: units can walk where %s of %d trunks stood" % (m.group(4) if m else "?", n0))
    lines = run(["vl.ClearTrees %.0f %.0f 800 count" % (X, Y), "vl.ClearTrees"], r"TREES", 0.8)
    m = re.search(r"counted: (\d+) tree", " ".join(lines))
    m2 = re.search(r"TREES: (\d+) tree", " ".join(lines))
    check(bool(m) and int(m.group(1)) == 0 and bool(m2) and int(m2.group(1)) == want - n0, "none left in the square, %s left in the forest" % (m2.group(1) if m2 else "?"))
    # a route straight through the clearing
    lines = run(["vl.Path %.0f %.0f %.0f %.0f" % (X - 700, Y, X + 700, Y)], r"path:", 0.8)
    m = re.search(r"path: (\w+), (\d+) corners, ([\d.]+) m", lines[-1]) if lines else None
    check(bool(m) and m.group(1) == "found" and float(m.group(3)) < 17.0, "a route across the clearing: %s" % (lines[-1].split("path: ")[-1] if lines else "none"))


def units():
    out = {}
    for l in run(["vl.Units"], r"unit ", 0.8):
        m = re.search(r"unit (.+?)\s+at\s+(-?\d+)\s+(-?\d+)\s+(-?\d+)\s+(.*)$", l)
        if m:
            out[m.group(1).strip().replace(" ", "_")] = (float(m.group(2)) / 100.0, -float(m.group(3)) / 100.0, float(m.group(4)) / 100.0, m.group(5))
    return out


def march():
    p0, p1 = J["teams"]["0"]["plaza"]["pos"], J["teams"]["1"]["plaza"]["pos"]
    before = set(units())
    run(["vl.Spawn Swordsman %.0f %.0f 3" % (p0[0] * 100 + 300, -p0[1] * 100 - 300), "vl.Spawn Archer %.0f %.0f 2" % (p0[0] * 100 + 300, -p0[1] * 100 - 500)], None, 1.5)
    there = sorted(set(units()) - before)
    run(["vl.Spawn Swordsman %.0f %.0f 3" % (p1[0] * 100 - 400, -p1[1] * 100 + 300)], None, 1.5)
    back = sorted(set(units()) - before - set(there))
    check(len(there) == 5 and len(back) == 3, "spawned %d + %d troops" % (len(there), len(back)))
    cmds = ["vl.Order %s %.0f %.0f 100 run" % (n, p1[0] * 100 - 500, -p1[1] * 100) for n in there]
    cmds += ["vl.Order %s %.0f %.0f 0 run" % (n, p0[0] * 100 + 500, -p0[1] * 100) for n in back]
    run(cmds, None, 1.0)
    t0, done = time.time(), False
    while time.time() - t0 < 330 and not done:
        time.sleep(6)
        u = units()
        done = all(n in u and "idle" in u[n][3] for n in there + back)
    u = units()
    for n in there:
        x, y, z, st = u.get(n, (0, 0, 0, "gone"))
        d = math.hypot(x - (p1[0] - 5.0), y - p1[1])
        check(d < 9.0 and not HZ[cell(x, y)], "%s marched to the enemy's plaza: %.1f m from the goal after %.0f s (%s)" % (n, d, time.time() - t0, st.strip()))
    for n in back:
        x, y, z, st = u.get(n, (0, 0, 0, "gone"))
        d = math.hypot(x - (p0[0] + 5.0), y - p0[1])
        check(d < 9.0 and not HZ[cell(x, y)], "%s marched to the player's plaza: %.1f m from the goal (%s)" % (n, d, st.strip()))
    # an archer up the player's tower
    t = G["tower0"]
    b2 = set(units())
    c = J["places"]["tower0"]                                              # 3 m out from its door, whichever way it faces
    k = 3.0 / max(math.hypot(t[0] - c[0], t[1] - c[1]), 1e-6)
    run(["vl.Spawn Archer %.0f %.0f 1" % ((t[0] + (t[0] - c[0]) * k) * 100, -(t[1] + (t[1] - c[1]) * k) * 100)], None, 1.5)
    a = sorted(set(units()) - b2)
    if a:
        run(["vl.Garrison %s" % a[0]], None, 8.0)
        st = units().get(a[0], (0, 0, 0, ""))
        check("tower" in st[3], "%s garrisons the player's watch tower: at height %.1f (%s)" % (a[0], st[2], st[3].strip()))
    else:
        check(False, "no archer spawned at the tower")


def main(a):
    what = a or ["routes", "barriers", "trees", "march"]
    if "routes" in what:
        routes()
    if "trees" in what:               # (first: the barrier probes clear the trees in their way)
        trees()
    if "barriers" in what:
        barriers()
    if "dock" in what:
        barriers(True)
    if "march" in what:
        march()
    print("%d failed" % len(fails))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
