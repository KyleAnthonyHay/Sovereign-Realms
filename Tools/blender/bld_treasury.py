"""The treasury: holds gold on top of the castle's stores. Authored in Unreal cm, front toward -X (bldkit.py).

Read from the tactical zoom as "the strongroom": a squat, windowless vault of big stone on a battered footing, bound
round with two bronze bands like a strongbox (the lower one bars the door), a heavy bronze-strapped door at the head
of three steps between two braziers, a frieze in the team's colour under the coping, and a bronze dome with a gold
finial on the flat roof. Before the door: iron-bound chests, one open on its coin, a spill of gold beside it.

States (bldkit.STATES): `complete`; `damaged` is the same build with the hooks below switched on (k.damaged) plus
damage(); `site` and `ruin` are small meshes of their own on the same footprint.
"""
from bldkit import STATES, inset_ring, ngon, rect  # noqa: F401  (STATES: which meshes build_building.py exports)

NAME = "treasury"
MESH = "SM_Bld_Treasury"
SEED = 53
FOOTPRINT = [-300.0, -300.0, 300.0, 300.0]
RING_RADIUS = 420.0
PREVIEW_FIGURES = [(-400, 130), (-440, -30)]

X0, X1, Y0, Y1 = -160.0, 230.0, -200.0, 200.0     # the vault's footing
FOOT = 54.0                                       # top of the footing
WALL = 292.0                                      # top of the walls
ROOF = 352.0                                      # top of the coping


def chest(k, pos, size=(66, 46, 36), yaw=0.0, open_=False):
    """A plank strongbox bound in bronze. Open: no lid, heaped with coin."""
    with k.at(pos, yaw):
        sx, sy, sz = size
        k.obox("Bld_Planks", (0, 0, sz / 2), size, top="Bld_Gold" if open_ else None)
        for x in (-sx * 0.3, sx * 0.3):                                       # the bands
            k.obox("Bld_Bronze", (x, 0, sz / 2), (7, sy + 4, sz + 3))
        if open_:
            k.blob("Bld_Gold", (0, 0, sz - 2), (sx - 14, sy - 12, 20), points=10, squash=0.3)
            k.obox("Bld_Planks", (0, sy / 2 + 5, sz + 16), (sx, 6, 36), roll=14)   # the lid thrown back
        else:
            k.obox("Bld_Planks", (0, 0, sz + 5), (sx + 4, sy + 4, 10))            # the lid
            k.obox("Bld_Bronze", (0, -sy / 2 - 2, sz - 4), (12, 5, 14))            # the lock plate


def vault(k):
    u0 = 20.0
    r0 = rect(X0, Y0, X1, Y1)
    r1 = k.wall("Bld_AshlarLarge", r0, 0, FOOT, inset=16, u0=u0, bleach=False)       # battered footing
    k.band("Bld_Trim", r1, FOOT, FOOT + 8, out=4, u0=u0)
    side = (Y1 - Y0) - 32
    depth = (X1 - X0) - 32
    door = dict(a=side / 2 - 52, b=side / 2 + 52, z0=FOOT + 8, z1=FOOT + 166, depth=38, back="Bld_Door", reveal="Bld_AshlarLarge", shade=0.6,
                back_shade=0.85)
    slit = lambda L, z: dict(a=L / 2 - 5, b=L / 2 + 5, z0=z, z1=z + 56, depth=14, back="Bld_Dark", shade=0.5)
    ops = {
        2: [door] + k.breach(side / 2 + 74, side / 2 + 160, FOOT + 40, FOOT + 190),
        1: [slit(depth, 190)] + k.breach(60, 150, FOOT + 60, FOOT + 170),
        3: [slit(depth, 190)],
        0: [slit(side, 190)],
    }
    r2 = k.wall("Bld_AshlarLarge", r1, FOOT + 8, WALL, inset=8, u0=u0, openings=ops)
    # bound like a strongbox: two bronze bands right round it; the lower one runs across the door as its bar
    for z in (FOOT + 76, FOOT + 186):
        f = (z - FOOT - 8) / (WALL - FOOT - 8)
        k.band("Bld_Bronze", inset_ring(r1, 8 * f), z, z + 14, out=5, u0=u0)
    fx = X0 + 16                                                                      # the front face at the footing's head
    for y in (-66, 66):                                                               # the bar's keeps, either side of the door
        k.obox("Bld_Bronze", (fx - 8, y, FOOT + 83), (16, 16, 30))
    k.obox("Bld_Trim", (fx - 2, 0, FOOT + 176), (26, 132, 16), grain="y")             # lintel
    k.steps("Bld_AshlarLarge", X0 - 96, X0 + 14, -78, 78, 0, FOOT + 8, 3, top="Bld_Trim")
    # coping, the team's frieze, a low parapet
    k.band("Bld_Trim", r2, WALL, WALL + 12, out=10, u0=u0)
    r3 = inset_ring(r2, -14)
    k.cap("Bld_AshlarLarge", r3, WALL + 12, down=True, shade=0.55)
    k.wall("Bld_Frieze", r3, WALL + 12, ROOF - 12, v0=0.0, bleach=False, u0=u0)
    k.band("Bld_Trim", r3, ROOF - 12, ROOF, out=6, u0=u0)
    k.cap("Bld_Trim", r3, ROOF)
    # the dome: bronze, on a low stone drum, a gold finial at its crown
    cx, cy = (X0 + X1) / 2, 0.0
    k.lathe("Bld_Ashlar", (cx, cy, ROOF), [(132, 0), (132, 26), (124, 30)], sides=12, rot=15)
    if not k.damaged:
        k.lathe("Bld_Bronze", (cx, cy, ROOF + 30), [(124, 0), (116, 34), (92, 68), (56, 94), (18, 108), (8, 112)], sides=12, rot=15)
        k.lathe("Bld_Gold", (cx, cy, ROOF + 140), [(6, 0), (16, 10), (18, 22), (10, 34), (4, 52)], sides=8)
    else:                                                                             # the crown has fallen in
        k.lathe("Bld_Bronze", (cx, cy, ROOF + 30), [(124, 0), (116, 34), (96, 62)], sides=12, rot=15, top="Bld_Dark")
        k.scorch("blot_m", (cx + 20, cy - 30, ROOF + 94), "up", out=1.5)
    k.pole_banner((X1 - 40, Y0 + 40, ROOF), height=250.0, cloth_w=56.0, cloth_h=150.0)


def forecourt(k):
    for y in (-124, 124):
        k.brazier((X0 - 60, y, 0), h=96)
    chest(k, (-232, 196, 0), open_=not k.damaged, yaw=18)
    chest(k, (-250, 128, 0), size=(58, 42, 32), yaw=-12)
    chest(k, (-240, -190, 0), yaw=8)
    chest(k, (-236, -192, 46), size=(52, 38, 28), yaw=-20)
    if not k.damaged:
        k.blob("Bld_Gold", (-190, 212, 0), (56, 46, 18), points=10, squash=0.3)      # coin spilt beside the open chest
    # the tally table: a plank on trestles, scales and a purse
    with k.at((-110, -262, 0), 6):
        k.obox("Bld_Planks", (0, 0, 62), (120, 54, 7))
        for x in (-44, 44):
            k.obox("Bld_Beam", (x, 0, 30), (8, 46, 60), grain="z")
        k.lathe("Bld_Bronze", (-24, 0, 66), [(12, 0), (3, 4), (3, 30), (22, 32), (22, 35)], sides=8, top="Bld_Gold")
        k.sack((30, 4, 66), 0.45, yaw=40)


def build(k, state="complete"):
    if state == "site":
        return site(k)
    if state == "ruin":
        return ruin(k)
    complete(k)
    if k.damaged:
        damage(k)


def complete(k):
    vault(k)
    forecourt(k)
    k.collider((FOOTPRINT[0], FOOTPRINT[1], 0), (FOOTPRINT[2], FOOTPRINT[3], 380))
    k.sockets["gate"] = (-360.0, 0.0, 0.0)
    k.sockets["label"] = (0.0, 0.0, ROOF + 250.0)
    k.sockets["popup"] = (-200.0, 0.0, 240.0)


def damage(k):
    """Added to the finished build on the damaged mesh: soot, looted chests, what fell."""
    fx = X0 + 16
    k.scorch("plume_m2", (fx - 6, -116, FOOT + 196))
    k.scorch("smear", (fx - 20, 60, ROOF - 60))
    k.scorch("lick", (fx - 4, 150, FOOT + 60))
    k.scorch("blot_m", (-236, 170, 0), "up", out=2.0)
    k.rubble((X0 - 50, -128, 0), (110, 150), 30, blocks=7, beams=0)
    k.rubble((60, Y1 + 40, 0), (150, 80), 22, blocks=5, beams=0)
    k.blob("Bld_Gold", (X0 - 70, -90, 22), (40, 34, 12), points=8, squash=0.3)        # a little coin among the fallen stone
    k.charred((-270, 210, 6), (-200, 176, 30), size=8)


def site(k):
    fp = FOOTPRINT
    k.footings(fp[0], fp[1], fp[2], fp[3])
    k.scaffold(X0 - 10, Y0 - 10, X1 + 10, Y1 + 10, height=340, lift=170, bay=200, depth=44, ladder=(2, 0), planks=0.4, braces=0.25)
    k.stone_stack((-240, 150, 0), yaw=80, rows=2)
    k.stone_stack((-236, -170, 0), yaw=100, rows=1)
    k.timber_pile((-60, -270, 0), length=200, base=3, planks=False)
    k.hoist((X1 + 30, Y1 + 30, 0), height=420, reach=150, yaw=215, load_z=300)
    chest(k, (-250, 0, 0), yaw=10)                                                   # the first of the gold, waiting for its walls


def ruin(k):
    r0 = rect(X0, Y0, X1, Y1)
    r1 = k.wall("Bld_AshlarLarge", r0, 0, FOOT, inset=16, u0=20.0, bleach=False)     # the footing outlasts the vault
    k.cap("Bld_Dirt", r1, FOOT)
    k.ruin_rect("Bld_AshlarLarge", X0 + 30, Y0 + 30, X1 - 30, Y1 - 30, hmax=170, hmin=18, thick=32, seg=58, z=FOOT, corners=(0.8, 0.4, 1.0, 0.55))
    cx = (X0 + X1) / 2
    k.scorch("blot_l", (cx, 10, FOOT), "up", out=1.5)
    k.rubble((cx, 0, FOOT), (280, 300), 60, blocks=11, beams=1)
    k.lathe("Bld_Bronze", (cx - 30, 40, FOOT + 40), [(96, 0), (84, 30), (40, 52)], sides=10, rot=30, top="Bld_Dark")   # the dome, fallen in
    k.rubble((X0 - 50, 20, 0), (70, 260), 0, blocks=6, beams=0, mound=False)          # spilt out of the breached front
    k.charred((-120, -150, FOOT + 6), (70, -40, FOOT + 110), size=12)
    chest(k, (-240, 150, 0), yaw=40)                                                 # a looted chest, empty on its side
    k.blob("Bld_Gold", (-200, -120, 0), (30, 26, 8), points=8, squash=0.3)           # what the looters dropped
