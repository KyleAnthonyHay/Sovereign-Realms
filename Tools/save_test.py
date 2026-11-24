#!/usr/bin/env python3
"""Saved games in Play-In-Editor: play a little, save, play on, load, and compare (the editor open, no play session):

    python Tools/save_test.py [realmv3|realmv2|realm|highlands|flatlands] [shots] [keep] [quick]

  shots   screenshots of the menus: Saved/Screenshots/VL/save_*.png (the pause menu, Save Game, the question before a
          slot is written over, Load Game, the title screen with Continue, its Load Game)
  keep    leave the play session running at the end
  quick   skip the minute of play after the load (the first run of a change)
What it does, and checks (PASS / FAIL lines; exit code 1 if anything failed):
  1. a match on the map; the player is given gold and food, lays a barracks, a farm and a watch tower, trains troops,
     raises the farm a level and starts raising the castle, puts an archer on the tower and swordsmen on the troop ship
     and sails it, sends an archer on patrol and a swordsman to guard the castle, has a building damaged, and waits
     until the enemy has laid a building of its own
  2. vl.Save 1 and, in the same frame, vl.SaveDump (the live state as JSON), vl.Battle, vl.Units, vl.Ship state
  3. plays on (a unit killed, gold given, troops sent off, the clock runs), then vl.Load 1 with vl.Load.Pause 1, and
     the same dump and logs from the loaded match before anything has moved
  4. compares: the map, difficulty and clock; both sides' stock and books; every building (kind, team, level, health,
     place, site progress, upgrade and training clocks, queues, destroyed); every unit (kind, name, team, place,
     health, stance, on a lookout / aboard, its walk); platoons, patrols, guards; the ships (place, course, who is
     aboard); the commanders (clocks, posture, squads); the camera
  5. plays for a minute: the clock runs, walkers arrive, a fight is fought, the enemy's commander thinks and builds,
     nobody is there twice
  6. the quicksave and quickload (vl.Quick, as F5 / F9), the autosave (vl.Autosave.Minutes), Continue on the title
     screen (a click on its button), and how a save from another version, of a missing map, with a missing building
     and a file that is no save at all are refused or put back without a crash
"""
import json
import os
import re
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "Tools"))
import pie

LOG = pie.LOG
ARGS = [a.lower() for a in sys.argv[1:]]
SHOTS = "shots" in ARGS
QUICK = "quick" in ARGS
MAP = next((a for a in ARGS if a in ("realmv3", "realmv2", "realm", "highlands", "flatlands")), "realmv3")
SAVES = os.path.join(ROOT, "Saved", "SaveGames")
fails = []


def log_tail(pattern, since):
    with open(LOG, errors="replace") as f:
        f.seek(since)
        return [re.sub(r"^\[[^\]]*\]\[[ \d]*\]LogSovereignRealms: (Warning: )?", "", l.rstrip()) for l in f if "LogSovereignRealms" in l and re.search(pattern, l)]


def cmd(cmds, pattern=None, wait=0.6):
    since = os.path.getsize(LOG)
    pie.run(cmds if isinstance(cmds, list) else [cmds])
    time.sleep(wait)
    return log_tail(pattern, since) if pattern else []


def wait_log(pattern, since, timeout):
    end = time.time() + timeout
    while time.time() < end:
        l = log_tail(pattern, since)
        if l:
            return l
        time.sleep(0.4)
    return []


def unrle(r):
    """The fog's explored cells, from the save's run-length coding (value, count pairs)."""
    out = []
    for i in range(0, len(r) - 1, 2):
        out += [r[i]] * r[i + 1]
    return out


def check(text, ok, detail=""):
    print(("PASS  " if ok else "FAIL  ") + text + (("   [" + str(detail) + "]") if detail != "" else ""))
    if not ok:
        fails.append(text)
    return ok


def lower(v):
    """The dump's keys in lower case (the engine's JSON writer has its own idea of their case)."""
    if isinstance(v, dict):
        return {k.lower(): lower(x) for k, x in v.items()}
    if isinstance(v, list):
        return [lower(x) for x in v]
    return v


def dump(name, extra=None, wait=0.8):
    """vl.SaveDump (with the other commands in the same frame); returns the state and the log lines."""
    path = os.path.join(SAVES, "dump_%s.json" % name)
    if os.path.exists(path):
        os.remove(path)
    lines = cmd((extra or []) + ["vl.SaveDump " + name], r".", wait)
    end = time.time() + 10
    while not os.path.exists(path) and time.time() < end:
        time.sleep(0.1)
    time.sleep(0.2)
    with open(path, encoding="utf-8") as f:
        return lower(json.load(f)), lines


def shot(name, settle=1.2):
    if SHOTS:
        path = os.path.join(pie.SHOTS, name + ".png")
        if os.path.exists(path):
            os.remove(path)
        time.sleep(settle)
        pie.run(["vl.Shot " + name + " ui"])
        end = time.time() + 15
        while not os.path.exists(path) and time.time() < end:
            time.sleep(0.1)
        print("      shot", path if os.path.exists(path) else "(not written)")


def wait_for(what, test, timeout, every=1.5):
    end = time.time() + timeout
    while time.time() < end:
        v = test()
        if v:
            return v
        time.sleep(every)
    print("      (timed out waiting for %s)" % what)
    return None


def buildings(d, team=None, kind=None, alive=True):
    return [b for b in d["buildings"] if (team is None or b["team"] == team) and (kind is None or b["kind"] == kind) and (not alive or not b["bdestroyed"])]


def units(d, team=None, kind=None):
    return [u for u in d["units"] if (team is None or u["team"] == team) and (kind is None or u["kind"] == kind)]


def xy(v):
    return (v["x"], v["y"])


def dist(a, b):
    return ((a["x"] - b["x"]) ** 2 + (a["y"] - b["y"]) ** 2) ** 0.5


def buttons():
    """vl.HUD: the buttons drawn last frame, {id: (u, v)}."""
    out = {}
    for l in cmd("vl.HUD", r"hud button", 0.6):
        m = re.search(r"hud button (\d+) at ([\d.]+) ([\d.]+)", l)
        if m:
            out[int(m.group(1))] = (float(m.group(2)), float(m.group(3)))
    return out


def click(button_id, wait=0.8):
    b = buttons()
    if button_id not in b:
        print("      (no button %d on the screen: %s)" % (button_id, sorted(b)))
        return False
    cmd("vl.UIClick %.4f %.4f" % b[button_id], None, wait)
    return True


def near(a, b, tol):
    return abs(a - b) <= tol


def compare(a, b):
    """The saved state (a) against the loaded match before anything has moved (b)."""
    check("the map, the difficulty and the clock", a["mappath"] == b["mappath"] and a["difficulty"] == b["difficulty"] and near(a["clock"], b["clock"], 0.11) and a["bbattle"] == b["bbattle"]
          and a["btestworld"] == b["btestworld"], "%s, difficulty %d, clock %.1f / %.1f" % (b["mappath"], b["difficulty"], a["clock"], b["clock"]))
    for t in range(2):
        ka, kb = a["kingdoms"][t], b["kingdoms"][t]
        same = all(ka[k] == kb[k] for k in ("gold", "food", "recruited", "lost", "killed", "buildingslost", "recruitedkind", "lostkind", "earned", "wasted", "spent", "killsby", "bjonathancame", "farmvariant"))
        timers = near(ka["spycooldown"], kb["spycooldown"], 0.11) and near(ka["jonathanwait"], kb["jonathanwait"], 0.11)
        check("team %d: its stock, its books and its clocks" % t, same and timers, "%d gold %d food, recruited %d lost %d killed %d; spy %.0f s, Jonathan %.0f s" % (
            kb["gold"], kb["food"], kb["recruited"], kb["lost"], kb["killed"], kb["spycooldown"], kb["jonathanwait"]))
    check("the names' counters", a["numbers"] == b["numbers"], b["numbers"])

    # ---- buildings: the same list in the same order
    ba, bb = a["buildings"], b["buildings"]
    ok = check("as many buildings", len(ba) == len(bb), "%d saved, %d loaded" % (len(ba), len(bb)))
    bad = []
    for i in range(min(len(ba), len(bb))):
        x, y = ba[i], bb[i]
        why = []
        for k in ("kind", "name", "team", "level", "bdestroyed", "queue", "trained", "feedplatoon", "bhasrally", "bruntime", "paidgold", "paidfood", "guardlevel", "bclaim", "bwasneutral", "mesh", "yard"):
            if x[k] != y[k]:
                why.append("%s %s -> %s" % (k, x[k], y[k]))
        for k, tol in (("health", 1.5), ("upgradeleft", 0.11), ("payout", 0.11), ("defence", 0.11), ("trainclock", 0.11), ("build", 0.002), ("guardrestock", 0.11)):
            if not near(x[k], y[k], tol):
                why.append("%s %.2f -> %.2f" % (k, x[k], y[k]))
        if dist(x["location"], y["location"]) > 1.0 or abs(x["location"]["z"] - y["location"]["z"]) > 1.0:
            why.append("moved %.0f cm" % dist(x["location"], y["location"]))
        if abs(((x["rotation"]["yaw"] - y["rotation"]["yaw"]) + 180) % 360 - 180) > 0.5:
            why.append("yaw %.0f -> %.0f" % (x["rotation"]["yaw"], y["rotation"]["yaw"]))
        if bool(x["levelactor"]) != bool(y["levelactor"]):
            why.append("the level's own / raised in the match")
        if why:
            bad.append("%s of team %d: %s" % (x["name"], x["team"], "; ".join(why)))
    check("every building as it was (kind, team, level, health, place, turn, site, clocks, queue, destroyed)", ok and not bad, "; ".join(bad[:4]) if bad else "%d buildings: %d sites, %d raised in the match, %d destroyed, %d being raised a level, %d training" % (
        len(bb), sum(1 for x in bb if x["build"] < 1 and not x["bdestroyed"]), sum(1 for x in bb if x["bruntime"]), sum(1 for x in bb if x["bdestroyed"]),
        sum(1 for x in bb if x["upgradeleft"] >= 0), sum(1 for x in bb if x["queue"])))

    # ---- units: the same list in the same order
    ua, ub = a["units"], b["units"]
    ok = check("as many units", len(ua) == len(ub), "%d saved, %d loaded" % (len(ua), len(ub)))
    bad = []
    worst = 0.0
    # (a guard walking to its post, a follower catching up: sent again at the orders' next look, not at the load)
    later = set(u for g in a["guards"] for u in g["units"]) | set(u for f in a["follows"] for u in f["units"]) | set(a["roamers"])
    for i in range(min(len(ua), len(ub))):
        x, y = ua[i], ub[i]
        why = []
        for k in ("kind", "name", "team", "btroop", "bdead", "stance", "bholdorder", "btowerguard", "garrison", "shipplace", "job"):
            if x[k] != y[k]:
                why.append("%s %s -> %s" % (k, x[k], y[k]))
        if not near(x["health"], y["health"], 0.6):
            why.append("health %.0f -> %.0f" % (x["health"], y["health"]))
        d = dist(x["feet"], y["feet"])
        worst = max(worst, d)
        # (on a deck or a lookout it stands where the ship or the tower puts it)
        if d > (60.0 if x["garrison"] >= 0 else 30.0) or abs(x["feet"]["z"] - y["feet"]["z"]) > 60.0:
            why.append("moved %.0f cm (z %.0f -> %.0f)" % (d, x["feet"]["z"], y["feet"]["z"]))
        if x["garrison"] < 0 and abs(((x["yaw"] - y["yaw"]) + 180) % 360 - 180) > 25.0 and not y["bwalking"]:
            why.append("facing %.0f -> %.0f" % (x["yaw"], y["yaw"]))
        if x["bwalking"] and x["attack"] < 0 and x["job"] < 0 and x["heading"] < 0 and i not in later and not y["bwalking"] and x["garrison"] < 0 and dist(x["feet"], x["goal"]) > 150.0:
            why.append("was walking to %.0f %.0f, now stands" % xy(x["goal"]))
        if why:
            bad.append("%s: %s" % (x["name"], "; ".join(why)))
    check("every unit as it was (kind, name, team, place, health, stance, on a lookout / aboard, its walk)", ok and not bad, "; ".join(bad[:4]) if bad else "%d units, the furthest %.1f cm from where it was; %d walking, %d on lookouts, %d aboard" % (
        len(ub), worst, sum(1 for x in ub if x["bwalking"]), sum(1 for x in ub if 100000 <= x["garrison"] < 200000), sum(1 for x in ub if x["garrison"] >= 200000)))
    names = [u["name"] for u in ub]
    check("nobody is there twice", len(names) == len(set(names)), [n for n in set(names) if names.count(n) > 1][:5])

    # ---- orders
    pa = [(sorted(p["members"]), p["formation"], p["stance"], p["bmarchtogether"], p["leader"]) for p in a["platoons"]]
    pb = [(sorted(p["members"]), p["formation"], p["stance"], p["bmarchtogether"], p["leader"]) for p in b["platoons"]]
    check("the platoons (members, formation, stance, leader), the recruits' flag", pa == pb and a["rallyplatoon"] == b["rallyplatoon"], [len(p[0]) for p in pb])
    ra = sorted((sorted(r["members"]), len(r["points"]), r["next"], r["bloop"]) for r in a["routes"])
    rb = sorted((sorted(r["members"]), len(r["points"]), r["next"], r["bloop"]) for r in b["routes"])
    check("the patrols and attack-moves", ra == rb, "%d saved, %d loaded" % (len(ra), len(rb)))
    ga = sorted((g["ward"], sorted(g["units"])) for g in a["guards"])
    gb = sorted((g["ward"], sorted(g["units"])) for g in b["guards"])
    check("the guards", ga == gb, "%d saved, %d loaded" % (len(ga), len(gb)))
    fa = sorted((f["leader"], sorted(f["units"])) for f in a["follows"])
    fb = sorted((f["leader"], sorted(f["units"])) for f in b["follows"])
    check("the followers, the roaming Spies, the selection", fa == fb and sorted(a["roamers"]) == sorted(b["roamers"]) and sorted(a["selection"]) == sorted(b["selection"]))

    # ---- ships
    sa, sb = a["ships"], b["ships"]
    ok = len(sa) == len(sb)
    bad = []
    for i in range(min(len(sa), len(sb))):
        x, y = sa[i], sb[i]
        if x["team"] != y["team"] or dist(x["location"], y["location"]) > 5.0 or abs(((x["yaw"] - y["yaw"]) + 180) % 360 - 180) > 1.0 or x["course"] != y["course"] or len(x["patrol"]) != len(y["patrol"]) \
                or len(x["waypoints"]) != len(y["waypoints"]) or (x["course"] == 0 and x["blanded"] != y["blanded"]):
            bad.append("ship %d: at %.0f %.0f yaw %.0f course %d landed %s -> %.0f %.0f yaw %.0f course %d landed %s" % (i, x["location"]["x"], x["location"]["y"], x["yaw"], x["course"], x["blanded"],
                                                                                                                 y["location"]["x"], y["location"]["y"], y["yaw"], y["course"], y["blanded"]))
    check("the ships (place, heading, course, landed)", ok and not bad, "; ".join(bad) if bad else "%d ship(s): %s" % (len(sb), ", ".join(("under sail" if s["course"] == 1 else "on patrol" if s["course"] == 2 else
                                                                                                                 "landed" if s["blanded"] else "at sea") for s in sb)))
    # ---- the commanders
    for t in range(2):
        x, y = a["commanders"][t], b["commanders"][t]
        if not x["bactive"] and not y["bactive"]:
            continue
        same = all(x[k] == y[k] for k in ("difficulty", "bactive", "posture", "wavessent", "raidssent", "buildstep", "foeattacks", "nextsquadid"))
        clocks = all(near(x[k], y[k], 0.11) for k in ("clock", "thinkclock", "strategyclock", "nextwavetime", "nextraidtime", "posturesince"))
        qa = sorted((q["id"], q["role"], q["task"], sorted(q["units"]), q["target"]) for q in x["squads"])
        qb = sorted((q["id"], q["role"], q["task"], sorted(q["units"]), q["target"]) for q in y["squads"])
        check("team %d's commander: its clocks, posture, attacks sent, squads, sightings" % t, same and clocks and qa == qb and len(x["seen"]) == len(y["seen"]),
              "clock %.0f, next attack at %.0f (in %.0f s), posture %d, %d squad(s), %d foe(s) seen" % (y["clock"], y["nextwavetime"], y["nextwavetime"] - y["clock"], y["posture"], len(qb), len(y["seen"])))
    check("who is played, and both cameras", a["played"] == b["played"] and a["bheromode"] == b["bheromode"] and near(a["camyaw"], b["camyaw"], 0.5) and near(a["zoom"], b["zoom"], 0.01)
          and near(a["overviewzoom"], b["overviewzoom"], 0.01) and near(a["overviewyaw"], b["overviewyaw"], 0.5) and dist(a["overviewfocus"], b["overviewfocus"]) < 5.0,
          "unit %d, %s, overview over %.0f %.0f zoom %.2f yaw %.0f" % (b["played"], "hero view" if b["bheromode"] else "overview", b["overviewfocus"]["x"], b["overviewfocus"]["y"], b["overviewzoom"], b["overviewyaw"]))


def battle_lines(lines):
    """vl.Battle's / vl.Units' / vl.Ship state's own lines, for the comparison by the game's logs."""
    teams = [re.sub(r"\(\+\d+ \+\d+ a minute\)", "", l) for l in lines if re.match(r"team \d: ", l)]
    # (without what only a tick works out again: who is at a site's walls now, "under repair", the whole seconds left)
    blds = sorted(re.sub(r" \(\d+ builders\)|, under repair|\((\d+) s\)", "", l).strip() for l in lines if re.match(r"\s+\S.* team -?\d level \d", l))
    us = {}
    for l in lines:
        m = re.match(r"unit (.+?)\s+at\s+(-?\d+)\s+(-?\d+)\s+(-?\d+)\s+(.*)$", l)
        if m:
            us[m.group(1).strip()] = (float(m.group(2)), float(m.group(3)), float(m.group(4)), m.group(5).split(",")[0].replace("  [selected]", ""))
    ships = []
    for l in lines:
        m = re.search(r"ship #(\d+) \S+ team (\d) at V\(X=([-\d.]+), Y=([-\d.]+), Z=([-\d.]+)\) yaw ([-\d.]+): (.*?); aboard (\d+) of", l)
        if m:
            ships.append((int(m.group(2)), float(m.group(3)), float(m.group(4)), float(m.group(6)), re.sub(r" \(.*", "", m.group(7)), int(m.group(8))))
    return teams, blds, us, ships


def compare_logs(la, lb):
    ta, ba, ua, sa = battle_lines(la)
    tb, bb, ub, sb = battle_lines(lb)
    check("vl.Battle: both sides' lines are the same (stock, storage, troops, queued, housing, castle level, the books)", ta == tb and len(tb) == 2, tb if ta == tb else [ta, tb])
    # (health and a site's progress within a point: the log rounds them, and a site's grow with its walls)
    def hp(line):
        m, p = re.search(r"health +(\d+)/", line), re.search(r"SITE (\d+)%", line)
        return (re.sub(r"SITE \d+%", "SITE %", re.sub(r"health +\d+/", "health /", line)), int(m.group(1)) if m else 0, int(p.group(1)) if p else 0)
    same_b = len(ba) == len(bb) and all(hp(x)[0] == hp(y)[0] and abs(hp(x)[1] - hp(y)[1]) <= 1 and abs(hp(x)[2] - hp(y)[2]) <= 1 for x, y in zip(ba, bb))
    diff = [x for x in ba if x not in bb] + [x for x in bb if x not in ba]
    check("vl.Battle: every building's line is the same (team, level, health within a point, site, training, raising)", same_b and len(bb) > 0, "%d buildings" % len(bb) if same_b else diff[:4])
    far = {n: round(((ua[n][0] - ub[n][0]) ** 2 + (ua[n][1] - ub[n][1]) ** 2) ** 0.5) for n in ua if n in ub}
    # (on a lookout or a deck, or not; whether it walks is compared from the dumps, order by order)
    states = [n for n in ua if n in ub and ua[n][3].startswith("on the") != ub[n][3].startswith("on the")]
    check("vl.Units: the same units, each within 60 cm of where it was, on a lookout or a deck as it was", set(ua) == set(ub) and all(d <= 60 for d in far.values()) and not states,
          "%d units, the furthest %d cm off" % (len(ub), max(far.values()) if far else 0) if set(ua) == set(ub) and not states else "only saved %s, only loaded %s, other state %s" % (
              sorted(set(ua) - set(ub))[:4], sorted(set(ub) - set(ua))[:4], [(n, ua[n][3], ub[n][3]) for n in states[:3]]))
    same = len(sa) == len(sb) and all(x[0] == y[0] and abs(x[1] - y[1]) < 5 and abs(x[2] - y[2]) < 5 and abs(((x[3] - y[3]) + 180) % 360 - 180) < 2 and x[5] == y[5] for x, y in zip(sa, sb))
    check("vl.Ship state: the same ships in the same places with as many aboard", same and len(sb) > 0, sb if same else [sa, sb])


def play(castle, ship):
    """Step 1: the things a save has to hold."""
    cx, cy = castle["location"]["x"], castle["location"]["y"]
    cmd(["vl.Give gold 6000", "vl.Give food 6000", "vl.TimeScale 6"], wait=0.5)
    for what in ("barracks", "farm", "tower", "range"):
        l = cmd("vl.Build %s %.0f %.0f 0 near" % (what, cx, cy), r"vl\.Build", 0.9)
        check("a %s is laid" % what, bool(l) and "refused" not in l[-1], l[-1] if l else "no answer")
    cmd("vl.Work Barracks", wait=0.3)

    def built(d, kind):
        return [b for b in buildings(d, 0, kind) if b["build"] >= 1.0]

    def builders_on(name):
        cmd("vl.Work " + name, wait=0.2)

    # every Builder on each site in turn (a site rises only while Builders work at it)
    for kind, name in (("Barracks", "Barracks"), ("Farm", "Farm"), ("Watch Tower", "Watch_Tower")):
        builders_on(name)
        ok = wait_for("the " + kind, lambda: built(dump("w")[0], kind), 120, 3.0)
        check("the %s is built" % kind, bool(ok))
    cmd(["vl.TrainAt Barracks 4", "vl.Upgrade Farm"], wait=0.5)
    wait_for("the recruits", lambda: len(units(dump("w")[0], 0, "Swordsman")) >= 7, 90, 3.0)
    wait_for("the farm at level 2", lambda: [b for b in buildings(dump("w")[0], 0, "Farm") if b["level"] >= 2], 90, 3.0)
    d, _ = dump("w")
    check("troops were trained and the farm is at level 2", len(units(d, 0, "Swordsman")) >= 7 and any(b["level"] >= 2 for b in buildings(d, 0, "Farm")),
          "%d swordsmen, farm level %s" % (len(units(d, 0, "Swordsman")), [b["level"] for b in buildings(d, 0, "Farm")]))
    # the enemy lays something of its own meanwhile
    foe = wait_for("the enemy's first building", lambda: [b for b in buildings(dump("w")[0], 1) if b["bruntime"]], 150, 4.0)
    check("the enemy has laid a building of its own", bool(foe), [b["name"] for b in foe or []])
    cmd(["vl.TimeScale 1"], wait=0.3)
    d, _ = dump("w")
    sw = [u["name"].replace(" ", "_") for u in units(d, 0, "Swordsman")]
    ar = [u["name"].replace(" ", "_") for u in units(d, 0, "Archer") if not u["btowerguard"]]
    # an archer on the tower, an archer on patrol, a swordsman guarding the castle, a building under way and damaged
    cmds = ["vl.Garrison %s Watch_Tower" % ar[0], "vl.Patrol %s %.0f %.0f" % (ar[1], cx + 1500, cy + 1800), "vl.Guard %s Castle" % sw[0], "vl.Upgrade Castle", "vl.TrainAt Barracks 3",
            "vl.Damage Farm 140", "vl.Build farm %.0f %.0f 0 near" % (cx - 2500, cy + 2500)]
    cmd(cmds, wait=1.0)
    if ship:
        # three swordsmen put aboard, and the ship sent out to sea (straight off the shore it lies at)
        cmd(["vl.SelectUnits none", "vl.SelectUnits %s" % sw[1], "vl.SelectUnits %s add" % sw[2], "vl.SelectUnits %s add" % sw[3], "vl.Ship put sel", "vl.SelectUnits none"], wait=0.8)
        s = ship
        dx, dy = s["x"] - s["land"][0], s["y"] - s["land"][1]
        n = max((dx * dx + dy * dy) ** 0.5, 1.0)
        l = cmd("vl.Ship sail %.0f %.0f" % (s["x"] + dx / n * 7000, s["y"] + dy / n * 7000), r"ship: ", 0.8)
        check("the troop ship sails with three aboard", any("sails to" in x for x in l), l[-1] if l else "no answer")
    wait_for("the archer on the lookout", lambda: any(100000 <= u["garrison"] < 200000 and not u["btowerguard"] for u in units(dump("w")[0], 0, "Archer")), 60, 2.0)
    cmd(["vl.Mode overview", "vl.Look %.0f %.0f 0.3 -40" % (cx, cy), "vl.SelectUnits %s" % sw[-1], "vl.Order %s %.0f %.0f" % (sw[-1], cx + 3000, cy - 2500)], wait=1.5)


def ships_now():
    out = []
    for l in cmd("vl.Ship state", r"ship #\d", 0.6):
        m = re.search(r"ship #(\d+) (\S+) team (\d) at V\(X=([-\d.]+), Y=([-\d.]+), Z=([-\d.]+)\) yaw ([-\d.]+): (.*); aboard (\d+) of (\d+), coming (\d+), landed (\d) at V\(X=([-\d.]+), Y=([-\d.]+), Z=([-\d.]+)\)", l)
        if m:
            g = m.groups()
            out.append(dict(i=int(g[0]), team=int(g[2]), x=float(g[3]), y=float(g[4]), yaw=float(g[6]), state=g[7], aboard=int(g[8]), landed=g[11] == "1", land=(float(g[12]), float(g[13]), float(g[14]))))
    return out


def open_map():
    since = os.path.getsize(LOG)
    pie.run(["vl.Map " + MAP])
    ok = wait_log(r"match started on", since, 120)
    time.sleep(3.0)
    return bool(ok)


def load(slot, expect=True, timeout=150):
    """vl.Load, and the wait for the save to be put back (or refused)."""
    since = os.path.getsize(LOG)
    pie.run(["vl.Load.Pause 1", "vl.Load " + slot])
    l = wait_log(r"load: the save of .* put back|load: .* not loaded|could not be put back: ", since, timeout)
    time.sleep(1.0)
    return l, log_tail(r"load: ", since)


def main():
    os.makedirs(SAVES, exist_ok=True)
    print(pie.mcp("StartPIE", {"options": {"bSimulate": False, "playMode": "PlayMode_InEditorFloating", "warmupSeconds": 2.0}})[:120])
    time.sleep(8)
    if not check("a match on " + MAP, open_map()):
        return
    cmd(["vl.Autosave.Minutes 0", "vl.Mode overview"], wait=0.5)
    d0, _ = dump("start")
    castle = (buildings(d0, 0, "Castle") or [None])[0]
    if not check("the player's castle stands", castle is not None):
        return
    ss = wait_for("the ships", ships_now, 12, 2.0) or []
    ship = next((s for s in ss if s["team"] == 0 and s["landed"]), None)
    print("      %s: %d buildings, %d units, %d ship(s)%s" % (d0["maptitle"], len(d0["buildings"]), len(d0["units"]), len(ss), "" if ship else " (no troop ship of the player's lies landed here: the ship's part is left out)"))

    # ---- 1. play
    play(castle, ship)

    # ---- 2. save, and the state in the same frame
    for f in ("VL_Slot1.sav", "VL_Slot2.sav"):
        if os.path.exists(os.path.join(SAVES, f)):
            os.remove(os.path.join(SAVES, f))
    a, la = dump("saved", ["vl.Save 1", "vl.Battle", "vl.Units", "vl.Ship state"], 1.2)
    check("vl.Save 1 writes Saved/SaveGames/VL_Slot1.sav", os.path.exists(os.path.join(SAVES, "VL_Slot1.sav")) and any("save: Slot 1 written" in l for l in la),
          "%d bytes" % os.path.getsize(os.path.join(SAVES, "VL_Slot1.sav")) if os.path.exists(os.path.join(SAVES, "VL_Slot1.sav")) else "no file")
    has = dict(site=any(b["build"] < 1 for b in buildings(a, 0)), raising=any(b["upgradeleft"] >= 0 for b in buildings(a, 0)), training=any(b["queue"] for b in buildings(a, 0)),
               hurt=any(b["health"] < 0.95 * 400 and b["kind"] == "Farm" for b in buildings(a, 0)), lookout=any(100000 <= u["garrison"] < 200000 and not u["btowerguard"] for u in a["units"]),
               tower_guards=any(u["btowerguard"] for u in a["units"]), aboard=sum(1 for u in a["units"] if u["garrison"] >= 200000), sailing=any(s["team"] == 0 and (s["course"] == 1 or not s["blanded"]) for s in a["ships"]),
               patrol=len(a["routes"]), guards=len(a["guards"]), walking=sum(1 for u in a["units"] if u["bwalking"]), enemy_built=sum(1 for b in buildings(a, 1) if b["bruntime"]),
               platoon=len(a["platoons"][0]["members"]))
    check("the save holds a site, a level being raised, a training queue, a damaged building, an archer on a lookout, a patrol, a guard, a walker and the enemy's own building",
          has["site"] and has["raising"] and has["training"] and has["lookout"] and has["patrol"] >= 1 and has["guards"] >= 1 and has["walking"] >= 1 and has["enemy_built"] >= 1, has)
    if ship:
        check("... and three aboard a ship under sail or out at sea", has["aboard"] == 3 and has["sailing"], "%d aboard" % has["aboard"])
    if SHOTS:
        cmd("vl.Menu pause", wait=0.8)
        shot("save_pause_menu")
        cmd("vl.SaveMenu save", wait=0.8)
        shot("save_menu")
        click(340 + 40)                 # (Slot 1, which has a save: the question)
        shot("save_overwrite")
        cmd("vl.SaveMenu load", wait=0.8)
        shot("save_load_menu")
        click(340 + 40)                 # (a match is on: the question)
        shot("save_load_ask")
        cmd("vl.Menu 0", wait=0.5)

    # ---- 3. play on, so that everything is different; then load
    k = units(a, 0, "Swordsman")[-1]["name"].replace(" ", "_")
    cmd(["vl.TimeScale 4", "vl.Give gold 777", "vl.Kill " + k, "vl.Order troops %.0f %.0f run" % (castle["location"]["x"] - 3000, castle["location"]["y"] - 3000), "vl.Look 0 0 0.8 20", "vl.Stop archers"], wait=6.0)
    c, _ = dump("later")
    check("the match has moved on since the save (the clock, the stock, a unit lost)", c["clock"] > a["clock"] + 10 and c["kingdoms"][0]["gold"] != a["kingdoms"][0]["gold"] and len(c["units"]) != len(a["units"]),
          "clock %.0f -> %.0f, gold %d -> %d, units %d -> %d" % (a["clock"], c["clock"], a["kingdoms"][0]["gold"], c["kingdoms"][0]["gold"], len(a["units"]), len(c["units"])))
    cmd("vl.TimeScale 1", wait=0.3)
    done, lines = load("1")
    if not check("vl.Load 1 opens the map again and puts the save back", bool(done) and "put back" in done[-1], (done or lines or ["nothing in the log"])[-1]):
        return
    b, lb = dump("loaded", ["vl.Battle", "vl.Units", "vl.Ship state"], 1.2)
    check("the load left nothing out", "0 left out), " in done[-1] and done[-1].count("(0 left out)") == 2, done[-1])

    # ---- 4. compare
    compare(a, b)
    compare_logs(la, lb)
    cmd(["vl.Load.Pause 0", "pause"], wait=1.0)

    # ---- 5. a minute of play after the load
    if not QUICK:
        t0, _ = dump("after0")
        check("the game is running again (the clock moves)", t0["clock"] > b["clock"], "%.1f -> %.1f" % (b["clock"], t0["clock"]))
        fa, ft = a.get("fog") or {}, t0.get("fog") or {}
        if fa.get("dim"):
            ea, et = unrle(fa.get("exploredrle", [])), unrle(ft.get("exploredrle", []))
            lost = sum(1 for i in range(min(len(ea), len(et))) if ea[i] and not et[i])
            check("the fog: what was explored is explored again, the enemy buildings seen are known", len(ea) == len(et) and lost == 0
                  and len(ft.get("seenbuildings", [])) >= len(fa.get("seenbuildings", [])),
                  "%d of %d cells explored at the save, %d lost; %d -> %d buildings seen" % (sum(1 for x in ea if x), len(ea), lost, len(fa.get("seenbuildings", [])), len(ft.get("seenbuildings", []))))
        # foes at the player's door: a fight
        cx, cy = castle["location"]["x"], castle["location"]["y"]
        walker = next((u for u in t0["units"] if u["bwalking"] and u["team"] == 0), None)
        cmd(["vl.SpawnTeam Swordsman 1 %.0f %.0f 3" % (cx + 2200, cy + 1200), "vl.TimeScale 3"], wait=20.0)
        t1, _ = dump("after1")
        cmd(["vl.TimeScale 1"], wait=0.3)
        gone = t1["clock"] - t0["clock"]
        check("a minute on: the clock ran", gone > 45, "%.0f s of play" % gone)
        k0, k1 = t0["kingdoms"], t1["kingdoms"]
        check("... a fight was fought (damage dealt, or the fallen counted)", sum(k1[0]["damageby"]) + sum(k1[1]["damageby"]) > sum(k0[0]["damageby"]) + sum(k0[1]["damageby"]) + 20
              or k1[0]["killed"] + k1[1]["killed"] > k0[0]["killed"] + k0[1]["killed"], "damage %.0f -> %.0f, kills %d -> %d" % (
                  sum(k0[0]["damageby"]) + sum(k0[1]["damageby"]), sum(k1[0]["damageby"]) + sum(k1[1]["damageby"]), k0[0]["killed"] + k0[1]["killed"], k1[0]["killed"] + k1[1]["killed"]))
        check("... the economy paid out (gold or food came in on both sides)", all(sum(k1[t]["earned"]) > sum(k0[t]["earned"]) for t in range(2)), [k1[t]["earned"] for t in range(2)])
        e0, e1 = t0["commanders"][1], t1["commanders"][1]
        moved = sum(1 for u0 in units(t0, 1) for u1 in units(t1, 1) if u0["name"] == u1["name"] and dist(u0["feet"], u1["feet"]) > 300)
        grown = len(buildings(t1, 1)) > len(buildings(t0, 1)) or any(x["build"] > y["build"] + 0.05 or x["level"] > y["level"] for x in buildings(t1, 1) for y in buildings(t0, 1)
                                                                    if x["name"] == y["name"] and dist(x["location"], y["location"]) < 5)
        check("... the enemy's commander carried on (its clock ran; its troops moved, or it built, trained or recruited)",
              e1["clock"] > e0["clock"] + 40 and (moved > 0 or grown or k1[1]["recruited"] > k0[1]["recruited"] or sum(k1[1]["spent"]) > sum(k0[1]["spent"])),
              "clock %.0f -> %.0f, %d of its troops moved, building %s, recruited %d -> %d, posture %d, next attack in %.0f s" % (
                  e0["clock"], e1["clock"], moved, "went on" if grown else "stood", k0[1]["recruited"], k1[1]["recruited"], e1["posture"], e1["nextwavetime"] - e1["clock"]))
        if walker:
            w1 = next((u for u in t1["units"] if u["name"] == walker["name"]), None)
            check("... the unit that was walking when saved got on (arrived, or went on to a fight)", w1 is None or dist(w1["feet"], walker["feet"]) > 200 or dist(walker["feet"], walker["goal"]) < 250,
                  "%s: %.0f cm on" % (walker["name"], dist(w1["feet"], walker["feet"]) if w1 else -1))
        sites0 = {b_["name"] + str(round(b_["location"]["x"])): b_["build"] for b_ in buildings(t0) if b_["build"] < 1}
        sites1 = {b_["name"] + str(round(b_["location"]["x"])): b_["build"] for b_ in buildings(t1)}
        check("... sites went on rising, the level went on being raised", all(sites1.get(k_, 1) >= v for k_, v in sites0.items()) and
              all(any(y["name"] == x["name"] and dist(x["location"], y["location"]) < 5 and (y["level"] > x["level"] or y["upgradeleft"] < x["upgradeleft"]) for y in buildings(t1))
                  for x in buildings(t0) if x["upgradeleft"] >= 0), {k_: (round(v, 2), round(sites1.get(k_, 1), 2)) for k_, v in sites0.items()})
        names = [u["name"] for u in t1["units"]]
        check("... nobody is there twice, nobody under the ground", len(names) == len(set(names)) and all(u["feet"]["z"] > -1500 for u in t1["units"]),
              [n for n in set(names) if names.count(n) > 1][:5] or "%d units" % len(names))
        if ship and t1["ships"]:
            s0_, s1_ = t0["ships"][0], t1["ships"][0]
            check("... the ship sailed on to where it was sent (or lies there)", dist(s0_["location"], s1_["location"]) > 300 or s1_["course"] == 0, "%.0f cm on, course %d" % (dist(s0_["location"], s1_["location"]), s1_["course"]))
            check("... its three are still aboard", sum(1 for u in t1["units"] if u["garrison"] >= 200000) == 3)

    # ---- 6. the quicksave and quickload, the autosave, the other slots' refusals, Continue
    for f in ("VL_Quick.sav", "VL_Auto.sav"):
        if os.path.exists(os.path.join(SAVES, f)):
            os.remove(os.path.join(SAVES, f))
    q, lq = dump("quick", ["vl.Quick save"], 1.0)
    check("the quicksave (F5's call) writes VL_Quick.sav", os.path.exists(os.path.join(SAVES, "VL_Quick.sav")) and any("quicksave (F5): done" in l for l in lq))
    cmd(["vl.Give gold 333", "vl.TimeScale 4"], wait=3.0)
    cmd("vl.TimeScale 1", wait=0.2)
    since = os.path.getsize(LOG)
    pie.run(["vl.Load.Pause 1", "vl.Quick load"])
    done = wait_log(r"load: the save of .* put back", since, 150)
    time.sleep(1.0)
    q2, _ = dump("quickloaded")
    check("the quickload (F9's call) puts it back", bool(done) and near(q["clock"], q2["clock"], 0.11) and q["kingdoms"][0]["gold"] == q2["kingdoms"][0]["gold"] and len(q["units"]) == len(q2["units"]),
          "clock %.1f / %.1f, gold %d / %d, units %d / %d" % (q["clock"], q2["clock"], q["kingdoms"][0]["gold"], q2["kingdoms"][0]["gold"], len(q["units"]), len(q2["units"])))
    cmd(["vl.Load.Pause 0", "pause"], wait=0.6)
    since = os.path.getsize(LOG)
    cmd(["vl.Autosave.Minutes 0.1"], wait=0.2)
    auto = wait_log(r"save: Autosave written", since, 25)
    cmd(["vl.Autosave.Minutes 3"], wait=0.2)
    check("the autosave writes VL_Auto.sav by itself (vl.Autosave.Minutes 0.1: within 6 s)", bool(auto) and os.path.exists(os.path.join(SAVES, "VL_Auto.sav")), auto[-1][:110] if auto else "no autosave")
    since2 = os.path.getsize(LOG)
    time.sleep(8.0)
    check("... and not again before its time (3 minutes by default)", not log_tail(r"save: Autosave written", since2))

    # a save from a newer version; a save whose map is gone; a save with a building whose mesh is gone; no save at all
    cmd(["vl.Save.TestVersion 99", "vl.Save 4", "vl.Save.TestVersion 0", "vl.Save 3", "vl.Save 5"], wait=1.5)
    p3, p5 = os.path.join(SAVES, "VL_Slot3.sav"), os.path.join(SAVES, "VL_Slot5.sav")
    raw = open(p3, "rb").read()
    mapname = a["mappath"].rsplit("/", 1)[-1].encode()
    check("(the test's own: the save names its map)", raw.count(mapname) >= 1)
    open(p3, "wb").write(raw.replace(mapname, mapname[:-2] + b"Zz"))
    raw = open(p5, "rb").read()
    barracks = raw.count(b"SM_BarracksYard")
    check("(the test's own: the save names the barracks' mesh)", barracks >= 1, "%d of them" % barracks)
    open(p5, "wb").write(raw.replace(b"SM_BarracksYard", b"SM_BarracksYarZ"))
    with open(os.path.join(SAVES, "VL_Slot2.sav"), "wb") as f:
        f.write(b"this is no saved game at all, only some bytes in its place" * 8)
    listing = cmd("vl.Saves", r"saves: ", 1.2)
    by = {re.match(r"saves: (\S+ ?\d?)", l).group(1).strip(): l for l in listing if re.match(r"saves: (Slot \d|Quicksave|Autosave)", l)}
    check("vl.Saves lists the seven slots", len(by) == 7, sorted(by))
    check("... Slot 1 can be loaded", "can be loaded" in by.get("Slot 1", ""), by.get("Slot 1", "")[7:])
    check("... Slot 2 (no save file at all) cannot be read", "cannot be read" in by.get("Slot 2", ""), by.get("Slot 2", "")[7:])
    check("... Slot 3 (its map is gone) says so", "is not in this game" in by.get("Slot 3", ""), by.get("Slot 3", "")[7:])
    check("... Slot 4 (version 99) is from a newer version", "newer version" in by.get("Slot 4", ""), by.get("Slot 4", "")[7:])
    before, _ = dump("refuse0")
    for slot, why in (("2", "cannot be read"), ("3", "not in this game"), ("4", "newer version")):
        l = cmd("vl.Load " + slot, r"load: ", 1.0)
        check("vl.Load %s is refused with the reason, and the match carries on" % slot, any("not loaded" in x and why in x for x in l), l[-1] if l else "no answer")
    after, _ = dump("refuse1")
    check("... the match is the one that was on (its clock runs on, nothing reloaded)", after["clock"] > before["clock"] and len(after["units"]) == len(before["units"]), "clock %.1f -> %.1f" % (before["clock"], after["clock"]))
    done, lines = load("5")
    ok = bool(done) and "put back" in done[-1]
    check("vl.Load 5 (barracks whose mesh is gone): loaded without them, and it says so", ok and "(%d left out)" % barracks in done[-1] and any("could not be put back" in l for l in lines), (done or lines or ["nothing"])[-1][:200])
    x, _ = dump("missing")
    check("... the rest of that save is there", len(x["buildings"]) == len(after["buildings"]) - barracks and len(x["units"]) >= len(after["units"]) - 1, "%d buildings, %d units" % (len(x["buildings"]), len(x["units"])))
    cmd(["vl.Load.Pause 0", "pause"], wait=0.6)
    alerts = cmd("vl.Saves", r"saves: in ", 0.8)
    check("... and that match knows it came from a save", any("was loaded from a save" in l for l in alerts), alerts[-1][-90:] if alerts else "")

    # Continue: the title screen (the map opened with no match), a click on its Continue button
    newest, _ = dump("newest", ["vl.Save 1"], 1.0)      # (in the same frame as the save)
    since = os.path.getsize(LOG)
    pie.run(["open " + a["mappath"]])
    time.sleep(12.0)
    b_ = wait_for("the title screen", lambda: (lambda x: x if 300 in x and 302 in x else None)(buttons()), 40, 2.0)
    check("the title screen has Continue, New Game and Load Game", bool(b_) and all(i in b_ for i in (300, 301, 302, 303, 304, 305)), sorted(b_ or []))
    shot("save_title")
    if SHOTS:
        click(302)
        shot("save_title_load")
        cmd("vl.Menu main", wait=0.5)
    since = os.path.getsize(LOG)
    pie.run(["vl.Load.Pause 1"])
    click(300, 0.5)
    done = wait_log(r"load: the save of .* put back", since, 150)
    said = log_tail(r"hud: Continue: ", since)
    time.sleep(1.0)
    if check("Continue loads the game saved last (Slot 1)", bool(done) and bool(said) and "Slot 1" in said[-1], (said or ["no click"])[-1]):
        z, _ = dump("continued")
        check("... as it was saved", near(z["clock"], newest["clock"], 0.11) and len(z["units"]) == len(newest["units"]) and len(z["buildings"]) == len(newest["buildings"]),
              "clock %.1f / %.1f, %d units, %d buildings" % (z["clock"], newest["clock"], len(z["units"]), len(z["buildings"])))
    cmd(["vl.Load.Pause 0", "pause", "vl.Autosave.Minutes 3"], wait=0.6)
    for f in ("VL_Slot2.sav", "VL_Slot3.sav", "VL_Slot4.sav", "VL_Slot5.sav"):
        if os.path.exists(os.path.join(SAVES, f)):
            os.remove(os.path.join(SAVES, f))       # (the test's broken saves are not left in the player's slots)


if __name__ == "__main__":
    try:
        main()
    finally:
        if "keep" not in ARGS:
            print(pie.mcp("StopPIE")[:80])
    print("\n%s (%s): %s" % ("save test", MAP, "all passed" if not fails else "%d FAILED: %s" % (len(fails), "; ".join(fails))))
    sys.exit(1 if fails else 0)
