"""The farm: produces food. Authored in Unreal cm, front toward -X (bldkit.py).

Read from the tactical zoom through the gold: a field of ripe barley in rows across the screen, a harvested strip
with stooks, a haystack. Beside it a small mudbrick-and-plaster cottage with a reed porch, a beehive granary, a
cart, an olive tree, a scarecrow in the team's colours and a little banner on the roof.

States (bldkit.STATES): `complete`; `damaged` is the same build with the hooks below switched on (k.damaged) plus
damage(); `site` and `ruin` are small meshes of their own on the same footprint.

Levels 1-3 (k.level), each adding to the last (medieval, weathered: slate, iron, dark stone, no gold):
  2  the cottage becomes a farmhouse: a stone footing, a jettied half-timbered upper storey under a pitched slate
     roof, a striped awning for a porch; the granary is rebuilt in stone under a flat iron-bound lid
  3  fortified: the granary is a tall round stone silo on dark stone with iron bands, a timber hoarding under a
     glazed head and a flat top ringed with crow-stepped merlons (a chess rook, like the castle's towers); the farmhouse gets a stone chimney, banners and creeper; fires burn at the yard's entrance
The level banner (kit.level_flag) stands at the front-left, at the corner where the field's fence meets the yard entrance.
"""
import math

from bldkit import NO_TOP, STATES, inset_ring, ngon, rect  # noqa: F401

NAME = "farm"
MESH = "SM_Bld_Farm"
SEED = 23
FOOTPRINT = [-440.0, -480.0, 440.0, 480.0]
RING_RADIUS = 620.0
LEVELS = 3
PREVIEW_FIGURES = [(-560, -60), (-600, 60)]

FX0, FX1, FY0, FY1 = -400.0, 256.0, -110.0, 452.0        # the field
BURN = (40.0, 110.0, 170.0)                               # damaged: x, y, radius of barley burnt to the ground


def cottage(k):
    x0, x1, y0, y1 = 96.0, 400.0, -452.0, -140.0
    hw = (y1 - y0) / 2
    cy = (y0 + y1) / 2
    with k.at((0, cy, 0)):
        lv = k.level
        base = "Bld_Mudbrick" if lv == 1 else "Bld_AshlarLarge"                    # level 2 on: a stone footing
        r0 = rect(x0, -hw, x1, hw)
        u0 = 44.0
        r1 = k.wall(base, r0, 0, 64, inset=8, u0=u0, bleach=False)                 # the brick footing, left bare
        k.cap(base, r0, 0.5, down=True)
        side = 2 * (hw - 8)
        door = dict(a=side / 2 - 30, b=side / 2 + 50, z0=64, z1=186, depth=18, back="Bld_Planks", reveal="Bld_Mudbrick", shade=0.7,
                    back_shade=0.75, no_sill=True)
        win = dict(a=side / 2 - 124, b=side / 2 - 76, z0=112, z1=172, depth=12, back="Bld_Shutter", reveal="Bld_Mudbrick", shade=0.7)
        win2 = dict(a=120, b=168, z0=112, z1=172, depth=12, back="Bld_Shutter", reveal="Bld_Mudbrick", shade=0.7)
        top = 236.0
        k.wall("Bld_Plaster", r1, 64, top, u0=u0, openings={2: [door, win] + k.breach(212, 288, 80, 208, depth=20), 3: [win2]})
        # the doorway reaches the ground: cut the footing too
        k.obox("Bld_Planks", (x0 + 6, hw - 8 - side / 2 - 10, 32), (16, 80, 64), grain="z")
        k.obox("Bld_Beam", (x0 + 2, hw - 8 - side / 2 - 10, 196), (16, 108, 18), grain="y")
        k.obox("Bld_Trim", (x0 - 6, hw - 8 - side / 2 - 10, 3), (40, 96, 6))
        k.beam_ends("Bld_Beam", (x0 + 8, hw - 30), (x0 + 8, -hw + 30), top - 22, 6, size=(14, 14), out=20)
        k.beam_ends("Bld_Beam", (x0 + 30, -hw + 8), (x1 - 30, -hw + 8), top - 22, 5, size=(14, 14), out=20)
        r2 = inset_ring(r1, -3)
        k.cap("Bld_Plaster", r2, top, down=True, shade=0.6)
        if lv == 1:
            k.wall("Bld_Plaster", r2, top, top + 26, u0=u0, bleach=False)
            k.parapet("Bld_Plaster", r2, top + 4, top + 26, thick=20, top="Bld_Plaster")
            # on the roof: sheaves drying, jars, a short standard
            for (x, y, yaw) in ((300, -60, 20), (332, 10, -30), (286, 44, 75)) if not k.damaged else ():
                sheaf(k, (x, y, top + 4), lying=True, yaw=yaw)
            if k.damaged:
                k.burn_hole((262, -6, top + 4), (150, 120), yaw=25, soot="blot_m")
            k.pot((170, 96, top + 4), 0.8)
            k.pot((214, 110, top + 4), 0.6)
            k.pole_banner((x1 - 44, -hw + 44, top + 4), height=210.0, cloth_w=64.0, cloth_h=192.0)
        else:
            upper_storey(k, r1, r2, top, u0)
        # reed porch over the door on two forked posts
        px = x0 - 118
        porch = "Bld_Thatch" if lv == 1 else "Bld_Awning"                          # level 2 on: a striped awning
        k.cloth(porch, [(x0 + 2, 124, 214), (x0 + 2, -96, 214), (px, -96, 176), (px, 124, 176)],       # damaged: burnt to tatters
                [(220, 0), (0, 0), (0, 126), (220, 126)], w=NO_TOP)
        if not k.damaged:
            k.poly(porch, [(x0 + 2, -96, 208), (x0 + 2, 124, 208), (px, 124, 170), (px, -96, 170)],
                   [(0, 0), (220, 0), (220, 126), (0, 126)], shade=0.55)
        for y in (-88, 116):
            k.cyl("Bld_Beam", (px + 10, y, 0), (px + 10, y, 176), 5.0, 4.0, sides=5)
        k.obox("Bld_Beam", (px + 10, 14, 172), (7, 226, 7), grain="y")
        k.obox("Bld_Beam", (x0 - 56, -92, 190), (124, 6, 6), pitch=-18)
        k.obox("Bld_Beam", (x0 - 56, 120, 190), (124, 6, 6), pitch=-18)
        # under the porch
        k.pot((x0 - 36, 92, 0), 1.05)
        k.pot((x0 - 80, 110, 0), 0.75)
        k.basket((x0 - 40, -66, 0), 24, 26, fill="Bld_Gold" if False else "Bld_Thatch")
        k.basket((x0 - 86, -78, 0), 20, 22, fill="Bld_Thatch")
        k.ladder((x1 - 150, hw + 46, 0), (x1 - 150, hw + 2, top + 30), width=34, rungs=7)


def upper_storey(k, r1, r2, top, u0):
    """Level 2 on (inside the cottage's frame): a half-timbered upper storey jettied out on beam ends under a pitched
    slate roof, its ridge across the view. Level 3: a stone chimney, banners, creeper on the old wall."""
    lv = k.level
    rj = inset_ring(r2, -14)
    xs, ys = [p[0] for p in rj], [p[1] for p in rj]
    xa, xb, ya, yb = min(xs), max(xs), min(ys), max(ys)
    k.band("Bld_Beam", r2, top, top + 12, out=14, u0=u0)                           # the jetty's bressummer
    z1, z2, rise = top + 12, top + 140, 130.0
    k.wall("Bld_Timber", rj, z1, z2, v0=0.0, bleach=False, u0=0.0)
    for y in (-96, 0, 96):                                   # shuttered windows in the panels
        k.obox("Bld_Shutter", (xa - 2, y, z1 + 64), (8, 40, 52), grain="z")
        k.obox("Bld_Beam", (xa - 4, y, z1 + 34), (12, 52, 7), grain="y")
    k.gable_end("Bld_Timber", xa, xb, ya, z2, rise, facing=-1)
    k.gable_end("Bld_Timber", xa, xb, yb, z2, rise, facing=1)
    zr = k.gable_roof("Bld_Slate", xa, xb, ya, yb, z2, rise, over=28.0, verge=20.0, holes=((-1, 44.0, 96.0, 64.0),))
    if lv >= 3:
        cx, cyy = (xa + xb) / 2 + 40, yb - 46                # a stone chimney through the back slope
        k.box("Bld_StoneDark", (cx - 26, cyy - 30, z2 + 40), (cx + 26, cyy + 30, zr + 52), u0=10.0, top="Bld_Dark")
        k.band("Bld_Trim", rect(cx - 26, cyy - 30, cx + 26, cyy + 30), zr + 40, zr + 52, out=5)
        for y in (-48, 48):                                  # banners between the upper windows
            k.cyl("Bld_Iron", (xa - 6, y - 22, z2 - 14), (xa - 6, y + 22, z2 - 14), 2.4, sides=4)
            k.hang_cloth((xa - 6, y - 17, z2 - 16), (xa - 6, y + 17, z2 - 16), 104.0)
        k.patch("Bld_Leaves", (xa + 20, ya - 2, 0), (1, 0, 0), (0, 0, 1), 180, 230, cells=12, fill=0.55, out=14)
        k.patch("Bld_Leaves", (xa + 12, ya + 40, 0), (0, -1, 0), (0, 0, 1), 70, 200, cells=12, fill=0.5, out=14)
        return zr + 52
    return zr


def silo(k, pos):
    """Level 3: the granary rebuilt as a tall round stone silo: dark stone below, iron bands, a timber hoarding under
    an oversailing glazed head, a flat top ringed with crow-stepped merlons. Returns its top."""
    with k.at(pos):
        k.lathe("Bld_StoneDark", (0, 0, 0), [(112, 0), (104, 128)], sides=12, rot=15, top=False)
        k.lathe("Bld_Iron", (0, 0, 0), [(106, 124), (106, 136)], sides=12, rot=15, top=False)
        k.lathe("Bld_Ashlar", (0, 0, 0), [(102, 132), (94, 470)], sides=12, rot=15, top=False)
        k.lathe("Bld_Iron", (0, 0, 0), [(100, 290), (100, 300)], sides=12, rot=15, top=False)
        k.lathe("Bld_Beam", (0, 0, 0), [(94, 452), (114, 472)], sides=12, rot=15, top=False)      # the hoarding's brackets
        k.lathe("Bld_Timber", (0, 0, 0), [(114, 472), (114, 536)], sides=12, rot=15, top=False)
        k.lathe("Bld_Trim", (0, 0, 0), [(120, 536), (120, 548)], sides=12, rot=15, top=False)
        ring = ngon(0, 0, 118.0 / math.cos(math.pi / 12), 12, rot=15)
        k.cap("Bld_AshlarLarge", ring, 536, down=True, shade=0.55)
        k.wall("Bld_Frieze", ring, 548, 596, v0=0.0, bleach=False)
        k.parapet("Bld_Ashlar", ring, 574, 596, thick=18, top="Bld_Trim")
        k.stepped_merlons("Bld_Ashlar", ring, 596, width=30, gap=18, thick=18, h1=20, h2=16, cap="Bld_Trim")
        top = 632.0
        # the filling hatch and a ledge under it, a loading door high up, facing the camera
        k.obox("Bld_Planks", (-102, 0, 150), (10, 46, 56), grain="z")
        k.obox("Bld_Beam", (-104, 0, 118), (18, 60, 8), grain="y")
        k.obox("Bld_Dark", (-93, 0, 340), (10, 30, 56))
        if k.damaged:
            k.scorch("plume_s", (-98, 0, 190), out=5)
            k.rubble((-130, -40, 0), (90, 120), 20, blocks=5, beams=0)
        return top


def sheaf(k, pos, lying=False, yaw=0.0):
    """A bound sheaf of barley: a waisted bundle, ears up (or lying on a roof)."""
    with k.at(pos, yaw):
        if lying:
            k.cyl("Bld_Thatch", (-34, 0, 9), (34, 0, 11), 9.0, 12.0, sides=6)
            k.cyl("Bld_Thatch", (-4, 0, 10), (4, 0, 10), 11.0, 11.0, sides=6, grain="ring")
        else:
            k.lathe("Bld_Thatch", (0, 0, 0), [(20, 0), (11, 44), (17, 78), (20, 86)], sides=6, top="Bld_Thatch", rot=k.U(0, 60))


def stook(k, pos):
    """Sheaves leaned together: a small gold tent in the stubble."""
    with k.at(pos, k.U(0, 90)):
        k.lathe("Bld_Thatch", (0, 0, 0), [(40, 0), (30, 36), (16, 72), (22, 96)], sides=7, top="Bld_Thatch", rot=k.U(0, 50))
        for a in (0.0, 90.0):
            c, s = math.cos(math.radians(a)), math.sin(math.radians(a))
            k.card("Bld_Wheat", (-c * 30, -s * 30, 64), (c * 30, s * 30, 64), 60, 60, u0=k.U(0, 256), sway=True)


def haystack(k, pos, r=92.0, h=176.0):
    with k.at(pos):
        if k.damaged:                                        # burnt down to a blackened half
            k.lathe("Bld_Thatch", (0, 0, 0), [(r * 0.92, 0), (r, h * 0.2), (r * 0.94, h * 0.42)], sides=9, rot=11, top=False)
            k.lathe("Bld_Char", (0, 0, 0), [(r * 0.94, h * 0.42), (r * 0.6, h * 0.58), (r * 0.2, h * 0.52)], sides=9, rot=11)
            return
        k.lathe("Bld_Thatch", (0, 0, 0), [(r * 0.92, 0), (r, h * 0.2), (r * 0.94, h * 0.5), (r * 0.62, h * 0.82), (r * 0.16, h)], sides=9, rot=11)
        k.cyl("Bld_Beam", (0, 0, h - 20), (4, 2, h + 44), 3.5, 2.5, sides=5)
        k.ladder((r + 34, 6, 0), (r * 0.72, 4, h * 0.72), width=30, rungs=5)


def granary(k, pos):
    """Beehive granary: a mudbrick drum drawing in to a plastered shoulder, under a reed cap."""
    stone = k.level >= 2                                     # level 2: built in stone under a bronze cap
    with k.at(pos):
        k.lathe("Bld_Ashlar" if stone else "Bld_Mudbrick", (0, 0, 0), [(104, 0), (110, 40), (106, 150), (92, 196)], sides=10, rot=18)
        k.lathe("Bld_Plaster", (0, 0, 196), [(92, 0), (70, 34), (58, 44)], sides=10, rot=18, top="Bld_Dark")
        if not k.damaged and stone:
            k.lathe("Bld_Planks", (0, 0, 236), [(70, 0), (64, 14)], sides=10, rot=18)             # a flat boarded lid, iron-bound
            k.lathe("Bld_Iron", (0, 0, 232), [(72, 0), (72, 8)], sides=10, rot=18, top=False)
        elif not k.damaged:                                  # damaged: the reed cap has burnt off the open throat
            k.lathe("Bld_Thatch", (0, 0, 228), [(84, 0), (56, 40), (10, 84)], sides=10, rot=18)
            k.cyl("Bld_Thatch", (0, 0, 306), (0, 0, 326), 9.0, 5.0, sides=6)
        else:
            k.lathe("Bld_Char", (0, 0, 236), [(66, 0), (62, 10)], sides=10, rot=18, top=False)
            k.charred((-50, -30, 244), (56, 20, 250), size=8)
        # the filling hatch and a ledge under it, facing the camera
        k.obox("Bld_Planks", (-108, 0, 116), (10, 44, 52), grain="z")
        k.obox("Bld_Beam", (-110, 0, 86), (18, 58, 8), grain="y")


def cart(k, pos, yaw=0.0):
    with k.at(pos, yaw):
        k.obox("Bld_Planks", (0, 0, 52), (150, 78, 8))                       # bed
        for s in (-1, 1):
            k.obox("Bld_Planks", (0, s * 39, 72), (150, 6, 34))               # side boards
            k.wheel((-6, s * 50, 38), radius=38.0, thick=8.0)
            k.obox("Bld_Beam", (-128, s * 26, 50), (124, 6, 7), pitch=10)     # shafts, resting on the ground
        k.obox("Bld_Planks", (73, 0, 72), (6, 78, 34))
        k.cyl("Bld_Beam", (-6, -52, 38), (-6, 52, 38), 4.5, sides=5)          # axle
        k.obox("Bld_Beam", (58, 0, 22), (8, 8, 44), pitch=-12)                # prop leg
        k.blob("Bld_Thatch", (6, 0, 96), (150, 84, 86), points=14, flat=True, squash=0.3)     # the load of hay
        k.sack((-52, 8, 60), 0.8, yaw=30)


def scarecrow(k, pos):
    with k.at(pos, -12):
        k.cyl("Bld_Beam", (0, 0, 0), (0, 0, 168), 4.0, 3.5, sides=5)
        k.obox("Bld_Beam", (0, 0, 128), (6, 118, 6), grain="y")
        k.blob("Bld_Thatch", (0, 0, 164), (30, 30, 34), points=10, flat=False, squash=0.2)      # sack head
        k.lathe("Bld_Thatch", (0, 0, 176), [(26, 0), (17, 6), (3, 20)], sides=7)                  # straw hat
        # a ragged tunic in the team's colour, hung over the crossbar
        for x in (-5, 5):
            k.poly("Bld_Awning", [(x, 44, 132), (x, -44, 132), (x, -34, 64), (x, 34, 64)], [(88, 0), (0, 0), (10, 68), (78, 68)],
                   w=[0.0, 0.0, 0.8, 0.8])
        for s in (-1, 1):
            k.card("Bld_Wheat", (0, s * 52, 96), (0, s * 62, 96), 36, 36, u0=k.U(0, 200))


def fence(k, pts, gaps=(), post_h=84.0, step=104.0):
    """Post-and-rail along a polyline; `gaps` are (segment index, from, to) left open."""
    for i in range(len(pts) - 1):
        a, b = pts[i], pts[i + 1]
        L = math.hypot(b[0] - a[0], b[1] - a[1])
        n = max(int(round(L / step)), 1)
        yaw = math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))
        prev = None
        for j in range(n + 1):
            f = j / n
            d = f * L
            open_here = any(g[0] == i and g[1] <= d <= g[2] for g in gaps)
            p = (a[0] + (b[0] - a[0]) * f + k.U(-3, 3), a[1] + (b[1] - a[1]) * f + k.U(-3, 3))
            if not open_here:
                h = post_h + k.U(-8, 8)
                k.cyl("Bld_Beam", (p[0], p[1], -4), (p[0] + k.U(-4, 4), p[1] + k.U(-4, 4), h), 5.5, 4.5, sides=5)
            if prev is not None and not open_here and not prev[1]:
                q = prev[0]
                mid = ((p[0] + q[0]) / 2, (p[1] + q[1]) / 2)
                seg = math.hypot(p[0] - q[0], p[1] - q[1])
                for z in (34, 64):
                    k.obox("Bld_Beam", (mid[0], mid[1], z + k.U(-3, 3)), (seg + 10, 4, 7), yaw=yaw, roll=k.U(-4, 4), pitch=k.U(-2, 2))
            prev = (p, open_here)


def field(k):
    z = 8.0
    r = rect(FX0, FY0, FX1, FY1)
    k.wall("Bld_Soil", r, -2, z, inset=6, u0=0.0, bleach=False)
    k.cap("Bld_Soil", inset_ring(r, 6), z)
    stand_y1 = 296.0                                         # standing barley up to here, stubble beyond
    x = FX0 + 14
    i = 0
    while x < FX1 - 10:
        # each row in two or three lengths, so heights and the pattern never line up
        y = FY0 + 8 + k.U(0, 10)
        while y < stand_y1 - 20:
            L = min(k.U(110, 190), stand_y1 - y)
            # the scarecrow stands in a small gap
            burnt = k.damaged and math.hypot(x - BURN[0], y + L / 2 - BURN[1]) < BURN[2]
            if not (abs(x + 150) < 20 and 130 < y + L / 2 < 190) and not burnt:
                k.card("Bld_Wheat", (x + k.U(-2, 2), y, z - 2), (x + k.U(-2, 2), y + L, z - 2), 128, 128, u0=k.U(0, 256), lean=k.U(-10, 6))
            y += L
        x += 32.0
        i += 1
    for (sx, sy) in ((-300, 372), (-96, 392), (112, 366)):
        stook(k, (sx, sy, z))
    scarecrow(k, (-150, 160, z))


def build(k, state="complete"):
    if state == "site":
        return site(k)
    if state == "ruin":
        return ruin(k)
    complete(k)
    if k.damaged:
        damage(k)


def complete(k):
    lv = k.level
    cottage(k)
    field(k)
    label = 470.0
    if lv >= 3:
        label = silo(k, (336, 44, 0)) + 150.0
    else:
        granary(k, (336, 44, 0))
        if lv == 2:
            label = 236.0 + 140.0 + 130.0 + 150.0            # over the farmhouse ridge
    haystack(k, (-96, -214, 0))
    cart(k, (-250, -300, 0), yaw=-28)
    k.tree((338, 352, 0), height=370, spread=190, blobs=6)
    k.tree((-396, -440, 0), height=300, spread=140, lean=(-10, 8), blobs=5)
    # the yard: sacks, a trough, a chopping block
    k.sack((30, -182, 0), 1.0, yaw=20)
    k.sack((52, -150, 0), 0.9, yaw=-50)
    k.sack((40, -168, 26), 0.85, yaw=80)
    k.box("Bld_Planks", (-190, -160, 0), (-90, -128, 30), top="Bld_Dark")
    k.cyl("Bld_Bark", (-330, -200, 0), (-330, -200, 34), 22.0, sides=7, grain="ring", cap_slot="Bld_Beam")
    # fence round the plot and the yard, open toward the road at the yard's front
    x0, y0, x1, y1 = FOOTPRINT[0] + 14, FOOTPRINT[1] + 14, FOOTPRINT[2] - 14, FOOTPRINT[3] - 14
    fence(k, [(x1 - 150, y0), (x0, y0), (x0, y1), (FX1 + 20, y1)],
          gaps=((1, 150, 300),) + (((0, 180, 420), (1, 560, 760), (2, 330, 520)) if k.damaged else ()))
    fence(k, [(FX0 - 6, FY0 - 16), (FX1 - 40, FY0 - 16)], post_h=72)
    if lv >= 3:                                              # fires either side of the yard's entrance
        for y in (-330, -196):
            k.brazier((-408, y, 0), h=84)
    k.level_flag((-436, -98, 0), height=280.0)
    k.collider((FOOTPRINT[0], FOOTPRINT[1], 0), (FOOTPRINT[2], FOOTPRINT[3], 300))
    k.sockets["label"] = (60.0, 0.0, label)
    k.sockets["popup"] = (-80.0, 170.0, 190.0)


def damage(k):
    """Added to the finished build on the damaged mesh: soot, the burnt field, what fell."""
    z = 8.0
    k.scorch("blot_l", (BURN[0], BURN[1], z), "up", out=1.5)
    k.scorch("blot_w", (BURN[0] - 60, BURN[1] + 120, z), "up", out=1.6)
    k.scorch("blot_m", (BURN[0] + 90, BURN[1] - 70, z), "up", out=1.7)
    for (x, y, a) in ((0, 60, 30), (80, 170, 100), (-40, 190, 160)):       # charred stooks and stakes in the burnt patch
        k.charred((x, y, z + 4), (x + math.cos(math.radians(a)) * 90, y + math.sin(math.radians(a)) * 90, z + 22), size=8)
    k.scorch("blot_s", (104, -398, 228))                     # the cottage, over its breach
    k.scorch("plume_s", (104, -214, 66), flip=True)
    k.rubble((56, -400, 0), (120, 130), 26, slot="Bld_Mudbrick", blocks=7, beams=1, block=(30, 18, 12))
    k.scorch("blot_m", (-110, -230, 0), "up", out=2.0)       # round the burnt haystack
    if k.level < 3:                                          # across the granary's open throat
        k.charred((250, 60, 200), (410, 30, 226), size=9)
    k.rubble((-250, 420, 0), (90, 60), 0, slot="Bld_Mudbrick", blocks=0, beams=2, mound=False)


def site(k):
    fp = FOOTPRINT
    k.footings(fp[0], fp[1], fp[2], fp[3], width=20, height=9, slot="Bld_Mudbrick", top="Bld_Mudbrick")
    k.scaffold(90, -458, 406, -134, height=250, lift=125, bay=160, depth=40, ladder=(2, 0))          # round the cottage
    k.stone_stack((-90, -330, 0), yaw=20, slot="Bld_Mudbrick", block=(40, 22, 14), courses=(4, 4, 3, 3), rows=3)
    k.timber_pile((-270, -250, 0), yaw=-24, length=210, base=3)
    # the field pegged out with stakes and line, a first furrow turned
    c = [(FX0, FY0), (FX1, FY0), (FX1, FY1), (FX0, FY1)]
    for i in range(4):
        (ax, ay), (bx, by) = c[i], c[(i + 1) % 4]
        k.cyl("Bld_Beam", (ax, ay, -4), (ax, ay, 58), 4.0, 3.0, sides=5)
        k.rope((ax, ay, 46), (bx, by, 46), 1.4)
    for i in range(5):
        x = FX0 + 40 + i * 44
        k.box("Bld_Soil", (x, FY0 + 30, 0), (x + 26, FY1 - 30, 9), u0=i * 40.0)
    k.sack((180, -30, 0), 1.0, yaw=40)
    k.sack((204, 4, 0), 0.9, yaw=-20)


def ruin(k):
    with k.at((0, -296, 0)):                                 # the cottage
        k.ruin_rect("Bld_Mudbrick", 108, -144, 388, 144, hmax=108, hmin=16, thick=24, seg=46, gaps=0.2, corners=(0.5, 1, 0.3, 0.8), step=12)
        k.rubble((250, 0, 0), (230, 240), 40, slot="Bld_Mudbrick", blocks=8, beams=3, block=(30, 18, 12))
    r = rect(FX0, FY0, FX1, FY1)                             # the field: scorched earth
    k.wall("Bld_Soil", r, -2, 8, inset=6, u0=0.0, bleach=False)
    k.cap("Bld_Soil", inset_ring(r, 6), 8)
    for (x, y, kind) in ((-240, 60, "blot_l"), (40, 130, "blot_l"), (-120, 320, "blot_w"), (150, 330, "blot_m"), (-320, 280, "blot_m")):
        k.scorch(kind, (x, y, 8), "up", out=1.5)
    for i in range(7):
        x, y, a = k.U(FX0 + 60, FX1 - 60), k.U(FY0 + 50, FY1 - 50), k.U(0, math.pi)
        k.charred((x, y, 11), (x + math.cos(a) * 70, y + math.sin(a) * 70, 11 + k.U(0, 24)), size=7)
    with k.at((336, 44, 0)):                                 # the granary's stump
        k.lathe("Bld_Mudbrick", (0, 0, 0), [(104, 0), (110, 34), (106, 52)], sides=10, rot=18, top="Bld_Soil")
        k.rubble((-10, 6, 52), (150, 150), 26, slot="Bld_Mudbrick", blocks=5, beams=1, block=(30, 18, 12))
    k.blob("Bld_Char", (-96, -214, 0), (190, 180, 70), points=14, squash=0.3)        # the haystack
    k.scorch("blot_l", (-96, -214, 0), "up", out=2.0)
    for (x, y, h) in ((338, 352, 54), (-396, -440, 40)):     # the olives
        k.cyl("Bld_Char", (x, y, -4), (x + 6, y - 4, h), 17.0, 12.0, sides=6, grain="ring")
    x0, y0, y1 = FOOTPRINT[0] + 14, FOOTPRINT[1] + 14, FOOTPRINT[3] - 14
    fence(k, [(250, y0), (x0, y0), (x0, y1), (FX1 + 20, y1)], gaps=((0, 60, 400), (1, 100, 560), (1, 700, 880), (2, 200, 640)), post_h=62)
    k.wheel((-240, -300, 5), radius=38.0, thick=8.0, axis="x")
    k.rubble((-250, -300, 0), (130, 90), 0, slot="Bld_Char", blocks=4, beams=2, mound=False, block=(60, 12, 6))
