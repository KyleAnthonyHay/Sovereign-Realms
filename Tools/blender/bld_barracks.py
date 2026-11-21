"""The barracks: trains Shieldbearers. Authored in Unreal cm, front toward -X (bldkit.py).

A long hall across the back of the plot, sandstone below and timber-framed plaster above under a low terracotta
roof, with a square armoury tower at its right end (battered base, glazed team frieze, crow-stepped merlons). In
front a walled drill yard of packed earth: a gateway between two piers with braziers and the team's standards,
spear racks, practice posts and a straw dummy, shields in the team's stripes on the wall and on a rack, stores
under a striped awning against the tower.

States (bldkit.STATES): `complete`; `damaged` is the same build with the hooks below switched on (k.damaged) plus
damage(); `site` and `ruin` are small meshes of their own on the same footprint.

Levels 1-3 (k.level), the training buildings' shared progression (built up under slate, then fortified):
  2  the hall gains a taller, jettied half-timbered storey under a steep dark slate roof, banners on its front and an
     iron-bound door; the armoury tower climbs a storey and flies a longer standard; the gate piers are raised
  3  fortified: the tower climbs two storeys more, a timber hoarding under its crenellated head and a standard on
     its flat roof; dark stone at the foot of hall and tower, a crenellated yard wall with fires on its corners, creeper
Towers end flat, like the castle's: an oversailing head on a trim corbel course, the glazed frieze, a parapet with
crow-stepped merlons round a roof terrace (rook_head; the range and the stable use it too). No pointed tops.
The level banner (kit.level_flag) stands at the front-left, outside the yard wall's left corner.
"""
import math

from bldkit import STATES, inset_ring, rect  # noqa: F401

NAME = "barracks"
MESH = "SM_Bld_Barracks"
SEED = 43
FOOTPRINT = [-460.0, -440.0, 460.0, 440.0]
RING_RADIUS = 640.0
PREVIEW_FIGURES = [(-560, -70), (-610, 60)]
LEVELS = 3

HX0, HX1, HY0, HY1 = 100.0, 436.0, -424.0, 196.0         # the hall
STONE, EAVE, RISE = 214.0, 300.0, 132.0                  # head of its stonework, wall head, roof rise
TX, TY, TH, H = 304.0, 312.0, 120.0, 520.0               # the armoury tower: centre, half width, parapet top
WX, WY = -427.0, 427.0                                   # centre lines of the yard wall
JETTY, RISE2 = 18.0, 176.0                               # level 2 on: the upper storey's overhang, the slate roof's rise
GATE = 78.0                                              # half width of the gateway
HOLES = ((-1, -262.0, 96.0, 78.0), (-1, 30.0, 150.0, 56.0), (1, -120.0, 84.0, 70.0))      # burnt through the roof (damaged)


def eave(k):
    """The hall's wall head: level 2 rebuilds the upper storey taller."""
    return EAVE + (70.0 if k.level >= 2 else 0.0)


def tower_top(k):
    """The armoury tower's parapet top: a storey more from level 2."""
    return H + (0.0, 110.0, 210.0)[k.level - 1]


def foot(k):
    """The stone of the lowest courses: darker and heavier at level 3."""
    return "Bld_StoneDark" if k.level >= 3 else "Bld_AshlarLarge"


def rook_head(k, r2, top, h, u0=0.0, width=50.0, gap=28.0, thick=24.0):
    """A tower's flat top in the castle's language, on the shaft ring r2 from `top` (= h - 76): a trim corbel course,
    the oversailing head with the glazed team frieze, a parapet with crow-stepped merlons round a roof terrace at
    h - 34. Returns the head's ring."""
    k.band("Bld_Trim", r2, top, top + 12, out=8, u0=u0)
    r3 = inset_ring(r2, -9)
    k.cap("Bld_AshlarLarge", r3, top + 12, down=True, shade=0.55)
    k.wall("Bld_Frieze", r3, top + 12, h, v0=0.0, bleach=False, u0=u0)
    k.parapet("Bld_Ashlar", r3, h - 34, h, thick=thick, top="Bld_Trim")
    k.stepped_merlons("Bld_Ashlar", r3, h, width=width, gap=gap, thick=thick, h1=26, h2=22, broken=0.1, cap="Bld_Trim")
    return r3


def hoarding(k, ring, z, out=40.0):
    """A timber hoarding round a square tower (`ring` = its wall there), floor at z: a planked breast, an open slot
    between posts under a wall plate, a low skirt of slate back to the wall (154 cm in all)."""
    ro = inset_ring(ring, -out)
    k.cap("Bld_Beam", ro, z, down=True, shade=0.6)
    k.wall("Bld_Planks", ro, z, z + 70, bleach=False, u0=k.U(0, 256))
    k.cap("Bld_Planks", ro, z + 70)
    k.wall("Bld_Dark", inset_ring(ring, -(out - 8)), z + 70, z + 112, bleach=False)
    rb = inset_ring(ring, -(out + 3))
    k.cap("Bld_Beam", rb, z + 112, down=True, shade=0.6)
    k.wall("Bld_Beam", rb, z + 112, z + 126, v0=0.0, bleach=False)
    rs, rw = inset_ring(ring, -(out + 10)), inset_ring(ring, -1)
    n = len(ring)
    for i in range(n):
        j = (i + 1) % n
        k.poly("Bld_Slate", [(rs[i][0], rs[i][1], z + 122), (rs[j][0], rs[j][1], z + 122), (rw[j][0], rw[j][1], z + 154), (rw[i][0], rw[i][1], z + 154)])
        (ax, ay), (bx, by) = ro[i], ro[j]
        L = math.hypot(bx - ax, by - ay)
        m = max(int(L / 62), 1)
        ix, iy = -(by - ay) / L * 5, (bx - ax) / L * 5       # a little inside the breast
        for t in range(m):
            f = (t + 0.5) / m
            k.obox("Bld_Beam", (ax + (bx - ax) * f + ix, ay + (by - ay) * f + iy, z + 91), (9, 9, 44))
        k.obox("Bld_Beam", (ax + ix + (bx - ax) / L * 5, ay + iy + (by - ay) / L * 5, z + 91), (10, 10, 44))


def front(ya, yb, **kw):
    """An opening in the hall's front wall between y = ya and yb."""
    return dict(a=(HY1 - 8) - yb, b=(HY1 - 8) - ya, **kw)


def shield(k, pos, r=30.0, lean=0.0, yaw=0.0):
    """A round shield facing local -X: bronze rim and boss, the face in the team's stripes."""
    with k.at(pos, yaw):
        n = (-math.cos(math.radians(lean)), 0.0, math.sin(math.radians(lean)))
        back = (n[0] * -5, 0, n[2] * -5)
        k.cyl("Bld_Bronze", back, (0, 0, 0), r, sides=10, grain="ring", cap_slot="Bld_Awning")
        k.cyl("Bld_Bronze", (0, 0, 0), (n[0] * 7, 0, n[2] * 7), r * 0.3, r * 0.1, sides=6, grain="ring")


def spear_rack(k, pos, yaw=0.0, n=5):
    """Two posts and two rails, spears leaned against them, points up."""
    with k.at(pos, yaw):
        for y in (-62, 62):
            k.cyl("Bld_Beam", (0, y, -4), (0, y, 118), 5.0, 4.2, sides=5)
        k.obox("Bld_Beam", (0, 0, 106), (5, 138, 6), grain="y")
        k.obox("Bld_Beam", (0, 0, 30), (5, 138, 6), grain="y")
        for i in range(n):
            y = (i - (n - 1) / 2) * 24 + k.U(-3, 3)
            k.cyl("Bld_Beam", (-30, y, 0), (5, y, 190), 2.3, sides=4, caps=False)
            k.cyl("Bld_Bronze", (5, y, 190), (8.4, y, 214), 3.6, 0.5, sides=4)


def pell(k, pos, with_shield=True):
    """A practice post: a stout stake bound with straw where the blows land, a cross arm."""
    with k.at(pos, k.U(-20, 20)):
        k.cyl("Bld_Bark", (0, 0, -4), (0, 0, 172), 11.0, 9.0, sides=7, grain="ring", cap_slot="Bld_Beam")
        k.lathe("Bld_Thatch", (0, 0, 78), [(14, 0), (17, 8), (17, 50), (13, 58)], sides=7, top=False)
        k.obox("Bld_Beam", (0, 0, 144), (7, 104, 7), grain="y")
        if with_shield:
            shield(k, (-9, 36, 124), r=26)


def dummy(k, pos, yaw=0.0):
    """A straw man on a stake in a team-coloured tabard, an old bronze cap on his head."""
    with k.at(pos, yaw):
        k.cyl("Bld_Beam", (0, 0, -4), (0, 0, 150), 4.5, 4.0, sides=5)
        k.obox("Bld_Beam", (0, 0, 122), (6, 100, 6), grain="y")
        k.blob("Bld_Thatch", (0, 0, 96), (38, 46, 70), points=10, flat=False, squash=0.2)
        k.blob("Bld_Thatch", (0, 0, 150), (26, 26, 28), points=9, flat=False, squash=0.2)
        k.lathe("Bld_Bronze", (0, 0, 156), [(15, 0), (13, 8), (5, 15)], sides=7)
        for x in (-12, 12):
            k.poly("Bld_Awning", [(x, 30, 126), (x, -30, 126), (x, -24, 66), (x, 24, 66)], [(60, 0), (0, 0), (6, 60), (54, 60)],
                   w=[0.0, 0.0, 0.6, 0.6])


def hall(k):
    u0 = 20.0
    r0 = rect(HX0, HY0, HX1, HY1)
    r1 = k.wall(foot(k), r0, 0, 44, inset=8, u0=u0, bleach=False)
    k.band("Bld_Trim", r1, 44, 52, out=3, u0=u0)
    fx = HX0 + 8
    win = dict(z0=118, z1=176, depth=12, back="Bld_Shutter", reveal="Bld_Trim", shade=0.7, back_shade=0.8)
    wins = (-350, -250, -150) if not k.damaged else (-350, -150)      # damaged: a breach takes the middle one
    ops = {2: [front(-64, 64, z0=52, z1=206, depth=30, back="Bld_Door", back_uv=(64, 50), reveal="Bld_AshlarLarge", shade=0.62, back_shade=0.82)]
           + [front(y - 22, y + 22, **win) for y in wins] + k.breach((HY1 - 8) + 196, (HY1 - 8) + 304, 62, 200),
           3: [dict(a=s - 22, b=s + 22, **win) for s in (96, 224)]}
    r2 = k.wall("Bld_Ashlar", r1, 52, STONE, u0=u0, openings=ops)
    for y in wins:
        k.obox("Bld_Trim", (fx - 4, y, 114), (14, 56, 8))
    E = eave(k)
    if k.level < 2:
        # timber-framed upper storey: a sill plate, posts, small dark lights, the wall plate
        k.band("Bld_Beam", r2, STONE, STONE + 12, out=4, u0=u0)
        light = dict(z0=STONE + 30, z1=EAVE - 26, depth=10, back="Bld_Dark", reveal="Bld_Beam", shade=0.6)
        k.wall("Bld_Plaster", r2, STONE + 12, EAVE, u0=u0, openings={2: [front(y - 16, y + 16, **light) for y in (-300, -200, -100, 100)]})
        y = HY0 + 14
        while y < HY1 - 4:
            k.obox("Bld_Beam", (fx - 2.5, y, (STONE + 12 + EAVE) / 2), (9, 12, EAVE - STONE - 12), grain="z")
            y += 100.0
        for x in (HX0 + 80, HX0 + 168, HX0 + 256):               # and on the sunlit gable end
            k.obox("Bld_Beam", (x, HY0 + 5.5, (STONE + 12 + EAVE) / 2), (12, 9, EAVE - STONE - 12), grain="z")
        k.band("Bld_Beam", r2, EAVE - 10, EAVE + 2, out=5, u0=u0)
        k.gable_end("Bld_Plaster", HX0 + 8, HX1 - 8, HY0 + 8, EAVE, RISE)
        k.obox("Bld_Beam", ((HX0 + HX1) / 2, HY0 + 5.5, EAVE + RISE * 0.42), (12, 9, RISE * 0.84), grain="z")
        k.obox("Bld_Beam", ((HX0 + HX1) / 2, HY0 + 5.5, EAVE + RISE * 0.36), (150, 9, 10))
        k.gable_roof("Bld_RoofTile", HX0 + 8, HX1 - 8, HY0 + 8, HY1, EAVE, RISE, over=36, verge=22, ridge="Bld_RoofTile", holes=HOLES)
    else:
        # level 2 on: a taller half-timbered storey jettied out on beam ends, under a steep slate roof
        k.band("Bld_Beam", r2, STONE, STONE + 12, out=4, u0=u0)
        k.beam_ends("Bld_Beam", (fx, HY1 - 40), (fx, HY0 + 30), STONE + 2, 9, size=(13, 13), out=JETTY + 4)
        k.beam_ends("Bld_Beam", (HX0 + 40, HY0 + 8), (HX1 - 40, HY0 + 8), STONE + 2, 5, size=(13, 13), out=JETTY + 4)
        rj = inset_ring(r2, -JETTY)
        k.cap("Bld_Beam", rj, STONE + 12, down=True, shade=0.6)
        light = dict(z0=STONE + 44, z1=STONE + 96, depth=10, back="Bld_Dark", reveal="Bld_Beam", shade=0.6)
        k.wall("Bld_Timber", rj, STONE + 12, E, u0=u0, v0=0.0, openings={2: [front(y - 16, y + 16, **light) for y in (-344, -216, -88, 104)],
                                                                         3: [dict(a=s - 16, b=s + 16, **light) for s in (112, 240)]})
        k.band("Bld_Beam", rj, E - 10, E + 2, out=4, u0=u0)
        k.gable_end("Bld_Timber", HX0 + 8 - JETTY, HX1 - 8 + JETTY, HY0 + 8 - JETTY, E, RISE2)
        k.gable_roof("Bld_Slate", HX0 + 8 - JETTY, HX1 - 8 + JETTY, HY0 + 8 - JETTY, HY1, E, RISE2, over=24, verge=20, ridge="Bld_Slate", holes=HOLES)
        for y in (-280, -152):                               # the company's banners hung from the jetty
            k.cyl("Bld_Iron", (fx - JETTY - 5, y - 30, STONE + 6), (fx - JETTY - 5, y + 30, STONE + 6), 2.4, sides=4)
            k.hang_cloth((fx - JETTY - 5, y - 24, STONE + 4), (fx - JETTY - 5, y + 24, STONE + 4), 96.0)
    if k.level >= 3:                                         # creeper on the sunlit gable end
        k.patch("Bld_Leaves", (HX0 + 110, HY0, 0), (1, 0, 0), (0, 0, 1), 170, 210, cells=12, fill=0.55, out=11)
    # the door: steps, a bronze sun over the lintel, braziers
    k.steps("Bld_AshlarLarge", HX0 - 58, HX0 + 12, -86, 86, 0, 52, 3, top="Bld_Trim")
    metal = "Bld_Bronze" if k.level < 2 else "Bld_Iron"      # level 2 on: the door is bound in iron
    if k.level < 2:
        k.obox(metal, (fx - 5, 0, STONE + 6), (6, 150, 5))
    for s in (-1, 1):
        k.obox(metal, (fx - 5, s * 76, 130), (5, 8, 156))
        k.brazier((HX0 - 20, s * 122, 0), h=84)
    if k.level >= 2:
        for z in (86, 136, 186):
            k.obox(metal, (fx + 24, 0, z), (4, 124, 9))
    # shields hung on the wall right of the door
    for (y, z) in ((104, 150), (160, 128)):
        if not (k.damaged and y > 150):
            shield(k, (fx - 6, y, z), r=28)


def tower(k):
    u0 = 150.0
    H = tower_top(k)
    r0 = rect(TX - TH, TY - TH, TX + TH, TY + TH)
    r1 = k.wall(foot(k), r0, 0, 110, inset=12, u0=u0, bleach=False)
    k.band("Bld_Trim", r1, 110, 120, out=4, u0=u0)
    side = 2 * (TH - 12)
    slit = lambda a, z: dict(a=a - 6, b=a + 6, z0=z, z1=z + 60, depth=14, back="Bld_Dark", shade=0.5)
    ops = {2: [slit(side / 2 - 64, 270), slit(side / 2 + 64, 270)] + k.breach(118, 196, 300, 420),
           3: [slit(side / 2, 230), slit(side / 2, 360)], 1: [slit(side / 2, 300)]}
    if k.level >= 2:
        ops[2] += [slit(side / 2 - 64, 420), slit(side / 2 + 64, 420)]
        ops[3] += [slit(side / 2, 480)]
    if k.level >= 3:
        ops[3] += [slit(side / 2, 600)]
    top = H - 76
    r2 = k.wall("Bld_Ashlar", r1, 120, top, inset=4, u0=u0, openings=ops)
    k.band("Bld_Trim", r2, top, top + 12, out=8, u0=u0)
    r3 = inset_ring(r2, -9)
    k.cap("Bld_AshlarLarge", r3, top + 12, down=True, shade=0.55)
    k.wall("Bld_Frieze", r3, top + 12, top + 76, v0=0.0, bleach=False, u0=u0)
    k.parapet("Bld_Ashlar", r3, H - 34, H, thick=24, top="Bld_Trim")
    k.stepped_merlons("Bld_Ashlar", r3, H, width=50, gap=28, thick=24, h1=26, h2=22, broken=0.1, cap="Bld_Trim")
    k.brazier((TX - 40, TY + 44, H - 34), h=66)
    for (x, y) in ((TX + 50, TY - 40), (TX + 20, TY + 20)):
        k.crate((x, y, H - 34), (44, 44, 34), yaw=k.U(-20, 20))
    # the standard hung down the front face (longer from level 2)
    bx = TX - TH + 12 - 8
    zb = H - 116
    if k.level >= 3:                                         # fortified: a timber hoarding under the head, a standard on the roof
        zh = top - 176
        hoarding(k, r2, zh)
        k.pole_banner((TX - 34, TY - 40, H - 34), height=220.0)
        k.patch("Bld_Leaves", (TX - TH, TY + 60, 0), (0, -1, 0), (0, 0, 1), 110, 250, cells=12, fill=0.55, out=15)
        bx, zb = bx - 46, zh + 66                            # the hung standard moves out onto the hoarding's breast
    k.cyl("Bld_Bronze", (bx, TY - 42, zb), (bx, TY + 42, zb), 2.6, sides=4)
    k.hang_cloth((bx, TY - 32, zb - 2), (bx, TY + 32, zb - 2), 192.0 if k.level < 2 else 250.0)


def yard_wall(k, a, b, broken=False, u0=0.0, face=2):
    """A stretch of the yard wall between two points on its centre line; `face`: its outward edge (level 3 crenellates it)."""
    if broken and k.damaged:
        k.stub("Bld_Ashlar", a, b, thick=26, hmax=96, hmin=16, seg=46, ends=(1.0, 0.9), gaps=0.34, top="Bld_Trim")
        return
    lo = (min(a[0], b[0]) - 13, min(a[1], b[1]) - 13, 0)
    hi = (max(a[0], b[0]) + 13, max(a[1], b[1]) + 13, 92)
    ring = k.box("Bld_Ashlar", lo, hi, top="Bld_Trim", u0=u0, bleach=True)
    k.band("Bld_Trim", ring, 92, 100, out=3, u0=u0)
    if k.level >= 3:
        k.crenels("Bld_Ashlar", ring, 100, height=40, width=44, gap=34, thick=26, cap="Bld_Trim", edges=(face,))


def yard(k):
    k.box("Bld_Dirt", (WX + 10, -WY + 10, -2), (HX0 + 2, WY - 10, 3), u0=0.0)       # packed earth
    yard_wall(k, (WX, -WY), (WX, -GATE - 24), broken=True, u0=40.0)
    yard_wall(k, (WX, GATE + 24), (WX, WY), u0=300.0)
    yard_wall(k, (WX + 13, -WY), (HX0 - 2, -WY), u0=520.0, face=3)
    yard_wall(k, (WX + 13, WY), (TX - TH - 2, WY), u0=760.0, face=1)
    ph = 150.0 if k.level < 2 else 200.0                     # level 2 raises the piers; level 3 lights the wall's front corners
    for s in (-1, 1):                                        # the gateway: piers, braziers, the standards inside
        k.obox_wall("Bld_AshlarLarge", (WX, s * (GATE + 24), 0), (52, 52, ph), 0.0, cap="Bld_Trim")
        k.brazier((WX, s * (GATE + 24), ph), h=58)
        if k.level >= 3:
            k.brazier((WX, s * WY, 140), h=58)
        if not (k.damaged and s < 0):
            k.pole_banner((WX + 44, s * (GATE + 86), 0), height=330.0)
    k.box("Bld_Trim", (WX - 20, -GATE, 0), (WX + 20, GATE, 5), v0=0.0)
    # drill ground, left of the way in
    if not k.damaged:
        spear_rack(k, (-150, -384, 0), yaw=90, n=6)
    spear_rack(k, (40, -384, 0), yaw=90, n=5)
    pell(k, (-250, -210, 0))
    pell(k, (-130, -290, 0), with_shield=False)
    dummy(k, (-290, -330, 0), yaw=20)
    # right of it: a shield rack, a bench, stores under the awning against the tower
    with k.at((-250, 250, 0), yaw=-12):
        for y in (-70, 70):
            k.cyl("Bld_Beam", (16, y, -4), (0, y, 96), 4.5, 4.0, sides=5)
        k.obox("Bld_Beam", (2, 0, 84), (5, 150, 6), grain="y")
        for i, y in enumerate((-46, 0, 46)):
            shield(k, (-10, y, 44), r=28, lean=14)
    k.obox("Bld_Planks", (-60, 150, 42), (34, 150, 6), grain="y")
    for y in (92, 208):
        k.obox("Bld_Beam", (-60, y, 20), (26, 10, 40), grain="z")
    ax, zb, za = TX - TH - 118, 178.0, 234.0
    k.cloth("Bld_Awning", [(TX - TH + 10, TY + 108, za), (TX - TH + 10, TY - 108, za), (ax, TY - 108, zb), (ax, TY + 108, zb)],
            [(216, 0), (0, 0), (0, 136), (216, 136)], w=[0.0, 0.0, 0.5, 0.5])
    for s in (-1, 1):
        k.cyl("Bld_Beam", (ax + 8, TY + s * 100, 0), (ax + 8, TY + s * 100, zb + 4), 4.2, 3.6, sides=5)
    k.obox("Bld_Beam", (ax + 8, TY, zb + 2), (6, 224, 6), grain="y")
    k.crate((TX - TH - 40, TY - 60, 0), (60, 58, 46), yaw=6)
    k.crate((TX - TH - 44, TY + 6, 0), (54, 54, 42), yaw=-8)
    k.crate((TX - TH - 40, TY - 30, 46), (46, 46, 36), yaw=18)
    k.pot((TX - TH - 36, TY + 70, 0), 1.0)
    k.pot((TX - TH - 84, TY + 84, 0), 0.75)
    k.sack((TX - TH - 96, TY - 70, 0), 1.0, yaw=30)


def build(k, state="complete"):
    if state == "site":
        return site(k)
    if state == "ruin":
        return ruin(k)
    complete(k)
    if k.damaged:
        damage(k)


def complete(k):
    hall(k)
    tower(k)
    yard(k)
    k.collider((FOOTPRINT[0], FOOTPRINT[1], 0), (FOOTPRINT[2], FOOTPRINT[3], 320))
    k.sockets["gate"] = (-520.0, 0.0, 0.0)           # where a recruit appears: just outside the gateway
    k.sockets["rally"] = (-820.0, 0.0, 0.0)          # default rally point, straight out from it
    k.sockets["label"] = (180.0, 0.0, (680.0, 800.0, 1010.0)[k.level - 1])
    k.level_flag((WX - 24, -372.0, 0), height=250.0)
    k.sockets["popup"] = (0.0, 0.0, 420.0)


def damage(k):
    """Added to the finished build on the damaged mesh: soot, what fell, what burnt."""
    fx = HX0 + 8
    k.scorch("smear", (fx, -250, 198))                       # over the breach, up under the eave
    k.scorch("plume_s", (fx, 132, 56))
    k.scorch("lick", (fx, -384, 44), flip=True)
    k.scorch("smear", (TX - TH + 12 - 9, TY + 30, tower_top(k) - 66))   # the tower's frieze
    if k.level >= 2:
        k.scorch("blot_s", (fx - JETTY, 70, STONE + 150))    # the timber storey
    k.scorch("plume_m2", (TX - TH + 12, TY - 60, 122), out=6)
    k.rubble((fx - 62, -250, 0), (130, 170), 34, slot="Bld_Ashlar", blocks=8, beams=1)
    k.rubble((fx - 80, 40, 3), (110, 220), 0, slot="Bld_RoofTile", blocks=8, beams=2, mound=False, block=(34, 26, 6))       # slid tiles
    k.rubble((TX - TH - 30, TY - 150, 0), (90, 110), 0, blocks=4, beams=0, mound=False)
    k.rubble((WX + 30, -250, 0), (110, 300), 0, slot="Bld_Ashlar", blocks=9, beams=0, mound=False, block=(40, 26, 20))
    k.scorch("blot_l", (-150, -340, 3), "up", out=1.5)       # where the spear rack burnt
    for (y, a) in ((-420, 70), (-370, 96), (-330, 60)):
        k.charred((-210, y, 6), (-210 + math.cos(math.radians(a)) * 150, y + math.sin(math.radians(a)) * 150, 10), size=6)
    k.charred((WX + 44, -GATE - 86, 0), (WX + 190, -GATE - 150, 14), size=9)       # the fallen standard's pole
    k.scorch("blot_m", (-80, 260, 3), "up", out=1.5)


def site(k):
    fp = FOOTPRINT
    k.footings(fp[0], fp[1], fp[2], fp[3], width=30, height=12)
    k.scaffold(HX0 - 8, HY0 - 8, HX1 + 8, TY + TH + 6, height=330, lift=165, bay=215, depth=44, ladder=(2, 1))
    k.stone_stack((-250, 210, 0), yaw=14)
    k.stone_stack((-150, 300, 0), yaw=80, courses=(2, 2))
    k.timber_pile((-260, -230, 0), yaw=78, length=230, base=4)
    k.hoist((HX0 - 52, HY0 - 52, 0), height=470, reach=190, yaw=45, load_z=300)
    for s in (-1, 1):                                        # the gateway pegged out
        k.cyl("Bld_Beam", (WX, s * (GATE + 24), -4), (WX, s * (GATE + 24), 70), 4.5, 3.5, sides=5)
    k.rope((WX, -GATE - 24, 56), (WX, GATE + 24, 56), 1.4)


def ruin(k):
    k.box("Bld_Dirt", (WX + 10, -WY + 10, -2), (HX1, WY - 10, 3), u0=0.0)
    k.ruin_rect("Bld_Ashlar", HX0 + 22, HY0 + 22, HX1 - 22, HY1, hmax=128, hmin=20, thick=28, seg=56, gaps=0.22, corners=(1, 0.5, 0.7, 0.3), z=3)
    k.ruin_rect("Bld_AshlarLarge", TX - TH + 14, TY - TH + 14, TX + TH - 14, TY + TH - 14, hmax=144, hmin=32, thick=30, seg=56, gaps=0.1,
                corners=(0.4, 1, 0.8, 0.6), z=3)
    k.rubble((270, -120, 3), (290, 520), 54, slot="Bld_RoofTile", blocks=14, beams=5, block=(40, 30, 8))       # the roof, fallen in
    k.rubble((TX, TY, 3), (190, 190), 60, blocks=7, beams=1)
    k.rubble((40, -230, 3), (150, 260), 30, slot="Bld_Ashlar", blocks=8, beams=1)
    for (a, b) in (((WX, -WY), (WX, -GATE - 24)), ((WX, GATE + 24), (WX, WY)), ((WX + 13, -WY), (HX0 - 2, -WY)), ((WX + 13, WY), (TX - TH - 2, WY))):
        k.stub("Bld_Ashlar", a, b, thick=26, hmax=92, hmin=16, seg=48, ends=(1.0, 0.8), gaps=0.4, top="Bld_Trim")
    for s in (-1, 1):
        k.obox_wall("Bld_AshlarLarge", (WX, s * (GATE + 24), 0), (52, 52, 96 if s > 0 else 56), 0.0)
    k.cyl("Bld_Char", (-250, -210, -4), (-246, -206, 70), 11.0, 9.0, sides=7, grain="ring")        # the practice posts' stumps
    k.cyl("Bld_Char", (-130, -290, -4), (-134, -290, 44), 11.0, 9.0, sides=7, grain="ring")
    for (x, y, kind) in ((-200, -300, "blot_l"), (-120, 240, "blot_l"), (-300, 20, "blot_m"), (20, 60, "blot_w")):
        k.scorch(kind, (x, y, 3), "up", out=1.5)
    k.charred((-60, 120, 6), (60, 250, 60), size=12)
    k.charred((-320, 200, 6), (-200, 300, 10), size=9)
    k.rubble((-390, 150, 3), (60, 200), 0, slot="Bld_Ashlar", blocks=6, beams=0, mound=False)
