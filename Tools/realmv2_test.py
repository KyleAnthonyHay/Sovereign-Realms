#!/usr/bin/env python3
"""Checks of L_RealmV2 in Play-In-Editor (the editor open on L_RealmV2, PIE running: python3 Tools/pie.py start; then
vl.StartMatch 0). The map designer's own checks; movement and battles are tested apart. Written from highland_test.py:

    Tools/.venv/bin/python Tools/realmv2_test.py [routes] [build] [stuck]

  routes    the path grid's routes from each castle's door to every mine, tower, bridge, contested zone and buildable
            area of the plan, and castle to castle (vl.Path), next to the plan's own measure (they must agree within an
            eighth)
  build     a barracks is laid in the middle of every buildable area and on each hill's top, a tower on the upper
            terrace (vl.Build ... near, after vl.Give gold): none may be refused
  stuck     every unit and building of the match stands on the plan's ground (vl.Units): none under it, none in the air
Reads SourceArt/realmv2.json and realmv2_terrain.npz. Prints PASS / FAIL lines; exit code 1 if anything failed.
"""
import json
import os
import re
import sys
import time

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "Tools"))
import pie

LOG = pie.LOG
J = json.load(open(os.path.join(ROOT, "SourceArt", "realmv2.json")))
Z = np.load(os.path.join(ROOT, "SourceArt", "realmv2_terrain.npz"))
H = Z["h"]
HALF, CELL = J["terrain"]["half"], J["terrain"]["cell"]
G = J["gates"]
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


def routes():
    b = J["balance"] or {}
    P, E = b.get("player", {}), b.get("enemy", {})
    rows = []
    for t, side, S in ((0, "player", P), (1, "enemy", E)):
        c = G["castle%d" % t]
        o = 1 - t
        rows += [("%s castle -> own mine" % side, c, G["mine%d" % t], S.get("own_mine")),
                 ("%s castle -> the tower by its mine" % side, c, G["tower%d" % t], S.get("mine_tower")),
                 ("%s castle -> its hill tower" % side, c, G["tower%db" % t], S.get("hill_tower")),
                 ("%s castle -> the north-west mine" % side, c, G["mine_nw"], S.get("mine_nw")),
                 ("%s castle -> the centre-east mine" % side, c, G["mine_c"], S.get("mine_centre_east")),
                 ("%s castle -> the south-east mine" % side, c, G["mine_se"], S.get("mine_se")),
                 ("%s castle -> the ruins" % side, c, J["places"]["ruins"], S.get("ruins")),
                 ("%s castle -> the upper terrace" % side, c, J["places"]["upper_terrace"], S.get("upper_terrace")),
                 ("%s castle -> the north crossing" % side, c, J["places"]["north_crossing"], S.get("north_crossing")),
                 ("%s castle -> the south crossing" % side, c, J["places"]["south_crossing"], S.get("south_crossing")),
                 ("%s castle -> the other castle" % side, c, G["castle%d" % o], S.get("enemy_castle")),
                 ("%s castle -> the other's mine" % side, c, G["mine%d" % o], S.get("enemy_mine"))]
        for a in J["buildable"]:
            if a["kind"] == "build":
                rows.append(("%s castle -> area %s" % (side, a["name"]), c, a["centre"], (b.get("flats", {}).get(a["name"]) or [None, None])[t]))
    print("%-52s %9s %9s" % ("route (path grid, in the game)", "grid m", "plan m"))
    for name, a, c, plan in rows:
        lines = run(["vl.Path %.0f %.0f %.0f %.0f" % (a[0] * 100, -a[1] * 100, c[0] * 100, -c[1] * 100)], r"path:", 0.7)
        m = re.search(r"path: (\w+), (\d+) corners, ([\d.]+) m", lines[-1]) if lines else None
        ok = bool(m) and m.group(1) == "found"
        length = float(m.group(3)) if m else None
        print("%-52s %9s %9s" % (name, length, plan))
        check(ok, "route found: " + name)
        if ok and plan:
            check(abs(length - plan) < 0.125 * plan + 8.0, "  and as long as the plan says (%.0f m, the plan %.0f m): %s" % (length, plan, name))


def build():
    run(["vl.Give gold 100000", "vl.Give food 100000"], None, 0.5)
    spots = []
    for a in J["buildable"]:
        if a["kind"] in ("build", "zone"):
            spots.append((a["name"], a["centre"][0], a["centre"][1]))
    spots += [("ruins plateau", -10.0, -30.0), ("west bluff", -286.0, -70.0), ("north bluff", 232.0, 284.0)]
    spots += [("upper terrace (a tower: it is small, and the old arch stands on it)", -40.0, 40.0)]
    for name, x, y in spots:
        lines = run(["vl.Give gold 1000", "vl.Build %s %.0f %.0f 0 near" % ("tower" if "tower" in name else "barracks", x * 100, -y * 100)], r"vl\.Build", 0.9)
        ok = bool(lines) and "refused" not in lines[-1]
        check(ok, "a barracks can be laid in %s (%.0f, %.0f)%s" % (name, x, y, "" if ok else ": " + (lines[-1].split("vl.Build", 1)[-1] if lines else "no answer")))


def stuck():
    lines = run(["vl.Units"], r"unit ", 1.0)
    n = bad = 0
    for l in lines:
        m = re.search(r"unit .* at\s+(-?\d+)\s+(-?\d+)\s+(-?\d+)", l)
        if not m or l.rstrip().endswith("on the tower"):      # (a tower's archers stand on its platform)
            continue
        x, y, z = float(m.group(1)) / 100.0, -float(m.group(2)) / 100.0, float(m.group(3)) / 100.0
        n += 1
        if abs(z - ground(x, y)) > 1.0:
            bad += 1
            print("   off the ground: %s" % l[-120:])
    check(n > 0 and bad == 0, "%d units listed, %d of them not standing on the plan's ground" % (n, bad))


if __name__ == "__main__":
    which = sys.argv[1:] or ["routes", "build", "stuck"]
    for w in which:
        {"routes": routes, "build": build, "stuck": stuck}[w]()
    print("%d failed" % len(fails))
    sys.exit(1 if fails else 0)
