"""The stable: trains Horse Riders. Authored in Unreal cm, front toward -X (bldkit.py).

A long mudbrick stall range across the back of the plot under terracotta tiles: four stalls behind timber posts
and plank half-doors. At its right end the taller hay loft, gable to the front: tack room below behind a glazed
team frieze, a boarded loft above with its door open on the hay, a hoist beam under the thatch. In front a fenced
yard of packed earth: a corral with the water trough on the left, saddles and spears on racks, a haystack and
bales on the right, and a wide gateway between two tall posts with the team's standards, kept clear for riders.

States (bldkit.STATES): `complete`; `damaged` is the same build with the hooks below switched on (k.damaged) plus
damage(); `site` and `ruin` are small meshes of their own on the same footprint.
"""
import math

from bld_barracks import spear_rack
from bld_farm import fence, haystack
from bld_range import bale
from bldkit import STATES, rect  # noqa: F401

NAME = "stable"
MESH = "SM_Bld_Stable"
SEED = 71
FOOTPRINT = [-500.0, -450.0, 500.0, 450.0]
RING_RADIUS = 700.0
PREVIEW_FIGURES = [(-610, -70), (-660, 60)]

SX0, SX1, SY0, SY1 = 160.0, 470.0, -434.0, 170.0         # the stall range
S_EAVE, S_RISE = 220.0, 100.0
PLINTH = 92.0                                            # mudbrick up to here, plaster above
STALLS = (-350.0, -215.0, -80.0, 55.0)                   # centres of the stall doors (y)
LC = (290.0, 298.0)                                      # the hay loft: centre; built turned 90 deg, gable to the front
LHW, LHD = 128.0, 180.0                                  # its half width (y) and half depth (x)
L_EAVE, L_RISE = 350.0, 120.0
LFX = LC[0] - LHD                                        # its front face (x)
FX, FY = 484.0, 434.0                                    # the fence line
GATE = 130.0                                             # half width of the gateway
S_HOLES = ((-1, -300.0, 96.0, 70.0), (-1, 20.0, 60.0, 54.0), (1, -150.0, 80.0, 60.0))     # burnt through the tiles (damaged)
L_HOLES = ((-1, 40.0, 70.0, 52.0),)


def band_ops(ops, z0, z1):
    """Openings clipped to the courses z0..z1 of a wall built in two materials."""
    out = []
    for o in ops:
        if o["z1"] > z0 and o["z0"] < z1:
            c = dict(o, z0=max(o["z0"], z0), z1=min(o["z1"], z1))
            if o["z0"] < z0:
                c["no_sill"] = True
            out.append(c)
    return out


def trough(k, pos, yaw=0.0, length=190.0):
    """A plank water trough on two bearers, brim full."""
    with k.at(pos, yaw):
        h = length / 2
        for s in (-1, 1):
            k.obox("Bld_Planks", (0, s * 27, 34), (length, 6, 36))
            k.obox("Bld_Planks", (s * (h - 3), 0, 34), (6, 48, 36), grain="y")
            k.obox("Bld_Beam", (s * h * 0.62, 0, 9), (12, 72, 18), grain="y")
        k.poly("Bld_Planks", [(-h, -24, 17), (-h, 24, 17), (h, 24, 17), (h, -24, 17)], shade=0.6)
        k.poly("Bld_Water", [(-h + 6, -24, 46), (h - 6, -24, 46), (h - 6, 24, 46), (-h + 6, 24, 46)])


def bucket(k, pos, full=True):
    k.lathe("Bld_Planks", pos, [(9, 0), (12, 22)], sides=7, top="Bld_Water" if full else "Bld_Dark", rot=k.U(0, 40))


def saddle(k, y, z):
    """A riding pad over a rail that runs along local Y: a team-striped cloth, a leather seat with bronze horns."""
    for s in (-1, 1):
        k.poly("Bld_Awning", [(0, y - 24, z + 5), (0, y + 24, z + 5), (s * 22, y + 24, z - 34), (s * 22, y - 24, z - 34)],
               [(0, 0), (48, 0), (48, 44), (0, 44)], w=[0.0, 0.0, 0.25, 0.25])
    k.obox("Bld_Bark", (0, y, z + 9), (30, 34, 9), grain="y")
    for s in (-1, 1):
        k.obox("Bld_Bronze", (0, y + s * 15, z + 16), (20, 5, 9))


def saddle_rack(k, pos, yaw=0.0, n=3):
    with k.at(pos, yaw):
        w = n * 58.0
        for y in (-w / 2, w / 2):
            k.cyl("Bld_Beam", (0, y, -4), (0, y, 96), 5.0, 4.4, sides=5)
            k.cyl("Bld_Beam", (-26, y, 0), (0, y, 70), 3.2, sides=4, caps=False)
        k.obox("Bld_Beam", (0, 0, 96), (8, w + 18, 8), grain="y")
        for i in range(n):
            if k.damaged and i == 1:
                continue
            saddle(k, (i - (n - 1) / 2) * 54, 100)


def hitch_rail(k, pos, yaw=0.0, length=150.0):
    with k.at(pos, yaw):
        for y in (-length / 2, length / 2):
            k.cyl("Bld_Bark", (0, y, -4), (0, y, 108), 7.0, 6.0, sides=6, grain="ring", cap_slot="Bld_Beam")
        k.obox("Bld_Beam", (0, 0, 96), (8, length + 26, 9), grain="y")
        k.lathe("Bld_Thatch", (0, length / 2, 60), [(9, 0), (13, 4), (13, 12), (9, 16)], sides=7, top="Bld_Dark")     # a coiled halter rope
        k.rope((0, length / 2 - 6, 96), (0, length / 2 - 2, 70), 1.6)


def stalls(k):
    u0 = 24.0
    r0 = rect(SX0, SY0, SX1, SY1)
    opening = lambda y: dict(a=SY1 - (y + 48), b=SY1 - (y - 48), z0=0.0, z1=176.0, depth=44, back="Bld_Dark", reveal="Bld_Mudbrick",
                             shade=0.62, back_shade=0.9, no_sill=True)
    ops = {2: [opening(y) for y in STALLS] + k.breach(SY1 - (-124), SY1 - (-172), 30, 150, depth=30),
           3: [dict(a=120, b=168, z0=110, z1=160, depth=12, back="Bld_Shutter", reveal="Bld_Mudbrick", shade=0.7)]}
    k.wall("Bld_Mudbrick", r0, 0, PLINTH, u0=u0, openings={e: band_ops(o, 0, PLINTH) for e, o in ops.items()}, bleach=False)
    k.wall("Bld_Plaster", r0, PLINTH, S_EAVE, u0=u0, openings={e: band_ops(o, PLINTH, S_EAVE) for e, o in ops.items()})
    k.cap("Bld_Mudbrick", r0, 0.5, down=True)
    fx = SX0
    for i, y in enumerate(STALLS):                           # plank half-doors; one stands open
        if i == 2 and not k.damaged:
            k.obox("Bld_Planks", (fx - 42, y + 54, 50), (6, 92, 96), yaw=82, grain="z")
        elif not (k.damaged and i == 1):
            k.obox("Bld_Planks", (fx + 8, y, 50), (6, 94, 96), grain="z")
            k.obox("Bld_Beam", (fx + 4, y, 94), (5, 96, 7), grain="y")
            k.obox("Bld_Bronze", (fx + 3, y + 36, 62), (4, 5, 14))
        k.blob("Bld_Thatch", (fx - 12, y + k.U(-14, 14), 2), (44, 70, 14), points=8, squash=0.3)      # bedding straw trodden out
    y = SY0 + 16.0                                           # timber posts between the stalls, a lintel, the wall plate
    for y in (SY0 + 9, -282.5, -147.5, -12.5, SY1 - 60):
        k.obox("Bld_Beam", (fx - 3, y, S_EAVE / 2), (10, 15, S_EAVE), grain="z")
    k.obox("Bld_Beam", (fx - 4, (SY0 + SY1) / 2 - 20, 184), (10, SY1 - SY0 - 40, 14), grain="y")
    k.band("Bld_Beam", r0, S_EAVE - 10, S_EAVE + 2, out=4, u0=u0)
    k.gable_end("Bld_Plaster", SX0, SX1, SY0, S_EAVE, S_RISE)
    k.obox("Bld_Beam", ((SX0 + SX1) / 2, SY0 - 2.5, S_EAVE + S_RISE * 0.4), (12, 9, S_RISE * 0.8), grain="z")
    k.gable_roof("Bld_RoofTile", SX0, SX1, SY0, SY1 + 6, S_EAVE, S_RISE, over=30, verge=20, ridge="Bld_RoofTile", holes=S_HOLES)


def loft(k):
    """Built in its own frame, turned 90 degrees: local +Y is the building's front (-X), local +X is +Y."""
    u0 = 300.0
    with k.at((LC[0], LC[1], 0), yaw=90):
        r0 = rect(-LHW, -LHD, LHW, LHD)
        door = dict(a=LHW - 64, b=LHW + 64, z0=0.0, z1=154.0, depth=20, back="Bld_Door", back_uv=(64, 50), reveal="Bld_Mudbrick", shade=0.62,
                    back_shade=0.82, no_sill=True)
        k.wall("Bld_Mudbrick", r0, 0, PLINTH, u0=u0, openings={1: band_ops([door], 0, PLINTH)}, bleach=False)
        k.wall("Bld_Plaster", r0, PLINTH, 172, u0=u0, openings={1: band_ops([door], PLINTH, 172)}, bleach=False)
        k.cap("Bld_Mudbrick", r0, 0.5, down=True)
        k.wall("Bld_Frieze", r0, 172, 236, v0=0.0, bleach=False, u0=u0)
        k.band("Bld_Beam", r0, 236, 248, out=5, u0=u0)
        hatch = dict(a=LHW - 52, b=LHW + 52, z0=258.0, z1=338.0, depth=12, back="Bld_Thatch", reveal="Bld_Beam", shade=0.7, back_shade=0.8)
        k.wall("Bld_Planks", r0, 248, L_EAVE, u0=u0, openings={1: [hatch] + k.breach(LHW + 60, LHW + 118, 256, 340, depth=14)})
        fy = LHD
        k.obox("Bld_Beam", (0, fy + 4, 162), (150, 10, 14))                       # the door's lintel
        for s in (-1, 1):                                                        # corner posts, the loft door's leaves folded back
            k.obox("Bld_Beam", (s * (LHW - 5), fy + 2.5, L_EAVE / 2), (14, 9, L_EAVE), grain="z")
            if not (k.damaged and s > 0):
                k.obox("Bld_Planks", (s * 78, fy + 4, 298), (46, 5, 80), grain="z")
        k.obox("Bld_Beam", (0, fy + 5, 254), (118, 12, 8))                        # the hatch sill
        k.blob("Bld_Thatch", (0, fy - 4, 262), (96, 30, 40), points=9, squash=0.3)      # hay spilling over it
        for facing, y in ((1, fy), (-1, -fy)):
            k.gable_end("Bld_Planks", -LHW, LHW, y, L_EAVE, L_RISE, facing=facing)
        k.obox("Bld_Beam", (0, fy + 3, L_EAVE - 2), (2 * LHW + 8, 10, 12))
        k.gable_roof("Bld_Thatch", -LHW, LHW, -LHD, LHD, L_EAVE, L_RISE, over=22, verge=28, holes=L_HOLES)
        # the hoist: a beam out of the gable, a bronze block, a bale on the rope
        zb = L_EAVE + L_RISE - 34
        k.obox("Bld_Beam", (0, fy + 36, zb), (12, 104, 12), grain="y")
        k.cyl("Bld_Bronze", (-7, fy + 78, zb - 10), (7, fy + 78, zb - 10), 8.0, sides=6, grain="ring")
        if not k.damaged:
            k.rope((0, fy + 78, zb - 12), (0, fy + 78, 372), 1.5)
            k.obox("Bld_Bronze", (0, fy + 78, 366), (5, 5, 14))
        k.cyl("Bld_Bronze", (0, fy + 3, 198), (0, fy + 9, 198), 15.0, sides=8, grain="ring")      # a sun disc over the door


def yard(k):
    k.box("Bld_Dirt", (-FX + 8, -FY + 8, -2), (SX0 + 60, SY1 - 2, 3), u0=0.0)       # packed earth, on into the stalls
    k.box("Bld_Dirt", (-FX + 8, SY1 - 2, -2), (SX0 + 2, FY - 8, 3), u0=0.0)
    k.box("Bld_Dirt", (SX0, SY1, -2), (LFX + 2, FY - 8, 3), u0=0.0)
    d = k.damaged
    fence(k, [(SX0 - 4, -FY), (-FX, -FY), (-FX, -GATE)], gaps=((0, 200, 420),) if d else ())
    fence(k, [(-FX, GATE), (-FX, FY), (LFX - 4, FY)], gaps=((1, 120, 300),) if d else ())
    for s in (-1, 1):                                        # the gateway: tall posts, bronze caps, the standards inside
        k.cyl("Bld_Bark", (-FX, s * GATE, -4), (-FX, s * GATE, 236), 10.0, 8.0, sides=7, grain="ring", cap_slot="Bld_Beam")
        k.lathe("Bld_Bronze", (-FX, s * GATE, 236), [(10, 0), (8, 6), (1, 20)], sides=7)
        k.cyl("Bld_Beam", (-FX + 4, s * (GATE + 70), 4), (-FX, s * GATE, 150), 4.0, sides=4, caps=False)       # a strut
        if not (d and s > 0):
            k.pole_banner((-FX - 2, s * (GATE + 52), 0), height=350.0)
    # the corral, left of the way in: water, a heap of fodder
    fence(k, [(-FX, -150), (-184, -150), (-184, -340)], gaps=((0, 60, 190),) if d else ())
    trough(k, (-330, -300, 0), yaw=4)
    bucket(k, (-212, -236, 0))
    bucket(k, (-420, -372, 0), full=False)
    k.blob("Bld_Thatch", (-410, -214, 0), (120, 100, 70), points=12, squash=0.35)
    k.cyl("Bld_Beam", (-360, -196, 0), (-404, -214, 150), 2.4, sides=4, caps=False)      # a hay fork stuck in it
    for y in (-10, 0, 10):
        k.cyl("Bld_Bronze", (-404, -214 + y * 0.6, 150), (-410, -214 + y, 176), 1.4, sides=4, caps=False)
    hitch_rail(k, (40, -250, 0), length=170)
    bucket(k, (72, -330, 0))
    # right of it: saddles, spears, hay
    saddle_rack(k, (-30, 262, 0), yaw=-6)
    spear_rack(k, (-236, 300, 0), yaw=8, n=6)
    if not d:
        haystack(k, (-392, 322, 0), r=74.0, h=136.0)
    else:
        k.lathe("Bld_Char", (-392, 322, 0), [(74, 0), (66, 26), (20, 44)], sides=9, rot=11)
    bale(k, (56, 396, 0), 88)
    bale(k, (60, 392, 46), 80)
    bale(k, (-44, 396, 0), 96)
    k.pot((LFX - 26, 196, 0), 0.95)
    k.sack((LFX - 30, 388, 92), 0.9, yaw=30)


def build(k, state="complete"):
    if state == "site":
        return site(k)
    if state == "ruin":
        return ruin(k)
    complete(k)
    if k.damaged:
        damage(k)


def complete(k):
    stalls(k)
    loft(k)
    yard(k)
    k.collider((FOOTPRINT[0], FOOTPRINT[1], 0), (FOOTPRINT[2], FOOTPRINT[3], 320))
    k.sockets["gate"] = (-570.0, 0.0, 0.0)           # where a rider appears: just outside the gateway
    k.sockets["rally"] = (-870.0, 0.0, 0.0)          # default rally point, straight out from it
    k.sockets["label"] = (200.0, 0.0, 640.0)
    k.sockets["popup"] = (0.0, 0.0, 420.0)


def damage(k):
    """Added to the finished build on the damaged mesh: soot, what fell, what burnt."""
    fx = SX0
    k.scorch("smear", (fx, -150, 150))                       # over the breach, up under the eave
    k.scorch("plume_s", (fx, -360, 120), flip=True)
    k.scorch("plume_s", (LFX, LC[1] + 86, 250), out=6)
    k.scorch("lick", (LFX, LC[1] - 96, 60))
    k.rubble((fx - 54, -150, 0), (110, 130), 24, slot="Bld_Mudbrick", blocks=7, beams=1, block=(30, 18, 12))
    k.rubble((fx - 76, 20, 3), (100, 200), 0, slot="Bld_RoofTile", blocks=8, beams=1, mound=False, block=(34, 26, 6))       # slid tiles
    k.charred((fx - 10, -215 - 40, 4), (fx - 96, -215 + 30, 10), size=7)                   # a stall door, down and burnt
    k.scorch("blot_l", (-392, 322, 3), "up", out=1.5)        # where the haystack burnt
    k.scorch("blot_m", (-300, -350, 3), "up", out=1.5)
    k.charred((-FX + 20, GATE + 52, 0), (-FX + 180, GATE + 150, 12), size=9)               # the fallen standard's pole
    k.charred((-330, -150, 6), (-240, -90, 10), size=7)
    k.charred((-150, 440, 6), (-40, 400, 10), size=7)


def site(k):
    fp = FOOTPRINT
    k.footings(fp[0], fp[1], fp[2], fp[3], width=22, height=9, slot="Bld_Mudbrick", top="Bld_Mudbrick")
    k.scaffold(SX0 - 8, SY0 - 4, SX1 + 6, FY + 2, height=300, lift=150, bay=215, depth=42, ladder=(2, 1))
    k.stone_stack((-150, -280, 0), yaw=12, slot="Bld_Mudbrick", block=(40, 22, 14), courses=(4, 4, 3, 3), rows=3)
    k.stone_stack((-60, -360, 0), yaw=80, slot="Bld_Mudbrick", block=(40, 22, 14), courses=(3, 3, 2), rows=2)
    k.timber_pile((-250, 270, 0), yaw=80, length=240, base=4)
    k.hoist((SX0 - 54, SY0 + 40, 0), height=430, reach=180, yaw=40, load_z=280)
    for i in range(3):                                       # reeds for the loft's thatch
        k.cyl("Bld_Thatch", (-20 + i * 18, 150, 12), (-8 + i * 18, 330, 12), 11.0, sides=6)
    for s in (-1, 1):                                        # the gateway pegged out
        k.cyl("Bld_Beam", (-FX, s * GATE, -4), (-FX, s * GATE, 70), 4.5, 3.5, sides=5)
    k.rope((-FX, -GATE, 56), (-FX, GATE, 56), 1.4)


def ruin(k):
    k.box("Bld_Dirt", (-FX + 8, -FY + 8, -2), (SX1, FY - 8, 3), u0=0.0)
    k.ruin_rect("Bld_Mudbrick", SX0 + 14, SY0 + 14, SX1 - 14, SY1 - 10, hmax=104, hmin=16, thick=26, seg=50, gaps=0.24, corners=(1, 0.4, 0.5, 0.8),
                step=12, z=3)
    k.ruin_rect("Bld_Mudbrick", LFX + 14, LC[1] - LHW + 14, LC[0] + LHD - 14, LC[1] + LHW - 14, hmax=108, hmin=24, thick=28, seg=50, gaps=0.14,
                corners=(0.5, 1, 0.9, 0.4), step=12, z=3)
    k.rubble((300, -150, 3), (230, 460), 46, slot="Bld_RoofTile", blocks=14, beams=5, block=(40, 30, 8))       # the roof, fallen in
    k.rubble((LC[0] - 10, LC[1] - 10, 3), (240, 180), 50, slot="Bld_Char", blocks=5, beams=3, block=(60, 12, 8))        # the burnt loft
    k.rubble((SX0 - 40, -60, 3), (110, 260), 0, slot="Bld_Mudbrick", blocks=9, beams=1, mound=False, block=(30, 18, 12))
    for i, y in enumerate((-282.5, -147.5, -12.5)):          # the stall posts' stumps
        k.cyl("Bld_Char", (SX0 - 3, y, 0), (SX0 - 1, y + 3, 50 + i * 26), 8.0, 6.5, sides=5)
    fence(k, [(SX0 - 4, -FY), (-FX, -FY), (-FX, -GATE)], gaps=((0, 150, 420), (1, 150, 260)), post_h=64)
    fence(k, [(-FX, GATE), (-FX, FY), (LFX - 4, FY)], gaps=((0, 60, 200), (1, 200, 480)), post_h=64)
    k.cyl("Bld_Char", (-FX, -GATE, -4), (-FX + 3, -GATE, 110), 10.0, 8.0, sides=7, grain="ring")
    k.cyl("Bld_Char", (-FX, GATE, -4), (-FX, GATE + 2, 56), 10.0, 8.0, sides=7, grain="ring")
    trough(k, (-330, -300, 0), yaw=4)                        # the trough outlasts the rest
    k.blob("Bld_Char", (-392, 322, 0), (150, 150, 56), points=11, squash=0.3)
    for (x, y, kind) in ((-392, 322, "blot_l"), (-120, 240, "blot_m"), (-250, -120, "blot_w"), (40, -260, "blot_l")):
        k.scorch(kind, (x, y, 3), "up", out=1.5)
    k.charred((-120, 190, 6), (-10, 290, 14), size=8)
    k.charred((-300, 380, 6), (-180, 410, 10), size=7)
    k.charred((30, -330, 6), (60, -170, 12), size=9)
    k.charred((60, 60, 6), (150, 140, 70), size=12)
