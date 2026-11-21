"""The granary: holds food on top of the castle's stores. Authored in Unreal cm, front toward -X (bldkit.py).

Read from the tactical zoom as "the grain store": a plank barn lifted clear of the damp (and the rats) on mushroom
staddle stones, under a steep gold thatch whose ridge runs across the screen; a loading door at the head of a short
flight of steps, a hoist beam out of the right-hand gable with a sack on the rope, and the harvest stacked round it
in sacks, baskets and jars. A banner in the team's colour stands at the corner of the yard.

States (bldkit.STATES): `complete`; `damaged` is the same build with the hooks below switched on (k.damaged) plus
damage(); `site` and `ruin` are small meshes of their own on the same footprint.

Levels 1-3 (k.level), each adding to the last (medieval and weathered: slate, dark stone, iron; no gold; the
treasury, its pair, climbs the same way):
  2  built up: the barn's walls are dressed stone with a jettied timber-framed loft half a storey higher, the thatch
     gives way to dark slate, standards hang either side of the door
  3  fortified: a square stone lookout turret rises through the ridge, topped as the castle's towers are (a glazed
     frieze, crow-stepped merlons round a flat roof, a standard on a pole), the lower walls are dark stone bound with an iron band, iron finials on the gable ends, fires either
     side of the steps, creeper on the front wall
The level banner (kit.level_flag) stands at the yard's front-left corner.
"""
from bldkit import MATERIALS, STATES, inset_ring, rect  # noqa: F401  (STATES: which meshes build_building.py exports)

NAME = "granary"
MESH = "SM_Bld_Granary"
SEED = 47
FOOTPRINT = [-320.0, -320.0, 320.0, 320.0]
RING_RADIUS = 450.0
LEVELS = 3
PREVIEW_FIGURES = [(-420, 120), (-460, -40)]

X0, X1, Y0, Y1 = -150.0, 210.0, -230.0, 230.0     # the barn's walls
FLOOR = 78.0                                      # top of the plank floor, on the staddles
EAVE = 262.0                                      # wall head
RISE = 196.0                                      # eave to ridge


def mat(slot, fallback):
    """A slot of the medieval set, or its stand-in while the kit does not have it yet."""
    return slot if slot in MATERIALS else fallback


SLATE, IRON, DARK, TIMBER = (mat("Bld_Slate", "Bld_RoofTile"), mat("Bld_Iron", "Bld_Bronze"), mat("Bld_StoneDark", "Bld_AshlarLarge"),
                             mat("Bld_Timber", "Bld_Plaster"))
JETTY = 148.0                                     # above the floor: where the loft's timber framing starts (level 2 on)


def lift(k):
    """How much higher the walls stand from level 2 on."""
    return 50.0 if k.level >= 2 else 0.0


def staddle(k, pos):
    """A mushroom-headed staddle stone: the granary stands on a grid of them."""
    k.lathe("Bld_Trim", pos, [(19, 0), (13, 12), (11, 44), (30, 50), (30, 57), (20, 62)], sides=7, top="Bld_Trim", rot=k.U(0, 50))


def staddles(k):
    for x in (X0 + 22, (X0 + X1) / 2, X1 - 22):
        for y in (Y0 + 22, Y0 + 22 + (Y1 - Y0 - 44) / 3, Y1 - 22 - (Y1 - Y0 - 44) / 3, Y1 - 22):
            staddle(k, (x, y, 0))


def lantern(k, zr):
    """Level 3: a square stone lookout turret through the middle of the ridge, flat-topped like the castle's towers:
    the head oversails on a corbel course over a glazed frieze, crow-stepped merlons, a standard on a pole."""
    xc, half = (X0 + X1) / 2, 70.0
    h = zr + 110                                                                     # the top of its parapet
    top = h - 64
    r0 = rect(xc - half, -half, xc + half, half)
    slit = dict(a=half - 5, b=half + 5, z0=top - 62, z1=top - 14, depth=12, back="Bld_Dark", shade=0.5)
    k.wall("Bld_Ashlar", r0, zr - 110, top, u0=80.0, bleach=False, openings={2: [slit]})
    k.band("Bld_Trim", r0, top, top + 10, out=8)
    r1 = inset_ring(r0, -9)
    k.cap("Bld_AshlarLarge", r1, top + 10, down=True, shade=0.55)
    k.wall("Bld_Frieze", r1, top + 10, h, v0=0.0, bleach=False, u0=80.0)
    k.parapet("Bld_Ashlar", r1, h - 30, h, thick=20, top="Bld_Trim")
    k.stepped_merlons("Bld_Ashlar", r1, h, width=40, gap=24, thick=20, h1=22, h2=18, cap="Bld_Trim")
    k.pole_banner((xc, 0, h - 30), height=112.0, cloth_w=48.0, cloth_h=84.0)
    if k.damaged:
        k.scorch("smear", (xc - half - 9, 10, top - 40))
        k.burn_hole((xc + 6, -8, h - 30), (70, 60), yaw=20, soot="blot_s")


def barn(k):
    lv = k.level
    E = EAVE + lift(k)                                                               # wall head
    stone = lv >= 2
    frame = "Bld_Trim" if stone else "Bld_Beam"
    staddles(k)
    # floor: bearers on the stones, planks across them
    for y in (Y0 + 22, Y0 + 22 + (Y1 - Y0 - 44) / 3, Y1 - 22 - (Y1 - Y0 - 44) / 3, Y1 - 22):
        k.obox("Bld_Beam", ((X0 + X1) / 2, y, 66), (X1 - X0 + 20, 14, 10))
    k.box("Bld_Planks", (X0 - 8, Y0 - 8, 70), (X1 + 8, Y1 + 8, FLOOR), bottom=True)
    # plank walls in a timber frame, a loading door in the front
    ring = rect(X0, Y0, X1, Y1)
    side = Y1 - Y0
    door = dict(a=side / 2 - 52, b=side / 2 + 52, z0=FLOOR, z1=FLOOR + 138, depth=22, back="Bld_Dark", reveal="Bld_Beam", shade=0.7,
                back_shade=0.9, no_sill=True)
    vent = dict(a=side / 2 - 150, b=side / 2 - 118, z0=FLOOR + 96, z1=FLOOR + 132, depth=10, back="Bld_Dark", shade=0.6)
    vent2 = dict(a=side / 2 + 118, b=side / 2 + 150, z0=FLOOR + 96, z1=FLOOR + 132, depth=10, back="Bld_Dark", shade=0.6)
    low = (DARK if lv >= 3 else "Bld_Ashlar") if stone else "Bld_Planks"
    zw = FLOOR + JETTY if stone else E                                               # the lower wall's head
    k.wall(low, ring, FLOOR, zw, u0=30.0, bleach=False,
           openings={2: [door, vent, vent2] + k.breach(side / 2 + 70, side / 2 + 168, FLOOR + 20, FLOOR + (126 if stone else 150), depth=20)})
    if stone:                                                                        # the loft: timber-framed, jettied out over the stone
        jr = inset_ring(ring, -14)
        k.cap("Bld_Planks", jr, zw, down=True, shade=0.55)
        k.band("Bld_Beam", jr, zw, zw + 14, out=2, u0=30.0)
        k.wall(TIMBER, jr, zw + 14, E, u0=0.0, bleach=False)
        k.beam_ends("Bld_Beam", (X0, Y1 - 24), (X0, Y0 + 24), zw - 10, 8, size=(12, 12), out=16)
        if lv >= 3:
            k.band(IRON, ring, FLOOR + 96, FLOOR + 108, out=4, u0=30.0)
        fx = X0 - 14 - 7                                                             # standards either side of the door
        for y in (-150, 150):
            k.cyl(IRON, (fx, y - 36, E - 30), (fx, y + 36, E - 30), 2.6, sides=4)
            k.hang_cloth((fx, y - 30, E - 32), (fx, y + 30, E - 32), 150.0)
        if lv >= 3 and not k.damaged:
            k.patch("Bld_Leaves", (X0 - 2, 190, FLOOR), (0, -1, 0), (0, 0, 1), 70, 130, cells=12, fill=0.6, out=4)
    k.band(frame, ring, FLOOR - 2, FLOOR + 12, out=5, u0=30.0)                       # sill beam
    k.band("Bld_Beam", inset_ring(ring, -14) if stone else ring, E - 12, E + 2, out=5, u0=30.0)        # wall plate
    for (x, y) in ((X0, Y0), (X0, Y1), (X1, Y0), (X1, Y1)):                          # corner posts
        k.obox(frame, (x, y, (FLOOR + zw) / 2), (18, 18, zw - FLOOR), grain="z")
    for y in (-58, 58):                                                              # door posts and lintel
        k.obox("Bld_Beam", (X0 - 2, y, FLOOR + 72), (12, 12, 148), grain="z")
    k.obox("Bld_Beam", (X0 - 2, 0, FLOOR + 146), (12, 136, 14), grain="y")
    # what the open door shows: the heaped grain and a sack on the sill
    if not k.damaged:
        k.blob("Bld_Thatch", (X0 + 40, 0, FLOOR), (70, 96, 84), points=12, squash=0.35)
        k.sack((X0 + 2, 26, FLOOR), 0.8, yaw=70)
    # the thatch: steep, deep-eaved, its ridge across the screen; plank gables
    roof = SLATE if stone else "Bld_Thatch"
    k.gable_roof(roof, X0, X1, Y0, Y1, E, RISE, over=32, verge=30, ridge=roof, edge="Bld_Beam",
                 holes=((-1, 150, 110, 70), (1, -70, 90, 60)) if lv >= 3 else ((-1, 96, 110, 78), (1, -70, 90, 60)))
    gable = TIMBER if stone else "Bld_Planks"
    k.gable_end(gable, X0, X1, Y0, E, RISE, facing=-1)
    k.gable_end(gable, X0, X1, Y1, E, RISE, facing=1)
    if lv >= 3:                                                                      # iron finials on the gable ends
        for y in (Y0 - 14, Y1 + 14):
            k.finial(((X0 + X1) / 2, y, E + RISE - 4), slot=IRON, h=70, r=15)
    if not stone:
        for y in (Y0 + 40, 0.0, Y1 - 40):                                            # hazel spars pinning the ridge
            k.obox("Bld_Beam", ((X0 + X1) / 2, y, E + RISE + 8), (54, 5, 5), yaw=k.U(-12, 12))
    if lv >= 3:
        lantern(k, E + RISE)
    # steps up to the door (a gap is left under the last tread, as the stones leave under the barn)
    k.steps("Bld_Planks", X0 - 150, X0 - 22, -60, 60, 0, FLOOR - 4, 4, top="Bld_Planks")
    # the hoist: a beam out of the right-hand gable, a rope, a sack on its way up
    xc = (X0 + X1) / 2
    k.obox("Bld_Beam", (xc, Y1 + 40, E + RISE - 44), (12, 130, 12), grain="y")
    k.obox("Bld_Beam", (xc, Y1 + 28, E + RISE - 76), (9, 78, 9), roll=-38, grain="y")
    k.obox("Bld_Planks", (xc, Y1 + 3, E + 62), (56, 6, 84), grain="z")             # the loft hatch under it
    if not k.damaged:
        k.rope((xc, Y1 + 92, E + RISE - 50), (xc, Y1 + 92, 226), 1.6)
        k.sack((xc, Y1 + 92, 196), 0.95, yaw=20)


def yard(k):
    """The harvest waiting to go in: sacks stacked by the steps, baskets of grain, jars, sheaves, a handcart."""
    for (x, y, z, s, yaw) in ((-262, 126, 0, 1.0, 12), (-258, 172, 0, 1.0, -24), (-222, 150, 0, 0.95, 60), (-250, 148, 27, 0.9, 80),
                              (-226, 196, 0, 0.9, -70), (-240, 174, 26, 0.85, 20), (-246, 160, 50, 0.8, -40)):
        if k.damaged and z > 30:
            continue                                          # the top of the stack has gone
        k.sack((x, y, z), s, yaw=yaw)
    k.basket((-268, -112, 0), 30, 30, fill="Bld_Thatch")
    k.basket((-232, -150, 0), 26, 26, fill="Bld_Thatch")
    k.basket((-286, -164, 0), 22, 22, fill="Bld_Thatch")
    k.pot((-204, -100, 0), 1.2)
    k.pot((-180, -136, 0), 0.9)
    # sheaves stood against the steps' side
    for (y, lean) in ((-78, -10), (-96, 6), (84, 8)):
        k.lathe("Bld_Thatch", (X0 - 96, y, 0), [(20, 0), (11, 44), (17, 78), (20, 86)], sides=6, top="Bld_Thatch", rot=k.U(0, 60))
    # a handcart with two sacks, its shafts on the ground
    with k.at((-90, -278, 0), -8):
        k.obox("Bld_Planks", (0, 0, 44), (120, 64, 8))
        for s in (-1, 1):
            k.obox("Bld_Planks", (0, s * 32, 60), (120, 6, 26))
            k.wheel((10, s * 42, 32), radius=32.0, thick=7.0)
            k.obox("Bld_Beam", (-104, s * 22, 40), (100, 6, 6), pitch=9)
        k.sack((6, 4, 48), 0.9, yaw=30)
        k.sack((-28, -6, 48), 0.8, yaw=-50)
    k.pole_banner((-282, 270, 0), height=320.0, cloth_w=56.0, cloth_h=150.0)
    if k.level >= 3:                                          # fires either side of the way up
        for y in (-150, 104):
            k.brazier((-306, y, 0), h=96)


def build(k, state="complete"):
    if state == "site":
        return site(k)
    if state == "ruin":
        return ruin(k)
    complete(k)
    if k.damaged:
        damage(k)


def complete(k):
    barn(k)
    yard(k)
    k.level_flag((-296, -268, 0), height=240.0)
    top = EAVE + lift(k) + RISE + (206.0 if k.level >= 3 else 0.0)
    k.collider((FOOTPRINT[0], FOOTPRINT[1], 0), (FOOTPRINT[2], FOOTPRINT[3], 420))
    k.sockets["gate"] = (-380.0, 0.0, 0.0)
    k.sockets["label"] = (0.0, 0.0, top + (60.0 if k.level >= 3 else 150.0))
    k.sockets["popup"] = (-200.0, 0.0, 260.0)


def damage(k):
    """Added to the finished build on the damaged mesh: soot, spilt grain, what fell."""
    k.scorch("plume_m2", (X0 - 2, -96, FLOOR + 150))
    k.scorch("smear", (X0 - (16 if k.level >= 2 else 2), 40, EAVE - 30))             # (the loft is jettied out from level 2)
    k.scorch("lick", (X0 - 2, 150, FLOOR + 40))
    k.scorch("blot_m", (-250, 160, 0), "up", out=2.0)
    k.blob("Bld_Thatch", (X0 - 40, -120, 0), (120, 110, 26), points=12, squash=0.3)   # grain run out through the breach
    k.charred((X0 - 30, -160, 8), (X0 - 6, -70, FLOOR + 60), size=9)
    E = EAVE + lift(k)
    k.charred((X0 + 40, 96 if k.level < 3 else 150, E + 60), (X0 - 70, 150 if k.level < 3 else 200, E - 40), size=10)
    k.rubble((X0 - 60, -110, 0), (120, 150), 20, slot="Bld_Planks", blocks=5, beams=2, block=(60, 12, 6))


def site(k):
    fp = FOOTPRINT
    k.footings(fp[0], fp[1], fp[2], fp[3], width=20, height=9, slot="Bld_Trim", top="Bld_Trim")
    staddles(k)                                               # the stones go in first
    k.scaffold(X0 - 14, Y0 - 14, X1 + 14, Y1 + 14, height=330, lift=165, bay=170, depth=40, ladder=(2, 0))
    k.timber_pile((-250, 160, 0), yaw=14, length=220, base=4)
    k.timber_pile((-246, -190, 0), yaw=-20, length=180, base=3, planks=True)
    k.blob("Bld_Thatch", (-90, -280, 0), (150, 70, 60), points=12, squash=0.3)       # bundles of reed for the roof
    k.sack((-270, -40, 0), 1.0, yaw=40)
    k.sack((-250, -8, 0), 0.9, yaw=-20)


def ruin(k):
    staddles(k)                                               # the stones outlast the barn
    k.scorch("blot_l", (30, -40, 0), "up", out=1.5)
    k.scorch("blot_w", (10, 110, 0), "up", out=1.6)
    k.blob("Bld_Char", (30, 0, 44), (330, 400, 70), points=16, squash=0.3)           # the floor and the grain, burnt
    k.blob("Bld_Thatch", (-70, -90, 40), (120, 130, 44), points=10, squash=0.35)     # a heap the fire missed
    for (a, b) in (((X0, Y0, 60), (X0 + 20, Y0 + 10, 250)), ((X1, Y1, 60), (X1 - 30, Y1 - 20, 190)), ((X0, Y1, 60), (X0 + 10, Y1 - 6, 140)),
                   ((-120, -150, 70), (150, -40, 130)), ((140, 160, 64), (-60, 60, 110)), ((-140, 40, 66), (60, 190, 96))):
        k.charred(a, b, size=12)
    k.rubble((30, 0, 50), (300, 380), 34, slot="Bld_Char", blocks=8, beams=3, block=(64, 14, 7))
    k.rubble((-230, 150, 0), (110, 120), 0, slot="Bld_Char", blocks=4, beams=1, mound=False, block=(40, 30, 20))
    k.cyl("Bld_Char", (-282, 270, -4), (-276, 266, 90), 5.0, 4.0, sides=5)           # the banner pole's stump
