"""The archery range: trains Archers. Authored in Unreal cm, front toward -X (bldkit.py).

A bowyer's lodge in the back corner (mudbrick and plaster under reed thatch, a glazed team frieze under the eave)
and a fenced yard: a shooting line under a striped awning on posts, three straw butts with painted faces against
a wall of bales at the far end, a bow rack and quiver jars at the line, a fletching bench by the lodge door, the
team's standard at the gate.

States (bldkit.STATES): `complete`; `damaged` is the same build with the hooks below switched on (k.damaged) plus
damage(); `site` and `ruin` are small meshes of their own on the same footprint.
"""
import math

from bld_farm import fence
from bldkit import STATES, rect  # noqa: F401

NAME = "range"
MESH = "SM_Bld_Range"
SEED = 59
FOOTPRINT = [-400.0, -400.0, 400.0, 400.0]
RING_RADIUS = 560.0
PREVIEW_FIGURES = [(-500, -240), (-540, -130)]

LX0, LX1, LY0, LY1 = 120.0, 384.0, -384.0, -96.0         # the lodge
EAVE, RISE = 240.0, 140.0
SX0, SX1, SY0, SY1 = -262.0, -128.0, 14.0, 372.0         # the shooting line's roof (low front edge, high back edge)
BUTTS = ((276.0, 52.0), (276.0, 190.0), (276.0, 326.0))
GATE = (-256.0, -124.0)                                  # the gap in the front fence (y)
F = 386.0                                                # the fence line
HOLES = ((-1, -300.0, 84.0, 58.0), (1, -180.0, 70.0, 54.0))


def front(ya, yb, **kw):
    """An opening in the lodge's front wall between y = ya and yb."""
    return dict(a=(LY1 - 6) - yb, b=(LY1 - 6) - ya, **kw)


def butt(k, pos, r=64.0, thick=26.0, fallen=False):
    """A straw archery butt on a trestle, leaning back a little so its painted face shows from above."""
    lean = math.radians(78.0 if fallen else 16.0)
    with k.at(pos, k.U(-8, 8)):
        cz = 14.0 if fallen else 100.0
        n = (-math.cos(lean), 0.0, math.sin(lean))           # the face's normal
        up = (math.sin(lean), 0.0, math.cos(lean))
        c = (0.0, 0.0, cz)
        back = tuple(c[i] - n[i] * thick for i in range(3))
        ring = lambda o, i: (o[0] + up[0] * math.sin(i * math.pi / 5) * r, o[1] + math.cos(i * math.pi / 5) * r,
                             o[2] + up[2] * math.sin(i * math.pi / 5) * r)
        order = list(reversed(range(10)))
        k.poly("Bld_Target", [ring(c, i) for i in order], [(64 + math.cos(i * math.pi / 5) * 62, 64 - math.sin(i * math.pi / 5) * 62) for i in order])
        k.cyl("Bld_Thatch", back, c, r, sides=10, grain="ring", caps=False)
        k.poly("Bld_Thatch", [ring(back, i) for i in range(10)])
        if fallen:
            return
        for s in (-1, 1):                                    # two legs in front, one prop behind
            k.cyl("Bld_Beam", (-26, s * 44, 0), (back[0] + 2, s * 30, cz + 20), 4.2, 3.6, sides=5)
        k.cyl("Bld_Beam", (74, 0, 0), (back[0] + 4, 0, cz + 34), 4.2, 3.6, sides=5)
        k.obox("Bld_Beam", (-14, 0, 36), (7, 104, 7), grain="y")       # the ledge the butt sits on


def bale(k, pos, yaw=0.0, size=(96.0, 52.0, 46.0)):
    k.obox("Bld_Thatch", (pos[0], pos[1], pos[2] + size[2] / 2), size, yaw=yaw)


def bow_rack(k, pos, yaw=0.0, n=4):
    """A rail on two posts with strung bows hung from it."""
    with k.at(pos, yaw):
        for y in (-66, 66):
            k.cyl("Bld_Beam", (0, y, -4), (0, y, 156), 4.6, 4.0, sides=5)
        k.obox("Bld_Beam", (0, 0, 148), (5, 146, 6), grain="y")
        for i in range(n):
            y = (i - (n - 1) / 2) * 30
            pts = [(-5, y, 140), (-5, y + 9, 116), (-5, y + 12, 92), (-5, y + 9, 68), (-5, y, 44)]
            for a, b in zip(pts[:-1], pts[1:]):
                k.cyl("Bld_Beam", a, b, 2.2, sides=4, caps=False)
            k.rope(pts[0], pts[-1], 0.9)
            k.obox("Bld_Bronze", (-5, y + 12, 92), (4, 4, 12))


def quiver(k, pos, scale=0.7):
    """A jar of arrows."""
    k.pot(pos, scale)
    for i in range(4):
        a = i * 1.7 + k.U(0, 1)
        x, y = pos[0] + math.cos(a) * 5 * scale, pos[1] + math.sin(a) * 5 * scale
        top = (x + math.cos(a) * 9, y + math.sin(a) * 9, pos[2] + 66 * scale + 46)
        k.cyl("Bld_Thatch", (x, y, pos[2] + 50 * scale), top, 1.3, sides=4, caps=False)
        k.obox("Bld_Plaster", (top[0], top[1], top[2] - 6), (5, 5, 14), yaw=math.degrees(a))       # fletching


def lodge(k):
    u0 = 36.0
    r0 = rect(LX0, LY0, LX1, LY1)
    r1 = k.wall("Bld_Mudbrick", r0, 0, 30, inset=6, u0=u0, bleach=False)
    k.cap("Bld_Mudbrick", r0, 0.5, down=True)
    fx = LX0 + 6
    win = dict(z0=92, z1=146, depth=12, back="Bld_Shutter", reveal="Bld_Mudbrick", shade=0.7)
    ops = {2: [front(-222, -150, z0=30, z1=156, depth=18, back="Bld_Planks", reveal="Bld_Mudbrick", shade=0.7, back_shade=0.75, no_sill=True)]
           + ([front(-330, -282, **win)] if not k.damaged else []) + k.breach((LY1 - 6) + 244, (LY1 - 6) + 352, 44, 150, depth=20),
           3: [dict(a=110, b=158, **win)]}
    k.wall("Bld_Plaster", r1, 30, EAVE - 60, u0=u0, openings=ops)
    k.wall("Bld_Frieze", r1, EAVE - 60, EAVE, v0=0.0, bleach=False, u0=u0)
    k.steps("Bld_Trim", LX0 - 34, LX0 + 8, -226, -146, 0, 30, 2)
    k.obox("Bld_Beam", (fx - 3, -186, 164), (14, 100, 14), grain="y")
    for y, facing in ((LY0 + 6, -1), (LY1 - 6, 1)):
        k.gable_end("Bld_Plaster", fx, LX1 - 6, y, EAVE, RISE, facing=facing)
    k.gable_roof("Bld_Thatch", fx, LX1 - 6, LY0 + 6, LY1 - 6, EAVE, RISE, over=38, verge=24, holes=HOLES)
    # the fletching bench by the door: shafts, a basket of feathers, a glue pot, a stool
    with k.at((36, -300, 0), yaw=8):
        k.obox("Bld_Planks", (0, 0, 74), (64, 150, 6), grain="y")
        for sx in (-1, 1):
            for sy in (-1, 1):
                k.obox("Bld_Beam", (sx * 24, sy * 64, 36), (7, 7, 72), grain="z")
        for i in range(3):
            k.cyl("Bld_Thatch", (-16 + i * 9, -62, 81), (-12 + i * 9, 22, 81), 3.4, sides=5)
        k.basket((12, 48, 77), 15, 16, fill="Bld_Plaster")
        k.pot((-18, 50, 77), 0.42)
        k.cyl("Bld_Bark", (-60, 10, 0), (-60, 10, 40), 15.0, sides=7, grain="ring", cap_slot="Bld_Beam")
    k.pot((LX0 - 24, -116, 0), 0.95)
    k.pole_banner((LX0 - 30, -60, 0), height=400.0)


def shooting_line(k):
    zf, zb = 178.0, 226.0
    k.box("Bld_Dirt", (SX0 - 6, SY0 - 10, -2), (SX1 + 60, SY1 + 6, 3), u0=0.0)       # the ground worn bare at the line
    k.cloth("Bld_Awning", [(SX1, SY1, zb), (SX1, SY0, zb), (SX0, SY0, zf), (SX0, SY1, zf)],
            [(SY1 - SY0, 0), (0, 0), (0, 142), (SY1 - SY0, 142)], w=[0.0, 0.0, 0.3, 0.3])
    for i, y in enumerate((SY0 + 8, (SY0 + SY1) / 2, SY1 - 8)):
        k.cyl("Bld_Beam", (SX1 - 6, y, 0), (SX1 - 6, y, zb + 4), 5.0, 4.2, sides=5)
        if k.damaged and i == 1:                             # damaged: a front post is down
            k.charred((SX0 + 6, y, 4), (SX0 - 120, y + 70, 12), size=9)
        else:
            k.cyl("Bld_Beam", (SX0 + 6, y, 0), (SX0 + 6, y, zf + 4), 5.0, 4.2, sides=5)
    k.obox("Bld_Beam", (SX1 - 6, (SY0 + SY1) / 2, zb + 2), (6, SY1 - SY0 + 12, 6), grain="y")
    k.obox("Bld_Beam", (SX0 + 6, (SY0 + SY1) / 2, zf + 2), (6, SY1 - SY0 + 12, 6), grain="y")
    k.obox("Bld_Beam", (SX1 + 34, (SY0 + SY1) / 2, 5), (12, SY1 - SY0, 10), grain="y")       # the line itself: a toe board
    for y in (SY0 + 60, (SY0 + SY1) / 2, SY1 - 60):
        quiver(k, (SX1 - 30, y + 34, 0))
    bow_rack(k, (SX0 + 40, (SY0 + SY1) / 2 - 20, 0), n=5)
    k.obox("Bld_Planks", (SX0 + 60, SY1 - 60, 40), (34, 110, 6), grain="y")      # a bench
    for y in (SY1 - 104, SY1 - 16):
        k.obox("Bld_Beam", (SX0 + 60, y, 19), (26, 9, 38), grain="z")


def targets(k):
    for i, (x, y) in enumerate(BUTTS):
        butt(k, (x, y, 0), fallen=k.damaged and i == 1)
    for (x, y, yaw) in ((356, 40, 90), (358, 140, 88), (356, 240, 92), (358, 338, 90)):      # the backstop: a wall of bales
        bale(k, (x, y, 0), yaw)
        if not (k.damaged and y in (140, 240)):
            bale(k, (x + 2, y + 6, 46), yaw + k.U(-5, 5))
    bale(k, (140, 320, 0), 20)
    bale(k, (150, 330, 46), 38, size=(90, 50, 44))


def build(k, state="complete"):
    if state == "site":
        return site(k)
    if state == "ruin":
        return ruin(k)
    complete(k)
    if k.damaged:
        damage(k)


def complete(k):
    lodge(k)
    shooting_line(k)
    targets(k)
    gy = (GATE[0] + F, GATE[1] + F)                          # the gate, as distances along the front run
    fence(k, [(LX0 - 2, -F), (-F, -F), (-F, F), (F, F), (F, LY1 + 14)],
          gaps=((1, gy[0], gy[1]),) + (((0, 150, 330), (1, 420, 600), (2, 250, 420)) if k.damaged else ()))
    for y in GATE:                                           # gateposts under a lintel
        k.cyl("Bld_Beam", (-F, y, -4), (-F, y, 214), 7.0, 6.0, sides=6)
    k.obox("Bld_Beam", (-F, (GATE[0] + GATE[1]) / 2, 204), (10, GATE[1] - GATE[0] + 40, 10), grain="y")
    k.cyl("Bld_Bronze", (-F - 6, (GATE[0] + GATE[1]) / 2, 204), (-F - 12, (GATE[0] + GATE[1]) / 2, 204), 13.0, sides=8, grain="ring")
    if not k.damaged:
        k.pole_banner((-F + 26, GATE[1] + 60, 0), height=300.0)
    k.tree((-316, -326, 0), height=290, spread=140, lean=(-8, 10), blobs=5)
    k.collider((FOOTPRINT[0], FOOTPRINT[1], 0), (FOOTPRINT[2], FOOTPRINT[3], 280))
    gate_y = (GATE[0] + GATE[1]) / 2
    k.sockets["gate"] = (-460.0, gate_y, 0.0)        # where a recruit appears: just outside the gate
    k.sockets["rally"] = (-760.0, gate_y, 0.0)       # default rally point, straight out from it
    k.sockets["label"] = (120.0, 0.0, 520.0)
    k.sockets["popup"] = (0.0, 0.0, 320.0)


def damage(k):
    """Added to the finished build on the damaged mesh: soot, what fell, what burnt."""
    fx = LX0 + 6
    k.scorch("plume_s", (fx, -124, 32), flip=True)
    k.scorch("blot_s", (fx, -306, 190))                      # over the breach, up onto the frieze
    k.rubble((fx - 50, -300, 0), (110, 130), 24, slot="Bld_Mudbrick", blocks=7, beams=1, block=(30, 18, 12))
    k.scorch("blot_l", ((SX0 + SX1) / 2 - 20, (SY0 + SY1) / 2 + 40, 3), "up", out=1.5)      # under the burnt awning
    k.scorch("blot_m", (BUTTS[1][0] - 20, BUTTS[1][1], 0), "up", out=2.0)
    k.blob("Bld_Char", (352, 190, 46), (60, 130, 50), points=10, squash=0.3)                # the bales that burnt
    k.charred((SX0 + 30, SY0 + 20, 6), (SX0 + 150, SY0 + 90, 10), size=7)
    k.charred((-F + 26, GATE[1] + 60, 0), (-F + 150, GATE[1] + 150, 12), size=9)             # the standard's pole
    k.scorch("blot_w", (-262, -290, 0), "up", out=2.0)
    k.charred((-386, -210, 6), (-330, -60, 12), size=7)


def site(k):
    fp = FOOTPRINT
    k.footings(fp[0], fp[1], fp[2], fp[3], width=20, height=9, slot="Bld_Mudbrick", top="Bld_Mudbrick")
    k.scaffold(LX0 - 6, LY0 - 6, LX1 + 6, LY1 + 6, height=236, lift=118, bay=150, depth=40, ladder=(2, 0))
    k.stone_stack((-120, -270, 0), yaw=16, slot="Bld_Mudbrick", block=(40, 22, 14), courses=(4, 4, 3, 3), rows=3)
    k.timber_pile((-200, 190, 0), yaw=84, length=210, base=3)
    for (x, y) in ((SX0, SY0), (SX1, SY0), (SX1, SY1), (SX0, SY1)):       # the shooting line pegged out
        k.cyl("Bld_Beam", (x, y, -4), (x, y, 56), 4.0, 3.0, sides=5)
    c = [(SX0, SY0), (SX1, SY0), (SX1, SY1), (SX0, SY1)]
    for i in range(4):
        k.rope(c[i] + (44,), c[(i + 1) % 4] + (44,), 1.4)
    for (x, y, yaw) in ((250, 150, 10), (262, 210, -6), (254, 180, 80)):  # bales for the butts, reeds for the thatch
        bale(k, (x, y, 0 if yaw < 50 else 46), yaw)
    for i in range(3):
        k.cyl("Bld_Thatch", (20 + i * 16, -30, 12), (30 + i * 16, 150, 12), 11.0, sides=6)


def ruin(k):
    k.ruin_rect("Bld_Mudbrick", LX0 + 16, LY0 + 16, LX1 - 16, LY1 - 16, hmax=96, hmin=16, thick=24, seg=46, gaps=0.22, corners=(1, 0.4, 0.7, 0.5),
                step=12)
    k.rubble(((LX0 + LX1) / 2, (LY0 + LY1) / 2, 0), (220, 240), 44, slot="Bld_Char", blocks=4, beams=4, block=(60, 12, 8))     # the burnt thatch
    k.rubble((LX0 - 20, -300, 0), (100, 150), 0, slot="Bld_Mudbrick", blocks=7, beams=0, mound=False, block=(30, 18, 12))
    for i, y in enumerate((SY0 + 8, (SY0 + SY1) / 2, SY1 - 8)):          # the shooting line: burnt stumps, a fallen plate
        k.cyl("Bld_Char", (SX1 - 6, y, -4), (SX1 - 4, y + 3, 40 + i * 22), 5.5, 4.5, sides=5)
    k.cyl("Bld_Char", (SX0 + 6, SY0 + 8, -4), (SX0 + 4, SY0 + 8, 58), 5.5, 4.5, sides=5)
    k.charred((SX1 - 10, SY0 + 30, 8), (SX0 + 30, SY1 - 80, 14), size=8)
    k.charred((SX0 + 10, SY1 - 30, 8), (SX1 + 20, SY1 - 120, 12), size=7)
    k.rubble((SX0 + 70, SY0 + 120, 3), (110, 160), 0, slot="Bld_Char", blocks=5, beams=1, mound=False, block=(54, 12, 6))
    k.box("Bld_Dirt", (SX0 - 6, SY0 - 10, -2), (SX1 + 60, SY1 + 6, 3), u0=0.0)
    k.scorch("blot_l", ((SX0 + SX1) / 2, (SY0 + SY1) / 2, 3), "up", out=1.5)
    k.cyl("Bld_Char", (-316, -326, -4), (-310, -330, 50), 15.0, 11.0, sides=6, grain="ring")      # the olive's stump
    butt(k, (BUTTS[0][0], BUTTS[0][1], 0), fallen=True)                   # one butt lies where it fell; the rest are ash
    for (x, y) in BUTTS[1:]:
        k.blob("Bld_Char", (x, y, 0), (130, 120, 56), points=11, squash=0.3)
        k.scorch("blot_m", (x - 30, y, 0), "up", out=2.0)
    k.blob("Bld_Char", (350, 200, 0), (70, 280, 50), points=14, squash=0.3)
    bale(k, (356, 40, 0), 90)
    gy = (GATE[0] + F, GATE[1] + F)
    fence(k, [(LX0 - 2, -F), (-F, -F), (-F, F), (F, F), (F, LY1 + 14)],
          gaps=((1, gy[0], gy[1]), (0, 160, 380), (1, 420, 620), (2, 220, 480), (3, 150, 330)), post_h=64)
    k.cyl("Bld_Char", (-F, GATE[0], -4), (-F + 3, GATE[0], 96), 7.0, 6.0, sides=6)
    k.cyl("Bld_Char", (-F, GATE[1], -4), (-F, GATE[1] + 2, 50), 7.0, 6.0, sides=6)
    k.scorch("blot_w", (-262, -270, 0), "up", out=2.0)
    k.charred((-340, -300, 6), (-220, -180, 10), size=9)
