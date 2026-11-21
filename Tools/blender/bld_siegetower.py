"""The siege tower: a defensive tower that hurls stones (area damage). Authored in Unreal cm, front toward -X (bldkit.py).

Squat and heavy where the watchtower is tall and slim: a wide shaft of dark stone below and big ashlar above, bound
with iron bands, on a battered footing; an iron-strapped door up three steps; a head oversailing on timber corbels
over the glazed team frieze, plain square merlons round a plank fighting deck. On the deck stands a timber
stone-thrower (a mangonel: iron-bound frame, twisted skein, the arm up against its padded stop, an iron cup at its
end, a winch and its rope behind), a kerbed pile of round shot beside it, a hoist slinging a block up the left face,
the team's standard on a pole and long banners down the front.

States (bldkit.STATES): `complete`; `damaged` is the same build with breaches, lost merlons, the arm snapped, a hole
burnt in the deck, soot and fallen stone; `site` and `ruin` are their own small meshes on the same footprint.
No levels.
"""
import math

from bldkit import STATES, inset_ring, rect  # noqa: F401  (STATES: which meshes build_building.py exports)

NAME = "siegetower"
MESH = "SM_Bld_SiegeTower"
SEED = 47
HALF = 240.0           # half width at the ground
DECK = 760.0           # the fighting deck
H = 800.0              # parapet top (the merlons stand on it)
FOOTPRINT = [-240.0, -240.0, 240.0, 240.0]
RING_RADIUS = 350.0
PREVIEW_FIGURES = [(-390, 130), (-440, -100)]
PREVIEW_FOCUS = (0.0, 0.0, 450.0)          # the game-camera previews look at the middle of the tower, so the engine is in frame

ENGINE = (24.0, -30.0, 30.0)                 # the stone-thrower on the deck: x, y, yaw (it throws toward its local -X)
PIVOT, TIP = (30.0, 0.0, 44.0), (-70.0, 0.0, 350.0)       # the arm in the engine's frame: skein to cup, at release


def build(k, state="complete"):
    if state == "site":
        return site(k)
    if state == "ruin":
        return ruin(k)
    complete(k)
    if k.damaged:
        damage(k)


def shot(k, pos, r=20.0):
    """One stone shot, dressed roughly round."""
    k.lathe("Bld_Rock", pos, [(r * 0.5, 0), (r, r * 0.6), (r, r * 1.35), (r * 0.5, r * 1.9)], sides=6, rot=k.U(0, 60), uvo=(k.U(0, 99), k.U(0, 99)))


def shot_pile(k, pos, n=3, r=20.0, yaw=0.0):
    """A pyramid of round shot inside a plank kerb."""
    with k.at(pos, yaw):
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


def along(f):
    """A point on the arm, f = 0 at the skein, 1 at the cup."""
    return tuple(PIVOT[i] + (TIP[i] - PIVOT[i]) * f for i in range(3))


def engine(k):
    """The stone-thrower, in its own frame (origin on the deck, throwing toward local -X). Returns the muzzle: the cup at
    the end of the arm where the stone leaves it, in building space."""
    with k.at((ENGINE[0], ENGINE[1], DECK), ENGINE[2]):
        ys = 64.0
        for s in (-1, 1):
            k.obox("Bld_Beam", (0, s * ys, 24), (284, 24, 26))                      # the sole beams
            k.obox("Bld_Beam", (-48, s * ys, 128), (24, 24, 184), grain="z")         # uprights of the stop
            k.cyl("Bld_Beam", (-132, s * ys, 38), (-54, s * ys, 196), 6.0, sides=4, caps=False)
            k.cyl("Bld_Beam", (112, s * ys, 38), (-40, s * ys, 178), 6.0, sides=4, caps=False)
            for x in (-132, 30, 132):                                                # iron straps round the joints
                k.obox("Bld_Iron", (x, s * ys, 24), (12, 28, 30))
            k.obox("Bld_Iron", (-48, s * ys, 214), (28, 28, 12))
            k.obox("Bld_Iron", (30, s * (ys + 13), 44), (36, 4, 36))                 # the washers of the skein
            k.obox("Bld_Beam", (128, s * ys, 62), (20, 20, 52), grain="z")           # the winch's cheeks
        for x in (-132, 132):
            k.obox("Bld_Beam", (x, 0, 24), (22, 2 * ys - 20, 22), grain="y")
        k.obox("Bld_Beam", (-48, 0, 214), (24, 2 * ys + 30, 24), grain="y")          # the stop bar and its padding
        k.obox("Bld_Thatch", (-41, 0, 214), (26, 66, 30), grain="y")
        k.cyl("Bld_Thatch", (30, -ys - 10, 44), (30, ys + 10, 44), 14.0, sides=6)    # the twisted skein
        # the winch: drum, rope wound on it, handspikes, the rope up to the arm
        k.cyl("Bld_Beam", (128, -ys - 22, 70), (128, ys + 22, 70), 9.0, sides=6)
        k.cyl("Bld_Thatch", (128, -26, 70), (128, 26, 70), 13.0, sides=6)
        for s in (-1, 1):
            k.cyl("Bld_Beam", (128, s * (ys + 17), 40), (128, s * (ys + 17), 100), 2.8, sides=4)
            k.cyl("Bld_Beam", (98, s * (ys + 17), 70), (158, s * (ys + 17), 70), 2.8, sides=4)
        if k.damaged:                                                                # the arm snapped at the stop
            k.cyl("Bld_Beam", PIVOT, along(0.5), 13.0, 11.0, sides=6)
            k.cyl("Bld_Char", along(0.5), along(0.64), 11.0, 6.0, sides=6)
            k.charred((-70, 40, 10), (-176, -30, 12), size=15)                       # the rest of it lies on the deck
            k.lathe("Bld_Iron", (-150, 60, 0), [(7, 0), (22, 6), (27, 22)], sides=7, top="Bld_Dark")
            k.rope((128, 0, 80), (40, 30, 6), 2.2)
        else:
            k.cyl("Bld_Beam", PIVOT, TIP, 13.0, 9.5, sides=6)
            for f in (0.12, 0.42, 0.86):                                             # iron hoops on the arm
                k.cyl("Bld_Iron", along(f - 0.02), along(f + 0.02), 14.5 - 3.0 * f, sides=6, grain="ring")
            k.lathe("Bld_Iron", (TIP[0] - 4, 0, TIP[2] - 8), [(8, 0), (26, 7), (31, 24)], sides=7, top="Bld_Dark")
            shot(k, (TIP[0] - 4, 0, TIP[2] + 2), 22)                                  # the stone in the cup
            k.rope((128, 0, 82), along(0.62), 2.2)
        return tuple(k._w(TIP))


def complete(k):
    u0 = 12.0
    r0 = rect(-HALF, -HALF, HALF, HALF)
    # battered footing of dark stone
    r1 = k.wall("Bld_StoneDark", r0, 0, 56, inset=22, u0=u0, bleach=False)
    k.band("Bld_Trim", r1, 56, 64, out=4, u0=u0)
    h1 = HALF - 22
    side = 2 * h1
    zm, top = 300.0, 590.0
    lo = {2: [dict(a=side / 2 - 58, b=side / 2 + 58, z0=64, z1=250, depth=40, back="Bld_Door", reveal="Bld_AshlarLarge", shade=0.62, back_shade=0.8)],
          0: [dict(a=side / 2 - 7, b=side / 2 + 7, z0=180, z1=250, depth=14, back="Bld_Dark", shade=0.5)]}
    rm = k.wall("Bld_StoneDark", r1, 64, zm, inset=8, u0=u0, openings=lo, bleach=False)
    s2 = side - 16
    hi = {2: [dict(a=s2 / 2 - 7, b=s2 / 2 + 7, z0=400, z1=470, depth=14, back="Bld_Dark", shade=0.5)]
             + k.breach(44, 160, 330, 462) + k.breach(270, 372, 420, 530),         # only on the damaged mesh
          1: [dict(a=s2 / 2 - 7, b=s2 / 2 + 7, z0=360, z1=430, depth=14, back="Bld_Dark", shade=0.5)],
          3: [dict(a=s2 / 2 - 7, b=s2 / 2 + 7, z0=360, z1=430, depth=14, back="Bld_Dark", shade=0.5)]}
    r2 = k.wall("Bld_AshlarLarge", rm, zm, top, inset=6, u0=u0, openings=hi)
    k.band("Bld_Iron", rm, zm - 8, zm + 8, out=4, u0=u0)                              # iron bands round the shaft
    k.band("Bld_Iron", inset_ring(rm, 6.0 * (486 - zm) / (top - zm)), 486, 498, out=3, u0=u0)
    # the door: iron straps, a heavy lintel, steps
    for z in (104, 156, 208):
        k.obox("Bld_Iron", (-h1 + 39, 0, z), (4, 112, 10))
    k.obox("Bld_Beam", (-h1 + 6, 0, 262), (26, 150, 22), grain="y")
    for y in (-66, 66):
        k.obox("Bld_Iron", (-h1 + 5, y, 262), (30, 10, 26))
    k.steps("Bld_AshlarLarge", -HALF - 62, -h1, -76, 76, 0, 64, 3, top="Bld_Trim")
    # the head: oversailing on timber corbels, glazed frieze, big ashlar, a plank deck inside the parapet
    h2 = h1 - 14
    for i, (a, b) in enumerate(zip(r2, r2[1:] + r2[:1])):
        k.beam_ends("Bld_Beam", a, b, top - 16, 5, size=(22, 26), out=34)
    k.band("Bld_Trim", r2, top, top + 14, out=12, u0=u0)
    r3 = inset_ring(r2, -28)
    k.cap("Bld_AshlarLarge", r3, top + 14, down=True, shade=0.55)
    k.wall("Bld_Frieze", r3, top + 14, top + 70, v0=0.0, bleach=False, u0=u0)
    k.wall("Bld_AshlarLarge", r3, top + 70, H, u0=u0)
    k.parapet("Bld_Ashlar", r3, DECK, H, thick=28, floor="Bld_Planks", top="Bld_Trim")
    k.crenels("Bld_Ashlar", r3, H, height=52, width=66, gap=42, thick=28, cap="Bld_Trim")
    # long banners down the front, on iron rods
    fx = -h2 - 9
    for y in (-124, 124):
        k.cyl("Bld_Iron", (fx, y - 44, top - 40), (fx, y + 44, top - 40), 3.0, sides=4)
        k.hang_cloth((fx, y - 36, top - 42), (fx, y + 36, top - 42), 210.0)
    # on the deck
    muzzle = engine(k)
    shot_pile(k, (-128, 138, DECK), n=3, r=19, yaw=8)
    for x, y in ((-60, 166), (-176, 60)):
        shot(k, (x, y, DECK), 19)
    k.pole_banner((166, 170, DECK), height=330, cloth_w=64, cloth_h=160)
    k.hoist((-150, -178, DECK), height=170, reach=112, yaw=-90, load_z=-230)        # slinging a block up the left face
    if not k.damaged:
        k.crate((150, -150, DECK), (54, 54, 42), yaw=14)
    # at the foot: shot waiting to go up, a few tumbled stones
    shot_pile(k, (-292, 168, 0), n=2, r=20, yaw=-12)
    for x, y, s in ((-262, -180, 24), (176, -262, 22), (-286, 236, 18)):
        k.blob("Bld_Rock", (x, y, 4), (s * 2.2, s * 1.8, s * 1.4), points=8)
    k.collider((-HALF, -HALF, 0), (HALF, HALF, H))
    k.sockets["label"] = (0.0, 0.0, 1240.0)
    k.sockets["popup"] = (0.0, 0.0, 640.0)
    k.sockets["muzzle"] = muzzle


def damage(k):
    """Added to the finished build on the damaged mesh: soot, the burnt deck, what fell."""
    front = lambda z: -(HALF - 30) + 6.0 * (z - 300) / 290.0             # the upper shaft's front face
    k.scorch("plume_m2", (front(462), 110, 462))
    k.scorch("smear", (front(530), -110, 530))
    k.scorch("smear", (-(HALF - 8) - 2, 80, 664), flip=True)
    k.scorch("lick", (-(HALF - 26), -150, 250))
    k.scorch("streak", (front(330), -40, 330))
    k.burn_hole((-96, 30, DECK), (130, 110), yaw=20, soot="blot_l")
    k.charred((150, -160, DECK + 6), (96, -110, DECK + 40), size=10)
    k.rubble((-266, 120, 0), (120, 190), 34, blocks=8, beams=1)
    k.rubble((-262, -150, 0), (90, 120), 0, blocks=5, beams=0, mound=False)


def site(k):
    fp = FOOTPRINT
    k.footings(fp[0], fp[1], fp[2], fp[3])
    g = 6.0
    k.scaffold(fp[0] - g, fp[1] - g, fp[2] + g, fp[3] + g, height=640, lift=214, bay=246, depth=44, ladder=(3, 0), planks=0.35, braces=0.2)
    k.stone_stack((-268, 120, 0), yaw=90, rows=1)             # under the first lift, between the two rows of poles
    k.timber_pile((20, 268, 0), length=230, base=2, planks=False)
    k.hoist((-292, -292, 0), height=700, reach=170, yaw=45, load_z=560)
    for x, y in ((-268, -40), (-268, 4), (-270, -84)):        # the first shot, waiting
        shot(k, (x, y, 0), 20)


def ruin(k):
    r0 = rect(-HALF, -HALF, HALF, HALF)
    r1 = k.wall("Bld_StoneDark", r0, 0, 56, inset=22, u0=12.0, bleach=False)       # the footing outlasts the shaft
    k.cap("Bld_Dirt", r1, 56)
    c = HALF - 22 - 17
    k.ruin_rect("Bld_StoneDark", -c, -c, c, c, hmax=200, hmin=16, thick=34, seg=58, z=56, corners=(0.5, 1.0, 0.8, 0.3))
    k.scorch("blot_l", (20, -30, 56), "up", out=1.5)
    k.rubble((20, 10, 56), (300, 280), 62, blocks=12, beams=2)
    # what is left of the engine: a sole beam, the snapped arm, its iron cup, shot rolled out of the pile
    k.charred((-140, -120, 62), (90, -20, 150), size=16)
    k.charred((120, 130, 62), (-50, 70, 112), size=13)
    k.charred((-30, 150, 70), (130, -90, 96), size=20)
    k.lathe("Bld_Iron", (-110, 90, 76), [(7, 0), (22, 6), (27, 22)], sides=7, top="Bld_Dark")
    for x, y, z in ((-150, -30, 60), (-96, 150, 62), (60, 110, 96), (-250, 60, 0), (-276, -110, 0)):
        shot(k, (x, y, z), 19)
    k.rubble((-226, 30, 0), (60, 260), 0, blocks=6, beams=0, mound=False)          # spilt out of the breached front
