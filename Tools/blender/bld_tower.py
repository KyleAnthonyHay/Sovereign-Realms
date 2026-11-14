"""The watchtower: a defensive tower the player builds. Authored in Unreal cm, front toward -X (bldkit.py).

A tall square sandstone shaft on a battered footing, a bronze-strapped door at its foot, arrow slits up the faces,
a corbelled fighting top with crow-stepped merlons, a timber hoarding gallery on beam ends overhanging the front, a
team-coloured glazed frieze under the parapet, a banner on the roof and a brazier for the night watch. Archers on
the top shoot at enemies within range (Sovereign Feel > Buildings > Tower).

States (bldkit.STATES): `complete`; `damaged` is the same build with breaches, lost merlons, half the hoarding gone,
a hole in the roof, soot and fallen stone; `site` and `ruin` are their own small meshes on the same footprint.
"""
from bldkit import STATES, inset_ring, rect  # noqa: F401  (STATES: which meshes build_building.py exports)

NAME = "tower"
MESH = "SM_Bld_Tower"
SEED = 31
HALF = 200.0           # shaft half width at the base
H = 900.0              # parapet top
FOOTPRINT = [-220.0, -220.0, 220.0, 220.0]
RING_RADIUS = 320.0
PREVIEW_FIGURES = [(-330, 120), (-380, -90)]


def build(k, state="complete"):
    if state == "site":
        return site(k)
    if state == "ruin":
        return ruin(k)
    complete(k)
    if k.damaged:
        damage(k)


def complete(k):
    u0 = 12.0
    r0 = rect(-HALF, -HALF, HALF, HALF)
    # battered footing of big blocks
    r1 = k.wall("Bld_AshlarLarge", r0, 0, 36, inset=18, u0=u0, bleach=False)
    k.band("Bld_Trim", r1, 36, 44, out=4, u0=u0)
    side = 2 * (HALF - 18)
    ops = {
        2: [dict(a=side / 2 - 46, b=side / 2 + 46, z0=44, z1=214, depth=40, back="Bld_Door", reveal="Bld_AshlarLarge", shade=0.62, back_shade=0.8),
            dict(a=side / 2 - 6, b=side / 2 + 6, z0=420, z1=484, depth=14, back="Bld_Dark", shade=0.5)],
        0: [dict(a=side / 2 - 6, b=side / 2 + 6, z0=z, z1=z + 64, depth=14, back="Bld_Dark", shade=0.5) for z in (300, 520)],
        1: [dict(a=side / 2 - 6, b=side / 2 + 6, z0=360, z1=424, depth=14, back="Bld_Dark", shade=0.5)],
        3: [dict(a=side / 2 - 6, b=side / 2 + 6, z0=z, z1=z + 64, depth=14, back="Bld_Dark", shade=0.5) for z in (260, 480)]
           + [dict(a=side * 0.25, b=side * 0.25 + 30, z0=220, z1=236, depth=8, back="Bld_Dark", shade=0.55)],
    }
    ops[2] += k.breach(36, 150, 500, 632) + k.breach(232, 326, 250, 350)       # only on the damaged mesh
    top = H - 150
    r2 = k.wall("Bld_Ashlar", r1, 44, top, inset=10, u0=u0, openings=ops)
    # lintel and step at the door
    k.obox("Bld_Beam", (-HALF + 22, 0, 224), (24, 124, 18), grain="y")
    k.steps("Bld_AshlarLarge", -HALF - 60, -HALF + 18, -64, 64, 0, 44, 2, top="Bld_Trim")
    # corbelled fighting top
    k.band("Bld_Trim", r2, top, top + 12, out=10, u0=u0)
    r3 = inset_ring(r2, -22)
    k.cap("Bld_AshlarLarge", r3, top + 12, down=True, shade=0.55)
    k.wall("Bld_Frieze", r3, top + 12, top + 70, v0=0.0, bleach=False, u0=u0)
    k.wall("Bld_AshlarLarge", r3, top + 70, H - 40, u0=u0)
    k.parapet("Bld_Ashlar", r3, H - 40, H, thick=24, top="Bld_Trim")
    k.stepped_merlons("Bld_Ashlar", r3, H, width=48, gap=28, thick=24, h1=26, h2=22, broken=0.1, cap="Bld_Trim")
    # timber hoarding over the front: beam ends carrying a plank gallery with a rail
    hx = -HALF - 22
    k.beam_ends("Bld_Beam", (hx, -170), (hx, 170), top - 40, 4, size=(20, 20), out=60)
    g0, g1 = (-190, 190) if not k.damaged else (-190, 6)      # damaged: the right half has burnt away
    k.obox("Bld_Planks", (hx - 36, (g0 + g1) / 2, top - 22), (76, g1 - g0, 12), grain="y")
    k.obox("Bld_Beam", (hx - 70, (g0 + g1) / 2, top + 40), (10, g1 - g0, 10), grain="y")
    for y in (-180, -60, 60, 180):
        if y < g1:
            k.obox("Bld_Beam", (hx - 70, y, top + 10), (10, 10, 60), grain="z")
    # banner on the roof, brazier at the parapet
    k.pole_banner((60, 70, H - 30), height=330, cloth_w=56, cloth_h=150)
    k.brazier((-40, -90, H - 30), h=70)
    # a few stones tumbled at the foot
    for x, y, s in ((-250, 150, 26), (-230, -170, 20), (150, -250, 22)):
        k.blob("Bld_Rock", (x, y, 4), (s * 2.2, s * 1.8, s * 1.4), points=8)
    k.collider((-220, -220, 0), (220, 220, H))
    k.sockets["label"] = (0.0, 0.0, H + 150.0)
    k.sockets["popup"] = (0.0, 0.0, 700.0)
    k.sockets["muzzle"] = (0.0, 0.0, H - 40.0)


def damage(k):
    """Added to the finished build on the damaged mesh: soot, the burnt roof, what fell."""
    front = lambda z: -(HALF - 18) + 10.0 * (z - 44) / (H - 150 - 44)      # the battered front face
    k.scorch("smear", (front(636), 90, 636))                 # above the upper breach, and on over the frieze
    k.scorch("smear", (-(HALF - 28) - 22, 70, H - 136), flip=True)
    k.scorch("plume_m2", (front(354), -92, 354))
    k.scorch("lick", (front(236), 96, 236))
    k.scorch("streak", (front(470), -150, 470))
    k.burn_hole((-56, 66, H - 40), (140, 120), yaw=20, soot="blot_l")
    hx = -HALF - 22
    k.charred((hx - 40, 30, H - 176), (hx - 64, 96, H - 300), size=9)       # a burnt plank hanging off the hoarding
    k.charred((hx - 10, 150, H - 190), (hx - 70, 150, H - 196), size=12)
    k.rubble((-240, 104, 0), (110, 170), 30, blocks=7, beams=1)
    k.rubble((-236, -150, 0), (90, 110), 0, blocks=4, beams=0, mound=False)


def site(k):
    fp = FOOTPRINT
    k.footings(fp[0], fp[1], fp[2], fp[3])
    g = 6.0
    k.scaffold(fp[0] - g, fp[1] - g, fp[2] + g, fp[3] + g, height=740, lift=247, bay=226, depth=44, ladder=(3, 0), planks=0.35, braces=0.2)
    k.stone_stack((-248, 112, 0), yaw=90, rows=1)             # under the first lift, between the two rows of poles
    k.timber_pile((20, 248, 0), length=220, base=2, planks=False)
    k.hoist((-270, -270, 0), height=800, reach=170, yaw=45, load_z=640)


def ruin(k):
    r0 = rect(-HALF, -HALF, HALF, HALF)
    r1 = k.wall("Bld_AshlarLarge", r0, 0, 36, inset=18, u0=12.0, bleach=False)       # the footing outlasts the shaft
    k.cap("Bld_Dirt", r1, 36)
    c = HALF - 18 - 15
    k.ruin_rect("Bld_Ashlar", -c, -c, c, c, hmax=184, hmin=16, thick=30, seg=54, z=36, corners=(0.55, 1.0, 0.75, 0.3))
    k.scorch("blot_l", (10, -20, 36), "up", out=1.5)
    k.rubble((20, 10, 36), (250, 240), 58, blocks=10, beams=2)
    k.charred((-120, -130, 40), (60, -30, 150), size=13)
    k.charred((100, 120, 44), (-40, 60, 96), size=11)
    k.rubble((-190, 40, 0), (50, 220), 0, blocks=5, beams=0, mound=False)       # spilt out of the breached front
