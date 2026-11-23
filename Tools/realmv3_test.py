#!/usr/bin/env python3
"""Checks of L_RealmV3 in Play-In-Editor (the editor open on L_RealmV3, PIE running: python Tools/pie.py start; then
vl.StartMatch 0). The map designer's own checks. Written from realmv2_test.py:

    Tools/.venv/Scripts/python Tools/realmv3_test.py [routes] [around] [times] [build] [stuck]

  routes    the path grid's routes from each castle's door to its mines, its towers, its ramp, the basin, both neutral
            mines and the other castle (vl.Path), next to the plan's own measure (they must agree within an eighth).
            Every route that leaves a plateau must go down its ramp and through its pass (a corner of the route on
            each), and a route to the other castle through both passes. The two sides' routes to the centre must be
            the same length within 5 %
  around    no way round: the path grid has no ground to stand on in the forest, on the coast or on the ridges (probes
            all round the island: vl.Path from the castle must answer "no walkable ground there"), and routes between
            many pairs of places on the two plateaus all go through both passes
  times     the hero runs (vl.Teleport, vl.Walk ... run) from the player's door to the middle of the basin, and from the
            middle up each side's pass and ramp: those two times must agree within 5 %
  build     a barracks is laid on each plateau (three places) and in the basin either side of the lane, a farm and a
            tower too (vl.Build ... near, after vl.Give gold): none may be refused
  stuck     every unit of the match stands on the plan's ground (vl.Units): none under it, none in the air
Reads SourceArt/realmv3.json and realmv3_terrain.npz. Prints PASS / FAIL lines; exit code 1 if anything failed.
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
J = json.load(open(os.path.join(ROOT, "SourceArt", "realmv3.json")))
Z = np.load(os.path.join(ROOT, "SourceArt", "realmv3_terrain.npz"))
H = Z["h"]
HALF, CELL = J["terrain"]["half"], J["terrain"]["cell"]
G = J["gates"]
RAMPS = J["places"]["ramps"]
PORTS = {}
for _p in J["places"]["ports"]:
    _q, _sg = _p["quay"], (-1.0 if _p["team"] == 0 else 1.0)
    PORTS[_p["team"]] = dict(quay_mid=[(_q[0] + _q[2]) / 2.0 + _sg * 0.5, (_q[1] + _q[3]) / 2.0 - _sg * 8.0], pier=[_p["dock"][0] + _sg * 2.0, _p["dock"][1]])
fails = []


def ground(x, y):
    n = H.shape[0]
    return float(H[min(n - 1, max(0, int((x + HALF) / CELL))), min(n - 1, max(0, int((y + HALF) / CELL)))])


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


def seg_gap(p, a, b):
    vx, vy = b[0] - a[0], b[1] - a[1]
    t = max(0.0, min(1.0, ((p[0] - a[0]) * vx + (p[1] - a[1]) * vy) / max(vx * vx + vy * vy, 1e-9)))
    return math.hypot(p[0] - (a[0] + t * vx), p[1] - (a[1] + t * vy))


def path(a, b):
    """-> (found, metres, [(x, y)] the corners in layout metres, the log line)"""
    lines = run(["vl.Path %.0f %.0f %.0f %.0f" % (a[0] * 100, -a[1] * 100, b[0] * 100, -b[1] * 100)], r"path:", 0.7)
    if not lines:
        return False, None, [], "no answer"
    m = re.search(r"path: (\w+), (\d+) corners, ([\d.]+) m", lines[-1])
    if not m:
        return False, None, [], lines[-1].split("path:", 1)[-1].strip()
    corners = [(float(x) / 100.0, -float(y) / 100.0) for (x, y, _z) in re.findall(r"\((-?\d+) (-?\d+) (-?\d+)\)", lines[-1])]
    return m.group(1) == "found", float(m.group(3)), corners, ""


def through(corners, start, name):
    """Does the route run along this ramp or pass (a stretch of it within its floor)?"""
    r = RAMPS[name]
    a, b = r["foot"][:2], r["head"][:2]
    pts = [start] + corners
    for p, q in zip(pts[:-1], pts[1:]):
        n = max(1, int(math.hypot(q[0] - p[0], q[1] - p[1]) / 1.0))
        for k in range(n + 1):
            c = (p[0] + (q[0] - p[0]) * k / n, p[1] + (q[1] - p[1]) * k / n)
            if seg_gap(c, a, b) < r["half_width"] + 0.5:
                return True
    return False


def routes():
    b = J["balance"] or {}
    centre = {}
    print("%-52s %9s %9s" % ("route (path grid, in the game)", "grid m", "plan m"))
    for t, side in ((0, "player"), (1, "enemy")):
        S = b.get(side, {})
        s, o = str(t), str(1 - t)
        c = G["castle" + s]
        rows = [("own Home 1 mine", G["mine" + s], S.get("home_mine_1"), []),
                ("own Home 2 mine", G["mine" + s + "b"], S.get("home_mine_2"), []),
                ("own tower 1", G["tower" + s], S.get("tower_1"), []),
                ("own tower 2", G["tower" + s + "b"], S.get("tower_2"), []),
                ("its port's quay", PORTS[t]["quay_mid"], S.get("quay"), ["port" + s]),
                ("its pier's head", PORTS[t]["pier"], S.get("pier_head"), ["port" + s]),
                ("the other side's quay", PORTS[1 - t]["quay_mid"], S.get("enemy_quay"), ["base0", "pass0", "pass1", "base1", "port" + o]),
                ("its ramp's head", RAMPS["base" + s]["head"][:2], S.get("ramp_head"), []),
                ("its ramp's foot", RAMPS["base" + s]["foot"][:2], S.get("ramp_foot"), ["base" + s]),
                ("the middle of the basin", [0.0, 0.0], S.get("centre"), ["base" + s, "pass" + s]),
                ("Neutral 1", G["mine_n1"], S.get("neutral_1"), ["base" + s, "pass" + s]),
                ("Neutral 2", G["mine_n2"], S.get("neutral_2"), ["base" + s, "pass" + s]),
                ("the basin's north ground", J["buildable"][2]["centre"], S.get("basin_north"), ["base" + s, "pass" + s]),
                ("the basin's south ground", J["buildable"][3]["centre"], S.get("basin_south"), ["base" + s, "pass" + s]),
                ("the other castle", G["castle" + o], S.get("enemy_castle"), ["base0", "pass0", "pass1", "base1"])]
        for name, goal, plan, via in rows:
            ok, length, corners, why = path(c, goal)
            full = "%s castle -> %s" % (side, name)
            print("%-52s %9s %9s" % (full, length, plan))
            check(ok, "route found: " + full + ("" if ok else " (" + why + ")"))
            if ok and plan:
                check(abs(length - plan) < 0.125 * plan + 8.0, "  and as long as the plan says (%.0f m, the plan %.0f m): %s" % (length, plan, full))
            for v in via:
                check(ok and through(corners, c, v), "  and it goes by %s: %s" % (v, full))
            if name == "the middle of the basin":
                centre[side] = length
    if len(centre) == 2 and all(centre.values()):
        d = abs(centre["player"] - centre["enemy"]) / max(centre.values())
        check(d <= 0.05, "the two sides' routes to the middle of the basin: %.1f m and %.1f m (%.1f %% apart; 5 %% allowed)" % (centre["player"], centre["enemy"], d * 100))


def around():
    c = G["castle0"]
    # ---- the forest, the coast and the ridges: no ground of the path grid's main region within 10 m of these
    probes = []
    for k in range(24):
        a = 2 * math.pi * k / 24
        probes.append(("the coast %3d deg" % round(math.degrees(a)), 150.0 * math.cos(a) / max(abs(math.cos(a)), abs(math.sin(a))), 150.0 * math.sin(a) / max(abs(math.cos(a)), abs(math.sin(a)))))
    # (a ring 176 m out, just inside the sea cliffs; not where a plateau comes within 14 m of the coast: its west / east side)
    probes = [(n, x * 176.0 / 150.0, y * 176.0 / 150.0) for (n, x, y) in probes]
    def near_plateau(x, y):
        for key in ("plateau0", "plateau1"):
            c = J["places"][key]
            if (abs(x - c[0]) / 78.0) ** 2.5 + (abs(y - c[1]) / 72.0) ** 2.5 < 1.0:
                return True
        return False
    probes = [(n, x, y) for (n, x, y) in probes if not near_plateau(x, y)]
    probes += [("the north-east spine", 100.0, 100.0), ("the south-west spine", -100.0, -100.0), ("the north-east corner", 140.0, 140.0), ("the south-west corner", -140.0, -140.0),
               ("the forest west of the basin", -110.0, -20.0), ("the forest east of the basin", 110.0, 20.0), ("the forest north of the basin", 20.0, 120.0),
               ("the forest south of the basin", -20.0, -120.0), ("the north-west crest", -32.0, 32.0), ("the south-east crest", 32.0, -32.0),
               ("the forest under plateau A's east cliff", -30.0, 110.0), ("the forest under plateau B's west cliff", 30.0, -110.0),
               ("the wood beside ramp A, 24 m off its middle", -49.0, 42.0), ("the wood beside ramp B", 49.0, -42.0),
               ("the sea cliff north of port A", -172.0, 160.0), ("the sea cliff south of port A", -172.0, 52.0),
               ("the sea cliff south of port B", 172.0, -160.0), ("the sea cliff north of port B", 172.0, -52.0)]
    bad = 0
    for name, x, y in probes:
        lines = run(["vl.Path %.0f %.0f %.0f %.0f" % (c[0] * 100, -c[1] * 100, x * 100, -y * 100)], r"path:", 0.5)
        none = bool(lines) and "no walkable ground" in lines[-1]
        if not none:
            # (the grid looks 10 m round the point: a probe near the playable ground may find it; then the route must end there)
            m = re.search(r"path: (\w+), (\d+) corners, ([\d.]+) m", lines[-1]) if lines else None
            ends = re.findall(r"\((-?\d+) (-?\d+) (-?\d+)\)", lines[-1])[-1:] if lines else []
            where = "ends at (%.0f, %.0f)" % (float(ends[0][0]) / 100, -float(ends[0][1]) / 100) if ends else (lines[-1][-80:] if lines else "no answer")
            bad += 1
            print("   a route to %s (%.0f, %.0f): %s" % (name, x, y, where))
    check(bad == 0, "%d places in the forest, on the coast and on the ridges: the path grid has ground at %d of them" % (len(probes), bad))
    # ---- from all over plateau A to all over plateau B: every route by both ramps and both passes
    p0 = J["places"]["plateau0"]
    starts = [(p0[0] + dx, p0[1] + dy) for (dx, dy) in ((-30, 34), (0, 36), (30, 34), (-22, -8), (22, -18), (-12, -34), (12, -34))]
    starts.append(tuple(PORTS[0]["quay_mid"]))                              # (from the port too)
    n = miss = 0
    for a in starts:
        for bb in ((-a[0], -a[1]), (-starts[0][0], -starts[0][1]), (-starts[3][0], -starts[3][1])):
            ok, length, corners, why = path(a, bb)
            n += 1
            if not (ok and all(through(corners, a, v) for v in ("base0", "pass0", "pass1", "base1"))):
                miss += 1
                print("   (%.0f, %.0f) -> (%.0f, %.0f): %s" % (a[0], a[1], bb[0], bb[1], "no route: " + why if not ok else "%.0f m, not by every ramp and pass" % length))
    check(miss == 0, "%d routes from plateau A to plateau B: %d of them not by both ramps and both passes" % (n, miss))


def times():
    """The hero runs (vl.Teleport, vl.Walk ... run). The whole way from the player's door to the middle of the basin;
    and, for the two sides against each other, from the middle of the basin up each side's pass and ramp to a point
    four fifths of the way up the ramp (the enemy's castle and towers shoot the hero dead at its door, so its side is
    run from the middle outwards, and the player's the same way for the comparison): the two must agree within 5 %."""
    def leg(name, a, b):
        za = ground(a[0], a[1])
        run(["vl.View follow", "vl.Teleport %.0f %.0f %.0f" % (a[0] * 100, -a[1] * 100, za * 100 + 120)], None, 2.5)
        since = os.path.getsize(LOG)
        t0 = time.time()
        pie.run(["vl.Walk %.0f %.0f run" % (b[0] * 100, -b[1] * 100)])
        arrived = None
        while time.time() - t0 < 90.0:
            time.sleep(0.5)
            got = log_tail(r"King David (arrived|GAVE UP) .* after ([\d.]+) s", since)
            if got:
                m = re.search(r"King David (arrived|GAVE UP) .* after ([\d.]+) s", got[-1])
                arrived = (m.group(1), float(m.group(2)))
                break
            if log_tail(r"King David has returned to the castle", since):
                arrived = ("was killed on the way", round(time.time() - t0, 1))
                break
        print("%s, the hero running: %s" % (name, "%s after %.1f s" % arrived if arrived else "did not get there in 90 s"))
        check(bool(arrived) and arrived[0] == "arrived", "the hero gets there: " + name)
        return arrived[1] if arrived and arrived[0] == "arrived" else None

    run(["vl.BattleLog 1"], None, 0.3)
    g = G["castle0"]
    leg("the player castle's door -> the middle of the basin", (g[0], g[1] - 3.0), (0.0, 0.0))
    out = []
    for t, side in ((0, "player"), (1, "enemy")):
        r = RAMPS["base%d" % t]
        up = (r["head"][0] + 0.2 * (r["foot"][0] - r["head"][0]), r["head"][1] + 0.2 * (r["foot"][1] - r["head"][1]))
        out.append(leg("the middle of the basin -> four fifths up the %s's ramp" % side, (0.0, 0.0), up))
    run(["vl.BattleLog 0"], None, 0.3)
    if all(out):
        d = abs(out[0] - out[1]) / max(out)
        check(d <= 0.05, "travel time between the middle and the ramp: player's side %.1f s, enemy's side %.1f s (%.1f %% apart; 5 %% allowed)" % (out[0], out[1], d * 100))


def build():
    run(["vl.Give gold 100000", "vl.Give food 100000"], None, 0.5)
    p0, p1 = J["places"]["plateau0"], J["places"]["plateau1"]
    spots = [("plateau A, behind the castle to the west", "barracks", p0[0] - 24, p0[1] + 38, ""), ("plateau A, behind the castle to the east", "farm", p0[0] + 22, p0[1] + 36, ""),
             ("plateau A, east of the plaza", "range", p0[0] + 26, p0[1] + 2, ""), ("plateau A, the south", "farm", p0[0] - 4, p0[1] - 34, ""),
             ("plateau A, the south-west", "barracks", p0[0] - 30, p0[1] - 12, ""), ("plateau A, by the ramp's head", "tower", p0[0] + 14, p0[1] - 34, ""),
             ("the basin's north ground", "barracks", J["buildable"][2]["centre"][0], J["buildable"][2]["centre"][1], ""),
             ("the basin's south ground", "barracks", J["buildable"][3]["centre"][0], J["buildable"][3]["centre"][1], ""),
             ("plateau B, behind the castle to the west (the enemy's Builder)", "barracks", p1[0] - 24, p1[1] - 38, " enemy"),
             ("plateau B, the north (the enemy's Builder)", "range", p1[0] + 4, p1[1] + 34, " enemy")]
    for name, what, x, y, who in spots:
        # (the enemy's commander builds on its plateau as the match goes: its side is asked at up to three places)
        for (ax, ay) in ([(x, y)] if not who else [(x, y), (p1[0] + 34, p1[1] - 34), (p1[0] - 24, p1[1] + 22)]):
            lines = run(["vl.Give gold 1000" + who, "vl.Build %s %.0f %.0f 0%s near" % (what, ax * 100, -ay * 100, who)], r"vl\.Build", 0.9)
            ok = bool(lines) and "refused" not in lines[-1]
            if ok:
                break
        check(ok, "a %s can be laid on %s (%.0f, %.0f)%s" % (what, name, x, y, "" if ok else ": " + (lines[-1].split("vl.Build", 1)[-1] if lines else "no answer")))


def stuck():
    lines = run(["vl.Units"], r"unit ", 1.0)
    n = bad = 0
    for l in lines:
        m = re.search(r"unit .* at\s+(-?\d+)\s+(-?\d+)\s+(-?\d+)", l)
        if not m or "on the tower" in l:                   # (a tower's archer stands on its platform)
            continue
        x, y, z = float(m.group(1)) / 100.0, -float(m.group(2)) / 100.0, float(m.group(3)) / 100.0
        n += 1
        if abs(z - ground(x, y)) > 1.0:
            bad += 1
            print("   off the ground: %s" % l[-120:])
    check(n > 0 and bad == 0, "%d units listed, %d of them not standing on the plan's ground" % (n, bad))


if __name__ == "__main__":
    which = sys.argv[1:] or ["routes", "around", "times", "build", "stuck"]
    for w in which:
        {"routes": routes, "around": around, "times": times, "build": build, "stuck": stuck}[w]()
    print("%d failed" % len(fails))
    sys.exit(1 if fails else 0)
