"""The watchtower: a defensive tower the player builds. Authored in Unreal cm, front toward -X (bldkit.py).

A tall square sandstone shaft on a battered footing, a bronze-strapped door at its foot, arrow slits up the faces,
a corbelled fighting top with crow-stepped merlons, a timber hoarding gallery on beam ends overhanging the front, a
team-coloured glazed frieze under the parapet, a banner on the roof and a brazier for the night watch. Archers on
the top shoot at enemies within range (Sovereign Feel > Buildings > Tower).

States (bldkit.STATES): `complete`; `damaged` is the same build with breaches, lost merlons, half the hoarding gone,
a hole in the roof, soot and fallen stone; `site` and `ruin` are their own small meshes on the same footprint.

Levels 1-3 (k.level), each adding to the last. Every top is flat and crenellated, like a chess rook (the castle's
language: an oversailing head on a trim corbel course, a glazed frieze, crow-stepped merlons, a banner on the roof):
  2  a storey taller; a crenellated bartizan with a glazed band corbels out of each corner of the fighting top, the
     door is iron-bound, long banners hang down the front
  3  fortified: taller again on a base of dark heavy stone with iron bands, the hoarding closed in as a half-timbered
     brattice with fires on it, a crenellated upper stage rising out of the roof terrace with the standard on it, creeper
The level banner (kit.level_flag) stands on the ground at the front-left, beside the door steps.
"""
import math

from bldkit import STATES, inset_ring, rect  # noqa: F401  (STATES: which meshes build_building.py exports)

NAME = "tower"
MESH = "SM_Bld_Tower"
SEED = 31
HALF = 200.0           # shaft half width at the base
H = 900.0              # parapet top at level 1
LEVELS = 3
TOPS = {1: H, 2: 1020.0, 3: 1110.0}       # parapet top by level
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
    lv = k.level
    H = TOPS[lv]
    u0 = 12.0
    r0 = rect(-HALF, -HALF, HALF, HALF)
    # battered footing of big blocks
    r1 = k.wall("Bld_StoneDark" if lv >= 3 else "Bld_AshlarLarge", r0, 0, 36, inset=18, u0=u0, bleach=False)
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
    if lv >= 3:
        # level 3: the lower shaft in dark heavy stone, an iron band where the paler work begins
        zm = 244.0
        f = 10.0 * (zm - 44) / (top - 44)
        lo = {e: [o for o in v if o["z1"] <= zm] for e, v in ops.items()}
        hi = {e: [o for o in v if o["z1"] > zm] for e, v in ops.items()}
        rm = k.wall("Bld_StoneDark", r1, 44, zm, inset=f, u0=u0, openings=lo, bleach=False)
        k.band("Bld_Iron", rm, zm - 6, zm + 6, out=3, u0=u0)
        r2 = k.wall("Bld_Ashlar", rm, zm, top, inset=10.0 - f, u0=u0, openings=hi)
        k.band("Bld_Iron", inset_ring(rm, (10.0 - f) * (560 - zm) / (top - zm)), 560, 570, out=3, u0=u0)
    else:
        r2 = k.wall("Bld_Ashlar", r1, 44, top, inset=10, u0=u0, openings=ops)
    if lv >= 2:                                              # iron straps across the door
        for z in (84, 130, 176):
            k.obox("Bld_Iron", (-HALF + 18 + 39, 0, z), (4, 92, 9))
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
    hx = -HALF - 22
    g0, g1 = (-190, 190) if not k.damaged else (-190, 6)      # damaged: the right half has burnt away / fallen
    if lv <= 2:
        # timber hoarding over the front: beam ends carrying a plank gallery with a rail
        k.beam_ends("Bld_Beam", (hx, -170), (hx, 170), top - 40, 4, size=(20, 20), out=60)
        k.obox("Bld_Planks", (hx - 36, (g0 + g1) / 2, top - 22), (76, g1 - g0, 12), grain="y")
        k.obox("Bld_Beam", (hx - 70, (g0 + g1) / 2, top + 40), (10, g1 - g0, 10), grain="y")
        for y in (-180, -60, 60, 180):
            if y < g1:
                k.obox("Bld_Beam", (hx - 70, y, top + 10), (10, 10, 60), grain="z")
    else:
        # level 3: the hoarding closed in: a half-timbered brattice on heavy beam ends, fires on its roof
        k.beam_ends("Bld_Beam", (hx, -176), (hx, 176), top - 46, 5, size=(26, 30), out=64)
        k.box("Bld_Planks", (hx - 80, g0, top - 32), (hx + 2, g1, top - 20), bottom=True, u0=u0)
        k.box("Bld_Timber", (hx - 76, g0 + 2, top - 20), (hx, g1 - 2, top + 44), v0=0.0, top="Bld_Planks", u0=0.0)
        for y in (-150, 150):
            if y < g1:
                k.brazier((hx - 38, y, top + 44), h=56)
    if lv >= 2:
        fx = -(HALF - 18) + 9.0                              # the front face up here
        for y in (-112, 112):                                # long banners down the front, on iron rods
            k.cyl("Bld_Iron", (fx - 10, y - 42, top - 84), (fx - 10, y + 42, top - 84), 2.8, sides=4)
            k.hang_cloth((fx - 10, y - 34, top - 86), (fx - 10, y + 34, top - 86), 250.0 if lv >= 3 else 210.0)
    if lv >= 3:                                              # creeper up the old stone beside the door
        k.patch("Bld_Leaves", (-HALF + 6, 120, 0), (0, -1, 0), (0, 0, 1), 130, 330, cells=12, fill=0.55, out=14)
    if lv <= 2:
        k.pole_banner((60, 70, H - 30), height=330, cloth_w=56, cloth_h=150)
        k.brazier((-40, -90, H - 30), h=70)
    roof_top = H if lv == 1 else crown(k, r3, H)
    # a few stones tumbled at the foot
    for x, y, s in ((-250, 150, 26), (-230, -170, 20), (150, -250, 22)):
        k.blob("Bld_Rock", (x, y, 4), (s * 2.2, s * 1.8, s * 1.4), points=8)
    k.level_flag((-256, -128, 0), height=300.0)
    k.collider((-220, -220, 0), (220, 220, H))
    k.sockets["label"] = (0.0, 0.0, roof_top + 150.0)
    k.sockets["popup"] = (0.0, 0.0, 700.0)
    k.sockets["muzzle"] = (0.0, 0.0, H - 40.0)


def crown(k, r3, H):
    """Level 2 on: a square crenellated bartizan corbelled out of every corner of the fighting top, a glazed band under
    its merlons. Level 3: a crenellated upper stage rises out of the roof terrace, the standard on it. Returns the
    top of the stonework."""
    lv = k.level
    xs, ys = [p[0] for p in r3], [p[1] for p in r3]
    x0, y0, x1, y1 = min(xs), min(ys), max(xs), max(ys)
    for sx in (-1, 1):
        for sy in (-1, 1):
            cx, cy = (x0 if sx < 0 else x1), (y0 if sy < 0 else y1)
            u0 = 40.0 + 90.0 * (sx + 1) + 45.0 * (sy + 1)
            rb = k.wall("Bld_StoneDark" if lv >= 3 else "Bld_AshlarLarge", rect(cx - 24, cy - 24, cx + 24, cy + 24), H - 236, H - 176, inset=-20, u0=u0, bleach=False)
            k.cap("Bld_AshlarLarge", rect(cx - 24, cy - 24, cx + 24, cy + 24), H - 236, down=True, shade=0.5)
            k.wall("Bld_Ashlar", rb, H - 176, H + 30, u0=u0)
            k.band("Bld_Trim", rb, H + 30, H + 40, out=7, u0=u0)
            rh = inset_ring(rb, -7)
            k.cap("Bld_AshlarLarge", rh, H + 40, down=True, shade=0.55)
            k.wall("Bld_Frieze", rh, H + 40, H + 88, v0=0.0, bleach=False, u0=u0)
            k.parapet("Bld_Ashlar", rh, H + 66, H + 88, thick=18, top="Bld_Trim")
            k.stepped_merlons("Bld_Ashlar", rh, H + 88, width=34, gap=22, thick=18, h1=20, h2=16, cap="Bld_Trim")
            k.obox("Bld_Dark", (cx + sx * 45, cy, H - 40), (6, 11, 52))
            k.obox("Bld_Dark", (cx - 45, cy, H - 40), (6, 11, 52))
            if k.damaged and sx < 0 and sy > 0:               # damaged: the front right bartizan is burnt out
                k.charred((cx - 30, cy - 20, H + 66), (cx + 26, cy + 30, H + 150), size=10)
                k.scorch("streak", (cx - 51, cy, H - 170), out=4)
    top = H + 124
    if lv >= 3:
        hs = 96.0
        s0 = rect(-hs, -hs, hs, hs)
        ops = {2: [dict(a=hs + y - 7, b=hs + y + 7, z0=H + 30, z1=H + 84, depth=13, back="Bld_Dark", shade=0.5) for y in (-44, 44)]}
        s1 = k.wall("Bld_AshlarLarge", s0, H - 40, H + 110, inset=4, u0=140.0, openings=ops)
        k.band("Bld_Trim", s1, H + 110, H + 122, out=9, u0=140.0)
        s3 = inset_ring(s1, -10)
        k.cap("Bld_AshlarLarge", s3, H + 122, down=True, shade=0.55)
        k.wall("Bld_Frieze", s3, H + 122, H + 176, v0=0.0, bleach=False, u0=140.0)
        k.parapet("Bld_Ashlar", s3, H + 150, H + 176, thick=22, top="Bld_Trim")
        k.stepped_merlons("Bld_Ashlar", s3, H + 176, width=44, gap=26, thick=22, h1=24, h2=20, cap="Bld_Trim")
        k.pole_banner((20, 20, H + 150), height=300, cloth_w=64, cloth_h=170)
        top = H + 220
    return top

def damage(k):
    """Added to the finished build on the damaged mesh: soot, the burnt roof, what fell."""
    H = TOPS[k.level]
    front = lambda z: -(HALF - 18) + 10.0 * (z - 44) / (H - 150 - 44)      # the battered front face
    k.scorch("smear", (front(636), 90, 636))                 # above the upper breach, and on over the frieze
    k.scorch("smear", (-(HALF - 28) - 22, 70, H - 136), flip=True)
    k.scorch("plume_m2", (front(354), -92, 354))
    k.scorch("lick", (front(236), 96, 236))
    k.scorch("streak", (front(470), -150, 470))
    if k.level <= 2:
        k.burn_hole((-56, 66, H - 40), (140, 120), yaw=20, soot="blot_l")
    else:                                                    # level 3: the upper stage's roof is burnt through
        k.burn_hole((-10, 20, H + 150), (120, 100), yaw=20, soot="blot_m")
        k.scorch("plume_s", (-96, -30, H - 40), out=5)
    if k.level >= 2:
        k.rubble((-246, 150, 0), (90, 110), 22, blocks=5, beams=0)
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
