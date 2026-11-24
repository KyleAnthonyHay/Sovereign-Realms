"""The second and third showreels' shots (Tools/showreel.py rec2 <name>): "b_*" the battle reel, "k_*" the kingdom
(golden hour) reel. The same scheme as Tools/showreel_shots.py: camera keys in plan metres (+X east, +Y north, +Z up),
the staging commands, the length; plus:

  reel      battle | kingdom: frames go to Saved/Showreel/reel2_battle|reel3_kingdom/frames/<shot>
  fresh     "match" (vl.Restart 0) or "test" (vl.Restart 0 then vl.TestWorld 0: every building at its most, 120 troops
            a side, the castles at level 7 with an archer on each corner) before the shot; None: as the game is
  step      steps a second of game time (30: real time; 60: half speed when played at 30)
  shake     in cam: (metres, degrees, hz) of a hand-held wander
  ship      a function of the frame (deterministic course) for the camera

Every shot is recorded with the HUD hidden, no fog of war, no music, no white hit flash (vl.Opt.HitFlash 0) and no gold see-through outline (vl.Opt.Silhouette 0: the owner does not
want it in the reels). The
kingdom reel's light: the sun low in the north-west (vl.Sun -11 35 7 4300) and no clouds (vl.Opt.Clouds 0, they stay
white); the battle reel's: the level's own midday sun.

The game: the packaged Development build (Builds/Windows/SovereignRealms-Development/SovereignRealms.exe
/Game/Maps/L_RealmV3?Match=1?Difficulty=0 -windowed -ResX=1920 -ResY=1080 -VLNoEnter), with
VL_SAVED=Builds/Windows/SovereignRealms-Development/SovereignRealms/Saved.
"""
import json
import math
import os
import time

import showreel as R

FPS = 30
REEL_DIRS = {"battle": "reel2_battle", "kingdom": "reel3_kingdom"}
STATE = os.path.join(R.OUT, "work2", "state.json")
BASE = ["vl.Fog 0", "vl.Music 0", "vl.Opt.HitFlash 0", "vl.Opt.Silhouette 0"]
LOOK = {
    "battle": ["vl.Sun reset", "vl.Opt.Clouds 1"],
    "kingdom": ["vl.Sun -11 35 7 4300", "vl.Opt.Clouds 0"],
}


def U(x, y, z=None):
    """plan metres -> Unreal cm string 'X Y [Z]'."""
    return ("%.0f %.0f" % (x * 100, -y * 100)) + ("" if z is None else " %.0f" % (z * 100))


def state():
    try:
        with open(STATE) as f:
            return json.load(f)
    except Exception:
        return {"hud": True}


def save_state(s):
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    with open(STATE, "w") as f:
        json.dump(s, f)


def hud_off():
    s = state()
    if s.get("hud", True):
        R.send(["ShowHUD"])
        s["hud"] = False
        save_state(s)


def fresh(kind):
    R.send(["vl.Restart 0"])
    time.sleep(24)
    s = state()
    s["hud"] = True
    save_state(s)
    hud_off()
    R.send(BASE)
    if kind == "test":
        R.send(["vl.TestWorld 0"])
        time.sleep(10)
    time.sleep(2)


SHOTS = {}


def shot(name, **kw):
    SHOTS[name] = kw


# ================================================================ the battle in the basin (a fresh match each)
# 120 swordsmen and 50 archers a side, in blocks that do not overlap (overlapping spawns push each other through the
# floor). The player's (east, x 34-39 m) charge west on an attack-move; the enemy's (west, x -30 to -25 m) stand until
# the charge comes within their reach (about 22 m) and then run at it: the fronts meet near x -10 m some 5.5 s after
# the order. King David runs with them.
ARMY = ["vl.SpawnTeam Swordsman 0 %s 40" % U(14, y) for y in (16, 5, -6)] +        ["vl.SpawnTeam Swordsman 1 %s 40" % U(-24, y) for y in (16, 5, -6)] +        ["vl.SpawnTeam Archer 0 %s 25" % U(26, y) for y in (12, -1)] +        ["vl.SpawnTeam Archer 1 %s 25" % U(-36, y) for y in (12, -1)]
CHARGE = ["vl.SelectUnits swordsmen", "vl.Formation smart", "vl.AttackMove selection %s run" % U(-34, 0)]


def battle(extra=()):
    def setup(name):
        R.send(ARMY + ["vl.Teleport %s 600 180" % U(11, 0), "vl.Draw 1"] + list(extra))
        time.sleep(4)
    return setup


# 01 the hook: FPV just over the heads of the charge, overtaking it, into the enemy's line as it meets them
#    (dry run, Saved/Showreel/work2/dry_battle.py: the player's front at x -9 at 1.7 s, the lines meet at x -14 at
#    about 2.5 s after the order, and fight there)
shot("b_rush", reel="battle", fresh="match", setup=battle(), frames=120, settle=0.4, easing="linear",
     pre=CHARGE + ["vl.Walk %s run" % U(-30, 0)],
     cam=dict(pos=[(22, 0.8, 6.4), (13, 0.6, 6.1), (4, 0.3, 5.95), (-4, 0.0, 5.9), (-9, -0.3, 6.0)],
              look=[(-4, 0.5, 4.9), (-12, 0.3, 4.9), (-20, 0.0, 5.0), (-26, -0.3, 5.0), (-30, -0.5, 5.1)],
              fov=[74, 72, 70, 68, 66], shake=(0.06, 0.5, 0.9)))

# 04 the clash, low and long-lensed from the basin's south side, a slow dolly with the push
shot("b_clash_low", reel="battle", fresh="match", setup=battle(), frames=180, settle=0.4, easing="inout", k=1.2,
     pre=CHARGE + ["vl.Walk %s run" % U(-30, 0)],
     cam=dict(pos=[(-3, -23, 4.8), (-7, -23.5, 4.75), (-11, -24, 4.75)], look=[(-9, -6, 5.0), (-13, -6, 5.0), (-17, -6, 5.0)],
              fov=[25, 24, 23], shake=(0.03, 0.25, 0.6)))

# 05b the player's charge comes at the lens, arrows over it (taken as a King David shot: he was held in the forming
#     line; kept for what it caught). The camera backs away low before the line at 7.9 m/s.
def king_cam_at(x0, ylat=-2.4, back=6.8, stop=-12.0, seed=11, ky=0.0):
    def f(i, n):
        kx = max(x0 - 7.9 * (0.25 + i / 30.0), stop)
        d = R.shake(i, 30, (0.05, 0.6), 1.0, seed)
        return (kx - back + d[0], ylat + d[1], 4.85 + d[2]), (kx, ky + d[3] * 0.05, 5.45), 48.0
    return f


shot("b_charge_lens", reel="battle", fresh="match", setup=battle(["vl.Teleport %s 600 180" % U(7, 0)]),
     frames=100, settle=0.4, pre=["vl.Walk %s run" % U(-30, 0)],
     at=[(6, c) for c in CHARGE], cam_fn=king_cam_at(7.0))

# 05 King David charges alone ahead of his army (12 m before its line), straight at the enemy's; the camera backs
#    away low and a little to his left at his pace, the army coming on behind him
shot("b_king_charge", reel="battle", fresh="match", setup=battle(["vl.Teleport %s 600 180" % U(1, 1.5)]),
     frames=90, settle=0.4, pre=["vl.Walk %s run" % U(-30, 1.5)],
     at=[(20, c) for c in CHARGE] + [(f, "vl.Attack") for f in (58, 74)],
     cam_fn=king_cam_at(1.0, ylat=0.2, back=5.2, stop=-14.0, seed=5, ky=1.5))

# 06 among the scrum: a hand-held camera at shoulder height beside the melee, drifting along the line
shot("b_scrum", reel="battle", fresh="match", setup=battle(), frames=210, settle=0.4, easing="inout", k=1.2,
     pre=CHARGE + ["vl.Walk %s run" % U(-30, 0)],
     cam=dict(pos=[(-8, -11.5, 5.5), (-11, -11, 5.5), (-14, -10.5, 5.6)], look=[(-15, -2, 5.0), (-18, -1, 5.0), (-21, 0, 5.0)],
              fov=[48, 46, 44], shake=(0.10, 0.9, 1.1)))


# 03 Jonathan, played, by the player's archers: he draws, holds, looses into the enemy coming on (half speed)
J_AT = (20.0, -14.0)
J_AIM = U(-24, 2, 6.0)
shot("b_jonathan", reel="battle", fresh="match", step=60, frames=200, settle=1.0, easing="inout", k=1.4,
     setup=battle(["vl.Jonathan spawn", "vl.Jonathan play", "vl.Mode hero"]),
     pre=["vl.Teleport %s 520 -160" % U(*J_AT), "vl.Bow aim %s" % J_AIM] + CHARGE,
     at=[(0, "vl.Bow aim %s" % J_AIM), (6, "vl.Bow draw 1"), (100, "vl.Bow draw 0"), (130, "vl.Bow draw 1"), (196, "vl.Bow draw 0")],
     cam=dict(pos=[(23.6, -17.6, 6.0), (23.3, -17.3, 5.95), (23.0, -17.0, 5.9)],
              look=[(7.5, -5.0, 5.4), (7.5, -5.0, 5.3), (7.5, -5.0, 5.2)], fov=[38, 35, 33]))


# 03b the same in profile, low: the bow drawn full against the sky, the enemy coming on far behind his aim
shot("b_jonathan2", reel="battle", fresh="match", step=60, frames=200, settle=1.0, easing="inout", k=1.4,
     setup=battle(["vl.Jonathan spawn", "vl.Jonathan play", "vl.Mode hero"]),
     pre=["vl.Teleport %s 520 -160" % U(*J_AT), "vl.Bow aim %s" % J_AIM] + CHARGE,
     at=[(0, "vl.Bow aim %s" % J_AIM), (6, "vl.Bow draw 1"), (100, "vl.Bow draw 0"), (130, "vl.Bow draw 1"), (196, "vl.Bow draw 0")],
     cam=dict(pos=[(20.9, -17.7, 5.35), (20.6, -17.5, 5.4), (20.3, -17.3, 5.45)],
              look=[(19.0, -13.7, 5.85), (19.0, -13.7, 5.8), (19.0, -13.7, 5.75)], fov=[36, 34, 32]))


# 07 the enemy's line charges head-on into the lens at half speed (the camera low by Jonathan, looking up the basin;
#    it was meant for his profile and missed him: kept for what it caught)
shot("b_wave", reel="battle", fresh="match", step=60, frames=200, settle=1.0, easing="inout", k=1.4,
     setup=battle(["vl.Jonathan spawn", "vl.Jonathan play", "vl.Mode hero"]),
     pre=["vl.Teleport %s 520 -160" % U(*J_AT), "vl.Bow aim %s" % J_AIM] + CHARGE,
     at=[(0, "vl.Bow aim %s" % J_AIM), (6, "vl.Bow draw 1"), (100, "vl.Bow draw 0"), (130, "vl.Bow draw 1"), (196, "vl.Bow draw 0")],
     cam=dict(pos=[(20.6, -17.9, 5.35), (20.2, -17.6, 5.4), (19.8, -17.3, 5.45)],
              look=[(15.8, -12.4, 5.75), (15.8, -12.4, 5.7), (15.8, -12.4, 5.65)], fov=[34, 32, 30]))


# ================================================================ the castle under attack
# The player's castle raised to level 3 (an archer on each front corner turret) and the east watch tower (168, -100)
# to level 3 (three archers on its lookout): paid with vl.Give and hurried with vl.TimeScale 10 (the level's own
# buildings: the same place every time; the Test World's layout is not). Then the enemy's swordsmen come at the
# tower and at the castle's door from the north.
def fortify_assault(name):
    R.send(["vl.Give gold 99999", "vl.Give food 99999", "vl.Upgrade Watch Tower", "vl.Upgrade Castle", "vl.TimeScale 10"])
    time.sleep(12)
    R.send(["vl.Upgrade Watch Tower", "vl.Upgrade Castle"])
    time.sleep(14)
    R.send(["vl.TimeScale 1", "vl.Order troops %s run" % U(150, -185)])
    time.sleep(3)
    R.send(["vl.SpawnTeam Swordsman 1 %s 30" % U(156, -80), "vl.SpawnTeam Swordsman 1 %s 40" % U(126, -118),
            "vl.SpawnTeam Archer 1 %s 20" % U(132, -106)])
    time.sleep(1.0)


# the east tower's lookout: over the shoulders of its three archers as they loose down on the enemy coming up
shot("b_tower_volley", reel="battle", fresh="match", setup=fortify_assault, frames=150, settle=0.3, easing="inout", k=1.2,
     cam=dict(pos=[(171.1, -103.1, 26.85), (170.6, -102.6, 26.8)], look=[(153, -80, 15.5), (151, -80, 15.0)],
              fov=[60, 56], shake=(0.02, 0.25, 0.6)))

# the castle's door from low in front, the enemy at it, the two corner archers loosing over them; a slow push
shot("b_corners", reel="battle", fresh="match", setup=fortify_assault, frames=150, settle=0.3, easing="inout", k=1.2,
     cam=dict(pos=[(118.5, -125.0, 15.6), (120.0, -127.5, 15.9)], look=[(130.0, -147.0, 20.0), (130.0, -147.0, 20.4)],
              fov=[46, 42], shake=(0.02, 0.2, 0.5)))


# ================================================================ the troop ship lands its troops
# The player's ship lies moored at its quay (245.5, -133.6), its gangplank out onto the quay at (240.9, -131.9).
# 24 swordsmen are put aboard (vl.Ship put sel), then unloaded at frame 0: they come down the gangplank in a file
# and run up the quay at the camera, low on the stones.
def ship_load(name):
    R.send(["vl.SpawnTeam Swordsman 0 %s 24" % U(200, -120), "vl.SelectUnits swordsmen"])
    time.sleep(1.0)
    R.send(["vl.Ship #1 put sel"])
    time.sleep(2.0)


shot("b_landing", reel="battle", fresh="match", setup=ship_load, frames=180, settle=0.3, easing="inout", k=1.2,
     pre=["vl.SelectUnits swordsmen"],
     at=[(0, "vl.Ship #1 unload"), (40, "vl.Order selection %s run" % U(222, -126))],
     cam=dict(pos=[(229.5, -128.5, -3.55), (230.5, -129.0, -3.6)], look=[(241.0, -132.5, -2.6), (241.0, -132.5, -2.8)],
              fov=[42, 38], shake=(0.03, 0.3, 0.6)))


# ================================================================ the kingdom at golden hour (reel 3)
# The sun low in the north-west (vl.Sun -11 35 7 4300), no clouds. Slow moves, long lenses, foreground close.
import showreel_shots as S1   # noqa: E402  (the troop ship's logged course)


def ship_cam_dusk(i, n):
    sx, sy = S1.ship_at(i)
    s = R.ease(i / (n - 1), "inout", 1.4)
    # seaward and ahead of the ship, low on the water, looking back across it at the cliff with the sun beside
    ox, oy, oz = 34 - 6 * s, 30 - 36 * s, -3.6 - 1.2 * s
    return (sx + ox, sy + oy, oz), (sx - 2, sy + 2, 2.0), 40 - 4 * s


# 01 the hook: the troop ship under sail up the east coast, the camera skimming the water beside it
shot("k_ship", reel="kingdom", fresh="match", frames=240, settle=4.0,
     pre=["vl.Ship #1 moor 27200 21500 -107"], at=[(0, "vl.Ship #1 sail 25200 15000")], cam_fn=ship_cam_dusk)

# 02 the realm from the player's plateau into the sun: long lens over the ridges to the enemy's towers in the haze
shot("k_vista", reel="kingdom", frames=150, easing="inout", k=1.3,
     cam=dict(pos=[(112, -86, 20.5), (106, -82, 21.5)], look=[(-120, 110, 20), (-124, 112, 19)], fov=[22, 20]))

# 03 parallax through the flowers south of the castle, the castle lit low from the west
shot("k_flowers", reel="kingdom", frames=150, easing="inout", k=1.3,
     cam=dict(pos=[(160, -187, 14.5), (148, -186, 14.7), (137, -184, 15.0)],
              look=[(133, -150, 18.5), (130, -150, 18.8), (125, -150, 19.0)], fov=[44, 44, 42]))

# 04 over the northern forest's canopy, low and slow, towards the sun
shot("k_canopy", reel="kingdom", frames=150, easing="inout", k=1.3,
     cam=dict(pos=[(180, 160, 26), (160, 145, 25.5), (140, 130, 26)], look=[(60, 200, 18), (40, 190, 18), (20, 180, 18)],
              fov=[50, 48, 46]))

# 05 the army comes home at dusk: a column marches to the castle's door, past the camera low in the grass
MARCH = ["vl.SpawnTeam Swordsman 0 %s 25" % U(166, -112), "vl.SpawnTeam Archer 0 %s 15" % U(172, -112),
         "vl.SelectUnits troops", "vl.Formation column", "vl.Order selection %s" % U(131, -138)]
shot("k_march", reel="kingdom", fresh="match", frames=180, settle=3.0, easing="inout", k=1.2, pre=MARCH,
     cam=dict(pos=[(146.0, -131.5, 14.45), (144.0, -132.5, 14.5)], look=[(156.0, -118.0, 15.3), (146.0, -122.0, 15.2)],
              fov=[34, 34]))

# 06 King David on the plateau's edge over the basin at sunset, his back to us; the camera comes slowly round him
shot("k_king_vista", reel="kingdom", fresh="match", frames=180, settle=2.0, easing="inout", k=1.3,
     pre=["vl.Mode hero", "vl.Teleport %s 1500 -140" % U(88, -78), "vl.Draw 0", "vl.Order troops %s" % U(130, -180)],
     cam=dict(pos=[(92.5, -82.0, 16.3), (91.5, -83.0, 16.0), (89.5, -83.2, 15.8)],
              look=[(60, -50, 10), (56, -50, 9), (52, -50, 8)], fov=[34, 32, 30]))

# 07 Jonathan on the plateau's edge draws against the low sun (profile, half speed)
shot("k_jonathan", reel="kingdom", fresh="match", step=60, frames=180, settle=1.5, easing="inout", k=1.3,
     pre=["vl.Jonathan spawn", "vl.Jonathan play", "vl.Mode hero"],
     at=[(0, "vl.Teleport %s 1500 -135" % U(90, -84)), (2, "vl.Bow aim %s" % U(40, -30, 12)), (10, "vl.Bow draw 1"),
         (150, "vl.Bow draw 0")],
     cam=dict(pos=[(87.6, -86.9, 15.4), (87.3, -86.5, 15.45)], look=[(91.0, -82.6, 15.9), (91.0, -82.6, 15.9)], fov=[34, 32]))

# 08 the realm from high over the player's town (the Test World: every building, the castle at level 7) at sunset
shot("k_town", reel="kingdom", fresh="test", frames=180, settle=2.0, easing="inout", k=1.2,
     cam=dict(pos=[(190, -215, 62), (180, -222, 56)], look=[(120, -130, 12), (118, -134, 13)], fov=[44, 40]))

# 10 the close: King David before his castle, the camera rising and drawing back (the logo over black after)
shot("k_castle", reel="kingdom", fresh="match", frames=180, settle=3.0, easing="inout", k=1.3,
     pre=["vl.Mode hero", "vl.Order troops %s" % U(158, -120), "vl.Teleport 12400 13200 1600 -90", "vl.Orbit -90 -10 400", "vl.Draw 1"],
     cam=dict(pos=[(122.6, -128.6, 15.2), (123.2, -124.5, 16.4), (124.5, -117.0, 19.0)],
              look=[(124.0, -132.2, 15.2), (125.0, -136.0, 16.0), (127.0, -142.0, 17.6)], fov=[40, 46, 52]))


def run(name):
    s = SHOTS[name]
    reel = s.get("reel", "battle")
    R.FRAMES = os.path.join(R.OUT, REEL_DIRS[reel], "frames")
    os.makedirs(R.FRAMES, exist_ok=True)
    if s.get("fresh"):
        fresh(s["fresh"])
    hud_off()
    R.send(BASE + LOOK[reel])
    if "setup" in s:
        s["setup"](name)
    frames = s["frames"]
    step = s.get("step", FPS)
    at = list(s.get("at", []))
    first = list(s.get("pre", []))
    views = None
    if "cam" in s:
        views = R.path_cmds(s["cam"], frames, s.get("easing", "inout"), s.get("k", 2.0), FPS, seed=sum(map(ord, name)) % 997)
    if "cam_fn" in s:
        views = []
        for i in range(frames):
            c, t, fov = s["cam_fn"](i, frames)
            views.append(R.view_cmd(c, t, fov))
    if views:
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
    R.record(name, frames, at, step, s.get("settle", 3.0), first)
