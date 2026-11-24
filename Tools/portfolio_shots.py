"""The portfolio's shots (Tools/portfolio_stills.py <shot>): each a function that stages and captures one or more stills.

Plan metres (+X east, +Y north, +Z up). Realm v3: the player's plateau south-east (castle about 124, -134), the
enemy's north-west (-130, 148), the basin between them, the ridges across, the player's quay at (245.5, -133.6).
"""
import time

import portfolio_stills as P
import showreel as R
import showreel2_shots as S2
import showreel_shots as S1

U = S2.U
shot = P.shot


# ================================================================ scenery (any match on Realm v3, midday, no fog)
@shot
def scenery():
    P.scene([
        ("a_island_s", (-40, -700, 330), (10, 20, 0), 46),
        ("a_island_sw", (-430, -470, 300), (0, 0, -10), 44),
        ("a_island_ne", (470, 430, 270), (0, 0, -10), 44),
        ("a_island_se_low", (330, -330, 110), (-60, 60, 0), 55),
        ("a_basin", (-76, -70, 82), (6, 6, 4), 60),
        ("a_plateau", (30, -28, 110), (122, -122, 14), 60),
        ("a_coast", (-40, -276, 24), (-110, -210, 6), 60),
        ("a_dock", (276, -78, 26), (240, -128, 2), 55),
        ("a_canopy", (90, 200, 30), (-30, 110, 6), 60),
        ("a_castle_flowers", (149, -186, 14.8), (130, -150, 19.2), 48),
        ("a_vista", (112, -86, 20.5), (-120, 110, 20), 22),
    ])


@shot
def scenery2():
    P.scene([
        ("a2_pass", (-84, 70, 34), (-52, -8, 4), 60),
        ("a2_ramp_low", (67.5, -2, 6.4), (75, -50, 10.5), 70),
        ("a2_ridge", (150, 60, 60), (-20, -20, 20), 50),
    ])


# ================================================================ the battle in the basin (showreel 2's staging)
def battle(extra=(), look=P.MIDDAY):
    S2.fresh("match")
    P.hud(False)
    R.send(P.CLEAN + look)
    S2.battle(extra)(None)


def charge_burst(name, view, frames, at=(), step=30, king=True):
    """the charge given at frame 0 (King David running with it), the camera fixed, a burst"""
    at = [(0, c) for c in S2.CHARGE] + list(at)
    if king:
        at.append((0, "vl.Walk %s run" % U(-30, 0)))
    at.append((0, view))
    return P.burst(name, frames, at, step, 0.5, [view])


@shot
def b_masses():
    # the two armies drawn up across the basin from high over its south-east end, then the charge
    battle()
    for n, c, t, f in (("b_masses_pre", (40, -34, 30), (-6, 5, 3), 50), ("b_masses_pre2", (-4, -38, 18), (-4, 6, 4), 60)):
        R.send([P.V(c, t, f)])
        time.sleep(1.0)
        R.send([P.V(c, t, f)])
        P.snap(n, 1.5)
    charge_burst("b_masses", P.V((30, -30, 20), (-8, 4, 4), 50), 150)


# ================================================================ the showreels' staged shots, as bursts to pick from
def run_spec(name, s, frames=None, step=None, look=None):
    """a shot spec of Tools/showreel2_shots.py (the same keys), recorded to _work/burst/<name>: frames (fewer than the
    reel's: the camera covers its path in fewer frames) and step (game steps a second) may be overridden"""
    if s.get("fresh"):
        S2.fresh(s["fresh"])
    P.hud(False)
    R.send(P.CLEAN + (look or S2.LOOK[s.get("reel", "battle")]))
    if "setup" in s:
        s["setup"](name)
    n0 = s["frames"]
    frames = frames or n0
    step = step or s.get("step", 30)
    at = [(int(f * frames / n0), c) for f, c in s.get("at", [])]
    first = list(s.get("pre", []))
    views = None
    if "cam" in s:
        views = R.path_cmds(s["cam"], frames, s.get("easing", "inout"), s.get("k", 2.0), 30, seed=sum(map(ord, name)) % 997)
    if "cam_fn" in s:
        views = []
        for i in range(frames):
            c, t, fov = s["cam_fn"](i * n0 / frames, n0)
            views.append(R.view_cmd(c, t, fov))
    if views:
        first.append(views[0])
        at += [(i, v) for i, v in enumerate(views)]
    if "follow" in s:
        for i in range(frames):
            u = R.ease(i / max(frames - 1, 1), s.get("easing", "inout"), s.get("k", 2.0))
            yaw, pitch, dist = R.spline(s["follow"], u)
            cmd = "vl.Orbit %.2f %.2f %.1f" % (yaw, pitch, dist)
            if i == 0:
                first.append(cmd)
            at.append((i, cmd))
    return P.burst(name, frames, at, step, s.get("settle", 3.0), first)


def reel(name, src=None, **kw):
    """register a reel shot (by its showreel2 name, or a spec) as a portfolio burst"""
    def f():
        spec = src if isinstance(src, dict) else S2.SHOTS[src or name]
        run_spec(name, spec, **kw)
    f.__name__ = name
    shot(f)


reel("b_rush", frames=80)
reel("b_clash_low", frames=90)
reel("b_scrum", frames=100)
reel("b_charge_lens")
reel("b_king_charge")
reel("b_jonathan")
reel("b_jonathan2")
reel("b_landing")
reel("b_tower_volley")
reel("b_corners")
reel("k_flowers", look=P.GOLDEN)
reel("k_ship", look=P.GOLDEN)
reel("k_march", look=P.GOLDEN)
reel("k_jonathan", look=P.GOLDEN)
reel("k_town", look=P.GOLDEN)
# reel 1's at midday, with a fresh match and the capture variables (reel 1's own runner predates them)
reel("r_archer_volley", dict(S1.SHOTS["09_archer_volley"], fresh="match"))
reel("r_ship", dict(S1.SHOTS["06_troop_ship"], fresh="match"))
reel("r_king_castle", dict(S1.SHOTS["13_king_castle"], fresh="match"))
reel("r_battle_line", dict(S1.SHOTS["07_battle_line"], fresh="match"), frames=120)
reel("r_king_charge", dict(S1.SHOTS["08_king_charge"], fresh="match"), frames=120)
