#!/usr/bin/env python3
"""Tests of building (VLConstruction.*) in Play-In-Editor on L_Realm (the editor open on L_Realm, PIE running:
python3 Tools/pie.py start):

    python3 Tools/build_test.py [start] [build] [yard] [farm] [repair] [enemy] [shots]

  start   a match: no barracks or range on either side, each side's Builder, 3 swordsmen and 2 archers
  build   the player's Builder raises a barracks on the meadow east of the castle; training is refused while it is a site
  yard    three swordsmen trained there wait in its yard, in ranks
  farm    a farm in the wood south of the castle: a farmstead variant, trees cleared, the grid walkable there
  repair  the barracks is hurt; the idle Builder mends it (out of action meanwhile)
  enemy   the enemy commander lays its barracks and range and its Builder raises them
  shots   screenshots: the top bar's chips, a site, the yard (Saved/Screenshots/VL/build_*.png)
Prints PASS / FAIL lines; exit code 1 if anything failed.
"""
import os
import re
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "Tools"))
import pie

fails = []
START = [0]


def lines(since):
    with open(pie.LOG, errors="replace") as f:
        f.seek(since)
        return [l.rstrip() for l in f if "LogSovereignRealms" in l]


def mark():
    return os.path.getsize(pie.LOG)


def wait_for(pattern, since, timeout):
    end = time.time() + timeout
    while time.time() < end:
        for l in lines(since):
            if re.search(pattern, l):
                return l
        time.sleep(0.5)
    return None


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (("  (" + detail + ")") if detail else ""))
    if not ok:
        fails.append(name)


def cmd(*c):
    m = mark()
    pie.run(list(c))
    time.sleep(0.6)
    return lines(m)


# the player's castle is at (-10400, 5600) in Unreal's axes; the meadow of the old barracks east of it, the wood south
BARRACKS = (-6600, 3400)
FARM = (-6000, 9800)


def main(a):
    a = a or ["start", "build", "yard", "farm", "repair", "enemy", "shots"]
    if "start" in a:
        m = mark()
        START[0] = m
        pie.run(["vl.StartMatch 1"])
        ok = wait_for(r"match started on .*a battle", m, 15)
        check("match starts as a battle", ok is not None, ok or "")
        out = cmd("vl.Battle")
        trainers = [l for l in out if re.search(r"^\S*\s+(Barracks|Archery Range)\s+team [01]", l.split("]")[-1].strip())]
        check("no barracks or range at the start", not trainers, "; ".join(trainers))
        out = cmd("vl.Construction")
        b0 = [l for l in out if "construction team 0: 1 builder" in l]
        b1 = [l for l in out if "construction team 1: 1 builder" in l]
        check("each side has one Builder", bool(b0) and bool(b1), " / ".join(l.split("LogSovereignRealms: ")[-1] for l in out if "construction team" in l))
        out = cmd("vl.TrainAt Castle Builder")
        check("the castle trains a Builder", any("train at" in l and "1 queued" in l for l in out), " ".join(l.split("LogSovereignRealms: ")[-1] for l in out if "train at" in l))
    if "build" in a:
        cmd("vl.Give gold 3000", "vl.Give food 1500", "vl.Give gold 3000 enemy")
        m = mark()
        out = cmd("vl.Build barracks %d %d 0 near" % BARRACKS)
        laid = [l for l in out if "vl.Build Barracks" in l]
        check("a barracks site is laid", laid and "refused" not in laid[0], laid[0].split("LogSovereignRealms: ")[-1] if laid else "no answer")
        out = cmd("vl.TrainAt Barracks")
        check("training refused while it is a site", any("still being built" in l for l in out), " ".join(l.split("LogSovereignRealms: ")[-1] for l in out if "train at" in l))
        ok = wait_for(r"Builder \d+ goes to work on", m, 10)
        check("a Builder goes to work on it", ok is not None, ok.split("LogSovereignRealms: ")[-1] if ok else "")
        ok = wait_for(r"BUILD Barracks of team 0 finished", m, 120)
        check("the barracks is raised", ok is not None)
    if "yard" in a:
        m = mark()
        cmd("vl.TrainAt Barracks 3")
        ok = wait_for(r"waits in the yard", m, 30)        # (18 s a swordsman since the times were doubled, 2026-11-22)
        check("a recruit waits in the yard", ok is not None, ok.split("LogSovereignRealms: ")[-1] if ok else "")
        time.sleep(44)
        out = cmd("vl.Construction")
        y = [l for l in out if "Barracks (team 0" in l]
        check("three wait in the barracks' yard", any("3 waiting in the yard" in l for l in y), " ".join(l.split("LogSovereignRealms: ")[-1] for l in y))
        out = cmd("vl.Units")
        print("   " + "\n   ".join(l.split("LogSovereignRealms: ")[-1] for l in out if "Swordsman" in l)[:1500])
    if "farm" in a:
        m = mark()
        out = cmd("vl.Build farm %d %d 0 near" % FARM, "vl.Work farm")
        laid = [l for l in out if "BUILD team 0 lays a Farm" in l]
        check("a farm site is laid with a variant", bool(laid) and "SM_Farmstead_" in laid[0], laid[0].split("LogSovereignRealms: ")[-1] if laid else "")
        check("its trees are cleared", bool(laid) and re.search(r"[1-9]\d* tree\(s\) cleared", laid[0]) is not None)
        ok = wait_for(r"BUILD Farm of team 0 finished", m, 90)
        check("the farm is raised", ok is not None)
        ok = wait_for(r"BUILD Farm: \d+ prop", m, 2)
        check("its props are placed", ok is not None, ok.split("LogSovereignRealms: ")[-1] if ok else "")
        m = mark()
        cmd("vl.Build farm %d %d 0 near" % (FARM[0] + 3000, FARM[1]))
        out = lines(m)
        laid2 = [l for l in out if "BUILD team 0 lays a Farm" in l]
        if laid and laid2:
            v1 = re.search(r"SM_Farmstead_\w", laid[0]).group(0)
            v2 = re.search(r"SM_Farmstead_\w", laid2[0]).group(0)
            check("the next farm is another variant", v1 != v2, "%s then %s" % (v1, v2))
    if "repair" in a:
        # ordered (vl.Work: as a right click with Builders selected), then by itself: the Builders now stand by it
        m = mark()
        cmd("vl.Damage Barracks 0 700", "vl.Work Barracks")
        ok = wait_for(r"REPAIR Barracks of team 0 started", m, 40)
        check("ordered Builders repair the barracks (out of action meanwhile)", ok is not None)
        ok = wait_for(r"REPAIR Barracks of team 0 ended", m, 60)
        check("the repair ends", ok is not None)
        m = mark()
        cmd("vl.Damage Barracks 0 700")
        ok = wait_for(r"REPAIR Barracks of team 0 started", m, 30)
        check("an idle Builder nearby repairs it by himself (after 10 s without a hit)", ok is not None)
        wait_for(r"REPAIR Barracks of team 0 ended", m, 60)
    if "enemy" in a:
        m0 = START[0]
        ok = wait_for(r"AI 1: lays a Barracks", m0, 60)
        check("the enemy lays a barracks", ok is not None, ok.split("LogSovereignRealms: ")[-1] if ok else "")
        ok = wait_for(r"AI 1: lays a Archery Range", m0, 90)
        check("the enemy lays an archery range", ok is not None, ok.split("LogSovereignRealms: ")[-1] if ok else "")
        ok = wait_for(r"BUILD Barracks of team 1 finished", m0, 120)
        check("the enemy's barracks is raised", ok is not None)
        ok = wait_for(r"BUILD Archery Range of team 1 finished", m0, 150)
        check("the enemy's range is raised", ok is not None)
    if "shots" in a:
        pie.run(["vl.Look %d %d 0.15" % BARRACKS])
        print(pie.main(["shot", "build_barracks", "2"]))
        pie.run(["vl.Look %d %d 0.15" % FARM])
        print(pie.main(["shot", "build_farm", "2"]))
    print("%d failed" % len(fails) if fails else "all passed")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
