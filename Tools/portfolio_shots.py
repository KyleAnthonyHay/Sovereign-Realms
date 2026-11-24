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
        R.send(P.CLEAN + (look or S2.LOOK[s.get("reel", "battle")]))
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


# ================================================================ the troop ship
def board_setup(name):
    R.send(["vl.SpawnTeam Swordsman 0 %s 24" % U(222, -126), "vl.SelectUnits swordsmen"])
    time.sleep(1.5)


# troops file up the gangplank onto the ship at its quay: the camera low on the quay behind them
reel("s_boarding", dict(fresh="match", setup=board_setup, frames=150, settle=0.3, easing="inout", k=1.2,
                        pre=["vl.SelectUnits swordsmen"], at=[(0, "vl.Ship #1 board sel")],
                        cam=dict(pos=[(229.5, -128.0, -3.3), (231.0, -128.8, -3.2)],
                                 look=[(242.0, -133.0, -2.2), (243.0, -133.5, -2.0)], fov=[46, 42], shake=(0.02, 0.2, 0.5))))


def deck_cam(i, n):
    # on the deck aft, looking forward along her course over the troops and the bow, the cliff to port
    import math
    x0, y0 = S1.ship_at(i)
    x1, y1 = S1.ship_at(min(i + 10, n - 1) if i + 10 < 240 else i)
    if (x1, y1) == (x0, y0):
        x1, y1 = S1.ship_at(i - 10)
        x1, y1 = 2 * x0 - x1, 2 * y0 - y1
    d = math.hypot(x1 - x0, y1 - y0) or 1.0
    ux, uy = (x1 - x0) / d, (y1 - y0) / d
    return (x0 - ux * 7.0, y0 - uy * 7.0, 3.2), (x0 + ux * 30.0, y0 + uy * 30.0, -1.0), 70.0


def ship_put(name):
    R.send(["vl.SpawnTeam Swordsman 0 %s 21" % U(200, -120), "vl.SelectUnits swordsmen"])
    time.sleep(1.0)
    R.send(["vl.Ship #1 put sel"])
    time.sleep(1.5)


reel("s_deck", dict(fresh="match", setup=ship_put, frames=240, settle=4.0, pre=["vl.Ship #1 moor 27200 21500 -107"],
                    at=[(0, "vl.Ship #1 sail 25200 15000")], cam_fn=deck_cam), frames=120, step=15)
reel("s_sail", dict(S1.SHOTS["06_troop_ship"], fresh="match", setup=ship_put), frames=120, step=15)


@shot
def r_raze():
    # the enemy's first farm razed (reel 1's staging: a fresh match, waits for the farm, then the swordsmen at it)
    spec = dict(S1.SHOTS["11_raze_farm"])
    spec.pop("setup")
    S1.raze("11_raze_farm")
    spec.update(cam=S1.SHOTS["11_raze_farm"]["cam"], pre=S1.SHOTS["11_raze_farm"]["pre"], fresh=None)
    run_spec("r_raze", spec, frames=100)


# ================================================================ gameplay, the HUD on (Saved/Portfolio/gameplay_ui)
# The fog of war on (it is part of the game), the two capture variables still off. vl.Shot <name> ui.
UI = ["DisableAllScreenMessages", "vl.Music 0", "vl.Opt.HitFlash 0", "vl.Opt.Silhouette 0"] + P.MIDDAY


def ui_fresh(fog=1):
    S2.fresh("match")
    P.hud(True)
    R.send(UI + ["vl.Fog %d" % fog])
    time.sleep(1.0)


def cursor(u, v):
    """the real pointer over the game's window at (u, v) of its view (the placing ghost follows the pointer)"""
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    hwnd = user32.FindWindowW(None, None)
    found = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def each(h, _):
        n = ctypes.create_unicode_buffer(256)
        user32.GetWindowTextW(h, n, 256)
        if "SovereignRealms" in n.value or "Sovereign Realms" in n.value:
            found.append(h)
        return True
    user32.EnumWindows(each, 0)
    if not found:
        print("no game window")
        return
    hwnd = found[0]
    r = wintypes.RECT()
    user32.GetClientRect(hwnd, ctypes.byref(r))
    pt = wintypes.POINT(int(r.right * u), int(r.bottom * v))
    user32.ClientToScreen(hwnd, ctypes.byref(pt))
    user32.SetForegroundWindow(hwnd)
    user32.SetCursorPos(pt.x, pt.y)


@shot
def ui_build():
    # the build menu open and a farm's ghost on the player's plateau; then laid, and the Builders at work on it
    ui_fresh()
    R.send(["vl.Mode overview", "vl.Look %s 0.22" % U(150, -160)])
    time.sleep(2.0)
    R.send(["vl.Place menu"])
    time.sleep(0.5)
    R.send(["vl.Place farm"])
    cursor(0.42, 0.42)
    time.sleep(1.0)
    cursor(0.43, 0.43)
    P.snap("ui_place_farm", 2.0, ui=True)
    R.send(["vl.Input click 0.43 0.43"])
    time.sleep(1.0)
    R.send(["vl.Place off", "vl.Work Farm"])
    cursor(0.98, 0.5)
    for k, wait in enumerate((14, 10)):
        time.sleep(wait)
        P.snap("ui_farm_site_%d" % k, 0.5, ui=True)


def hero_king():
    R.send(["vl.Mode hero", "vl.View follow", "vl.Teleport %s 1500 -45" % U(112, -118), "vl.Draw 1"])
    time.sleep(2.0)
    R.send(["vl.Orbit -45 -10 600"])
    time.sleep(1.5)


@shot
def ui_hero_now():
    # as ui_hero, in the match as it is
    R.send(UI)
    P.hud(True)
    hero_king()
    P.snap("ui_hero_king", 1.0, ui=True)
    R.send(["vl.SelectUnits troops", "vl.HeroOrder mode on"])
    time.sleep(1.0)
    R.send(["vl.HeroAim %s 6" % U(95, -95), "vl.HeroOrder corder"])
    time.sleep(1.5)
    P.snap("ui_command_mode", 0.5, ui=True)
    R.send(["vl.HeroOrder mode off"])


@shot
def ui_hero():
    # King David in the hero view at the head of his troops, sword drawn; then command mode (R) with them selected
    ui_fresh()
    R.send(["vl.SpawnTeam Swordsman 0 %s 20" % U(118, -112), "vl.SpawnTeam Archer 0 %s 10" % U(124, -108)])
    hero_king()
    P.snap("ui_hero_king", 1.0, ui=True)
    R.send(["vl.SelectUnits troops", "vl.HeroOrder mode on"])
    time.sleep(1.0)
    R.send(["vl.HeroAim %s 6" % U(95, -95), "vl.HeroOrder corder"])
    time.sleep(1.5)
    P.snap("ui_command_mode", 0.5, ui=True)
    R.send(["vl.HeroOrder mode off"])


@shot
def ui_jonathan():
    # Jonathan, played, draws his bow at the enemy coming up the hill (the hero view's crosshair, his health)
    ui_fresh(fog=0)
    R.send(["vl.Jonathan castle"])
    time.sleep(2.0)
    R.send(["vl.Jonathan spawn", "vl.Jonathan play", "vl.Mode hero", "vl.View follow"])
    time.sleep(2.0)
    R.send(["vl.Teleport %s 1500 -127" % U(100, -100), "vl.SpawnTeam Swordsman 1 %s 15" % U(80, -74)])
    time.sleep(1.5)
    R.send(["vl.Bow aim %s" % U(82, -76, 15.5), "vl.Bow draw 1"])
    time.sleep(1.2)
    P.snap("ui_jonathan_draw", 0.3, ui=True)


@shot
def ui_overview_battle():
    # the overview over the basin: the player's army selected, on an attack-move at the enemy's (routes, minimap)
    ui_fresh(fog=1)
    R.send(S2.ARMY + ["vl.Teleport %s 600 180" % U(11, 0)])
    time.sleep(1.0)
    R.send(["vl.Mode overview", "vl.Look %s 0.45" % U(-2, 4), "vl.SelectUnits swordsmen", "vl.AttackMove selection %s run" % U(-34, 0)])
    cursor(0.98, 0.5)
    time.sleep(2.5)
    P.snap("ui_overview_battle", 0.3, ui=True)


@shot
def ui_castle():
    # the castle selected in the overview: its level card and upgrade
    ui_fresh(fog=1)
    R.send(["vl.Give gold 2000", "vl.Give food 2000", "vl.Mode overview", "vl.Look %s 0.3" % U(128, -140)])
    time.sleep(2.5)
    R.send(["vl.Click 0.5 0.45"])
    cursor(0.98, 0.5)
    P.snap("ui_castle", 2.0, ui=True)


# the same, the camera further back and higher on the quay, over the troops' shoulders as they go aboard
reel("s_boarding2", dict(fresh="match", setup=board_setup, frames=150, settle=0.3, easing="inout", k=1.2,
                         pre=["vl.SelectUnits swordsmen"], at=[(0, "vl.Ship #1 board sel")],
                         cam=dict(pos=[(230.5, -124.0, -1.0), (232.0, -124.8, -1.2)],
                                  look=[(244.0, -133.0, -0.5), (244.5, -133.4, -0.7)], fov=[52, 50])), frames=100, step=15)


def deck_cam2(i, n):
    # at the bow, a man's height over the deck, looking aft and to port over the troops, the mast and the cliff
    x, y, z = deck_cam(i, n)[0]
    ux, uy = (deck_cam(i, n)[1][0] - x) / 37.0, (deck_cam(i, n)[1][1] - y) / 37.0
    x0, y0 = x + ux * 7.0, y + uy * 7.0
    px, py = -uy, ux                              # to port (left of her course)
    return (x0 + ux * 5.0 - px * 1.2, y0 + uy * 5.0 - py * 1.2, 2.0), (x0 - ux * 6.0 + px * 6.0, y0 - uy * 6.0 + py * 6.0, 1.6), 74.0


reel("s_deck2", dict(fresh="match", setup=ship_put, frames=240, settle=4.0, pre=["vl.Ship #1 moor 27200 21500 -107"],
                     at=[(0, "vl.Ship #1 sail 25200 15000")], cam_fn=deck_cam2), frames=80, step=10)


# the player's archers in profile, low, loosing over the charge (the battle staging; they hold their ground)
reel("b_archers_side", dict(fresh="match", setup=S2.battle(), frames=120, settle=0.4, easing="inout", k=1.2,
                            pre=S2.CHARGE + ["vl.Hold archers", "vl.Walk %s run" % U(-30, 0)],
                            cam=dict(pos=[(31.0, -9.5, 5.2), (30.0, -9.0, 5.3)], look=[(24.0, 4.0, 6.6), (23.0, 4.0, 6.8)],
                                     fov=[44, 42], shake=(0.02, 0.2, 0.5))))


@shot
def s_boarding3():
    # troops walk out along the pier and up onto the moored troop ship, the camera at the pier's root on the quay
    S2.fresh("match")
    P.hud(False)
    R.send(P.CLEAN + P.MIDDAY)
    R.send(["vl.SpawnTeam Swordsman 0 %s 20" % U(224, -130), "vl.SelectUnits swordsmen"])
    time.sleep(1.5)
    v = P.V((219, -124, -1.0), (243, -134, -1.5), 55)
    P.burst("s_boarding3", 120, [(0, v), (0, "vl.Ship #1 board sel")], 15, 0.5, [v, "vl.SelectUnits swordsmen"])


def deck_cam3(i, n):
    # on the stern, over the port rail: forward along the deck over the troops, the mast and the sail, sea ahead
    # (offsets measured on the moored ship: 8.6 m aft of her centre and 3 m to port, looking 8.4 m ahead, 2.5 to starboard)
    import math
    x0, y0 = S1.ship_at(i)
    j = min(i + 6, 239.0)
    x1, y1 = S1.ship_at(j)
    if j - i < 3:
        xb, yb = S1.ship_at(i - 6)
        x1, y1 = 2 * x0 - xb, 2 * y0 - yb
    d = math.hypot(x1 - x0, y1 - y0) or 1.0
    fx, fy = (x1 - x0) / d, (y1 - y0) / d
    lx, ly = -fy, fx                               # port: to the left of her course
    cam = (x0 - fx * 8.6 + lx * 3.0, y0 - fy * 8.6 + ly * 3.0, -0.3)
    look = (x0 + fx * 8.4 - lx * 2.5, y0 + fy * 8.4 - ly * 2.5, -2.5)
    return cam, look, 70.0


reel("s_deck3", dict(fresh="match", setup=ship_put, frames=240, settle=4.0, pre=["vl.Ship #1 moor 27200 21500 -107"],
                     at=[(0, "vl.Ship #1 sail 25200 15000")], cam_fn=deck_cam3), frames=80, step=10)


# the town at its fullest (the Test World: every building raised, the castle at level 7) from high, at midday
@shot
def town():
    S2.fresh("test")
    P.hud(False)
    R.send(P.CLEAN + P.MIDDAY)
    P.scene([("t_town_high", (190, -215, 62), (120, -130, 12), 44),
             ("t_town_low", (165, -175, 24), (122, -134, 14), 50),
             ("t_town_wide", (240, -260, 110), (110, -120, 0), 46)])


# ================================================================ Realm v2 (vl.Map realmv2, then vl.StartMatch 0)
@shot
def realmv2():
    P.scene([
        ("v2_mountain", (28 + 300 * -0.766, 146 + 300 * -0.643, 105), (28, 146, 112), 54),
        ("v2_mountain_b", (28 + 290 * -0.42, 146 + 290 * -0.91, 135), (28, 146, 118), 50),
        ("v2_island", (-60, -900, 520), (0, 40, 0), 46),
        ("v2_island_w", (-850, -350, 480), (0, 30, 0), 46),
    ])


@shot
def ui_jonathan2():
    # Jonathan, played, among the player's archers in the basin battle: he draws on the enemy's charging line
    S2.fresh("match")
    P.hud(True)
    R.send(UI + ["vl.Fog 0"])
    S2.battle(["vl.Jonathan spawn", "vl.Jonathan play", "vl.Mode hero"])(None)
    R.send(["vl.Teleport %s 520 -160" % U(*S2.J_AT), "vl.Bow aim %s" % S2.J_AIM, "vl.View follow"] + S2.CHARGE)
    time.sleep(0.5)
    R.send(["vl.Bow draw 1"])
    time.sleep(1.3)
    P.snap("ui_jonathan_battle", 0.2, ui=True)
    R.send(["vl.Bow draw 0"])
    time.sleep(1.5)
    R.send(["vl.Bow draw 1"])
    time.sleep(1.3)
    P.snap("ui_jonathan_battle2", 0.2, ui=True)
