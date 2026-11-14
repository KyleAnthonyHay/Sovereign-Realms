"""Shieldbearer: bronze-age line infantryman.

Bronze conical helmet with a team-coloured crest, team shoulder mantle (a full
short cloak from behind), leather cuirass with a bronze pectoral, linen kilt
with a team hem, bronze greaves, a big round team-coloured shield with a bronze
boss on the left arm and a straight bronze leaf-blade sword in the right hand.

Design grid: 24 x 36, column 12 is the pivot, row 36 is the ground line.
Positions in this file are (column, row) in that grid.
"""

from pixelkit import P, Canvas, Held

CELL = 64
PIVOT = (32, 60)
OX, OY = PIVOT[0] - 12, PIVOT[1] - 36


def cv():
    return Canvas(CELL, CELL, OX, OY)


# ==========================================================================
# The sword, drawn once per angle. Anchor = middle of the grip (where the fist closes).
# Other angles are exact mirrors of these (no resampling).
# ==========================================================================

SW_UP = P("""
..A..
.ABD.
.ABD.
.ABD.
.ABD.
.ABD.
.ABD.
.ABD.
.ABD.
.ABD.
.ABD.
CBBCD
..q..
..q..
..s..
..E..
""", ax=2, ay=13)

# Leaning back, two rows per column.
SW_STEEP = P("""
A.......
AB......
ABD.....
.ABD....
.ABD....
..ABD...
..ABD...
...ABD..
...ABD..
....ABD.
....ABD.
...CBBCD
.....q..
......q.
......sE
""", ax=6, ay=13)

# 45 degrees, tip up-left.
SW_DIAG = P("""
AA.............
ABB............
.ABBD..........
..ABBD.........
...ABBD........
....ABBD.......
.....ABBD......
......ABBD.....
.......ABBD.C..
........ABBDC..
.........ABCD..
.........CC.q..
........C...q..
.............s.
..............E
""", ax=12, ay=12)

# Level, tip to the right.
SW_FWD = P("""
...C............
...CAAAAAAAAAAA.
EsqCBBBBBBBBBBBA
...CDDDDDDDDDDD.
...C............
""", ax=1, ay=2)

_RELIGHT = {"A": "D", "D": "A"}            # keep the bright edge on the left after a mirror
SW_DOWN = SW_UP.vflip()
SW_DOWN_OUT = SW_DIAG.vflip()              # tip down-left, 45 degrees
SW_DOWN_STEEP = SW_STEEP.vflip()           # tip down-left, steep
SW_DOWN_FWD = SW_DIAG.flip().vflip()       # tip down-right
SW_UP_FWD = SW_DIAG.flip()                 # tip up-right


# ==========================================================================
# FRONT (facing the camera)
# ==========================================================================

F_HEAD = P("""
.....WX.....
....WXXY....
....XXYZ....
....BBCD....
...BABCCD...
..BABBCCDD..
.BABBCCCCDD.
.BBBCCCCCDE.
BBBCCCCCDDEE
.DcccbbccdD.
.CbbkaakbcD.
.CabkaakbcD.
.DbbbbcbccE.
..iihiihij..
...ihhiij...
""")

# Eyes screwed shut, mouth open.
F_HEAD_HIT = P("""
.....WX.....
....WXXY....
....XXYZ....
....BBCD....
...BABCCD...
..BABBCCDD..
.BABBCCCCDD.
.BBBCCCCCDE.
BBBCCCCCDDEE
.DcccbbccdD.
.CbbbaabbcD.
.CakkaakkcD.
.DbbbbcbccE.
..iihiihij..
...ihjjij...
""")

F_TORSO = P("""
.WWXXXXXXXXYZ.
WWXXXXBCXXXYYZ
XXYqpppqqqrYYZ
.qpppBCqqqrrs.
.qppqCDqqqrrs.
.rqqqqqqqrrss.
.ssrrsBCsrrss.
""")

F_KILT = P("""
.112212212334.
.112312312334.
11223123123344
11223123123344
XXXXYXXYXXYYZZ
""")

# Legs are drawn knee-to-ankle plus a separate foot, so walk poses can shorten
# the leg and move the foot without redrawing either.
F_LEG = P("""
bccd
abbc
abbc
ABCD
BBCD
BCDE
qqrs
""")

F_LEG_FWD = P("""
bccd
abbc
ABCD
ABCD
BBCD
BCDE
qqrs
""")

F_LEG_BACK = P("""
cccd
bbcd
BCCD
BCDE
CDDE
qrrs
""")

F_LEG_LIFT = P("""
abbc
aabc
ABCD
BBCD
qqrs
""")

F_FOOT_L = P("""
abbbc
rrrrs
""", ax=1)
F_FOOT_R = P("""
abbbc
rrrrs
""")
F_FOOT_L_BIG = P("""
abbbc
abbbc
rrrrs
""", ax=1)
F_FOOT_R_BIG = P("""
abbbc
abbbc
rrrrs
""")
F_FOOT_TOE = P("""
bccd
rrss
""")

# ---- sword arm (viewer's left). Arm anchor = shoulder, which sits at (2, 16). ----

F_ARM_IDLE = Held(P("""
....abb.
....abbc
....abbc
aabbbbc.
abbbccd.
abccd...
""", ax=4), (-3, 4), SW_UP)

# Wind-up 1: elbow out, fist at head height.
F_ARM_HALF = Held(P("""
aabc....
abbc....
abbc....
.abc....
.abbc...
.abbbbb.
..bbccc.
...cc...
""", ax=4, ay=5), (-3, -4), SW_UP)

# Wind-up 2 (peak): arm straight up, blade at its tallest.
F_ARM_UP = Held(P("""
aabc.
abbc.
abbc.
.abc.
.abbc
.abbc
.abbc
.abbc
.bbcc
..cc.
""", ax=1, ay=8), (0, -7), SW_UP)

# Strike: arm thrown down and forward, blade cutting out to the side.
F_ARM_STRIKE = Held(P("""
abb...
abbc..
abbc..
abbc..
.abc..
.abbc.
.aabc.
.abbc.
.abcc.
"""), (2, 7), SW_DOWN_OUT)

# Recovery: blade carried through, hanging low.
F_ARM_LOW = Held(P("""
....abb.
....abbc
...abbc.
..abbc..
.abbc...
aabc....
abbc....
abcc....
""", ax=4), (-3, 6), SW_DOWN_STEEP)

F_SMEAR = P("""
.......n
......n.
.....n..
....nn..
....n...
...nn...
...n....
..nn....
..nm....
..nm....
.nmm....
.nmm....
.nmm....
.mmm....
nmm.....
nmm.....
nmm.....
nmm.....
nmm.....
nmm.....
.mm.....
.mm.....
.mmm....
..mm....
..mmm...
""")

F_SHIELD = P("""
....BBBBC....
..BBWWWXXCC..
.BWWWWXXXXXC.
.BWWXXXXXXXD.
BWWXXXXXXXXYD
BWXXXABCXXXYD
BWXXABBCDXYYD
BXXXBBCDDYYYD
CXXXXCDDYYYZD
.CXXXXYYYYZD.
.DXXXXYYYZZD.
..DDYYYZZDE..
....DDDEE....
""")


def _front_legs(c, legL, legR):
    for side_, pose in (("L", legL), ("R", legR)):
        x = 7 if side_ == "L" else 13
        foot = F_FOOT_L if side_ == "L" else F_FOOT_R
        big = F_FOOT_L_BIG if side_ == "L" else F_FOOT_R_BIG
        if pose == "stand":
            c.put(F_LEG.tall(2), x, 27).put(foot, x, 34)
        elif pose == "fwd":       # planted toward the camera: longer shin, bigger foot
            c.put(F_LEG_FWD.tall(2), x, 26).put(big, x, 33)
        elif pose == "back":      # trailing: shorter, in shadow, toe down
            c.put(F_LEG_BACK.tall(2), x, 27).put(F_FOOT_TOE, x, 33)
        elif pose == "lift":      # passing: knee up, foot off the ground
            c.put(F_LEG_LIFT.tall(2), x, 27).put(F_FOOT_TOE, x, 32)
        elif pose == "kneel":     # buckling
            c.put(F_LEG.rows(3, 7), x, 30).put(foot, x, 34)


def front(legL="stand", legR="stand", body=0, bx=0, head=(0, 0), head_part=F_HEAD, arm=F_ARM_IDLE, arm_d=(0, 0),
          shield_d=(0, 0), lean=(0, 0, 0)):
    c = cv()
    _front_legs(c, legL, legR)
    kx, tx, hx = bx + lean[0], bx + lean[1], bx + lean[2]
    c.put(F_KILT, 5 + kx, 22 + body, sep="b")
    c.put(F_TORSO, 5 + tx, 15 + body)
    if arm is not None:
        arm.draw(c, 2 + tx + arm_d[0], 16 + body + arm_d[1], sep="r")
    c.put(head_part, 6 + hx + head[0], 0 + body + head[1], sep="b")
    if shield_d is not None:
        c.put(F_SHIELD, 12 + tx + shield_d[0], 15 + body + shield_d[1], sep="all")
    return c


# ==========================================================================
# SIDE (facing east; the game mirrors it for west)
# ==========================================================================

S_HEAD = P("""
...WWXXY....
..WXXXXXYZ..
.WXXXXXXXYZ.
.XYBBBCCDYZ.
..BABBCCCD..
.BABBCCCCCD.
.BBBCCCCCCD.
.BBCCCCCDDDE
.CCDDccbbb..
.CDDbbbbkab.
.DDDabbbkaa.
..DDibbbbbc.
...iihhhhi..
....iihhi...
""")

S_HEAD_HIT = P("""
...WWXXY....
..WXXXXXYZ..
.WXXXXXXXYZ.
.XYBBBCCDYZ.
..BABBCCCD..
.BABBCCCCCD.
.BBBCCCCCCD.
.BBCCCCCDDDE
.CCDDccbbb..
.CDDbbbbbab.
.DDDabbkkaa.
..DDibbbbbc.
...iihhjhi..
....iihhi...
""")

S_TORSO = P("""
.WWXXXXXY.
WWXXXXXXYY
XXXYqpppqr
XXYYqppqqr
XYYZqqqqrr
YYZ.rqqrrs
.Z..ssBCss
""")

S_KILT = P("""
.1122233.
112123344
112123344
112123344
XXXYXXYYZ
""")

# Single-leg poses for the side view, knee to sole. ax = hip column.
S_LEG_STAND = P("""
bbcd..
abbc..
abbc..
ABCD..
BBCD..
BCDE..
qqrs..
abbbc.
rrrrrs
""")

# Contact, leading leg: reaching forward, heel down, toe still up.
S_LEG_CONTACT_F = P("""
bbcd......
abbc......
.abbc.....
.ABCD.....
..ABCD....
..BBCD....
...qqrsbc.
....abbbbc
....rrrrs.
""")

# Contact, trailing leg: pushed back, heel lifting.
S_LEG_CONTACT_B = P("""
...bbcd
...abbc
..abbc.
..ABCD.
.ABCD..
.BBCD..
qqrs...
abbbc..
.rrrs..
""", ax=3)

# Just after toe-off: shin kicked up behind.
S_LEG_LIFT_B = P("""
....bbcd
....abbc
...aabbc
.BBCCDc.
qABCD...
abqr....
rrs.....
""", ax=4)

# Passing: knee driving forward, foot clear of the ground.
S_LEG_PASS = P("""
bbcd....
abbbc...
.aabbc..
..ABCD..
..BBCD..
.qqrs...
.abbbc..
..rrrs..
""")

S_LEG_KNEEL = P("""
BBCD..
BCDE..
qqrs..
abbbc.
rrrrrs
""")

S_LEGS = {"stand": S_LEG_STAND, "cf": S_LEG_CONTACT_F, "cb": S_LEG_CONTACT_B, "lift": S_LEG_LIFT_B, "pass": S_LEG_PASS}

S_SHIELD = P("""
..BBC..
.BWWXC.
BWWXXYC
BWXXXYD
BWXXXYD
BWXABYD
BXXBCYD
BXXCDYD
BXXXYYD
CXXXYZD
CXXYYZD
.CYYZD.
..DDE..
""")

# ---- sword arm (near side). Arm anchor = shoulder, which sits at (9, 16). ----

# Idle: hand at the hip, blade leaning back over the shoulder line, clear of the head.
S_ARM_IDLE = Held(P("""
.....abb
....abbc
....abbc
....abc.
...abbc.
aabbbc..
abbcc...
.bcd....
""", ax=5), (-4, 6), SW_STEEP)

# Wind-up 1: arm drawn straight back, blade tilted back.
S_ARM_RAISE1 = Held(P("""
aabc.......
abbc.......
abbccbbabb.
.bbbbbbbbbc
..ccccccbbc
.......bcc.
""", ax=7, ay=2), (-6, -1), SW_DIAG)

# Wind-up 2 (peak): fist behind the helmet, blade vertical and tall.
S_ARM_RAISE2 = Held(P("""
aabc....
abbc....
abbcc...
.abbbc..
..abbbc.
...abbbc
....abbc
.....bbc
......c.
""", ax=5, ay=7), (-4, -6), SW_UP)

# Strike: arm thrown forward, blade level.
S_ARM_STRIKE = Held(P("""
abbbbbbbaab
.bbbbbbbabb
..cccccccbc
"""), (9, 1), SW_FWD)

# Recovery: blade carried through, low and forward.
S_ARM_LOW = Held(P("""
abb........
abbbc......
.abbbc.....
..abbbc....
...abbbc...
....abbbab.
.....bbabbc
......cbbcc
"""), (8, 6), SW_DOWN_FWD)

S_SMEAR = P("""
nn..................
..nnn...............
.....nnn............
........nn..........
..........nn........
...........nmn......
.............mn.....
.............mmn....
..............mm....
...............mm...
...............mmn..
................mm..
................mm..
.................mm.
.................mm.
.................mm.
.................mmn
.................mm.
.................mm.
""")


def side(near="stand", far="stand", near_x=9, far_x=12, body=0, bx=0, head=(0, 0), head_part=S_HEAD,
         arm=S_ARM_IDLE, arm_d=(0, 0), shield_d=(0, 0), lean=(0, 0, 0)):
    c = cv()
    if far == "kneel":
        c.put(S_LEG_KNEEL.darker(), far_x, 31)
    else:
        c.put(S_LEGS[far].tall(2).darker(), far_x, 27)
    if near == "kneel":
        c.put(S_LEG_KNEEL, near_x, 31, sep="lr")
    else:
        c.put(S_LEGS[near].tall(2), near_x, 27, sep="lr")
    kx, tx, hx = bx + lean[0], bx + lean[1], bx + lean[2]
    c.put(S_KILT, 8 + kx, 22 + body, sep="b")
    c.put(S_TORSO, 7 + tx, 15 + body)
    c.put(head_part, 6 + hx + head[0], 1 + body + head[1], sep="b")
    if shield_d is not None:
        c.put(S_SHIELD, 15 + tx + shield_d[0], 15 + body + shield_d[1], sep="all")
    if arm is not None:
        arm.draw(c, 9 + tx + arm_d[0], 16 + body + arm_d[1], sep="all")
    return c


# ==========================================================================
# BACK (facing away from the camera)
# ==========================================================================

B_HEAD = P("""
.....XY.....
....WXXY....
....XXYZ....
....BBCD....
...BABCCD...
..BABBCCDD..
.BABBCCCCDD.
.BBBCCCCCDE.
.BBCCCCCCDE.
.BCCCCCCDDE.
.CCCCCCDDDE.
..DDDDDDEE..
...iiiijj...
""")

B_CLOAK = P("""
.WWXXXXXXXXYZ.
WWXXXXXXXXXYYZ
WXXXYXXXXYXYYZ
WXXXYXXXXYXYYZ
XXXYYXXXYYXYZZ
XXXYXXXXYXXYZZ
.XYYXXXYYXYYZ.
""")

B_KILT = P("""
.112212212334.
.112312312334.
11223123123344
11223123123344
XXXXYXXYXXYYZZ
""")

# Legs from behind: bare calves, greave straps.
B_LEG = P("""
bccd
abbc
abbc
qbbr
abbc
qbcr
qqrs
""")
B_LEG_FWD = P("""
cccd
bbcd
qbcr
bbcd
qccr
qrrs
""")
B_LEG_BACK = P("""
bccd
abbc
abbc
qbbr
abbc
abbc
qbcr
qqrs
""")
B_LEG_LIFT = P("""
abbc
abbc
qbbr
abbc
qqrs
""")
B_FOOT = P("""
bbcc
rrrs
""")
B_FOOT_SOLE = P("""
qrrs
rrss
rsss
""")

# Inside face of the shield, seen from behind (wood, bronze rim, arm strap).
B_SHIELD = P("""
....BBBBC....
..BBqqqqqCC..
.Bpqqqrqqqqr.
.Bpqqqrqqqqr.
Bpqqqqrqqqqqr
Bpqqqqrqqqqrr
Bqqsssssqqqrr
Bqqqqqrqqqqrr
Cqqqqqrqqqrrr
.Cqqqqrqqqrr.
.Dqqqqrqqrrs.
..DDqqrrrss..
....DDDEE....
""")

# ---- sword arm from behind (viewer's right). Shoulder sits at (21, 16). ----
B_ARM_IDLE = F_ARM_IDLE.flip(_RELIGHT)
B_ARM_HALF = F_ARM_HALF.flip(_RELIGHT)
B_ARM_UP = F_ARM_UP.flip(_RELIGHT)
B_ARM_LOW = F_ARM_LOW.flip(_RELIGHT)

# Strike seen from behind: arm thrown out and away, blade sweeping up-screen.
B_ARM_STRIKE = Held(P("""
.aabc
abbbc
bbbcc
.cc..
""", ax=1, ay=2), (1, -1), SW_UP_FWD)

B_SMEAR = P("""
nnnn..........
....nnmm......
........mmm...
..........mmm.
............mm
.............m
""")


def _back_legs(c, legL, legR):
    for side_, pose in (("L", legL), ("R", legR)):
        x = 7 if side_ == "L" else 13
        if pose == "stand":
            c.put(B_LEG.tall(2), x, 27).put(B_FOOT, x, 34)
        elif pose == "fwd":       # stepping away from the camera: shorter, higher, in shadow
            c.put(B_LEG_FWD.tall(2), x, 27).put(B_FOOT.darker(), x, 33)
        elif pose == "back":      # trailing toward the camera: longer, sole showing
            c.put(B_LEG_BACK.tall(2), x, 26).put(B_FOOT_SOLE, x, 33)
        elif pose == "lift":
            c.put(B_LEG_LIFT.tall(2), x, 27).put(B_FOOT_SOLE.rows(0, 2), x, 32)
        elif pose == "kneel":
            c.put(B_LEG.rows(3, 7), x, 30).put(B_FOOT, x, 34)


def back(legL="stand", legR="stand", body=0, bx=0, head=(0, 0), arm=B_ARM_IDLE, arm_d=(0, 0), shield_d=(0, 0),
         lean=(0, 0, 0)):
    c = cv()
    kx, tx, hx = bx + lean[0], bx + lean[1], bx + lean[2]
    if shield_d is not None:
        c.put(B_SHIELD, -2 + tx + shield_d[0], 15 + body + shield_d[1])
    _back_legs(c, legL, legR)
    c.put(B_KILT, 5 + kx, 22 + body, sep="b")
    if arm is not None:
        arm.draw(c, 21 + tx + arm_d[0], 16 + body + arm_d[1])
    c.put(B_CLOAK, 5 + tx, 14 + body, sep="lrb")
    c.put(B_HEAD, 6 + hx + head[0], 0 + body + head[1], sep="b")
    return c


# ==========================================================================
# DEATH: corpse and its loose gear
# ==========================================================================

def _seg(rows):
    return "\n".join(r.replace(" ", "") for r in rows)


# Lying on his back, head to the left.
# Segments: crest, helmet, face, beard, mantle, cuirass, belt, kilt, hem, legs, feet.
CORPSE_UP = P(_seg([
    "... ..BBC. ... .. .WX ..... . .... . ..... ...",
    "... .BABCC Dcb .. WXX Yqppq r 1122 X bBBCq ab.",
    ".WX BABCCC Dbk bi WXX qppqq r 1212 X aABCq bbc",
    "WXX BBCCCC Dba hi XXX qpBCq r 1213 X cCDEr rs.",
    "XXY BBCCCD Dba hi XXB qqCDq s 2123 Y ..... ...",
    "XYZ BCCCCD Dbk ii XXC qqqqr s 2123 Y bBBCq ab.",
    ".YZ CCCCDD Ecb ij XXY rqqrr s 2233 Y aABCq bbc",
    "... .CDDDE Ecc .. XYY rrrrs s 3334 Z cCDEr rs.",
    "... ..DEE. ... .. YYZ ..... . .... . ..... ...",
]))

# Face down (the unit was facing away): helmet back, cloak, calves.
CORPSE_DOWN = P(_seg([
    "... ..BBC. ... .. .WX ..... . .... . ..... ...",
    "... .BABCC CD. .. WWX XXXXY Y 1122 X babqb bc.",
    ".WX BABCCC CDi .. WXX XXYXX Y 1212 X abbqb bbc",
    "WXX BBCCCC CDi i. XXX XYXXX Y 1213 X cccrc rs.",
    "XXY BBCCCD DDi i. XXX XXXYX Z 2123 Y ..... ...",
    "XYZ BCCCCD DEi i. XXX XYXXY Z 2123 Y babqb bc.",
    ".YZ CCCCDD DEj .. XXY YXXYY Z 2233 Y abbqb bbc",
    "... .CDDDE EE. .. XYY YYYYZ Z 3334 Z cccrc rs.",
    "... ..DEE. ... .. YYZ ..... . .... . ..... ...",
]))

SHIELD_FLAT = P("""
....BBBBBC...
.BBWWXXXXXCC.
BWXXXABCXXYYD
CXXXXBCDYYYZD
.DDYYYYYZZDE.
...DDDDEE....
""")

DUST = P("""
..u....
.uuv.u.
uuvvuuv
""")

# One limp arm for the corpse (lies along the ground beside the body).
CORPSE_ARM = P("""
abbbbbab
.cccccbc
""")


def corpse(kind, dy=0, shield=(3, -6), sword=(0, 0), dust=False, falling=False):
    c = cv()
    body = CORPSE_UP if kind == "up" else CORPSE_DOWN
    if falling:                      # feet still near the ground, head and shoulders on the way down
        c.put(SW_DIAG, 28 + sword[0], 10 + sword[1])
        c.put(body.stair(2), -3, 26 + dy)
        c.put(SHIELD_FLAT, 8 + shield[0], 26 + shield[1], sep="all")
        return c
    c.put(SHIELD_FLAT, 8 + shield[0], 26 + shield[1])
    c.put(body, -6, 26 + dy, sep="t")
    c.put(CORPSE_ARM, 8, 34 + dy, sep="t")
    c.put(SW_FWD, 17 + sword[0], 35 + sword[1], sep="t")
    if dust:
        c.put(DUST, -11, 33, fx=True)
        c.put(DUST.flip(), 28, 33, fx=True)
    return c


# ==========================================================================
# Animation tables
# ==========================================================================

def build():
    fr = {}

    # ---- idle: 4 frames. The breath lifts arm and shield first, then the head, and settles in the same order. ----
    fr[("idle", "front")] = [front(), front(arm_d=(0, -1)), front(head=(0, -1), arm_d=(0, -1), shield_d=(0, -1)), front(head=(0, -1))]
    fr[("idle", "side")] = [side(), side(arm_d=(0, -1)), side(head=(0, -1), arm_d=(0, -1), shield_d=(0, -1)), side(head=(0, -1))]
    fr[("idle", "back")] = [back(), back(arm_d=(0, -1)), back(head=(0, -1), arm_d=(0, -1), shield_d=(0, -1)), back(head=(0, -1))]

    # ---- walk: contact, down, passing, then the same on the other foot ----
    fr[("walk", "front")] = [
        front("fwd", "back", body=0, arm_d=(0, 0), shield_d=(0, 0)),
        front("stand", "lift", body=1, arm_d=(0, 1), shield_d=(1, 0)),
        front("stand", "lift", body=-1, arm_d=(0, -1), shield_d=(1, -1)),
        front("back", "fwd", body=0, arm_d=(0, 0), shield_d=(0, 0)),
        front("lift", "stand", body=1, arm_d=(0, 1), shield_d=(-1, 0)),
        front("lift", "stand", body=-1, arm_d=(0, -1), shield_d=(-1, -1)),
    ]
    fr[("walk", "back")] = [
        back("fwd", "back", body=0),
        back("stand", "lift", body=1, arm_d=(0, 1), shield_d=(-1, 0)),
        back("stand", "lift", body=-1, arm_d=(0, -1), shield_d=(-1, -1)),
        back("back", "fwd", body=0),
        back("lift", "stand", body=1, arm_d=(0, 1), shield_d=(1, 0)),
        back("lift", "stand", body=-1, arm_d=(0, -1), shield_d=(1, -1)),
    ]
    W = dict(near_x=10, far_x=11)
    fr[("walk", "side")] = [
        side("cf", "cb", body=0, arm_d=(-1, 0), shield_d=(1, 0), **W),
        side("stand", "lift", body=1, arm_d=(0, 1), shield_d=(0, 1), **W),
        side("stand", "pass", body=-1, arm_d=(0, -1), shield_d=(0, -1), **W),
        side("cb", "cf", body=0, arm_d=(1, 0), shield_d=(-1, 0), **W),
        side("lift", "stand", body=1, arm_d=(0, 1), shield_d=(0, 1), **W),
        side("pass", "stand", body=-1, arm_d=(0, -1), shield_d=(0, -1), **W),
    ]

    # ---- attack: 0-2 wind-up, 3 strike, 4-5 recovery ----
    a = [
        front(body=1, shield_d=(-1, 0)),
        front(body=0, arm=F_ARM_HALF, shield_d=(-1, 0)),
        front(body=-1, arm=F_ARM_UP, shield_d=(0, -1)),
        front("fwd", "back", body=2, arm=F_ARM_STRIKE, shield_d=(2, 1)),
        front("fwd", "back", body=1, arm=F_ARM_LOW, shield_d=(1, 0)),
        front(body=0, arm_d=(-1, 1)),
    ]
    a[3].put(F_SMEAR, -11, 6, fx=True)
    fr[("attack", "front")] = a

    a = [
        side(body=1, bx=-1, shield_d=(1, 0)),
        side(body=0, bx=-1, arm=S_ARM_RAISE1, shield_d=(1, -1)),
        side(body=-1, bx=0, arm=S_ARM_RAISE2, shield_d=(1, -1)),
        side("cf", "cb", near_x=11, far_x=10, body=1, bx=2, arm=S_ARM_STRIKE, shield_d=(-2, 3)),
        side("cf", "cb", near_x=11, far_x=10, body=1, bx=1, arm=S_ARM_LOW, shield_d=(-1, 2)),
        side(body=0, bx=0, arm_d=(1, 1), shield_d=(0, 1)),
    ]
    a[3].put(S_SMEAR, 15, -4, fx=True)
    fr[("attack", "side")] = a

    a = [
        back(body=1, shield_d=(1, 0)),
        back(body=0, arm=B_ARM_HALF, shield_d=(1, 0)),
        back(body=-1, arm=B_ARM_UP, shield_d=(0, -1)),
        back("back", "fwd", body=-1, arm=B_ARM_STRIKE, shield_d=(-1, -1)),
        back("back", "fwd", body=0, arm=B_ARM_LOW, shield_d=(-1, 0)),
        back(body=0, arm_d=(1, 1)),
    ]
    a[3].put(B_SMEAR, 21, -6, fx=True)
    fr[("attack", "back")] = a

    # ---- hit: flinch, half recovered ----
    fr[("hit", "front")] = [
        front(body=1, head=(0, 1), head_part=F_HEAD_HIT, arm_d=(1, 1), shield_d=(-2, -1)),
        front(body=0, head=(0, 1), head_part=F_HEAD_HIT, arm_d=(0, 1), shield_d=(-1, 0)),
    ]
    fr[("hit", "side")] = [
        side(body=1, bx=-2, head=(-1, 1), head_part=S_HEAD_HIT, arm_d=(-1, 1), shield_d=(-1, -1)),
        side(body=0, bx=-1, head=(0, 1), head_part=S_HEAD_HIT, arm_d=(0, 1), shield_d=(0, 0)),
    ]
    fr[("hit", "back")] = [
        back(body=1, head=(0, 1), arm_d=(-1, 1), shield_d=(2, -1)),
        back(body=0, head=(0, 1), arm_d=(0, 1), shield_d=(1, 0)),
    ]

    # ---- death: stagger, buckle and topple, airborne, impact, rest (last frame holds) ----
    fall = dict(dy=-1, shield=(-9, -24), falling=True)
    land = dict(dy=1, shield=(3, -7), dust=True)
    fr[("death", "side")] = [
        side(body=0, bx=-1, head=(-1, 0), head_part=S_HEAD_HIT, arm=S_ARM_LOW, lean=(0, -1, -2), shield_d=(1, -2)),
        side("kneel", "kneel", body=4, bx=-2, head_part=S_HEAD_HIT, arm=None, lean=(-1, -3, -6), shield_d=(3, -4)),
        corpse("up", **fall),
        corpse("up", **land),
        corpse("up"),
    ]
    fr[("death", "front")] = [
        front(body=0, head=(0, 1), head_part=F_HEAD_HIT, arm=F_ARM_LOW, lean=(0, -1, -2), shield_d=(2, -2)),
        front("kneel", "kneel", body=4, bx=-2, head_part=F_HEAD_HIT, arm=None, lean=(-1, -3, -6), shield_d=(4, -4)),
        corpse("up", **fall),
        corpse("up", **land),
        corpse("up"),
    ]
    fr[("death", "back")] = [
        back(body=0, head=(0, 1), arm=B_ARM_LOW, lean=(0, -1, -2), shield_d=(-2, -2)),
        back("kneel", "kneel", body=4, bx=-2, arm=None, lean=(-1, -3, -6), shield_d=(-3, -4)),
        corpse("down", **fall),
        corpse("down", **land),
        corpse("down"),
    ]
    return fr


META = {
    "name": "shieldbearer",
    "display_name": "Shieldbearer",
    "figure_height_px": 36,
    "attack": {"windup_frames": [0, 1, 2], "strike_frame": 3, "recovery_frames": [3, 4, 5]},
}
