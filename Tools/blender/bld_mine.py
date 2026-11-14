"""The gold mine: produces gold. Authored in Unreal cm, front toward -X (bldkit.py).

Read at a glance as dark opening + timber frame + gold: an adit under a heavy timber set, cut into a rock outcrop
(turf on its top, ore showing in the face), a track of sleepers and rails with a loaded cart, crates and baskets of
washed gold under a striped awning, a windlass over a side shaft, a spoil heap, a tool rack, lanterns, a banner.
"""
import math

from bldkit import clip_ring, convex_ring, rect

NAME = "mine"
MESH = "SM_Bld_Mine"
SEED = 37
FOOTPRINT = [-400.0, -420.0, 420.0, 420.0]
RING_RADIUS = 580.0
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


def timber_set(k, x, hw, h, post=26.0, shade=False):
    """One mining set: two raking posts and a cap beam."""
    slot = "Bld_Beam"
    for s in (-1, 1):
        k.obox(slot, (x, s * (hw + post * 0.3), h / 2), (post, post, h + 6), roll=s * 3.0, grain="z")
    k.obox(slot, (x, 0, h + post * 0.42), (post + 4, hw * 2 + post * 2.4, post), grain="y")
    if not shade:
        for s in (-1, 1):                                    # bronze dogs pinning the cap
            k.obox("Bld_Bronze", (x - post / 2 - 1.5, s * hw, h + post * 0.4), (3, 8, post + 6))


def portal(k):
    x = MOUTH_X - 20
    timber_set(k, x, AW, AH)
    # lagging: boards between the cap and the rock, and cribbing either side
    k.obox("Bld_Planks", (x + 10, 0, AH + 44), (8, AW * 2 + 40, 36), grain="y")
    k.obox("Bld_Planks", (x + 12, 0, AH + 80), (8, AW * 2 + 6, 30), grain="y")
    for s in (-1, 1):
        for i, z in enumerate((30, 78, 126)):
            k.obox("Bld_Planks", (x + 12, s * (AW + 58 + i * 4), z), (8, 70 - i * 10, 36), grain="y", roll=s * (2 + i))
    # a lantern hung from the cap beam's end, another on a post by the track
    lantern(k, (x - 4, -AW - 44, AH + 4), hang=34)
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
        k.poly("Bld_Awning", [(104, 100, 218), (104, -116, 218), (-122, -116, 168), (-122, 100, 168)],
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
        for s in (-1, 1):
            for d in (-1, 1):
                k.cyl("Bld_Beam", (d * 44, s * 84, 0), (0, s * 80, 146), 5.5, 4.5, sides=5)
            k.obox("Bld_Beam", (0, s * 82, 60), (56, 5, 6))
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
    k.blob("Bld_Dirt", (-296, 318, 0), (220, 200, 170), points=22, squash=0.35)
    k.blob("Bld_Dirt", (-214, 372, -6), (150, 120, 110), points=16, squash=0.35)
    k.blob("Bld_Dirt", (-360, 256, -8), (110, 120, 90), points=14, squash=0.35)
    for (x, y, z, s) in ((-330, 270, 40, 44), (-262, 300, 58, 36), (-300, 372, 46, 40), (-226, 344, 34, 30), (-352, 330, 20, 34)):
        k.blob("Bld_Rock" if s > 34 else "Bld_Ore", (x, y, z), (s, s, s * 0.8), points=8)
    # a barrow plank up the heap
    k.obox("Bld_Planks", (-232, 280, 34), (150, 26, 5), yaw=26, pitch=-20)


def build(k):
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
    k.brazier((-110, 96, 0), h=88)
    k.collider((FOOTPRINT[0], FOOTPRINT[1], 0), (FOOTPRINT[2], FOOTPRINT[3], 420))
    k.sockets["label"] = (120.0, 0.0, 620.0)
    k.sockets["popup"] = (-214.0, 0.0, 200.0)
