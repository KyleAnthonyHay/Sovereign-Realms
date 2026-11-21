"""The siege workshop: builds Catapults. Authored in Unreal cm, front toward -X (bldkit.py).

An open-sided timber shed, gable to the front: a heavy tiled roof on eight posts with stone pads, tie beams and
king posts, closed only at the back by a mudbrick wall under a glazed team frieze. Inside, a half-built catapult
on its trestle of a frame: three wheels on, the fourth leaning by the door, the throwing arm up against its stop.
Left of the shed the timber yard (poles on bearers, sawn planks), right of it a workbench and rope coils under a
striped awning and the pile of shaped stone shot. A fenced yard with a wide gateway and the team's standards.

States (bldkit.STATES): `complete`; `damaged` is the same build with the hooks below switched on (k.damaged) plus
damage(); `site` and `ruin` are small meshes of their own on the same footprint.

Levels 1-3 (k.level), each adding to the last (medieval and weathered: slate, dark stone, iron; no gold; towers
end flat under a crenellated crown, as the castle's do):
  2  built up: the tiles give way to dark slate, the corner posts stand in stone piers, the back wall is ashlar, a
     stone yard wall replaces the fence, and a square store tower rises at the back left: its head oversails on a
     corbel course over a glazed frieze, crow-stepped merlons round a flat roof, a standard on a pole
  3  fortified: a second tower at the back right, both a storey taller on dark stone with a timber hoarding under
     the head; the yard wall is higher and of dark stone, iron finials on the shed's ridge, fires at the gateway,
     creeper on the old tower
The level banner (kit.level_flag) stands inside the yard's front-left corner.
"""
import math

from mathutils import Vector

from bld_farm import fence
from bldkit import MATERIALS, STATES, inset_ring, rect  # noqa: F401

NAME = "workshop"
MESH = "SM_Bld_Workshop"
SEED = 83
FOOTPRINT = [-500.0, -500.0, 500.0, 500.0]
RING_RADIUS = 730.0
LEVELS = 3
PREVIEW_FIGURES = [(-610, -70), (-660, 60)]

CX = 210.0                                               # the shed's centre (x); it is built turned 90 deg, gable to the front
W, D = 250.0, 250.0                                      # its half width (y) and half depth (x)
EAVE, RISE = 320.0, 170.0
OVER, VERGE = 36.0, 30.0
PX, PY = 234.0, (-234.0, -78.0, 78.0, 234.0)             # the posts: +-x and the four bents (shed frame; +y = the front)
SFX = CX - D                                             # the shed's front (x)
F = 484.0                                                # the fence line
GATE = 140.0                                             # half width of the gateway
CAT = (125.0, -10.0, -28.0)                              # the catapult: x, y, yaw
TOWER_X, TOWER_Y, TOWER_HALF = 414.0, 400.0, 62.0             # the store towers (levels 2 and 3): back corners of the yard
HOLES = ((-1, 70.0, 130.0, 74.0), (1, -80.0, 96.0, 60.0), (1, 150.0, 200.0, 50.0))       # burnt through the tiles (damaged)


def facing(pts, toward):
    """The points ordered so the face's normal points along `toward`."""
    a, b, c = (Vector(p) for p in pts[:3])
    return list(pts) if (b - a).cross(c - a).dot(Vector(toward)) > 0 else list(reversed(pts))


def coil(k, pos, r=20.0, turns=2):
    """A coil of rope lying flat."""
    h = turns * 9.0
    k.lathe("Bld_Thatch", pos, [(r, 0), (r, h), (r * 0.6, h)], sides=7, top="Bld_Dark", rot=k.U(0, 40))


def shot(k, pos, r=21.0):
    """One stone shot, dressed roughly round."""
    k.lathe("Bld_Rock", pos, [(r * 0.5, 0), (r, r * 0.6), (r, r * 1.35), (r * 0.5, r * 1.9)], sides=5, rot=k.U(0, 72), uvo=(k.U(0, 99), k.U(0, 99)))


def stone_shot(k, pos, n=3, r=21.0):
    """A pyramid of roughly rounded stone shot inside a plank kerb."""
    with k.at(pos, k.U(-8, 8)):
        step = r * 1.9
        for layer in range(n):
            m = n - layer
            for i in range(m):
                for j in range(m):
                    x, y = (i - (m - 1) / 2) * step, (j - (m - 1) / 2) * step
                    if not (layer == 0 and m == 3 and i == 1 and j == 1):            # the one nobody sees
                        shot(k, (x + k.U(-2, 2), y + k.U(-2, 2), layer * r * 1.45), r)
        e = n * step / 2 + 8
        for s in (-1, 1):
            k.obox("Bld_Planks", (0, s * e, 8), (2 * e + 6, 6, 16))
            k.obox("Bld_Planks", (s * e, 0, 8), (6, 2 * e + 6, 16), grain="y")


def plank_stack(k, pos, yaw=0.0, length=220.0, layers=5):
    """Sawn planks stacked to season, stickers between the layers."""
    with k.at(pos, yaw):
        for i in range(layers):
            z = 8 + i * 13
            k.obox("Bld_Planks", (k.U(-6, 6), 0, z + 4), (length, 78 - (4 if i % 2 else 0), 8))
            if i < layers - 1:
                for x in (-length * 0.32, length * 0.32):
                    k.obox("Bld_Beam", (x, 0, z + 10.5), (8, 80, 5), grain="y")
        for x in (-length * 0.32, length * 0.32):
            k.obox("Bld_Beam", (x, 0, 4), (12, 90, 8), grain="y")


def workbench(k, pos, yaw=0.0):
    """A joiner's bench: mallet, bronze adze and saw, a coil of rope, a jar of pegs."""
    with k.at(pos, yaw):
        k.obox("Bld_Planks", (0, 0, 78), (210, 66, 8))
        for sx in (-1, 1):
            for sy in (-1, 1):
                k.obox("Bld_Beam", (sx * 92, sy * 25, 37), (9, 9, 74), grain="z")
            k.obox("Bld_Beam", (sx * 92, 0, 22), (7, 52, 7), grain="y")
        k.obox("Bld_Beam", (0, 0, 22), (184, 7, 7))
        k.cyl("Bld_Bark", (-70, -8, 90), (-70, 14, 90), 8.0, sides=6, grain="ring", cap_slot="Bld_Beam")       # mallet
        k.cyl("Bld_Beam", (-70, 3, 90), (-40, 6, 86), 2.4, sides=4)
        k.obox("Bld_Bronze", (-8, -10, 84), (46, 9, 3), yaw=14)                                                   # saw
        k.obox("Bld_Beam", (20, -4, 85), (16, 6, 6), yaw=14)
        k.obox("Bld_Bronze", (48, 16, 85), (8, 20, 5), yaw=-20)                                                   # adze
        k.cyl("Bld_Beam", (50, 14, 85), (84, -6, 85), 2.2, sides=4)
        coil(k, (-34, 18, 82), r=13, turns=1)
        k.pot((86, 14, 82), 0.36)
        k.cyl("Bld_Bark", (-40, -66, 0), (-40, -66, 42), 16.0, sides=7, grain="ring", cap_slot="Bld_Beam")      # a block to sit on


def catapult(k, wreck=False):
    """The half-built engine: frame, three wheels, uprights and stop bar, the skein and the arm; no sling yet."""
    beam = "Bld_Char" if wreck else "Bld_Beam"
    with k.at((CAT[0], CAT[1], 0), CAT[2]):
        if wreck:
            k.obox(beam, (0, -58, 12), (290, 18, 20), yaw=6)
            k.obox(beam, (-20, 50, 12), (240, 18, 20), yaw=-14, roll=20)
            k.obox(beam, (10, -6, 20), (18, 150, 18), yaw=20, grain="y")
            k.charred((80, -90, 10), (-70, 70, 44), size=13)
            k.wheel((-112, -84, 30), radius=40.0, thick=9.0)
            return
        for s in (-1, 1):
            k.obox("Bld_Beam", (0, s * 58, 50), (300, 18, 20))                    # side beams
            k.obox("Bld_Beam", (16, s * 58, 138), (17, 17, 158), grain="z")        # uprights
            k.cyl("Bld_Beam", (-104, s * 58, 60), (12, s * 58, 196), 5.0, sides=4, caps=False)
            k.cyl("Bld_Beam", (118, s * 58, 60), (22, s * 58, 176), 5.0, sides=4, caps=False)
            k.obox("Bld_Bronze", (16, s * 68, 62), (26, 3, 26))                    # washers of the skein
        for x in (-138, -20, 138):
            k.obox("Bld_Beam", (x, 0, 50), (18, 134, 18), grain="y")
        k.obox("Bld_Beam", (16, 0, 214), (18, 152, 18), grain="y")                 # the stop bar and its padding
        k.obox("Bld_Thatch", (10, 0, 214), (24, 58, 24), grain="y")
        k.cyl("Bld_Thatch", (56, -62, 64), (56, 62, 64), 10.0, sides=6)            # the twisted skein
        k.cyl("Bld_Beam", (56, 0, 64), (-16, 0, 300), 8.5, 6.0, sides=6)           # the arm, up against the stop
        k.lathe("Bld_Bronze", (-18, 0, 296), [(5, 0), (17, 5), (21, 16)], sides=7, top="Bld_Dark")
        for (x, s) in ((-100, -1), (-100, 1), (100, -1)):
            k.wheel((x, s * 78, 40), radius=40.0, thick=9.0)
        for x in (-100, 100):
            k.cyl("Bld_Beam", (x, -86, 40), (x, 86, 40), 4.5, sides=5)
        k.crate((100, 62, 0), (40, 40, 38), yaw=20)                               # the corner still on a block


def mat(slot, fallback):
    """A slot of the medieval set, or its stand-in while the kit does not have it yet."""
    return slot if slot in MATERIALS else fallback


SLATE, IRON, DARK, TIMBER = (mat("Bld_Slate", "Bld_RoofTile"), mat("Bld_Iron", "Bld_Bronze"), mat("Bld_StoneDark", "Bld_AshlarLarge"),
                             mat("Bld_Timber", "Bld_Plaster"))


def roof_slot(k):
    """Terracotta tiles at level 1, then dark slate."""
    return SLATE if k.level >= 2 else "Bld_RoofTile"


def tower_h(k):
    """The top of a store tower's parapet."""
    return 570.0 if k.level >= 3 else 470.0


def tower(k, sy):
    """Level 2 on: a square store tower in a back corner of the yard (sy -1 = left), topped as the castle's are: the
    head oversails on a corbel course over the glazed frieze, crow-stepped merlons round a flat roof, a standard on a
    pole. Level 3: taller, on dark stone, a timber hoarding under the head. Returns its top."""
    lv = k.level
    cx, cy, half, h = TOWER_X, sy * TOWER_Y, TOWER_HALF, tower_h(k)
    u0 = 60.0 + sy * 40
    top = h - 76
    r1 = k.wall(DARK if lv >= 3 else "Bld_AshlarLarge", rect(cx - half, cy - half, cx + half, cy + half), 0, 110, inset=10, u0=u0, bleach=False)
    k.band("Bld_Trim", r1, 110, 122, out=4, u0=u0)
    ops = {2: k.breach(18, 84, 126, 236)} if sy < 0 else {}
    r2 = k.wall("Bld_Ashlar", r1, 122, top, inset=4, u0=u0, openings=ops)
    zb = top - 16                                                                # where the standard hangs from
    if lv >= 3:                                                                  # the hoarding: a timber gallery jettied out under the head
        hr = inset_ring(r2, -20)
        z0, z1 = top - 120, top - 6
        k.cap("Bld_Planks", hr, z0, down=True, shade=0.55)
        k.band("Bld_Beam", hr, z0, z0 + 12, out=2, u0=u0)
        k.wall(TIMBER, hr, z0 + 12, z1, u0=0.0, bleach=False)
        k.cap("Bld_Planks", hr, z1)
        zb = z0 - 6
    k.band("Bld_Trim", r2, top, top + 12, out=9, u0=u0)
    r3 = inset_ring(r2, -10)                                                     # the head oversails on the corbel course
    k.cap("Bld_AshlarLarge", r3, top + 12, down=True, shade=0.55)
    k.wall("Bld_Frieze", r3, top + 12, top + 76, v0=0.0, bleach=False, u0=u0)
    k.parapet("Bld_Ashlar", r3, h - 36, h, thick=20, top="Bld_Trim")
    k.stepped_merlons("Bld_Ashlar", r3, h, width=40, gap=24, thick=20, h1=24, h2=20, cap="Bld_Trim")
    pole = 150.0
    k.pole_banner((cx, cy, h - 36), height=pole, cloth_w=52.0, cloth_h=110.0)
    fx = cx - half + 14 - 7                                                      # a long standard down its face
    k.cyl(IRON, (fx, cy - 40, zb), (fx, cy + 40, zb), 2.6, sides=4)
    k.hang_cloth((fx, cy - 32, zb - 2), (fx, cy + 32, zb - 2), 190.0)
    if lv >= 3 and sy < 0 and not k.damaged:                                     # creeper up the old tower's face
        k.patch("Bld_Leaves", (cx - half + 13, cy - 26, 0), (0, -1, 0), (0, 0, 1), 64, 250, cells=12, fill=0.6, out=3)
    return h - 36 + pole + 14


def wall_h(k):
    return 84.0 if k.level >= 3 else 62.0


def yard_wall(k):
    """Level 2 on: the fence becomes a low stone wall (higher and of dark stone at level 3); breached where the fence was broken."""
    d, t, h = k.damaged, 11.0, wall_h(k)
    stone = DARK if k.level >= 3 else "Bld_Ashlar"
    runs = [(-F - t, -F - t, -F + t, -GATE - 16), (-F - t, GATE + 16, -F + t, F + t)]
    for (sy, gap) in ((-1, (-260.0, -30.0)), (1, (-124.0, 76.0))):
        y0, y1 = sy * F - t, sy * F + t
        if d:
            runs += [(-F + t, y0, gap[0], y1), (gap[1], y0, CX, y1)]
            k.rubble(((gap[0] + gap[1]) / 2, sy * F, 0), (gap[1] - gap[0], 70), 16, slot=stone, blocks=5, beams=0, block=(36, 24, 18))
        else:
            runs.append((-F + t, y0, CX, y1))
    for i, (x0, y0, x1, y1) in enumerate(runs):
        k.box(stone, (x0, y0, 0), (x1, y1, h), u0=40.0 * i)
        k.box("Bld_Trim", (x0 - 3, y0 - 3, h), (x1 + 3, y1 + 3, h + 12), top="Bld_Trim", bottom=True, u0=40.0 * i)


def shed(k):
    """Built in its own frame, turned 90 degrees: local +Y is the building's front (-X), local +X is +Y."""
    zr = EAVE + RISE
    with k.at((CX, 0, 0), yaw=90):
        for i, y in enumerate(PY):
            for s in (-1, 1):
                x = s * PX
                k.box("Bld_Trim", (x - 19, y - 19, 0), (x + 19, y + 19, 22), u0=k.U(0, 200))
                if k.damaged and s < 0 and i == 2:                               # a post burnt through; its bent sags on the braces
                    k.obox("Bld_Char", (x, y, 80), (22, 22, 116), grain="z")
                    k.charred((x - 10, y + 10, 8), (x - 150, y + 60, 16), size=20)
                else:
                    k.obox("Bld_Beam", (x, y, 22 + (EAVE - 22) / 2), (22, 22, EAVE - 22), grain="z")
                if k.level >= 2 and i in (0, 3):                                 # the corner posts stand in stone piers
                    k.box("Bld_Ashlar", (x - 28, y - 28, 22), (x + 28, y + 28, EAVE - 96), top="Bld_Trim", u0=k.U(0, 200))
                    k.box("Bld_Trim", (x - 32, y - 32, EAVE - 96), (x + 32, y + 32, EAVE - 84), top="Bld_Trim", bottom=True)
                for dy in (-1, 1):                                               # knee braces up to the plate
                    if -D < y + dy * 60 < D and (i in (0, 3) or dy > 0):
                        k.cyl("Bld_Beam", (x, y, EAVE - 78), (x, y + dy * 62, EAVE - 10), 4.6, sides=4, caps=False)
                if i == 3:
                    k.cyl("Bld_Beam", (x, y, EAVE - 84), (x - s * 66, y, EAVE - 16), 4.6, sides=4, caps=False)   # and to the tie beam
            k.obox("Bld_Beam", (0, y, EAVE - 9), (2 * PX + 34, 16, 18))                                          # tie beam
            if i in (0, 3) or not k.damaged:
                k.obox("Bld_Beam", (0, y, EAVE + (RISE - 16) / 2), (14, 14, RISE - 16), grain="z")              # king post
            if i == 3:
                for s in (-1, 1):
                    k.cyl("Bld_Beam", (s * 16, y, EAVE + 4), (s * 128, y, EAVE + RISE * (1 - 128 / W) - 8), 5.0, sides=4, caps=False)
        for s in (-1, 1):
            k.obox("Bld_Beam", (s * PX, 0, EAVE + 2), (18, 2 * D + 16, 16), grain="y")                           # wall plates
        # the back wall and its frieze, seen through the shed
        r0 = rect(-W, -D, W, -D + 26)
        back = "Bld_Ashlar" if k.level >= 2 else "Bld_Mudbrick"
        k.wall(back, r0, 0, EAVE - 64, u0=40.0, bleach=False)
        k.cap(back, r0, 0.5, down=True)
        k.wall("Bld_Frieze", r0, EAVE - 64, EAVE, v0=0.0, bleach=False, u0=40.0)
        k.gable_end("Bld_Planks", -W, W, -D + 26, EAVE, RISE, facing=1)
        k.gable_end("Bld_Planks", -W, W, -D, EAVE, RISE, facing=-1)
        # the pediment over the open front: boards, a bronze sun
        zp = EAVE + RISE * 0.56
        hw = W * (1 - 0.56)
        k.poly("Bld_Planks", facing([(-hw, D, zp), (hw, D, zp), (0, D, zr)], (0, 1, 0)))
        k.poly("Bld_Planks", facing([(-hw, D - 2, zp), (hw, D - 2, zp), (0, D - 2, zr)], (0, -1, 0)), shade=0.6)
        k.obox("Bld_Beam", (0, D + 2, zp), (2 * hw + 10, 10, 12))
        k.cyl("Bld_Bronze", (0, D + 1, zp + 30), (0, D + 7, zp + 30), 15.0, sides=8, grain="ring")
        k.gable_roof(roof_slot(k), -W, W, -D, D, EAVE, RISE, over=OVER, verge=VERGE, ridge=roof_slot(k), holes=HOLES, ceiling=False)
        if k.level >= 3:                                                         # iron on the ridge's ends
            for y in (-D - VERGE + 14, D + VERGE - 14):
                k.finial((0, y, zr - 2), slot=IRON, h=74, r=15)
        ze = EAVE - OVER * RISE / W
        for s in (-1, 1):                                                        # the roof's underside: boards
            pts = [(0, -D - VERGE, zr - 6), (0, D + VERGE, zr - 6), (s * (W + OVER), D + VERGE, ze - 6), (s * (W + OVER), -D - VERGE, ze - 6)]
            k.poly("Bld_Planks", facing(pts, (0, 0, -1)), shade=0.62)
        # the standards, hung down the front posts
        for s in (-1, 1):
            fy = D + (16 if k.level >= 2 else 4)                                 # clear of the stone piers
            k.cyl("Bld_Bronze", (s * PX - 40, fy, 300), (s * PX + 40, fy, 300), 2.6, sides=4)
            k.hang_cloth((s * PX - 32, fy + 1, 298), (s * PX + 32, fy + 1, 298), 192.0)
        # stores along the back wall
        k.crate((-170, -D + 62, 0), (64, 56, 46), yaw=4)
        k.crate((-166, -D + 60, 46), (48, 46, 36), yaw=-10)
        k.pot((-96, -D + 60, 0), 1.0)
        coil(k, (150, -D + 66, 0), r=24, turns=3)
        for i in range(3):                                                       # arm blanks leaned in the corner
            k.cyl("Bld_Beam", (196 - i * 16, -D + 96, 0), (212 - i * 10, -D + 30, 250), 5.5, 4.5, sides=5)


def yard(k):
    d = k.damaged
    k.box("Bld_Dirt", (-F + 8, -F + 8, -2), (F - 8, F - 8, 3), u0=0.0)           # packed earth
    if k.level >= 2:
        yard_wall(k)
    else:
        fence(k, [(CX, -F), (-F, -F), (-F, -GATE)], gaps=((0, 240, 470),) if d else (), step=116)
        fence(k, [(-F, GATE), (-F, F), (CX, F)], gaps=((1, 360, 560),) if d else (), step=116)
    for s in (-1, 1):                                        # the gateway: stout posts with bronze caps, the standards
        k.cyl("Bld_Bark", (-F, s * GATE, -4), (-F, s * GATE, 190), 11.0, 9.0, sides=7, grain="ring", cap_slot="Bld_Beam")
        k.lathe("Bld_Bronze", (-F, s * GATE, 190), [(11, 0), (9, 6), (1, 20)], sides=7)
        k.cyl("Bld_Beam", (-F + 4, s * (GATE + 72), 4), (-F, s * GATE, 130), 4.0, sides=4, caps=False)
    k.wheel((SFX - 30, PX - 74, 40), radius=40.0, thick=9.0, axis="x")             # the fourth wheel, by the front post
    # the timber yard, left
    k.timber_pile((150, -392, 0), yaw=3, length=320, base=4)
    if not d:
        k.timber_pile((-250, -380, 0), yaw=-8, length=250, base=3, planks=False)
    plank_stack(k, (-60, -330, 0), yaw=86, length=190, layers=4)
    k.cyl("Bld_Bark", (-420, -250, 14), (-200, -236, 14), 14.0, 12.0, sides=6, cap_slot="Bld_Beam")       # a trunk waiting for the saw
    # right: the bench and the rope under an awning, the shot
    ax0, ax1, ay0, ay1, za, zb = 70.0, 350.0, W + OVER + 6, 446.0, 250.0, 190.0
    k.cloth("Bld_Awning", [(ax1, ay0, za), (ax0, ay0, za), (ax0, ay1, zb), (ax1, ay1, zb)],
            [(ax1 - ax0, 0), (0, 0), (0, 164), (ax1 - ax0, 164)], w=[0.0, 0.0, 0.4, 0.4])
    for x in (ax0 + 8, ax1 - 8):
        k.cyl("Bld_Beam", (x, ay1 - 6, 0), (x, ay1 - 6, zb + 4), 4.6, 4.0, sides=5)
        k.cyl("Bld_Beam", (x, ay0 + 4, 0), (x, ay0 + 4, za + 4), 4.6, 4.0, sides=5)
    k.obox("Bld_Beam", ((ax0 + ax1) / 2, ay1 - 6, zb + 2), (ax1 - ax0 + 14, 6, 6))
    k.obox("Bld_Beam", ((ax0 + ax1) / 2, ay0 + 4, za + 2), (ax1 - ax0 + 14, 6, 6))
    workbench(k, (220, 384, 0), yaw=2)
    coil(k, (92, 350, 0), r=26, turns=3)
    coil(k, (30, 396, 0), r=22, turns=2)
    k.cyl("Bld_Thatch", (20, 330, 10), (-40, 352, 10), 10.0, sides=6)             # a bundle of sinew cord
    stone_shot(k, (-190, 372, 0), n=3)
    for (x, y) in ((-96, 330), (-286, 440), (-110, 420)):
        shot(k, (x, y, 0))
    k.obox("Bld_Trim", (-330, 330, 14), (56, 40, 28), yaw=24)                    # a block waiting to be dressed


def build(k, state="complete"):
    if state == "site":
        return site(k)
    if state == "ruin":
        return ruin(k)
    complete(k)
    if k.damaged:
        damage(k)


def complete(k):
    shed(k)
    catapult(k)
    yard(k)
    top = EAVE + RISE
    if k.level >= 2:
        top = tower(k, -1)
    if k.level >= 3:
        tower(k, 1)
        for s in (-1, 1):                                    # fires on the wall either side of the gateway
            k.brazier((-F, s * (GATE + 96), wall_h(k) + 12), h=64)
    k.level_flag((-448, -340, 0), height=300.0)
    k.collider((FOOTPRINT[0], FOOTPRINT[1], 0), (FOOTPRINT[2], FOOTPRINT[3], 360))
    k.sockets["gate"] = (-570.0, 0.0, 0.0)           # where a catapult appears: just outside the gateway
    k.sockets["rally"] = (-870.0, 0.0, 0.0)          # default rally point, straight out from it
    k.sockets["label"] = (200.0, 0.0, max(680.0, top + 50.0))
    k.sockets["popup"] = (0.0, 0.0, 460.0)


def damage(k):
    """Added to the finished build on the damaged mesh: soot, what fell, what burnt."""
    k.rubble((SFX - 70, -90, 3), (120, 240), 0, slot=roof_slot(k), blocks=10, beams=2, mound=False, block=(34, 26, 6))      # slid tiles
    k.rubble((120, -150, 3), (150, 150), 0, slot=roof_slot(k), blocks=6, beams=1, mound=False, block=(34, 26, 6))
    k.scorch("blot_l", (-250, -350, 3), "up", out=1.5)       # where the pole stack burnt
    for (y, a) in ((-420, 4), (-392, -8), (-350, 8)):
        k.charred((-360, y, 8), (-360 + math.cos(math.radians(a)) * 230, y + math.sin(math.radians(a)) * 230, 12), size=14)
    k.scorch("blot_m", (200, 370, 3), "up", out=1.5)         # under the burnt awning
    k.scorch("plume_m", (SFX - 12, -PX, 60), out=14)
    k.scorch("blot_w", (-380, 60, 3), "up", out=1.5)
    k.charred((300, 470, 6), (420, 440, 10), size=7)
    if k.level >= 2:                                         # the left tower: soot over its breach, what fell from it
        fx = TOWER_X - TOWER_HALF + 14
        k.scorch("plume_m", (fx, -TOWER_Y + 10, 236))
        k.rubble((fx - 50, -TOWER_Y + 10, 3), (90, 110), 22, blocks=5, beams=0)
    if k.level >= 3:
        k.scorch("smear", (TOWER_X - TOWER_HALF + 4, TOWER_Y - 10, tower_h(k) - 66), flip=True)       # the right tower's frieze


def site(k):
    fp = FOOTPRINT
    k.footings(fp[0], fp[1], fp[2], fp[3], width=22, height=9, slot="Bld_Trim", top="Bld_Trim")
    k.scaffold(SFX - 8, -W - 8, CX + D + 8, W + 8, height=310, lift=155, bay=260, depth=42, ladder=(2, 1))
    k.timber_pile((-250, -370, 0), yaw=-8, length=260, base=4)
    k.timber_pile((-300, 360, 0), yaw=80, length=230, base=3)
    k.stone_stack((-120, 380, 0), yaw=14, courses=(2, 2))
    k.hoist((SFX - 56, -W - 60, 0), height=450, reach=190, yaw=40, load_z=300)
    for i in range(4):                                       # roof tiles stacked on edge
        k.obox("Bld_RoofTile", (-100 + i * 9, -250, 18), (6, 60, 36), yaw=4)
    for s in (-1, 1):                                        # the gateway pegged out
        k.cyl("Bld_Beam", (-F, s * GATE, -4), (-F, s * GATE, 70), 4.5, 3.5, sides=5)
    k.rope((-F, -GATE, 56), (-F, GATE, 56), 1.4)


def ruin(k):
    k.box("Bld_Dirt", (-F + 8, -F + 8, -2), (F - 8, F - 8, 3), u0=0.0)
    hs = (98, 44, 76, 30, 90, 58, 26, 84)
    n = 0
    for y in PY:                                             # the posts' stumps on their pads
        for s in (-1, 1):
            wx, wy = CX - y, s * PX
            k.box("Bld_Trim", (wx - 19, wy - 19, 0), (wx + 19, wy + 19, 22), u0=k.U(0, 200))
            k.obox("Bld_Char", (wx, wy, 22 + hs[n] / 2), (22, 22, hs[n]), grain="z", yaw=k.U(-8, 8))
            n += 1
    k.stub("Bld_Mudbrick", (CX + D - 13, -W), (CX + D - 13, W), thick=26, hmax=104, hmin=20, seg=50, ends=(1.0, 0.6), gaps=0.2, step=12, z=3)
    k.rubble((CX + 10, 10, 3), (340, 360), 46, slot="Bld_RoofTile", blocks=16, beams=6, block=(40, 30, 8))       # the roof, fallen in
    k.rubble((SFX - 50, -120, 3), (110, 220), 0, slot="Bld_RoofTile", blocks=7, beams=1, mound=False, block=(36, 28, 7))
    catapult(k, wreck=True)
    for (x, y) in ((-190, 372), (-150, 340), (-230, 400), (-96, 330), (-286, 440), (-160, 410), (-210, 330)):   # the shot outlasts the rest
        shot(k, (x, y, 0))
    fence(k, [(CX, -F), (-F, -F), (-F, -GATE)], gaps=((0, 150, 520), (1, 120, 250)), post_h=64, step=116)
    fence(k, [(-F, GATE), (-F, F), (CX, F)], gaps=((0, 80, 220), (1, 250, 560)), post_h=64, step=116)
    k.cyl("Bld_Char", (-F, -GATE, -4), (-F + 3, -GATE, 100), 11.0, 9.0, sides=7, grain="ring")
    k.cyl("Bld_Char", (-F, GATE, -4), (-F, GATE + 2, 54), 11.0, 9.0, sides=7, grain="ring")
    for (x, y, kind) in ((150, -350, "blot_l"), (-250, -350, "blot_l"), (200, 380, "blot_m"), (-320, 40, "blot_w"), (-40, -60, "blot_m")):
        k.scorch(kind, (x, y, 3), "up", out=1.5)
    for (a, b) in (((20, -420, 8), (280, -400, 14)), ((40, -370, 8), (300, -376, 12)), ((-340, -400, 8), (-150, -350, 12)),
                   ((90, 330, 6), (260, 420, 12)), ((-80, 120, 6), (-10, 250, 60))):
        k.charred(a, b, size=13)
