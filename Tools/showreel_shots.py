"""The showreel's shots (Tools/showreel.py rec <name>): camera keys in plan metres, the staging commands, the length.

Each shot: map (the game must already be on it: see `setup`), `pre` commands (staging, given `settle` seconds before
the recording starts), `frames`, and either `cam` (pos / look / fov keys, eased) or `follow` (vl.Orbit keys on the
hero's own camera: yaw, pitch, distance), plus `at` (frame, command) for things that happen during the shot.
"""
import math
import showreel as R

FPS = 30


def U(x, y, z=None):
    """plan metres -> Unreal cm string 'X Y [Z]'."""
    return ("%.0f %.0f" % (x * 100, -y * 100)) + ("" if z is None else " %.0f" % (z * 100))


SHOTS = {}


def shot(name, **kw):
    SHOTS[name] = kw


# ---------------------------------------------------------------- Realm v3
# 01 the opening: from far out over the sea, a long push in and down to the player's plateau (south-east)
shot("01_island_push", map="realmv3", frames=150, easing="inout", k=1.6,
     cam=dict(pos=[(-40, -700, 330), (70, -430, 170), (165, -262, 48)],
              look=[(10, 20, 0), (70, -110, 6), (128, -150, 16)],
              fov=[46, 52, 62]))


# 03 parallax: a slow sideways glide a hand over the flowers south of the player's castle, the castle and its flag behind
shot("03_parallax_castle", map="realmv3", frames=135, easing="inout", k=1.4,
     cam=dict(pos=[(162, -187, 14.55), (149, -186, 14.8), (136, -184, 15.2)],
              look=[(134, -150, 19.0), (130, -150, 19.2), (124, -150, 19.4)],
              fov=[48, 48, 46]))

# 04 FPV: down the player's ramp, through the pass and out over the basin, fast and low (the drone's own heading)
shot("04_fpv_pass", map="realmv3", frames=150, easing="inout", k=3.0,
     cam=dict(pos=[(72, -118, 22), (75, -80, 17), (74, -40, 11), (68, -10, 6.8), (58, 7, 6.2), (46, 17, 6.8), (28, 14, 9), (6, 6, 13)],
              ahead=(0.06, 1.5), fov=[84, 86, 88, 90, 90, 88, 84, 80]))

# 05 King David runs from his castle to the ramp's head; the hero camera swings round him, low
shot("05_king_run", map="realmv3", frames=150, easing="inout", k=2.0,
     pre=["vl.Mode hero", "vl.View follow", "vl.CamLag 0", "vl.Teleport 12400 12800 1600 -128", "vl.Walk 8000 7600 run"],
     settle=1.0,
     follow=[(85.0, -3.0, 300.0), (150.0, -5.0, 360.0), (220.0, -8.0, 460.0)])


# 06 the troop ship, 21 troops aboard, sails up the east coast to the player's port; the camera skims the water
#    beside it, the plateau's sea cliff behind. Its course (fixed time step: the same every time) was logged in a dry
#    run (`vl.Ship #1 state` every 10 frames): SHIP_PATH, Unreal cm, one sample per 10 frames.
SHIP_PATH = [(27200.00, 21500.00), (27195.27, 21484.83), (27181.94, 21442.09), (27160.00, 21371.76), (27129.46, 21273.86),
             (27090.32, 21148.37), (27042.58, 20995.31), (26986.24, 20814.67), (26921.30, 20606.46), (26847.75, 20370.66),
             (26765.60, 20107.29), (26676.75, 19822.42), (26587.42, 19536.03), (26498.09, 19249.64), (26408.76, 18963.24),
             (26319.43, 18676.85), (26230.11, 18390.46), (26140.78, 18104.07), (26051.45, 17817.68), (25962.12, 17531.28),
             (25872.79, 17244.89), (25783.46, 16958.50), (25694.14, 16672.11), (25604.81, 16385.72), (25516.40, 16102.26)]


def ship_at(i):
    f = min(i / 10.0, len(SHIP_PATH) - 1.0001)
    k = int(f)
    u = f - k
    (x0, y0), (x1, y1) = SHIP_PATH[k], SHIP_PATH[k + 1]
    return ((x0 + (x1 - x0) * u) / 100.0, -(y0 + (y1 - y0) * u) / 100.0)


def ship_cam(i, n):
    sx, sy = ship_at(i)
    s = R.ease(i / (n - 1), "inout", 1.5)
    # offsets in plan metres: from ahead-and-seaward to abeam and a little behind, dropping towards the water
    ox, oy, oz = 50 - 8 * s, 44 - 52 * s, -2.0 - 1.8 * s
    return (sx + ox, sy + oy, oz), (sx - 1, sy + 3, 1.0), 46 - 4 * s


shot("06_troop_ship", map="realmv3", frames=240, settle=4.0,
     pre=["vl.Ship #1 moor 27200 21500 -107"],
     at=[(0, "vl.Ship #1 sail 25200 15000")],
     cam_fn=ship_cam)


# ---- the battle in the basin (a fresh match each: `vl.Restart 0`, then the armies spawned; the player's charge west)
ARMIES = ["vl.SpawnTeam Swordsman 0 2600 200 30", "vl.SpawnTeam Archer 0 4200 400 20",
          "vl.SpawnTeam Swordsman 1 -2000 -200 30", "vl.SpawnTeam Archer 1 -3600 -400 20",
          "vl.Teleport 1900 200 600 180", "vl.Draw 1"]
CHARGE = ["vl.SelectUnits troops", "vl.Formation smart", "vl.AttackMove selection -3400 -300 run"]

# 07 the clash, side on and long-lensed: a dolly along the south edge of the basin as the lines meet
shot("07_battle_line", map="realmv3", frames=240, restart=True, settle=1.5,
     pre=ARMIES, at=[(0, c) for c in CHARGE] + [(0, "vl.Walk -3000 -200 run")],
     cam=dict(pos=[(24, -19, 10.5), (9, -20, 9.5), (-6, -19, 9.0)],
              look=[(14, 0, 4.5), (2, 0, 4.5), (-8, 0, 4.5)], fov=[42, 40, 38]))

# 08 King David leads the charge: his own camera low in front of him, the troops behind, then swinging round
shot("08_king_charge", map="realmv3", frames=180, restart=True, settle=1.0,
     pre=ARMIES + ["vl.Mode hero", "vl.View follow", "vl.CamLag 0"],
     at=[(0, c) for c in CHARGE] + [(0, "vl.Walk -3000 -200 run")] + [(f, "vl.Attack") for f in (100, 122, 144, 166)],
     follow=[(10.0, -4.0, 420.0), (35.0, -6.0, 460.0), (80.0, -10.0, 560.0)])

# 09 the archers' volley: behind the player's archers, low, as they loose over the swordsmen's heads
shot("09_archer_volley", map="realmv3", frames=180, restart=True, settle=1.0,
     pre=["vl.SpawnTeam Swordsman 0 800 200 25", "vl.SpawnTeam Archer 0 2000 600 20",
          "vl.SpawnTeam Swordsman 1 -3000 -400 30", "vl.SpawnTeam Archer 1 -4200 -600 15"],
     at=[(0, "vl.SelectUnits swordsmen"), (0, "vl.AttackMove selection -3400 -300 run"), (0, "vl.Hold archers")],
     cam=dict(pos=[(28, -11, 6.5), (25.5, -9.5, 7.2)], look=[(4, 0, 6.0), (-8, 0, 7.0)], fov=[46, 40]))

# 10 the fog of war: from the player's plateau, the enemy's side under the mist, only the tallest things showing
shot("10_fog_towers", map="realmv3", frames=150, settle=4.0, easing="inout", k=1.5,
     pre=["vl.Fog 1", "vl.Fog.Reveal 0"],
     at=[(149, "vl.Fog 0")],
     cam=dict(pos=[(70, -70, 46), (52, -52, 42)], look=[(-120, 120, 14), (-120, 120, 12)], fov=[34, 32]))

# 12 FPV low over the northern forest's canopy, banking up over the ridge to the basin
shot("12_canopy_fly", map="realmv3", frames=150, easing="inout", k=3.0,
     cam=dict(pos=[(175, 175, 27), (130, 140, 25), (90, 105, 26), (55, 70, 34), (25, 38, 40)],
              ahead=(0.08, 4.0), fov=[80, 84, 86, 84, 78]))


# 11 a building razed: the enemy's first farm (built by its commander a minute or so into a fresh match: a building
#    placed in play sinks when it falls; the level's own towers only vanish), the player's swordsmen at it
def raze_setup():
    import os, re, time
    R.send(["vl.Restart 0"])
    time.sleep(20)
    R.send(["ShowHUD", "vl.Fog 0", "vl.Music 0"])
    log = os.path.join(R.SAVED, "Logs", "SovereignRealms.log")
    n0 = os.path.getsize(log)
    end = time.time() + 240
    while time.time() < end:
        with open(log, "rb") as f:
            f.seek(n0)
            txt = f.read().decode("utf-8", "replace")
        m = re.search(r"BUILD Farm of team 1 finished at ([-\d.]+) ([-\d.]+)", txt)
        if m:
            return float(m.group(1)) / 100.0, -float(m.group(2)) / 100.0
        time.sleep(2)
    raise SystemExit("the enemy built no farm")


def raze(name):
    fx, fy = raze_setup()
    # a slow arc round it
    # (from the side away from the enemy's castle, which would stand in front of it)
    cx, cy = -130.0, 148.0
    d = math.hypot(fx - cx, fy - cy)
    ux, uy = (fx - cx) / d, (fy - cy) / d
    px, py = -uy, ux
    pos = [(fx + ux * 34 + px * 10, fy + uy * 34 + py * 10, 23), (fx + ux * 30 - px * 2, fy + uy * 30 - py * 2, 21)]
    look = [(fx, fy, 17), (fx, fy, 16)]
    SHOTS[name]["cam"] = dict(pos=pos, look=look, fov=[50, 50])
    SHOTS[name]["pre"] = ["vl.Spawn Swordsman %s 10" % U(fx + ux * 14, fy + uy * 14)]
    print("farm at", fx, fy)


shot("11_raze_farm", map="realmv3", frames=150, settle=1.5, setup=raze,
     at=[(0, "vl.AttackAt troops Farm enemy"), (45, "vl.Damage Farm enemy 3000")])


# 13 the closing shot: King David before his castle, sword drawn, the camera rising and drawing back to the flag
shot("13_king_castle", map="realmv3", frames=180, restart=True, settle=3.0, easing="inout", k=1.3,
     pre=["vl.Mode hero", "vl.Order troops 15800 12000", "vl.Teleport 12400 13200 1600 -90", "vl.Orbit -90 -10 400", "vl.Draw 1"],
     cam=dict(pos=[(122.6, -128.6, 15.2), (123.2, -124.5, 16.4), (124.5, -117.0, 19.0)],
              look=[(124.0, -132.2, 15.2), (125.0, -136.0, 16.0), (127.0, -142.0, 17.6)], fov=[40, 46, 52]))


def orbit_keys(cx, cy, cz, r, z, a0, a1, n=6, tz=None, r1=None, z1=None):
    pos, look = [], []
    for i in range(n):
        s = i / (n - 1)
        a = math.radians(a0 + (a1 - a0) * s)
        rr = r + ((r1 if r1 is not None else r) - r) * s
        zz = z + ((z1 if z1 is not None else z) - z) * s
        pos.append((cx + rr * math.cos(a), cy + rr * math.sin(a), zz))
        look.append((cx, cy, tz if tz is not None else cz))
    return pos, look


# 02 Realm v2's colossal mountain (184 m): a slow orbit from the south-west, rising, the eleven peaks turning
_p, _l = orbit_keys(28, 146, 105, 300, 105, -140, -96, n=5, tz=110, r1=270, z1=150)
shot("02_mountain_orbit", map="realmv2", frames=165, easing="inout", k=1.5,
     cam=dict(pos=_p, look=[(28, 146, 100), (28, 146, 110), (28, 146, 118), (28, 146, 124), (28, 146, 128)], fov=[54, 54, 52, 50, 48]))

def run(name):
    s = SHOTS[name]
    if "setup" in s:
        s["setup"](name)
    frames = s["frames"]
    at = list(s.get("at", []))
    first = list(s.get("pre", []))
    if "cam" in s:
        views = R.path_cmds(s["cam"], frames, s.get("easing", "inout"), s.get("k", 2.0))
        first.append(views[0])
        at += [(i, v) for i, v in enumerate(views)]
    if "cam_fn" in s:
        views = []
        for i in range(frames):
            c, t, fov = s["cam_fn"](i, frames)
            views.append(R.view_cmd(c, t, fov))
        first.append(views[0])
        at += [(i, v) for i, v in enumerate(views)]
    if "follow" in s:
        f = s["follow"]
        for i in range(frames):
            u = R.ease(i / max(frames - 1, 1), s.get("easing", "inout"), s.get("k", 2.0))
            yaw, pitch, dist = R.spline(f, u)
            cmd = "vl.Orbit %.2f %.2f %.1f" % (yaw, pitch, dist)
            if i == 0:
                first.append(cmd)
            at.append((i, cmd))
    if s.get("restart"):
        R.send(["vl.Restart 0"])
        import time
        time.sleep(22)
        R.send(["ShowHUD", "vl.Fog 0", "vl.Music 0"])
        time.sleep(2)
    R.record(name, frames, at, FPS, s.get("settle", 4.0), first)
