#!/usr/bin/env python3
"""Every building of the build menu raised by the player's Builders, working, turned (VLConstruction.*), in
Play-In-Editor on a battle map (the editor open on L_Realm or L_Highlands, PIE running: python3 Tools/pie.py start):

    python3 Tools/buildings_test.py [start] [build] [works] [limits] [mine] [rotate]

  start   a match (easy), gold and food, three more Builders
  build   a barracks, an archery range, a farm and a watch tower near the castle (each a site, raised by the Builders),
          one farm through the menu's placing and a real click; refusals (on the castle, a site trains nobody)
  works   the farm brings food, the barracks and the range train a troop that waits in the yard, the tower shoots a foe
  limits  farms and towers up to their limits, then refused
  mine    mines are not built: a free mine of the map is claimed by a right click with a Builder selected, is a claim
          under way (nothing rises, nothing paid out), then brings gold; one that falls stands abandoned and is
          claimed again
  rotate  the barracks turned four times comes back to where it stood with the same walkable ground round it, those
          waiting in its yard turn with it and a new recruit finds the turned yard; the castle and a mine are refused
Positions come from the game (vl.Construction logs the castles and the veins), so it runs on any battle map.
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


def lines(since):
    with open(pie.LOG, errors="replace") as f:
        f.seek(since)
        return [l.rstrip().split("LogVoxelLab: ")[-1] for l in f if "LogVoxelLab" in l]


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
    print(("PASS " if ok else "FAIL ") + name + (("  (" + str(detail) + ")") if detail else ""))
    if not ok:
        fails.append(name)
    return ok


def cmd(*c, wait=0.8):
    m = mark()
    pie.run(list(c))
    time.sleep(wait)
    return lines(m)


def first(out, pattern):
    for l in out:
        if re.search(pattern, l):
            return l
    return ""


def world():
    """The castles, the mines and the buildings raised in the match, from vl.Construction."""
    out = cmd("vl.Construction")
    w = {"castle": {}, "veins": [], "built": [], "raw": out}
    for l in out:
        m = re.search(r"castle of team (\d) at (-?\d+) (-?\d+)", l)
        if m:
            w["castle"][int(m.group(1))] = (int(m.group(2)), int(m.group(3)))
        m = re.search(r"mine (\S+) at (-?\d+) (-?\d+) yaw (-?\d+): (.*)", l)
        if m:
            w["veins"].append(dict(actor=m.group(1), x=int(m.group(2)), y=int(m.group(3)), state=m.group(5)))
        m = re.search(r"^\s*(.+?) \(team (\d), (\S*)\) (\S+) at (-?\d+) (-?\d+) yaw (-?\d+): (\d+)% built.*?(\d+) waiting in the yard", l)
        if m:
            if int(m.group(2)) == 0:                        # (the player's only: the enemy builds too)
                w["built"].append(dict(name=m.group(1), team=0, mesh=m.group(3), x=int(m.group(5)), y=int(m.group(6)), yaw=int(m.group(7)),
                                       built=int(m.group(8)), waiting=int(m.group(9))))
    return w


def income():
    l = first(cmd("vl.Battle"), r"^team 0:")
    m = re.search(r"\(\+(\d+) \+(\d+) a minute\)", l)
    return (int(m.group(1)), int(m.group(2))) if m else (0, 0)


def raise_one(kind, name, at, timeout=150):
    """Lays a site near `at` and has every Builder work on it; True when it is finished."""
    m = mark()
    out = cmd("vl.Build %s %d %d 0 near" % (kind, at[0], at[1]))
    laid = first(out, r"^vl\.Build ")
    if not check("%s: a site is laid" % name, laid and "refused" not in laid, laid):
        return False
    cmd("vl.Work " + name.replace(" ", "_"))
    done = wait_for(r"BUILD %s of team 0 finished" % name, m, timeout)
    return check("%s: the Builders raise it" % name, done is not None, done or "not finished in %d s" % timeout)


def main(a):
    a = a or ["start", "build", "works", "limits", "mine", "rotate"]
    if "start" in a:
        m = mark()
        pie.run(["vl.StartMatch 0"])
        ok = wait_for(r"match started on ", m, 20)
        check("a match starts", ok is not None, ok or "")
        cmd("vl.Give gold 9000", "vl.Give food 4000", "vl.SpawnUnit Builder 3")
    w = world()
    castle = w["castle"].get(0)
    if not check("the player's castle is found", castle is not None, castle):
        return 1
    foe = w["castle"].get(1, (castle[0] + 1, castle[1]))
    # toward the enemy's castle and across: four spots round the player's own
    dx, dy = foe[0] - castle[0], foe[1] - castle[1]
    n = max((dx * dx + dy * dy) ** 0.5, 1.0)
    fx, fy = dx / n, dy / n
    spot = lambda f, s: (int(castle[0] + fx * f - fy * s), int(castle[1] + fy * f + fx * s))
    if "build" in a:
        out = cmd("vl.Build barracks %d %d 0" % castle)
        l = first(out, r"^vl\.Build ")
        check("refused on the castle itself", "refused" in l, l)
        raise_one("barracks", "Barracks", spot(3200, 2200))
        m = mark()
        out = cmd("vl.Build range %d %d 0 near" % spot(3200, -2200))
        l = first(cmd("vl.TrainAt Archery_Range"), r"train at|being built")
        check("a site trains nobody", "being built" in l, l)
        cmd("vl.Work Archery_Range")
        done = wait_for(r"BUILD Archery Range of team 0 finished", m, 150)
        check("Archery Range: the Builders raise it", done is not None)
        raise_one("farm", "Farm", spot(1200, 4200))
        raise_one("tower", "Watch Tower", spot(5200, 0))
        # the menu's own path: the card (BeginPlacement), the ghost under the pointer, a real click
        w2 = world()
        farm = [b for b in w2["built"] if b["name"] == "Farm"]
        if farm:
            m = mark()
            cmd("vl.Place farm", wait=1.0)
            check("the menu starts placing", wait_for(r"build: placing a Farm", m, 3) is not None)
            laid, said = False, []
            for k in range(6):                              # (the middle of the view over a few places: one will be free)
                at = (farm[0]["x"] + int(fx * (400 - 900 * k) - fy * (3000 + 500 * k)), farm[0]["y"] + int(fy * (400 - 900 * k) + fx * (3000 + 500 * k)))
                m2 = mark()
                cmd("vl.Look %d %d 0.2" % at, wait=1.2)
                cmd("vl.Input click 0.5 0.5", wait=1.5)
                l = first(lines(m2), r"BUILD team 0 lays a Farm")
                said += [x for x in lines(m2) if x.startswith("alert:")]
                if l:
                    laid = True
                    break
            check("a click on the ground lays the ghost's farm", laid, l or "; ".join(said))
            cmd("vl.Place off")
            if laid:
                cmd("vl.Work Farm")
                check("Farm (placed by hand): raised", wait_for(r"BUILD Farm of team 0 finished", m, 150) is not None)
    if "works" in a:
        w2 = world()
        for name in ("Barracks", "Archery Range"):
            m = mark()
            cmd("vl.TrainAt " + name.replace(" ", "_"))
            l = wait_for(r"trained .* at %s \(team 0\)" % name, m, 40)
            check("%s trains a troop, who waits in its yard" % name, l is not None and "waits in the yard" in l, l or "")
        g, f = income()
        farms = len([b for b in w2["built"] if b["name"] == "Farm" and b["built"] == 100])
        check("the farms bring food", farms > 0 and f > 0, "%d farm(s), +%d food a minute" % (farms, f))
        tower = [b for b in w2["built"] if b["name"] == "Watch Tower"]
        if check("a watch tower stands", bool(tower)):
            m = mark()
            cmd("vl.BattleLog 1", "vl.SpawnTeam Swordsman 1 %d %d 1" % (tower[0]["x"] + int(fx * 900), tower[0]["y"] + int(fy * 900)))
            l = wait_for(r"hit: Enemy .* takes \d+ from StaticMeshActor", m, 25)
            check("the tower shoots a foe in reach", l is not None, l or "")
            time.sleep(8)
            cmd("vl.BattleLog 0")
    if "limits" in a:
        for kind, name, limit in (("farm", "Farm", 3), ("tower", "Watch Tower", 2)):
            refused, laid = "", 0
            for i in range(limit + 1):
                out = cmd("vl.Build %s %d %d 0 near" % ((kind,) + spot(-2600 - 1500 * i, 3800 if kind == "farm" else -3800)), wait=1.2)
                l = first(out, r"^vl\.Build ")
                if "refused" in l:
                    refused = l
                    break
                laid += 1
            check("%s: refused at its limit of %d" % (name, limit), "limit %d reached" % limit in refused, refused or "never refused")
            for i in range(laid):                           # (the sites laid to reach it are cancelled: 75% back)
                cmd("vl.Demolish " + name.replace(" ", "_"))
        out = cmd("vl.Construction")
        print("   " + first(out, r"construction team 0"))
    if "mine" in a:
        # mines are not built: a free one of the map is claimed (Builders ordered onto it), and one that falls stands
        # abandoned, to be claimed again
        l = " ".join(cmd("vl.Place mine"))
        check("the build menu has no mine", "claimed, not built" in l, l[-160:])
        w2 = world()
        g0, _ = income()
        free = [v for v in w2["veins"] if v["state"].startswith("free")]
        free.sort(key=lambda v: (v["x"] - castle[0]) ** 2 + (v["y"] - castle[1]) ** 2)
        if check("a free mine on the map", bool(free), "; ".join("%s %s" % (v["actor"], v["state"]) for v in w2["veins"])):
            v = free[0]
            print("   mine %s at %d %d: %s" % (v["actor"], v["x"], v["y"], v["state"]))
            l = first(cmd("vl.Build tower %d %d 0" % (v["x"], v["y"])), r"^vl\.Build ")
            check("nothing is built on a mine", "refused" in l, l)
            # the player's way: Builders selected, a right click on the mine
            m = mark()
            cmd("vl.SelectUnits Builder_1", "vl.Look %d %d 0.25" % (v["x"], v["y"]), wait=1.5)
            for (u, vv) in ((0.5, 0.5), (0.5, 0.42), (0.5, 0.34), (0.44, 0.38), (0.56, 0.38), (0.5, 0.26), (0.42, 0.46), (0.58, 0.46)):
                cmd("vl.RightClick %.2f %.2f" % (u, vv), wait=1.0)      # (the mine stands above the ground the view looks at)
                if first(lines(m), r"^CLAIM team 0"):
                    break
            l = first(lines(m), r"^CLAIM team 0")
            if not check("a right click on it with a Builder selected claims it", l != "", l or "; ".join(x for x in lines(m) if "order at" in x or "alert" in x)[-300:]):
                l = first(cmd("vl.Build mine %d %d" % (v["x"], v["y"]), wait=1.5), r"^vl\.Build ")
                check("... claimed by the console instead", l != "" and "refused" not in l, l)
            st = [x for x in world()["veins"] if x["actor"] == v["actor"]]
            check("it is a claim under way, the mine standing as it stood", bool(st) and "being claimed" in st[0]["state"] and "HIDDEN" not in st[0]["state"], st[0]["state"] if st else "")
            g_site, _ = income()
            check("a claim under way gives nothing yet", g_site == g0, "+%d gold a minute (was +%d)" % (g_site, g0))
            cmd("vl.Work Gold_Mine")
            done = wait_for(r"BUILD Gold Mine of team 0 finished", m, 240)
            check("the Builders reach it and work the claim through", done is not None)
            time.sleep(1)
            g1, _ = income()
            check("the claimed mine brings gold", g1 > g0, "+%d -> +%d gold a minute" % (g0, g1))
            l = first(cmd("vl.Rotate Gold_Mine"), r"refused")
            check("a mine is not turned, and says why", "part of the land" in l, l)
            # it falls: it is not taken away, and can be claimed again
            mines0 = [x for x in world()["veins"] if x["state"] == "team 0"]
            cmd("vl.Damage Gold_Mine 99999", wait=4.0)
            now = world()["veins"]
            gone = [x for x in now if x["state"].startswith("free (abandoned)")]
            check("a fallen mine stands abandoned (not taken away)", len(gone) == 1 and "HIDDEN" not in gone[0]["state"] and len([x for x in now if x["state"] == "team 0"]) == len(mines0) - 1,
                  "; ".join("%s %s" % (x["actor"], x["state"]) for x in now))
            if gone:
                m = mark()
                l = first(cmd("vl.Build mine %d %d" % (gone[0]["x"], gone[0]["y"]), wait=1.5), r"^vl\.Build ")
                check("... and is claimed again", l != "" and "refused" not in l, l)
                cmd("vl.Work Gold_Mine")
                check("... and worked through again", wait_for(r"BUILD Gold Mine of team 0 finished", m, 240) is not None)
    if "rotate" in a:
        out = cmd("vl.Rotate Castle")
        check("the castle is not turned", "castle cannot be turned" in " ".join(out), first(out, r"refused"))
        before = world()
        waiting = sum(b["waiting"] for b in before["built"] if b["name"] == "Barracks")
        out = cmd("vl.Rotate Barracks 4", wait=3.0)
        rep = [l for l in out if l.startswith("vl.Rotate Barracks")]
        turned = [l for l in rep if " turned:" in l]
        check("the barracks turns four times", len(turned) == 4, "; ".join(l.split(":")[0] for l in rep[1:]) + " " + first(out, r"ROTATE .* refused"))
        key = lambda l: re.search(r"yaw (-?\d+) at ([-\d.]+ [-\d.]+ [-\d.]+);.*walkable (\d+), digest (\w+)", l).groups() if l else None
        if len(rep) >= 5:
            check("... and stands where it stood, the walkable ground round it the same", key(rep[0]) == key(rep[-1]), "%s -> %s" % (key(rep[0]), key(rep[-1])))
            yaws = [key(l)[0] for l in rep]
            check("... a quarter turn clockwise each time", len(set(yaws[:4])) == 4, " ".join(yaws))
            for l in rep:
                print("   " + l)
        time.sleep(4)
        count = lambda: sum(b["waiting"] for b in world()["built"] if b["name"] == "Barracks")
        check("those waiting in its yard turned with it", count() == waiting, "%d before, %d after" % (waiting, count()))
        # turn by turn, as the player does it, with time between: those waiting must be in their ranks after each
        kept = []
        for k in range(4):
            cmd("vl.Rotate Barracks", wait=2.5)
            kept.append(count())
        check("... and after each of four more turns, a few seconds apart", kept == [waiting] * 4, "waiting %s (%d before)" % (kept, waiting))
        # one more turn, then a recruit: it must find the yard where it is now
        m = mark()
        out = cmd("vl.Rotate Barracks", wait=1.5)
        check("the barracks turns once more", first(out, r" turned:") != "", first(out, r"^vl\.Rotate"))
        cmd("vl.TrainAt Barracks")
        l = wait_for(r"trained .* at Barracks \(team 0\)", m, 40)
        check("a troop trained in the turned barracks waits in its yard", l is not None and "waits in the yard" in l, l or "")
        time.sleep(12)
        end = world()
        now = sum(b["waiting"] for b in end["built"] if b["name"] == "Barracks")
        check("... and stands in its ranks there", now == waiting + 1, "%d waiting (%d before)" % (now, waiting))
        for name in ("Archery Range", "Farm", "Watch Tower"):
            out = cmd("vl.Rotate " + name.replace(" ", "_"), wait=1.5)
            l = first(out, r"^vl\.Rotate .* (turned|refused)")
            check("%s: turned, or refused with a reason" % name, " turned:" in l or "refused (" in l, l.split(";")[0])
        stuck = [l for l in cmd("vl.Units") if "GAVE UP" in l]
        check("nobody is stuck", not stuck, "; ".join(stuck)[:300])
    print("%d failed: %s" % (len(fails), "; ".join(fails)) if fails else "all passed")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
