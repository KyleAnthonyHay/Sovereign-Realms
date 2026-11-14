"""The farm: produces food. Authored in Unreal cm, front toward -X (bldkit.py).

Read from the tactical zoom through the gold: a field of ripe barley in rows across the screen, a harvested strip
with stooks, a haystack. Beside it a small mudbrick-and-plaster cottage with a reed porch, a beehive granary, a
cart, an olive tree, a scarecrow in the team's colours and a little banner on the roof.
"""
import math

from bldkit import inset_ring, rect

NAME = "farm"
MESH = "SM_Bld_Farm"
SEED = 23
FOOTPRINT = [-440.0, -480.0, 440.0, 480.0]
RING_RADIUS = 620.0
PREVIEW_FIGURES = [(-560, -60), (-600, 60)]

FX0, FX1, FY0, FY1 = -400.0, 256.0, -110.0, 452.0        # the field


def cottage(k):
    x0, x1, y0, y1 = 96.0, 400.0, -452.0, -140.0
    hw = (y1 - y0) / 2
    cy = (y0 + y1) / 2
    with k.at((0, cy, 0)):
        r0 = rect(x0, -hw, x1, hw)
        u0 = 44.0
        r1 = k.wall("Bld_Mudbrick", r0, 0, 64, inset=8, u0=u0, bleach=False)       # the brick footing, left bare
        k.cap("Bld_Mudbrick", r0, 0.5, down=True)
        side = 2 * (hw - 8)
        door = dict(a=side / 2 - 30, b=side / 2 + 50, z0=64, z1=186, depth=18, back="Bld_Planks", reveal="Bld_Mudbrick", shade=0.7,
                    back_shade=0.75, no_sill=True)
        win = dict(a=side / 2 - 124, b=side / 2 - 76, z0=112, z1=172, depth=12, back="Bld_Shutter", reveal="Bld_Mudbrick", shade=0.7)
        win2 = dict(a=120, b=168, z0=112, z1=172, depth=12, back="Bld_Shutter", reveal="Bld_Mudbrick", shade=0.7)
        top = 236.0
        k.wall("Bld_Plaster", r1, 64, top, u0=u0, openings={2: [door, win], 3: [win2]})
        # the doorway reaches the ground: cut the footing too
        k.obox("Bld_Planks", (x0 + 6, hw - 8 - side / 2 - 10, 32), (16, 80, 64), grain="z")
        k.obox("Bld_Beam", (x0 + 2, hw - 8 - side / 2 - 10, 196), (16, 108, 18), grain="y")
        k.obox("Bld_Trim", (x0 - 6, hw - 8 - side / 2 - 10, 3), (40, 96, 6))
        k.beam_ends("Bld_Beam", (x0 + 8, hw - 30), (x0 + 8, -hw + 30), top - 22, 6, size=(14, 14), out=20)
        k.beam_ends("Bld_Beam", (x0 + 30, -hw + 8), (x1 - 30, -hw + 8), top - 22, 5, size=(14, 14), out=20)
        r2 = inset_ring(r1, -3)
        k.cap("Bld_Plaster", r2, top, down=True, shade=0.6)
        k.wall("Bld_Plaster", r2, top, top + 26, u0=u0, bleach=False)
        k.parapet("Bld_Plaster", r2, top + 4, top + 26, thick=20, top="Bld_Plaster")
        # on the roof: sheaves drying, jars, a short standard
        for (x, y, yaw) in ((300, -60, 20), (332, 10, -30), (286, 44, 75)):
            sheaf(k, (x, y, top + 4), lying=True, yaw=yaw)
        k.pot((170, 96, top + 4), 0.8)
        k.pot((214, 110, top + 4), 0.6)
        k.pole_banner((x1 - 44, -hw + 44, top + 4), height=210.0, cloth_w=64.0, cloth_h=192.0)
        # reed porch over the door on two forked posts
        px = x0 - 118
        k.poly("Bld_Thatch", [(x0 + 2, 124, 214), (x0 + 2, -96, 214), (px, -96, 176), (px, 124, 176)],
               [(220, 0), (0, 0), (0, 126), (220, 126)])
        k.poly("Bld_Thatch", [(x0 + 2, -96, 208), (x0 + 2, 124, 208), (px, 124, 170), (px, -96, 170)],
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
        k.lathe("Bld_Thatch", (0, 0, 0), [(r * 0.92, 0), (r, h * 0.2), (r * 0.94, h * 0.5), (r * 0.62, h * 0.82), (r * 0.16, h)], sides=9, rot=11)
        k.cyl("Bld_Beam", (0, 0, h - 20), (4, 2, h + 44), 3.5, 2.5, sides=5)
        k.ladder((r + 34, 6, 0), (r * 0.72, 4, h * 0.72), width=30, rungs=5)


def granary(k, pos):
    """Beehive granary: a mudbrick drum drawing in to a plastered shoulder, under a reed cap."""
    with k.at(pos):
        k.lathe("Bld_Mudbrick", (0, 0, 0), [(104, 0), (110, 40), (106, 150), (92, 196)], sides=10, rot=18)
        k.lathe("Bld_Plaster", (0, 0, 196), [(92, 0), (70, 34), (58, 44)], sides=10, rot=18, top="Bld_Dark")
        k.lathe("Bld_Thatch", (0, 0, 228), [(84, 0), (56, 40), (10, 84)], sides=10, rot=18)
        k.cyl("Bld_Thatch", (0, 0, 306), (0, 0, 326), 9.0, 5.0, sides=6)
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
            if not (abs(x + 150) < 20 and 130 < y + L / 2 < 190):
                k.card("Bld_Wheat", (x + k.U(-2, 2), y, z - 2), (x + k.U(-2, 2), y + L, z - 2), 128, 128, u0=k.U(0, 256), lean=k.U(-10, 6))
            y += L
        x += 32.0
        i += 1
    for (sx, sy) in ((-300, 372), (-96, 392), (112, 366)):
        stook(k, (sx, sy, z))
    scarecrow(k, (-150, 160, z))


def build(k):
    cottage(k)
    field(k)
    granary(k, (336, 44, 0))
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
    fence(k, [(x1 - 150, y0), (x0, y0), (x0, y1), (FX1 + 20, y1)], gaps=((1, 150, 300),))
    fence(k, [(FX0 - 6, FY0 - 16), (FX1 - 40, FY0 - 16)], post_h=72)
    k.collider((FOOTPRINT[0], FOOTPRINT[1], 0), (FOOTPRINT[2], FOOTPRINT[3], 300))
    k.sockets["label"] = (60.0, 0.0, 470.0)
    k.sockets["popup"] = (-80.0, 170.0, 190.0)
