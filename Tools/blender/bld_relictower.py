"""The relic tower: an ancient tower raised again on a hilltop relic site. Authored in Unreal cm, front toward -X (bldkit.py).

Older and grander than the watchtower, and a different shape so it reads at a glance: a broad three-stepped plinth, a
square battered base stage of big blocks with the door, a crenellated gallery corbelled out round its head (the lower
archer platform), and out of that an eight-sided shaft of pale stone with two carved rune bands (plain geometric
glyphs, the upper band inlaid with gold), an oversailing eight-sided fighting top with a glazed team frieze (the upper
archer platform) and, on a pier in its middle, the beacon: a wide bronze fire bowl, the highest thing on the building.
Long team banners hang down the shaft's two front diagonal faces and beside the door; moss and creeper on the old stone.

States (bldkit.STATES): `complete`; `damaged` is the same build with breaches, lost merlons, torn banners, soot, a
burnt hole in the top and fallen stone; `site` and `ruin` are their own meshes on the same footprint. The ruin is the
stump: the plinth and the base stage with a ragged head, the first courses of the shaft standing highest at the back.
No levels.

Sockets: label, popup, muzzle (where an archer stands on the top, in front of the beacon pier) and muzzle2 (on the
gallery, in front of the shaft). Like the watchtower it has no gate socket.
"""
import math

from mathutils import Vector

from bldkit import STATES, inset_ring, ngon, rect  # noqa: F401  (STATES: which meshes build_building.py exports)

NAME = "relictower"
MESH = "SM_Bld_RelicTower"
SEED = 47
FOOTPRINT = [-250.0, -250.0, 250.0, 250.0]
RING_RADIUS = 360.0
PREVIEW_FIGURES = [(-390, 130), (-440, -100)]

PLINTH = 72.0          # top of the three steps
BASE = 190.0           # half width of the base stage at its foot
BATTER = 12.0
GALLERY = 380.0        # head of the base stage; the gallery floor is 20 above
SHAFT = 132.0          # apothem of the eight-sided shaft at its foot (on the gallery floor)
SHAFT_IN = 8.0         # its batter
T = 1040.0             # head of the shaft; the fighting top's floor is T + 110, its parapet T + 150
H = T + 150.0
FLOOR = T + 110.0
BEACON = FLOOR + 244.0     # tip of the fire
C8 = math.cos(math.radians(22.5))

# rune glyphs: strokes (x0, y0, x1, y1) in cells of a 4 x 7 box. Plain geometry only.
GLYPHS = [
    [(0, 0, 1, 7), (3, 0, 4, 7), (1, 6, 3, 7)],                                   # gate
    [(0, 0, 4, 1), (0, 1, 1, 5), (1.5, 1, 2.5, 5), (3, 1, 4, 5)],                 # comb
    [(0, 5, 4, 6), (0, 1, 4, 2), (1.5, 3, 2.5, 4)],                               # two bars and a dot
    [(0, 0, 4, 1), (1, 3, 3, 4), (0, 6, 4, 7)],                                   # three bars
    [(0, 1, 4, 2), (0, 5, 4, 6), (0, 2, 1, 5), (3, 2, 4, 5), (1.5, 3, 2.5, 4)],   # square and dot
    [(0, 0, 1, 7), (3, 0, 4, 7), (1, 1, 3, 2), (1, 5, 3, 6)],                     # ladder
    [(0, 0, 1, 7), (3, 0, 4, 7), (1.5, 3, 2.5, 4)],                               # two posts and a dot
    [(0, 0, 1, 4), (3, 3, 4, 7), (1, 3, 3, 4)],                                   # step
]


def octa(apothem):
    """Eight-sided ring with a flat face to the front: edge 3 faces -X, 1 +Y, 5 -Y, 7 +X; 2 and 4 the front diagonals."""
    return ngon(0.0, 0.0, apothem / C8, 8, rot=22.5)


def shaft_ap(z):
    return SHAFT - SHAFT_IN * (z - GALLERY - 20.0) / (T - GALLERY - 20.0)


def edge(ring, i):
    p0, p1 = Vector(ring[i]), Vector(ring[(i + 1) % len(ring)])
    d = p1 - p0
    L = d.length
    d /= L
    return p0, d, Vector((d.y, -d.x)), L


def weathered(k, start):
    """Bleaches the stone built since face `start` from head to foot (UV1.x = 0: the sun-bleached tint of every wall
    head in M_Building), so the old shaft is paler than new work. The Blender preview does not show it."""
    for f in k.faces[start:]:
        if f[0] in ("Bld_Ashlar", "Bld_AshlarLarge"):
            f[3][:] = [0.0 if w < 9000.0 else w for w in f[3]]


def build(k, state="complete"):
    if state == "site":
        return site(k)
    if state == "ruin":
        return ruin(k)
    complete(k)
    if k.damaged:
        damage(k)


# ---------------------------------------------------------------------- parts
def plinth(k):
    for i, half in enumerate((250.0, 232.0, 214.0)):
        k.box("Bld_AshlarLarge", (-half, -half, i * 24.0), (half, half, (i + 1) * 24.0), top="Bld_Trim", u0=20.0 + 70.0 * i)
    k.steps("Bld_AshlarLarge", -286, -214, -62, 62, 0, PLINTH, 3, top="Bld_Trim")


def base_door():
    return dict(a=BASE - 46, b=BASE + 46, z0=PLINTH, z1=PLINTH + 170, depth=40, back="Bld_Door", reveal="Bld_AshlarLarge", shade=0.62, back_shade=0.8)


def slit(side, z, off=0.0):
    return dict(a=side / 2 + off - 6, b=side / 2 + off + 6, z0=z, z1=z + 64, depth=14, back="Bld_Dark", shade=0.5)


def runes(k, slot, z, first=0, cell=8.0, out=2.0, faces=range(8)):
    """One glyph on each face of the shaft, its foot at z: flat strokes a hair proud of the stone (carved and filled)."""
    ring = octa(shaft_ap(z + 3.5 * cell))
    for i in faces:
        p0, d, nrm, L = edge(ring, i)
        s0 = L / 2 - 2 * cell
        for (xa, ya, xb, yb) in GLYPHS[(first + i) % len(GLYPHS)]:
            corners = [(s0 + xa * cell, z + ya * cell), (s0 + xb * cell, z + ya * cell), (s0 + xb * cell, z + yb * cell), (s0 + xa * cell, z + yb * cell)]
            pts = []
            for s, zz in corners:
                p = p0 + d * s + nrm * out
                pts.append((p.x, p.y, zz))
            k.poly(slot, pts)
        for s in (12.0, L - 12.0 - cell):                      # a square stop either side of the glyph
            pts = []
            for ds, dz in ((0, 0), (cell, 0), (cell, cell), (0, cell)):
                p = p0 + d * (s + ds) + nrm * out
                pts.append((p.x, p.y, z + 3 * cell + dz))
            k.poly(slot, pts)


def rune_band(k, slot, z, first, faces=range(8)):
    """A carved band: two string courses with a row of glyphs between them."""
    k.band("Bld_Trim", octa(shaft_ap(z)), z, z + 10, out=5, u0=30.0)
    k.band("Bld_Trim", octa(shaft_ap(z + 84)), z + 84, z + 94, out=5, u0=30.0)
    runes(k, slot, z + 19, first, faces=faces)


def face_banner(k, ring, i, z, drop, width=56.0, out=10.0):
    """A long banner on an iron rod down face i of a ring."""
    p0, d, nrm, L = edge(ring, i)
    mid = p0 + d * (L / 2) + nrm * out
    a, b = mid + d * (width / 2), mid - d * (width / 2)         # left -> right as seen from outside
    ra, rb = mid + d * (width / 2 + 8), mid - d * (width / 2 + 8)
    k.cyl("Bld_Iron", (ra.x, ra.y, z + 2), (rb.x, rb.y, z + 2), 2.8, sides=4)
    k.hang_cloth((a.x, a.y, z), (b.x, b.y, z), drop)


def head_merlons(k, ring, z, thick=22.0):
    """Round the eight-sided top: a pier on every corner and a crow-stepped merlon in the middle of every face."""
    n = len(ring)
    for i in range(n):
        p0, d, nrm, L = edge(ring, i)
        lost = k.drng.random() if k.damaged else 1.0
        v = Vector(ring[i])
        c = v - v.normalized() * (15.0 / C8)
        if not (k.damaged and lost < 0.22):
            k.obox_wall("Bld_Ashlar", (c.x, c.y, z), (26, 26, 26 if (k.damaged and lost < 0.45) else 48), math.degrees(math.atan2(v.y, v.x)),
                        cap=None if (k.damaged and lost < 0.45) else "Bld_Trim", cap_h=6.0)
        m = p0 + d * (L / 2) - nrm * (thick / 2)
        yaw = math.degrees(math.atan2(d.y, d.x))
        lost = k.drng.random() if k.damaged else 1.0
        if k.damaged and lost < 0.3:
            continue
        k.obox_wall("Bld_Ashlar", (m.x, m.y, z), (44, thick, 26), yaw)
        if not (k.damaged and lost < 0.55):
            k.obox_wall("Bld_Ashlar", (m.x, m.y, z + 26), (22, thick, 22), yaw, cap="Bld_Trim", cap_h=6.0)


def beacon(k, pos):
    """The beacon: an eight-sided pier with a gold collar carrying a wide bronze fire bowl. Flames at the texture's own
    scale: a tall one in the middle and four round it."""
    with k.at(pos):
        k.lathe("Bld_Trim", (0, 0, 0), [(46, 0), (46, 12), (34, 12), (30, 96)], sides=8, rot=22.5, top=False)
        k.lathe("Bld_Gold", (0, 0, 96), [(33, 0), (33, 12)], sides=8, rot=22.5, top=False)
        k.lathe("Bld_Trim", (0, 0, 108), [(30, 0), (40, 10), (40, 18)], sides=8, rot=22.5)
        k.lathe("Bld_Bronze", (0, 0, 126), [(16, 0), (40, 10), (52, 26), (54, 34)], sides=8, rot=22.5, top="Bld_Dark")
        z = 156.0
        for (x, y, dz, yaws) in ((0, 0, 24, (0.0, 90.0)), (-22, -16, 0, (20.0,)), (-18, 22, 4, (-25.0,)), (24, 14, 2, (15.0,)), (20, -22, 6, (-15.0,))):
            for yaw in yaws:
                c, s = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
                a, b = (x + s * 32, y - c * 32), (x - s * 32, y + c * 32)
                k.poly("Bld_Flame", [(a[0], a[1], z + dz), (b[0], b[1], z + dz), (b[0], b[1], z + dz + 64), (a[0], a[1], z + dz + 64)],
                       [(0, 64), (64, 64), (64, 0), (0, 0)], w=[0.0, 0.0, 1.0, 1.0])


# ---------------------------------------------------------------------- the finished tower
def complete(k):
    u0 = 12.0
    plinth(k)
    # base stage: big old blocks, battered, the door at the head of the steps
    side = 2 * BASE
    ops = {
        2: [base_door()] + k.breach(236, 330, PLINTH + 150, PLINTH + 262),
        1: [slit(side, 190)],
        3: [slit(side, 190)],
        0: [slit(side, 230)],
    }
    r0 = rect(-BASE, -BASE, BASE, BASE)
    r1 = k.wall("Bld_AshlarLarge", r0, PLINTH, GALLERY, inset=BATTER, u0=u0, openings=ops)
    k.obox("Bld_Trim", (-BASE + 2, 0, PLINTH + 182), (26, 128, 20), grain="y")              # door lintel
    for y in (-58, 58):                                                                      # and jamb stones
        k.obox("Bld_Trim", (-BASE - 1, y, PLINTH + 86), (14, 16, 172), grain="z")
    # the gallery: corbelled out, crenellated; the lower archer platform
    k.band("Bld_Trim", r1, GALLERY, GALLERY + 12, out=12, u0=u0)
    rg = inset_ring(r1, -34)
    k.cap("Bld_AshlarLarge", rg, GALLERY + 12, down=True, shade=0.55)
    k.wall("Bld_AshlarLarge", rg, GALLERY + 12, GALLERY + 60, u0=u0)
    k.parapet("Bld_Ashlar", rg, GALLERY + 20, GALLERY + 60, thick=22, top="Bld_Trim")
    k.stepped_merlons("Bld_Ashlar", rg, GALLERY + 60, width=46, gap=30, thick=22, h1=26, h2=22, broken=0.12, cap="Bld_Trim")
    gx = -(BASE - BATTER) - 34
    k.beam_ends("Bld_Trim", (gx + 34, -150), (gx + 34, 150), GALLERY - 12, 6, size=(22, 22), out=28)     # corbel stones
    for y in (-120, 120):                                                                    # banners beside the door
        k.cyl("Bld_Iron", (gx - 6, y - 30, GALLERY - 2), (gx - 6, y + 30, GALLERY - 2), 2.8, sides=4)
        k.hang_cloth((gx - 6, y - 24, GALLERY - 4), (gx - 6, y + 24, GALLERY - 4), 150.0)

    # the eight-sided shaft
    gz = GALLERY + 20.0
    es = 2 * SHAFT * math.tan(math.radians(22.5))
    sops = {
        3: [slit(es, 470)] + k.breach(14, es - 14, 690, 820),
        1: [slit(es, 700)],
        5: [slit(es, 700)],
        2: [slit(es, 500)],
        4: [slit(es, 500)] + k.breach(10, es - 26, 468, 548),
        7: [slit(es, 600)],
    }
    s0 = octa(SHAFT)
    first = len(k.faces)
    s1 = k.wall("Bld_Ashlar", s0, gz, T, inset=SHAFT_IN, u0=u0, openings=sops)
    k.band("Bld_Trim", s0, gz, gz + 14, out=7, u0=u0, under=False)
    rune_band(k, "Bld_Dark", 566, 0)
    rune_band(k, "Bld_Gold", 846, 3)
    # the fighting top: oversailing, a glazed frieze under the parapet; the upper archer platform
    k.band("Bld_Trim", s1, T, T + 12, out=12, u0=u0)
    s3 = inset_ring(s1, -34)
    k.cap("Bld_AshlarLarge", s3, T + 12, down=True, shade=0.55)
    k.wall("Bld_Frieze", s3, T + 12, T + 70, v0=0.0, bleach=False, u0=u0)
    k.wall("Bld_AshlarLarge", s3, T + 70, FLOOR, u0=u0)
    k.wall("Bld_Ashlar", s3, FLOOR, H, u0=u0)
    k.parapet("Bld_Ashlar", s3, FLOOR, H, thick=22, top="Bld_Trim")
    head_merlons(k, s3, H)
    weathered(k, first)
    for i in range(8):                                                                       # a corbel stone under each corner
        v = Vector(s1[i])
        c = v + v.normalized() * 10.0
        k.obox("Bld_Trim", (c.x, c.y, T - 14), (30, 20, 28), yaw=math.degrees(math.atan2(v.y, v.x)))
    for i in (2, 4):                                                                         # long banners on the front diagonals
        face_banner(k, s1, i, T - 22, 250.0)
    beacon(k, (0, 0, FLOOR))

    # age: creeper up the base and the shaft, moss on the plinth, old stones in the grass
    k.patch("Bld_Leaves", (-BASE + 2, -128, PLINTH), (0, -1, 0), (0, 0, 1), 110, 250, cells=12, fill=0.6, out=10)
    k.patch("Bld_Leaves", (96, -BASE + 4, PLINTH), (1, 0, 0), (0, 0, 1), 150, 210, cells=12, fill=0.55, out=10)
    k.patch("Bld_Leaves", (-60, BASE - 4, PLINTH), (-1, 0, 0), (0, 0, 1), 130, 170, cells=12, fill=0.5, out=10)
    k.patch("Bld_Leaves", (-shaft_ap(gz) - 1, 14, gz), (0, -1, 0), (0, 0, 1), 84, 150, cells=12, fill=0.5, out=8)
    k.patch("Bld_Leaves", (-241, 150, 24), (0, 1, 0), (-1, 0, 0), 150, 34, cells=12, fill=0.75, out=2)
    k.patch("Bld_Leaves", (-223, -150, 48), (0, 1, 0), (-1, 0, 0), 120, 34, cells=12, fill=0.75, out=2)
    for x, y, s in ((-292, 176, 30), (-276, -196, 24), (190, -286, 26), (-300, -120, 16)):
        k.blob("Bld_Rock", (x, y, 4), (s * 2.2, s * 1.8, s * 1.4), points=8)

    k.collider((-250, -250, 0), (250, 250, H))
    k.sockets["label"] = (0.0, 0.0, BEACON + 110.0)
    k.sockets["popup"] = (0.0, 0.0, 1000.0)
    k.sockets["muzzle"] = (-92.0, 0.0, FLOOR)                 # between the parapet and the beacon pier
    k.sockets["muzzle2"] = (-162.0, 0.0, gz)                  # the middle of the gallery walk, in front of the shaft


def damage(k):
    """Added to the finished build on the damaged mesh: soot, the burnt top, what fell."""
    fs = lambda z: -shaft_ap(z)                                # the shaft's front face
    k.scorch("plume_s", (fs(824), 0, 824))                     # the shaft's faces are a metre wide: narrow marks only
    k.scorch("streak", (fs(560), 14, 560), out=5)
    k.scorch("plume_m2", (-BASE + 8, -92, PLINTH + 264))
    k.scorch("lick", (-(BASE - BATTER) - 34, 40, GALLERY + 14), out=4)
    k.scorch("streak", (-(BASE - BATTER), 150, GALLERY - 200), out=4)
    k.burn_hole((-44, 44, FLOOR), (84, 66), yaw=25, soot="blot_s")
    k.charred((-156, 60, GALLERY + 22), (-200, 150, GALLERY + 70), size=10)
    k.rubble((-164, 96, GALLERY + 20), (50, 90), 0, blocks=4, beams=0, mound=False, block=(36, 26, 20))
    k.rubble((-262, 120, 0), (120, 190), 34, blocks=8, beams=1)
    k.rubble((-226, -150, 48), (60, 120), 0, blocks=5, beams=0, mound=False)
    k.rubble((120, -262, 0), (130, 80), 0, blocks=4, beams=0, mound=False)


# ---------------------------------------------------------------------- construction site
def site(k):
    fp = FOOTPRINT
    k.footings(fp[0], fp[1], fp[2], fp[3])
    g = 6.0
    k.scaffold(fp[0] - g, fp[1] - g, fp[2] + g, fp[3] + g, height=1000, lift=250, bay=256, depth=44, ladder=(3, 0), planks=0.35, braces=0.22)
    k.stone_stack((-278, 128, 0), yaw=90, rows=1)             # under the first lift, between the two rows of poles
    k.stone_stack((120, -278, 0), yaw=0, rows=1, courses=(2, 2))
    k.timber_pile((20, 278, 0), length=230, base=2, planks=False)
    k.hoist((-300, -300, 0), height=1060, reach=190, yaw=45, load_z=860)


# ---------------------------------------------------------------------- ruin
def ruin(k):
    """The stump of the ancient tower: the plinth, the base stage to a ragged head, the shaft's first courses standing
    highest at the back, the door a dark gap, the fallen head a heap of big blocks off the front corner."""
    plinth(k)
    side = 2 * BASE
    hz = 236.0                                                  # the base stage still stands solid to here
    f = BATTER * (hz - PLINTH) / (GALLERY - PLINTH)
    door = dict(base_door(), z1=PLINTH + 150, back="Bld_Dark", reveal="Bld_Char")
    r1 = k.wall("Bld_AshlarLarge", rect(-BASE, -BASE, BASE, BASE), PLINTH, hz, inset=f, u0=12.0, openings={2: [door]}, bleach=False)
    k.cap("Bld_Dirt", r1, hz)
    c = BASE - f - 16
    k.ruin_rect("Bld_AshlarLarge", -c, -c, c, c, hmax=150, hmin=16, thick=32, seg=58, z=hz, corners=(0.35, 1.0, 0.8, 0.15), gaps=0.25)
    # the shaft: eight ragged faces, tall at the back, gone at the front
    ring = octa(SHAFT - 15)
    weight = [1.0, 0.8, 0.35, 0.1, 0.1, 0.3, 0.7, 1.0]          # by corner, round from the back right
    for i in range(8):
        k.stub("Bld_Ashlar", ring[i], ring[(i + 1) % 8], thick=30, hmax=330, hmin=24, seg=50, ends=(weight[i], weight[(i + 1) % 8]),
               gaps=0.1, z=hz, step=16.0)
    k.scorch("blot_l", (-10, 10, hz), "up", out=1.5)
    k.rubble((-10, 0, hz), (190, 180), 44, slot="Bld_Ashlar", blocks=9, beams=2)
    k.charred((-120, -110, hz + 4), (30, -20, hz + 96), size=12)
    # the head came down off the front left corner: a heap of big blocks, a merlon or two among them
    k.rubble((-250, -262, 0), (190, 150), 46, blocks=7, beams=1, block=(72, 48, 40))
    k.obox_wall("Bld_Ashlar", (-336, -196, 0), (44, 22, 30), 28.0, cap="Bld_Trim", cap_h=6.0)
    k.rubble((-262, 110, 0), (130, 210), 38, blocks=9, beams=1)
    k.rubble((-230, -130, 48), (60, 150), 0, blocks=5, beams=0, mound=False)
    k.rubble((140, -268, 0), (150, 90), 26, blocks=5, beams=0)
    k.patch("Bld_Leaves", (-BASE + 2, -120, PLINTH), (0, -1, 0), (0, 0, 1), 130, 170, cells=12, fill=0.65, out=10)
    k.patch("Bld_Leaves", (90, -BASE + 4, PLINTH), (1, 0, 0), (0, 0, 1), 170, 170, cells=12, fill=0.6, out=10)
    k.patch("Bld_Leaves", (-241, 150, 24), (0, 1, 0), (-1, 0, 0), 150, 34, cells=12, fill=0.75, out=2)
