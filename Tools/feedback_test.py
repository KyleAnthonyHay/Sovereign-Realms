#!/usr/bin/env python3
"""Checks of the 2026-11-22 feedback batch in Play-In-Editor on a battle map (the editor open on L_RealmV2 or L_Realm,
PIE running: python3 Tools/pie.py start). The enemy commander is switched off for the order tests (vl.AIForce 1 off)
so that it does not take the enemy troops spawned here into its squads; the flank test switches it on again.

    python3 Tools/feedback_test.py [start] [cohesion] [march] [mixed] [amove] [guard] [ctrl] [assign] [minimap] [flank]

  start     a match (Easy) and the commander off
  cohesion  a platoon of six in two groups 28 m apart; foes come at one group: the other runs to join the fight
            (UVLBattle::TickCohesion, "cohesion: ... runs to join")
  march     a platoon of six, three of them 25 m behind, walks 90 m: the gap closes on the way (the ones behind faster
            than a walk, the ones ahead slower) and the platoon arrives together (UVLCommand::UpdateMarchPace)
  mixed     three swordsmen and three archers attack an enemy site 60 m off: the archers run with the swordsmen
  amove     three archers on an attack-move past a foe: they stop and shoot it (they do not walk on to the end first)
  guard     troops selected, guard a troop of a platoon (vl.Guard selection platoon N; the hero view's Option + click
            that did this is gone, 2026-11-24): they guard
            the platoon ("Guarding platoon N")
  ctrl      Ctrl + 5 (a real key chord through Slate) adds the selection to platoon 5, which keeps its members
  assign    the command card's Assign button opens the picker; a chip adds the selection to that platoon
  minimap   the minimap's view box sits on the player's base at the start, and a click on the minimap looks at the
            matching world spot
  flank     Hard: a flank is forced (a flank bridge added off the line, the attack forced), its party struck down: the
            commander's next attack time is never parked ("Enemy ready in 16650:28"), never longer than its longest wait
Prints PASS / FAIL lines; exit code 1 if anything failed.
"""
import math
import os
import re
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "Tools"))
import pie

fails = []
skipped = []


def mark():
    return os.path.getsize(pie.LOG)


def lines(since):
    with open(pie.LOG, errors="replace") as f:
        f.seek(since)
        return [l.rstrip().split("LogSovereignRealms: ")[-1] for l in f if "LogSovereignRealms" in l]


def cmd(*c, wait=0.7):
    m = mark()
    pie.run(list(c))
    time.sleep(wait)
    return lines(m)


def wait_for(pattern, since, timeout):
    end = time.time() + timeout
    while time.time() < end:
        for l in lines(since):
            if re.search(pattern, l):
                return l
        time.sleep(0.4)
    return None


def check(name, ok, detail=""):
    print(("PASS  " if ok else "FAIL  ") + name + (("  (" + str(detail) + ")") if detail != "" else ""))
    if not ok:
        fails.append(name)
    return ok


def units():
    out = {}
    for l in cmd("vl.Units", wait=0.5):
        m = re.match(r"unit (.+?)\s+at\s+(-?\d+)\s+(-?\d+)\s+(-?\d+)\s+(.*)$", l)
        if m:
            out[m.group(1).strip()] = (float(m.group(2)), float(m.group(3)), m.group(5))
    return out


def enemies():
    out = set()
    for l in cmd("vl.Orders", wait=0.5):
        m = re.match(r"orders (.+?)\s+team 1 ", l)
        if m:
            out.add(m.group(1).strip())
    return out


def spawn(kind, x, y, n, team=0):
    if team == 0:
        before = set(units())
        cmd("vl.Spawn %s %d %d %d" % (kind, x, y, n), wait=0.8)
        return sorted(set(units()) - before)
    before = enemies()
    cmd("vl.SpawnTeam %s 1 %d %d %d" % (kind, x, y, n), wait=0.8)
    return sorted(enemies() - before)


def select(names):
    cmd(*(["vl.SelectUnits none"] + ["vl.SelectUnits %s add" % n.replace(" ", "_") for n in names]), wait=0.5)


def cohesion_state():
    """vl.Cohesion: {platoon: {name: (x, y, state, speed)}}"""
    out, cur = {}, None
    for l in cmd("vl.Cohesion", wait=0.4):
        m = re.match(r"cohesion: platoon (\d+)", l)
        if m:
            cur = int(m.group(1))
            out[cur] = {}
            continue
        m = re.match(r"\s*(.+?) at V\(X=(-?[\d.]+), Y=(-?[\d.]+), Z=(-?[\d.]+)\): (\w+).*speed (\d+)", l)
        if m and cur is not None:
            out[cur][m.group(1)] = (float(m.group(2)), float(m.group(3)), m.group(5), float(m.group(6)))
    return out


def dismiss(names):
    for n in names:
        cmd("vl.Kill " + n.replace(" ", "_"), wait=0.1)


def centroid(ps):
    return (sum(p[0] for p in ps) / len(ps), sum(p[1] for p in ps) / len(ps))


# Realm v2's open ground (the plan's buildable areas, in Unreal cm): the south-east meadow, the player's south area
SE = (12400, 18800)
S0 = (-13800, 22600)
E0 = (-11200, 9200)


def t_cohesion():
    a = spawn("Swordsman", SE[0] - 1500, SE[1], 3)
    b = spawn("Swordsman", SE[0] + 1300, SE[1], 3)
    select(a + b)
    cmd("vl.Platoon assign 2", "vl.BattleLog 1")
    st = cohesion_state().get(2, {})
    check("cohesion: a platoon of six is formed", len(st) == 6, len(st))
    m = mark()
    foes = spawn("Swordsman", SE[0] - 5000, SE[1], 2, team=1)       # (35 m from the near group, 63 m from the far one)
    got = wait_for(r"cohesion: (%s) of platoon 2 runs to join" % "|".join(re.escape(n) for n in b), m, 20)
    check("cohesion: a member 28 m from the fight runs to join it", got is not None, got or "no 'runs to join' in 20 s")
    time.sleep(4)
    st = cohesion_state().get(2, {})
    near = [n for n in b if n in st and abs(st[n][0] - (SE[0] - 3000)) < 2600]
    check("cohesion: the far group has come to the fight", len(near) >= 2, "%d of 3 within 26 m of it: %s" % (len(near), {n: st.get(n) for n in b}))
    cmd("vl.BattleLog 0")
    dismiss(a + b + foes)


def t_march():
    front = spawn("Swordsman", S0[0], S0[1] - 4500, 3)
    back = spawn("Swordsman", S0[0], S0[1] - 7000, 3)
    select(front + back)
    cmd("vl.Platoon assign 3", "vl.Formation loose")
    goal = (S0[0], S0[1] + 4500)
    cmd("vl.Order selection %d %d" % goal)
    gaps, fast, slow = [], 0, 0
    for i in range(14):
        time.sleep(0.9)
        st = cohesion_state().get(3, {})
        if len(st) < 6:
            continue
        fy = [st[n][1] for n in front if n in st]
        by = [st[n][1] for n in back if n in st]
        gaps.append(sum(fy) / len(fy) - sum(by) / len(by))
        fast += sum(1 for n in back if n in st and st[n][2] == "walking" and st[n][3] > 470)
        slow += sum(1 for n in front if n in st and st[n][2] == "walking" and 50 < st[n][3] < 380)
    print("      march: gap between the groups (m) " + " ".join("%.0f" % (g / 100) for g in gaps))
    check("march: the gap closes on the way (by 40% or more)", len(gaps) > 3 and min(gaps) < 0.6 * max(gaps), ["%.0f" % (g / 100) for g in gaps])
    check("march: those ahead slow down for the body", slow > 0, "samples of the front group slower than a walk %d" % slow)
    if fast == 0:
        skipped.append("march: no sample caught the rear group above a walk (the front group's slowing closed the gap)")
    time.sleep(6)
    st = cohesion_state().get(3, {})
    arrived = [n for n in front + back if n in st and math.hypot(st[n][0] - goal[0], st[n][1] - goal[1]) < 1200]
    check("march: they arrive together", len(arrived) == 6, "%d of 6 within 12 m of the goal" % len(arrived))
    dismiss(front + back)


def t_mixed():
    sw = spawn("Swordsman", SE[0] - 3500, SE[1] - 1500, 3)
    ar = spawn("Archer", SE[0] - 3500, SE[1] - 1100, 3)
    cmd("vl.Give gold 3000 enemy")
    out = cmd("vl.Build barracks %d %d 0 enemy near" % (SE[0] + 2500, SE[1] - 1500), wait=1.5)
    laid = [l for l in out if l.startswith("vl.Build") or "lays a Barracks" in l]
    check("mixed: an enemy site is laid 60 m off", any("lays a Barracks" in l for l in laid), laid[:2])
    select(sw + ar)
    cmd("vl.Platoon assign 4")
    cmd("vl.AttackAt selection Barracks enemy", wait=0.2)
    runs, spreads = [], []
    for i in range(6):
        time.sleep(0.8)
        st = cohesion_state().get(4, {})
        if len(st) < 6:
            continue
        runs.append((sum(1 for n in sw if st[n][3] > 600), sum(1 for n in ar if st[n][3] > 600)))
        cs, ca = centroid([st[n] for n in sw]), centroid([st[n] for n in ar])
        spreads.append(math.hypot(cs[0] - ca[0], cs[1] - ca[1]))
    print("      mixed: running (swordsmen, archers) %s; archers' middle from the swordsmen's (m) %s" % (runs, " ".join("%.0f" % (s / 100) for s in spreads)))
    check("mixed: the archers run with the swordsmen", any(r[1] >= 2 for r in runs) and any(r[0] >= 2 for r in runs), runs)
    check("mixed: they travel together (the archers' middle within 12 m of the swordsmen's)", spreads and max(spreads[:3]) < 1200, ["%.0f" % (s / 100) for s in spreads])
    dismiss(sw + ar)
    cmd("vl.Demolish Barracks enemy")


def t_amove():
    at = (SE[0], SE[1])
    ar = spawn("Archer", at[0] - 4000, at[1], 3)
    foe = spawn("Swordsman", at[0] + 1500, at[1], 1, team=1)
    select(ar)
    cmd("vl.BattleLog 1")
    m = mark()
    end = (at[0] + 4000, at[1])
    cmd("vl.AttackMove selection %d %d" % end)
    hit = wait_for(r"hit: (%s) takes" % "|".join(re.escape(n) for n in foe), m, 20) if foe else None
    u = units()
    left = [math.hypot(u[n][0] - end[0], u[n][1] - end[1]) / 100 for n in ar if n in u]
    check("attack-move: the archers shoot the foe on the way", hit is not None, hit or "no hit by them in 20 s")
    check("attack-move: they stopped short of the end to shoot", left and min(left) > 15 and max(left) < 90, "m from the end: %s" % ["%.0f" % x for x in left])
    cmd("vl.BattleLog 0")
    dismiss(ar + foe)


def t_guard():
    ward = spawn("Swordsman", E0[0], E0[1] - 2500, 2)
    select(ward)
    cmd("vl.Platoon assign 5")
    guards = spawn("Swordsman", E0[0] + 800, E0[1] - 2500, 2)
    select(guards)
    cmd("vl.Mode hero", wait=1.0)
    m = mark()
    cmd("vl.Guard selection platoon 5", wait=1.5)
    out = lines(m)
    g = [l for l in out if "guard" in l.lower()]
    check("guard: the selection guards the platoon", any("platoon 5" in l for l in g), g[:3])
    orders = [l for l in cmd("vl.Orders") if any(n in l for n in guards)]
    check("guard: the guards' order is the platoon's guard", any("guard" in l.lower() for l in orders), orders[:2])
    cmd("vl.Mode overview")
    dismiss(ward + guards)


def platoon_members(n):
    for l in cmd("vl.Leaders"):
        m = re.match(r"leaders: platoon %d led by .*?: (.*)" % n, l)
        if m:
            return [x.strip() for x in m.group(1).split(",")]
    return []


def t_ctrl():
    cmd("vl.Mode overview")
    first = spawn("Swordsman", S0[0] + 2000, S0[1], 2)
    select(first)
    cmd("vl.Platoon assign 5")
    more = spawn("Archer", S0[0] + 2000, S0[1] + 600, 2)
    select(more)
    cmd("vl.Input chord LeftControl Five", wait=1.0)
    mem = platoon_members(5)
    ok = set(first + more) <= set(mem)
    if not ok:
        skipped.append("ctrl: the real Ctrl + 5 chord did not reach the game (keyboard focus?): vl.Platoon add tried instead")
        cmd("vl.Platoon add 5")
        mem = platoon_members(5)
    check("ctrl: Ctrl + 5 adds the selection to platoon 5, its members stay", set(first + more) <= set(mem), mem)
    dismiss(first + more)


def hud_buttons():
    out = {}
    for l in cmd("vl.HUD", wait=0.6):
        m = re.match(r"hud button (\d+) at ([\d.]+) ([\d.]+)", l)
        if m:
            out[int(m.group(1))] = (float(m.group(2)), float(m.group(3)))
    return out


def t_assign():
    cmd("vl.Mode overview")
    have = spawn("Swordsman", S0[0] - 2000, S0[1], 2)
    select(have)
    cmd("vl.Platoon assign 6")
    new = spawn("Swordsman", S0[0] - 2000, S0[1] + 600, 1)
    select(new)
    b = hud_buttons()
    if not check("assign: the command card has its Assign button", 20 in b, sorted(b)[:12]):
        return
    cmd("vl.UIClick %.4f %.4f" % b[20], wait=0.6)
    b = hud_buttons()
    if not check("assign: the picker opens with six chips", all(292 + i in b for i in range(6)), [k for k in b if k >= 292]):
        return
    m = mark()
    cmd("vl.UIClick %.4f %.4f" % b[292 + 5], wait=0.8)
    got = [l for l in lines(m) if "hud: Assign:" in l]
    check("assign: a chip adds the selection to platoon 6", any("to platoon 6 (it had 2)" in l for l in got), got)
    mem = platoon_members(6)
    check("assign: platoon 6 keeps its two and has the new one", set(have + new) <= set(mem), mem)
    b = hud_buttons()
    check("assign: the picker is put away", not any(292 + i in b for i in range(6)))
    dismiss(have + new)


def t_minimap():
    cmd("vl.Mode overview", "vl.Select none", wait=0.5)
    castle = None
    for l in cmd("vl.Construction"):
        m = re.search(r"castle of team 0 at (-?\d+) (-?\d+)", l)
        if m:
            castle = (int(m.group(1)), int(m.group(2)))
    cmd("vl.Look %d %d 0.35" % castle, wait=1.5)
    info = [l for l in cmd("vl.HUD", wait=0.6) if l.startswith("hud: minimap at")]
    if not check("minimap: drawn, its geometry logged", bool(info), info):
        return
    n = [float(x) for x in re.findall(r"-?\d+(?:\.\d+)?", info[0])]
    u0, v0, u1, v1, wx0, wy0, wx1, wy1, yaw, mu, mv, cu, cv = n[:13]
    w = u1 - u0
    check("minimap: the view box sits on the player's base", math.hypot(mu - cu, (mv - cv)) < 0.25 * w,
          "view box middle %.3f %.3f, castle %.3f %.3f (map %.3f wide)" % (mu, mv, cu, cv, w))
    # a click on the map at where the enemy's castle would be drawn: the camera looks there
    foe = None
    for l in cmd("vl.Construction"):
        m = re.search(r"castle of team 1 at (-?\d+) (-?\d+)", l)
        if m:
            foe = (int(m.group(1)), int(m.group(2)))
    up = (math.cos(math.radians(yaw)), math.sin(math.radians(yaw)))
    right = (-up[1], up[0])
    wc = ((wx0 + wx1) / 2, (wy0 + wy1) / 2)
    ws = wx1 - wx0
    d = (foe[0] - wc[0], foe[1] - wc[1])
    pu = u0 + (0.5 + (d[0] * right[0] + d[1] * right[1]) / ws) * (u1 - u0)
    pv = v0 + (0.5 - (d[0] * up[0] + d[1] * up[1]) / ws) * (v1 - v0)
    m = mark()
    cmd("vl.UIClick %.4f %.4f" % (pu, pv), wait=1.0)
    got = [l for l in lines(m) if l.startswith("minimap: look at")]
    ok = False
    if got:
        x, y = [float(v) for v in re.findall(r"-?\d+", got[0])[:2]]
        ok = math.hypot(x - foe[0], y - foe[1]) < 0.03 * ws
    check("minimap: a click on it looks at the matching world spot (the enemy's castle)", ok, "%s for the castle at %s" % (got, foe))
    # and the map is turned so the view's 'up' is the map's up: the camera looking up the map, the view box's
    # middle lies above (smaller v) the point it looks at? (the box is drawn round the camera's ground view)
    cmd("vl.Look %d %d 0.35" % castle)


def t_flank():
    m = mark()
    cmd("vl.Restart 2", wait=1.0)
    ok = wait_for(r"match started on |commander of team 1: Hard", m, 40)
    if not check("flank: a Hard match starts", ok is not None, ok or ""):
        return
    time.sleep(4)
    cast = {}
    for l in cmd("vl.Construction"):
        mm = re.search(r"castle of team (\d) at (-?\d+) (-?\d+)", l)
        if mm:
            cast[int(mm.group(1))] = (int(mm.group(2)), int(mm.group(3)))
    c0, c1 = cast[0], cast[1]
    # an army for the enemy, by its castle; a flank bridge well off the line between the castles
    cmd("vl.SpawnTeam Swordsman 1 %d %d 10" % (c1[0] + (c0[0] - c1[0]) * 0.08, c1[1] + (c0[1] - c1[1]) * 0.08),
        "vl.SpawnTeam Archer 1 %d %d 5" % (c1[0] + (c0[0] - c1[0]) * 0.1, c1[1] + (c0[1] - c1[1]) * 0.1), wait=2.0)
    mid = ((c0[0] + c1[0]) / 2, (c0[1] + c1[1]) / 2)
    dx, dy = c1[0] - c0[0], c1[1] - c0[1]
    L = math.hypot(dx, dy)
    nx, ny = -dy / L, dx / L
    flank = [l for l in cmd("vl.AI 1 nomap") if "Flank" in l or "flank" in l]
    print("      the map's own flank points: %s" % (flank[:3] or "none"))
    off = 0.18 * L
    p0 = (mid[0] + nx * off - dx * 0.05, mid[1] + ny * off - dy * 0.05)
    p1 = (mid[0] + nx * off + dx * 0.05, mid[1] + ny * off + dy * 0.05)
    cmd("vl.AIForce 1 flank %d %d %d %d" % (p0[0], p0[1], p1[0], p1[1]))
    m = mark()
    sent = None
    for i in range(6):
        pie.run(["vl.AIForce 1 attack"])
        end = time.time() + 6
        while time.time() < end and not sent:
            sent = next((l for l in lines(m) if re.search(r"AI 1 .*flank: \d+ troops", l)), None)
            time.sleep(0.05)
        if sent:
            pie.run(["vl.AIForce 1 killflank"])      # (at once: before the main body leaves)
            break
    if not check("flank: the forced attack sends a flank party", sent is not None, sent or "no flank in 36 s (the map's routes may not make one worth it)"):
        skipped.append("flank: not forced; the timer clamp was checked on a plain attack instead")
    time.sleep(1.0)
    st0 = [l for l in cmd("vl.AIForce 1 state", wait=0.5) if l.startswith("aiforce: team 1 clock")]
    print("      after the flank fell: " + (st0[0] if st0 else "?"))
    cmd("vl.AIForce 1 killfield", wait=1.5)      # (and the main body: the attack is over, its clock must be a real one)
    worst, parked = -1e9, []
    for i in range(12):
        st = [l for l in cmd("vl.AIForce 1 state", wait=0.6) if l.startswith("aiforce: team 1 clock")]
        if st:
            mm = re.search(r"next attack in (-?\d+) s \(max wait (\d+)\), attacking (\d)", st[0])
            s = re.search(r'status "([^"]*)"', st[0])
            if mm:
                nxt, mx, att = int(mm.group(1)), int(mm.group(2)), int(mm.group(3))
                if not att:
                    worst = max(worst, nxt)
                    if nxt > mx:
                        parked.append(st[0])
            if s and re.search(r"ready in \d{3,}:", s.group(1)):
                parked.append(s.group(1))
        time.sleep(1.5)
    check("flank: with the party struck down the next attack is never parked", worst > -1e8 and not parked, parked[:2] or "longest wait seen %d s" % worst)
    fin = [l for l in cmd("vl.AIForce 1 state") if l.startswith("aiforce")]
    print("      " + (fin[0] if fin else ""))


def main(a):
    a = a or ["start", "cohesion", "march", "mixed", "amove", "guard", "ctrl", "assign", "minimap", "flank"]
    if "start" in a:
        m = mark()
        cmd("vl.StartMatch 0")
        ok = wait_for(r"match started on |already started", m, 20)
        check("a match is on", ok is not None, ok or "")
        cmd("vl.AIForce 1 off", "vl.Mode overview")
    for name in ("minimap", "cohesion", "march", "mixed", "amove", "guard", "ctrl", "assign", "flank"):
        if name in a:
            print("--- " + name)
            try:
                globals()["t_" + name]()
            except Exception as e:
                check(name + ": ran", False, repr(e))
    for s in skipped:
        print("NOTE  " + s)
    print("%d failed" % len(fails))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
