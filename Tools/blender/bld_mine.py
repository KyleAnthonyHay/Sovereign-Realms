"""The gold mine: produces gold. Authored in Unreal cm, front toward -X (bldkit.py).

Read at a glance as dark opening + timber frame + gold: an adit under a heavy timber set, cut into a rock outcrop
(turf on its top, ore showing in the face), a track of sleepers and rails with a loaded cart, crates and baskets of
washed gold under a striped awning, a windlass over a side shaft, a spoil heap, a tool rack, lanterns, a banner.

States (bldkit.STATES): `complete`; `damaged` is the same build with the hooks below switched on (k.damaged) plus
damage(); `site` and `ruin` are small meshes of their own on the same footprint.

Levels 1-3 (k.level), each adding to the last. Towers end flat and crenellated, like a chess rook (the castle's
language: an oversailing head on a trim corbel course, a glazed frieze, crow-stepped merlons, a banner on the roof):
  2  the timber set at the mouth is rebuilt as a stone portal (ashlar piers, an iron-bound timber lintel, crow-stepped
     merlons, banners) and a square crenellated stone lookout with a glazed head stands on the crest, a banner on it
  3  fortified: the portal stands on dark heavy stone between two crenellated pylons; the lookout rises a storey in
     dark stone with a timber hoarding under its head; fires beside it, creeper on the stone
The level banner (kit.level_flag) stands on the ground at the front-left, left of the stores' awning.
"""
import math

from bldkit import STATES, clip_ring, convex_ring, inset_ring, rect  # noqa: F401

NAME = "mine"
MESH = "SM_Bld_Mine"
SEED = 37
FOOTPRINT = [-400.0, -420.0, 420.0, 420.0]
RING_RADIUS = 580.0
LEVELS = 3
PREVIEW_FIGURES = [(-520, -120), (-560, 0)]

MOUTH_X = -30.0          # the cliff face the adit is cut into
AW, AH = 86.0, 204.0     # adit half width, height


def outcrop(k):
    """A stepped bluff like the field's own terraces (coursed cliff faces, turf tops), the adit cut through its
    lowest face. The base tier is three convex pieces, so the tunnel is a real gap that falls into shadow."""
    base = convex_ring([(MOUTH_X, -220), (MOUTH_X, 220), (56, 344), (206, 412), (350, 362), (418, 196), (418, -176), (342, -352), (192, -412), (48, -338)])
    h1 = 252.0
    left = clip_ring(base, 1, -AW, True)
    right = clip_ring(base, 1, AW, False)
    mid = clip_ring(clip_ring(clip_ring(base, 1, -AW, False), 1, AW, True), 0, 200.0, True)
    for ring, u0 in ((left, 0.0), (right, 300.0)):
        k.wall("Bld_Cliff", ring, -6, h1, v0=0.0, bleach=False, u0=u0)
        k.cap("Bld_Turf", ring, h1)
    k.wall("Bld_Cliff", mid, AH, h1, v0=0.0, bleach=False, u0=140.0)
    k.cap("Bld_Turf", mid, h1)
    k.cap("Bld_Dark", mid, AH, down=True)
    back = clip_ring(clip_ring(clip_ring(base, 1, -AW, False), 1, AW, True), 0, 200.0, False)
    k.wall("Bld_Cliff", back, -6, h1, v0=0.0, bleach=False, u0=40.0)
    k.cap("Bld_Turf", back, h1)
    tiers = [
        (h1, 372.0, [(34, -196), (44, 190), (124, 300), (250, 344), (362, 272), (402, 100), (392, -150), (300, -302), (160, -332), (62, -272)]),
        (372.0, 468.0, [(140, -150), (132, 122), (200, 232), (300, 232), (372, 120), (372, -112), (290, -232), (190, -232)]),
        (468.0, 536.0, [(212, -72), (216, 82), (280, 132), (340, 62), (336, -72), (270, -122)]),
    ]
    for i, (z0, z1, pts) in enumerate(tiers):
        ring = convex_ring(pts)
        top = k.wall("Bld_Cliff", ring, z0, z1, inset=8, v0=0.0, bleach=False, u0=70.0 * (i + 1))
        k.cap("Bld_Turf", top, z1)
    # boulders at the foot and on the ledges
    for (x, y, z, sx, sy, sz) in ((16, -376, 16, 150, 120, 130), (-10, 362, 12, 130, 130, 110), (-62, 326, 4, 70, 60, 50), (60, -250, h1 + 10, 90, 80, 70),
                                  (110, 260, h1 + 6, 70, 80, 56), (300, -200, 372 + 8, 80, 70, 60)):
        k.blob("Bld_Rock", (x, y, z), (sx, sy, sz), points=12)
    # inside: floor, back wall, a second timber set receding into the dark
    k.poly("Bld_Dark", [(MOUTH_X - 40, -AW, 1.5), (MOUTH_X - 40, AW, 1.5), (199, AW, 1.5), (199, -AW, 1.5)])
    k.poly("Bld_Dark", [(150, AW, 0), (150, -AW, 0), (150, -AW, AH), (150, AW, AH)])
    timber_set(k, 60.0, AW - 18, AH - 26, post=18, shade=True)
    # gold showing in the face round the mouth
    for (y, z, s) in ((-150, 150, 64), (140, 96, 56), (-124, 56, 46), (176, 204, 50), (-30, 232, 40), (-196, 214, 40)):
        k.blob("Bld_Ore", (MOUTH_X + 2, y, z), (30, s, s * 0.8), points=9, flat=False, squash=0.2)


def timber_set(k, x, hw, h, post=26.0, shade=False, broken=False):
    """One mining set: two raking posts and a cap beam. broken: one post snapped and burnt, the cap down."""
    slot = "Bld_Beam"
    if broken:
        k.obox(slot, (x, -(hw + post * 0.3), h / 2), (post, post, h + 6), roll=-3.0, grain="z")
        k.obox("Bld_Char", (x, hw + post * 0.3, h * 0.2), (post, post, h * 0.4), roll=3.0, grain="z")
        k.charred((x - 4, -hw - 10, h + post * 0.2), (x - 16, hw + 30, 24), size=post)
        return
    for s in (-1, 1):
        k.obox(slot, (x, s * (hw + post * 0.3), h / 2), (post, post, h + 6), roll=s * 3.0, grain="z")
    k.obox(slot, (x, 0, h + post * 0.42), (post + 4, hw * 2 + post * 2.4, post), grain="y")
    if not shade:
        for s in (-1, 1):                                    # bronze dogs pinning the cap
            k.obox("Bld_Bronze", (x - post / 2 - 1.5, s * hw, h + post * 0.4), (3, 8, post + 6))


PX0, PX1, PW, PZ = -88.0, MOUTH_X + 6.0, 208.0, 304.0     # the stone portal of level 2 on: front, back, half width, top


def stone_portal(k):
    """Level 2 on: the mouth dressed in stone: two ashlar piers, a block over them on an iron-bound timber lintel,
    crow-stepped merlons, banners down the piers. Level 3: dark heavy stone below, a slate-capped turret on each end,
    creeper. Damaged: the right half of the head has come down."""
    lv = k.level
    y1 = PW if not k.damaged else -6.0
    zb = 96.0                                                # level 3: dark stone up to here
    for s in (-1, 1):
        ya, yb = (-PW, -AW) if s < 0 else (AW, PW)
        u0 = 20.0 if s < 0 else 320.0
        if lv >= 3:
            k.box("Bld_StoneDark", (PX0 - 6, ya - (6 if s < 0 else 0), 0), (PX1, yb + (6 if s > 0 else 0), zb), u0=u0, top="Bld_Trim")
            k.box("Bld_AshlarLarge", (PX0, ya, zb), (PX1, yb, AH + 8), u0=u0, top="Bld_Trim")
        else:
            k.box("Bld_AshlarLarge", (PX0, ya, 0), (PX1, yb, AH + 8), u0=u0, top="Bld_Trim")
    k.obox("Bld_Beam", (PX0 - 4, (y1 - PW) / 2 if k.damaged else 0, AH + 22), (26, (y1 + PW) if k.damaged else AW * 2 + 84, 30), grain="y")
    for y in ((-AW - 36, -AW + 10, 0, AW - 10, AW + 36) if not k.damaged else (-AW - 36, -AW + 10)):     # iron straps on the lintel
        k.obox("Bld_Iron", (PX0 - 5, y, AH + 22), (30, 10, 34))
    k.box("Bld_Ashlar", (PX0, -PW, AH + 8), (PX1, y1, PZ - 14), u0=60.0, bottom=True)
    k.box("Bld_Trim", (PX0 - 6, -PW - 6, PZ - 14), (PX1, y1 + (6 if not k.damaged else 0), PZ), v0=0.0, u0=60.0, bottom=True)
    head = rect(PX0 - 6, -PW - 6, PX1, y1 + (6 if not k.damaged else 0))
    L = y1 + PW + 12
    k.stepped_merlons("Bld_Ashlar", head, PZ, width=50, gap=28, thick=24, h1=26, h2=22, cap="Bld_Trim", edges=(2,),
                      skip_spans={2: [(0, 100), (L - 100, L)] if not k.damaged else [(L - 100, L)]} if lv >= 3 else None)
    for s in (-1, 1):                                        # banners down the piers on iron rods
        y = s * (AW + 62)
        k.cyl("Bld_Iron", (PX0 - 8, y - 40, 200), (PX0 - 8, y + 40, 200), 2.6, sides=4)
        k.hang_cloth((PX0 - 8, y - 32, 198), (PX0 - 8, y + 32, 198), 150.0)
    if lv >= 3:
        for s in (-1, 1):
            if k.damaged and s > 0:                          # the right turret went with the head
                continue
            ya, yb = (-PW - 10, -PW + 100) if s < 0 else (PW - 100, PW + 10)
            pr = rect(PX0 - 10, ya, PX1, yb)
            k.wall("Bld_AshlarLarge", pr, PZ - 14, PZ + 60, u0=100.0)
            k.band("Bld_Trim", pr, PZ + 60, PZ + 70, out=6)
            ph = inset_ring(pr, -6)
            k.cap("Bld_AshlarLarge", ph, PZ + 70, down=True, shade=0.55)
            k.wall("Bld_Frieze", ph, PZ + 70, PZ + 118, v0=0.0, bleach=False, u0=100.0)
            k.parapet("Bld_Ashlar", ph, PZ + 96, PZ + 118, thick=18, top="Bld_Trim")
            k.stepped_merlons("Bld_Ashlar", ph, PZ + 118, width=36, gap=22, thick=18, h1=20, h2=16, cap="Bld_Trim")
            k.obox("Bld_Dark", (PX0 - 10, (ya + yb) / 2, PZ + 26), (6, 11, 44))
        k.patch("Bld_Leaves", (PX0 - 2, 150, 0), (0, -1, 0), (0, 0, 1), 110, 250, cells=12, fill=0.55, out=14)
    if k.damaged:
        k.rubble((-150, 120, 0), (130, 170), 40, blocks=9, beams=1)
        k.scorch("smear", (PX0, -90, PZ - 150), out=5)
    # inside the stone: the first timber set, in the dark
    timber_set(k, MOUTH_X + 14, AW - 6, AH - 8, post=20, shade=True)


def lookout(k):
    """Level 2 on: a square stone lookout on the crest of the outcrop: an oversailing glazed head, crow-stepped merlons,
    a banner on its roof. Level 3: a storey taller in dark stone, a timber hoarding under the head. Returns the top
    of its stonework."""
    lv = k.level
    cx, cy, half = 276.0, 4.0, 82.0
    z0, zt = 440.0, (800.0 if lv >= 3 else 700.0)
    r0 = rect(cx - half, cy - half, cx + half, cy + half)
    side = 2 * half
    win = dict(depth=13, back="Bld_Dark", reveal="Bld_Trim", shade=0.55)
    ops = {2: [dict(a=side / 2 + y - 7, b=side / 2 + y + 7, z0=552, z1=612, **win) for y in (-34, 34)] + k.breach(26, 92, 540, 640)}
    r1 = k.wall("Bld_StoneDark" if lv >= 3 else "Bld_AshlarLarge", r0, z0, zt - 66, inset=5, u0=220.0, openings=ops, bleach=False)
    k.band("Bld_Trim", r1, zt - 66, zt - 54, out=8)
    r3 = inset_ring(r1, -9)
    k.cap("Bld_AshlarLarge", r3, zt - 54, down=True, shade=0.55)
    k.wall("Bld_Frieze", r3, zt - 54, zt, v0=0.0, bleach=False, u0=220.0)
    k.parapet("Bld_Ashlar", r3, zt - 26, zt, thick=22, top="Bld_Trim")
    k.stepped_merlons("Bld_Ashlar", r3, zt, width=44, gap=26, thick=22, h1=24, h2=20, cap="Bld_Trim")
    k.pole_banner((cx + 20, cy + 16, zt - 26), height=230.0, cloth_w=56, cloth_h=150)
    if k.damaged:
        k.scorch("smear", (cx - half, cy + 26, 646), out=7)
    if lv >= 3:
        k.band("Bld_Iron", inset_ring(r0, 2), 524, 534, out=3)
        hx = cx - half + 2                                   # timber hoarding over the front, under the head
        g1 = half - 4 if not k.damaged else 10.0
        k.beam_ends("Bld_Beam", (hx, -half + 14 + cy), (hx, half - 14 + cy), zt - 96, 4, size=(16, 16), out=50)
        k.obox("Bld_Planks", (hx - 30, cy + (g1 - half + 4) / 2, zt - 82), (62, g1 + half - 4, 10), grain="y")
        k.obox("Bld_Beam", (hx - 58, cy + (g1 - half + 4) / 2, zt - 36), (8, g1 + half - 4, 8), grain="y")
        for y in (-74, -25, 25, 74):
            if y < g1:
                k.obox("Bld_Beam", (hx - 58, cy + y, zt - 58), (8, 8, 48), grain="z")
    return zt + 44


def portal(k):
    x = MOUTH_X - 20
    if k.level >= 2:
        stone_portal(k)
    else:
        timber_set(k, x, AW, AH, broken=k.damaged)
        # lagging: boards between the cap and the rock, and cribbing either side
        if not k.damaged:
            k.obox("Bld_Planks", (x + 10, 0, AH + 44), (8, AW * 2 + 40, 36), grain="y")
            k.obox("Bld_Planks", (x + 12, 0, AH + 80), (8, AW * 2 + 6, 30), grain="y")
        for s in (-1, 1):
            for i, z in enumerate((30, 78, 126)):
                k.obox("Bld_Planks", (x + 12, s * (AW + 58 + i * 4), z), (8, 70 - i * 10, 36), grain="y", roll=s * (2 + i))
        # a lantern hung from the cap beam's end
        lantern(k, (x - 4, -AW - 44, AH + 4), hang=34)
    # a lantern on a post by the track
    k.cyl("Bld_Beam", (-196, -110, 0), (-196, -110, 178), 5.0, 4.0, sides=5)
    k.obox("Bld_Beam", (-196, -92, 172), (5, 44, 5), grain="y")
    lantern(k, (-196, -74, 170), hang=22)


def lantern(k, top, hang=24.0):
    x, y, z = top
    k.cyl("Bld_Bronze", (x, y, z), (x, y, z - hang), 1.2, sides=4)
    k.lathe("Bld_Bronze", (x, y, z - hang - 30), [(7, 0), (10, 4), (10, 7)], sides=6, rot=30)
    k.lathe("Bld_Bronze", (x, y, z - hang - 7), [(11, 0), (6, 5), (1.5, 9)], sides=6, rot=30)
    for a in (0, 60, 120, 180, 240, 300):
        c, s = math.cos(math.radians(a + 30)) * 9, math.sin(math.radians(a + 30)) * 9
        k.cyl("Bld_Bronze", (x + c, y + s, z - hang - 24), (x + c, y + s, z - hang - 7), 1.0, sides=4)
    for yaw in (0.0, 90.0):
        c, s = math.cos(math.radians(yaw)) * 9, math.sin(math.radians(yaw)) * 9
        pts = [(x - c, y - s, z - hang - 25), (x + c, y + s, z - hang - 25), (x + c, y + s, z - hang - 7), (x - c, y - s, z - hang - 7)]
        k.poly("Bld_Flame", pts, [(8, 64), (56, 64), (56, 16), (8, 16)], w=[0.0, 0.0, 0.4, 0.4])


def track(k):
    x0, x1 = -372.0, MOUTH_X + 150.0
    x = x0 + 10
    while x < x1:
        k.obox("Bld_Beam", (x, k.U(-3, 3), 4), (12, 92 + k.U(-6, 6), 8), yaw=k.U(-4, 4), grain="y")
        x += 46
    for s in (-1, 1):
        k.obox("Bld_Bronze", ((x0 + x1) / 2, s * 30, 11), (x1 - x0, 5, 6))
    # buffer stop
    k.obox("Bld_Beam", (x0 - 2, 0, 22), (14, 96, 14), grain="y")
    for s in (-1, 1):
        k.obox("Bld_Beam", (x0 + 14, s * 36, 16), (40, 10, 10), pitch=28)
    # the ore cart: a plank tub on four small wheels, bronze-bound, heaped with gold ore
    with k.at((-214, 0, 0)):
        for sx in (-1, 1):
            for sy in (-1, 1):
                k.wheel((sx * 30, sy * 32, 30), radius=17.0, thick=6.0)
            k.cyl("Bld_Bronze", (sx * 30, -36, 30), (sx * 30, 36, 30), 3.0, sides=5)
        ring = rect(-52, -36, 52, 36)
        top = k.wall("Bld_Planks", ring, 34, 84, inset=-8, u0=20.0, bleach=False)
        k.cap("Bld_Planks", ring, 34, down=True, shade=0.6)
        for z in (40, 78):
            k.band("Bld_Bronze", ring if z == 40 else top, z, z + 6, out=1.5 if z == 40 else 1.5)
        k.blob("Bld_Gold", (0, 0, 88), (118, 84, 62), points=14, flat=True, squash=0.3)
        k.blob("Bld_Ore", (-30, 14, 94), (40, 36, 34), points=8)
        k.blob("Bld_Ore", (26, -18, 96), (34, 34, 30), points=8)


def stores(k):
    """Washed gold and crated ore under a striped awning."""
    with k.at((-262, -258, 0), yaw=6):
        k.crate((30, -40, 0), (64, 60, 46), yaw=0, fill="Bld_Gold")
        k.crate((38, 34, 0), (60, 56, 44), yaw=8, fill="Bld_Ore")
        k.crate((-40, 30, 0), (56, 56, 42), yaw=-6, fill="Bld_Ore")
        k.crate((34, 30, 44), (50, 48, 38), yaw=20, fill="Bld_Gold")
        k.basket((-46, -44, 0), 26, 28, fill="Bld_Gold")
        k.basket((-84, 0, 0), 22, 24, fill="Bld_Gold")
        k.blob("Bld_Gold", (-10, -92, 4), (74, 64, 44), points=12)        # a heap tipped out on the ground
        # awning: four poles, cloth sloping toward the camera
        for (x, y, h) in ((-110, -104, 170), (-110, 88, 170), (96, -104, 214), (96, 88, 214)):
            k.cyl("Bld_Beam", (x, y, 0), (x, y, h), 4.5, 3.5, sides=5)
        k.cloth("Bld_Awning", [(104, 100, 218), (104, -116, 218), (-122, -116, 168), (-122, 100, 168)],
                [(216, 0), (0, 0), (0, 232), (216, 232)], w=[0.0, 0.0, 0.3, 0.3])
        k.obox("Bld_Beam", (96, -8, 214), (5, 216, 5), grain="y")
        k.obox("Bld_Beam", (-110, -8, 170), (5, 216, 5), grain="y")
    # tool rack against the left shoulder: picks and a shovel
    with k.at((-74, -306, 0), yaw=-78):
        for y in (-52, 52):
            k.cyl("Bld_Beam", (0, y, 0), (10, y, 118), 4.5, 4.0, sides=5)
        k.obox("Bld_Beam", (8, 0, 100), (5, 120, 6), grain="y")
        for i, y in enumerate((-30, 0, 30)):
            k.cyl("Bld_Beam", (-24, y, 0), (4, y, 116), 2.6, sides=5)
            if i < 2:
                k.obox("Bld_Bronze", (4, y, 116), (6, 44, 6), roll=12)
            else:
                k.obox("Bld_Bronze", (-22, y, 10), (4, 20, 26), pitch=-14)


def windlass(k):
    """A hand windlass over a side shaft: stone collar, two trestles, a drum with cranks, rope and bucket."""
    with k.at((-150, 228, 0)):
        k.lathe("Bld_Rock", (0, 0, 0), [(72, 0), (70, 24), (60, 30)], sides=9, top=False)
        k.lathe("Bld_Rock", (0, 0, 0), [(46, 30), (46, 2)], sides=9, top=False)
        k.poly("Bld_Rock", [(math.cos(2 * math.pi * i / 9) * 60, math.sin(2 * math.pi * i / 9) * 60, 30) for i in range(9)])
        k.poly("Bld_Dark", [(math.cos(2 * math.pi * i / 9) * 46, math.sin(2 * math.pi * i / 9) * 46, 30.6) for i in range(9)])
        for s in (-1, 1) if not k.damaged else (-1,):
            for d in (-1, 1):
                k.cyl("Bld_Beam", (d * 44, s * 84, 0), (0, s * 80, 146), 5.5, 4.5, sides=5)
            k.obox("Bld_Beam", (0, s * 82, 60), (56, 5, 6))
        if k.damaged:                                        # the drum has come down across the collar
            k.charred((-20, -70, 150), (30, 96, 34), size=17)
            k.charred((40, 60, 6), (-50, 110, 10), size=10)
            return
        k.cyl("Bld_Beam", (0, -96, 140), (0, 96, 140), 9.0, sides=7)
        k.cyl("Bld_Thatch", (0, -30, 140), (0, 30, 140), 12.5, sides=7, grain="ring")        # rope wound on the drum
        for s in (-1, 1):
            k.cyl("Bld_Bronze", (0, s * 96, 140), (0, s * 112, 140), 2.5, sides=4)
            k.cyl("Bld_Bronze", (0, s * 112, 140), (s * 22, s * 112, 122), 2.5, sides=4)
            k.cyl("Bld_Beam", (s * 22, s * 108, 122), (s * 22, s * 128, 122), 3.4, sides=5)
        k.rope((0, 6, 140), (0, 6, 70), 1.8)
        k.lathe("Bld_Planks", (0, 6, 40), [(12, 0), (16, 26), (16, 30)], sides=7, top="Bld_Ore")
        k.blob("Bld_Gold", (0, 6, 70), (22, 22, 14), points=7)


def spoil(k):
    """Waste rock tipped beside the shaft: a low earth mound under a litter of broken stone, a barrow plank up it."""
    k.blob("Bld_Dirt", (-292, 316, 0), (250, 220, 120), points=26, squash=0.25)
    k.blob("Bld_Dirt", (-212, 372, -4), (150, 120, 76), points=18, squash=0.25)
    for i in range(16):
        a, d = k.U(0, 2 * math.pi), k.U(0, 1) ** 0.6 * 100
        x, y = -292 + math.cos(a) * d * 1.1, 316 + math.sin(a) * d
        z = 56 * max(0.0, 1.0 - d / 118) + 2
        s = k.U(22, 44)
        k.blob("Bld_Ore" if i % 5 == 0 else "Bld_Rock", (x, y, z), (s, s * k.U(0.7, 1.0), s * 0.7), points=8)
    k.obox("Bld_Planks", (-226, 262, 26), (150, 26, 5), yaw=30, pitch=-16)


def build(k, state="complete"):
    if state == "site":
        return site(k)
    if state == "ruin":
        return ruin(k)
    complete(k)
    if k.damaged:
        damage(k)


def complete(k):
    outcrop(k)
    portal(k)
    track(k)
    stores(k)
    windlass(k)
    spoil(k)
    # scrub on the outcrop and a standard on its shoulder
    for (x, y, z, s) in ((110, -290, 262, 90), (250, 290, 380, 100), (330, -40, 474, 70)):
        k.blob("Bld_LeafCore", (x, y, z), (s, s, s * 0.6), points=10)
        k.blob("Bld_Leaves", (x, y, z), (s * 1.18, s * 1.18, s * 0.72), points=10, w=0.2)
    k.pole_banner((84, -150, 372), height=300.0)
    k.brazier((-110, 96, 0) if k.level == 1 else (-150, 60, 0), h=88)
    label = 620.0
    if k.level >= 2:
        label = lookout(k) + 150.0
    if k.level >= 3:
        for y in (-104, 112):
            k.brazier((176, y, 468), h=76)
    k.level_flag((-340, -412, 0), height=250.0)
    k.collider((FOOTPRINT[0], FOOTPRINT[1], 0), (FOOTPRINT[2], FOOTPRINT[3], 420))
    k.sockets["label"] = (120.0, 0.0, label)
    k.sockets["popup"] = (-214.0, 0.0, 200.0)


def damage(k):
    """Added to the finished build on the damaged mesh: a rock fall in the adit, soot, burnt stores."""
    for (x, y, z, sx, sy, sz) in ((-36, 34, 30, 120, 110, 110), (-60, -40, 16, 100, 90, 70), (-20, -10, 110, 90, 100, 80), (-96, 60, 8, 60, 70, 44),
                                  (-110, -84, 6, 54, 50, 40)):
        k.blob("Bld_Rock", (x, y, z), (sx, sy, sz), points=11)
    k.scorch("smear", (39, 10, 256), out=10)                 # over the mouth, on the ledge's face
    fx = MOUTH_X if k.level == 1 else PX0                   # the face at the mouth: the rock, or the stone portal
    k.scorch("plume_m", (fx, -160 if k.level == 1 else -150, 4), out=5)
    k.scorch("lick", (fx, 150, 0), out=5, flip=True)
    k.scorch("blot_l", (-262, -258, 0), "up", out=2.0)       # the stores burnt out under their awning
    k.scorch("blot_m", (-150, 228, 31), "up", out=1.5)
    k.charred((-330, -330, 4), (-250, -210, 150), size=9)
    k.charred((-150, -360, 6), (-40, -300, 12), size=10)
    k.rubble((-300, 90, 0), (110, 120), 0, slot="Bld_Rock", blocks=5, beams=1, mound=False, block=(34, 28, 22))


def site(k):
    fp = FOOTPRINT
    k.footings(fp[0], fp[1], fp[2], fp[3], width=26, height=10, slot="Bld_Cliff", top="Bld_Rock")
    k.scaffold(-84, -426, 426, 426, height=270, lift=135, bay=215, depth=44, edges=(1, 2, 3), ladder=(2, 2))       # across the face
    k.timber_pile((-250, -250, 0), yaw=74, length=220, base=4)          # pit props for the adit
    k.stone_stack((-290, 250, 0), yaw=10, slot="Bld_Rock", block=(50, 40, 30), courses=(2, 2), rows=2)
    k.hoist((-128, 0, 0), height=330, reach=120, yaw=0, load_z=200)
    x = -360.0
    while x < -140:                                          # the first sleepers of the track
        k.obox("Bld_Beam", (x, k.U(-3, 3), 4), (12, 92, 8), yaw=k.U(-4, 4), grain="y")
        x += 46


def ruin(k):
    base = convex_ring([(MOUTH_X, -220), (MOUTH_X, 220), (56, 344), (206, 412), (350, 362), (418, 196), (418, -176), (342, -352), (192, -412), (48, -338)])
    top = k.wall("Bld_Cliff", base, -6, 84, inset=10, v0=0.0, bleach=False)
    k.cap("Bld_Dirt", top, 84)                              # the turf went with the slide: bare scree
    upper = convex_ring([(120, -230), (110, 200), (220, 300), (350, 220), (380, -120), (280, -290)])
    top = k.wall("Bld_Cliff", upper, 84, 128, inset=8, v0=0.0, bleach=False, u0=70.0)
    k.cap("Bld_Dirt", top, 128)
    for i in range(9):
        x, y, s = k.U(110, 370), k.U(-250, 250), k.U(40, 80)
        k.blob("Bld_Rock", (x, y, 84 if abs(y) > 200 or x < 130 else 128), (s, s * k.U(0.7, 1.0), s * 0.6), points=8)
    # the adit has fallen in: boulders where the mouth was, its timbers burnt
    for (x, y, z, sx, sy, sz) in ((-30, 10, 30, 200, 190, 130), (-90, -70, 14, 110, 100, 70), (-80, 90, 10, 100, 110, 64), (30, -150, 70, 120, 110, 80),
                                  (60, 140, 76, 110, 120, 70), (-150, 10, 6, 70, 80, 44), (16, -360, 16, 150, 110, 110), (-10, 352, 12, 130, 120, 100)):
        k.blob("Bld_Rock", (x, y, z), (sx, sy, sz), points=12)
    k.obox("Bld_Char", (-60, -110, 40), (24, 24, 84), roll=-10, grain="z")
    k.charred((-70, -100, 96), (-110, 80, 30), size=22)
    k.charred((-120, 120, 4), (-40, 150, 70), size=16)
    x = -362.0
    while x < -150:                                          # what is left of the track
        if k.rng.random() < 0.7:
            k.obox("Bld_Beam", (x, k.U(-6, 6), 4), (12, 92 + k.U(-6, 6), 8), yaw=k.U(-12, 12), grain="y")
        x += 46
    k.blob("Bld_Dirt", (-292, 316, 0), (250, 220, 100), points=22, squash=0.25)      # the spoil heap stays
    k.scorch("blot_l", (-262, -258, 0), "up", out=2.0)
    k.rubble((-262, -258, 0), (150, 130), 0, slot="Bld_Char", blocks=5, beams=2, mound=False, block=(56, 14, 8))
    k.scorch("blot_m", (-180, 140, 0), "up", out=2.0)
    for (x, y, s) in ((-230, -80, 30), (-300, 60, 24), (-190, 250, 34), (-120, -230, 26)):
        k.blob("Bld_Rock", (x, y, 4), (s * 2.2, s * 1.8, s * 1.3), points=8)
