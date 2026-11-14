"""Archer: light bronze-age skirmisher.

Team-coloured headcloth held by a cord, with a drape over the neck and
shoulders; sleeveless linen tunic; leather quiver strap across the chest;
team sash with a hanging tail; leather bracer; bare legs and sandals; a tall
recurve bow in the left hand and a quiver of arrows on the back. No shield,
no armour, two heads slimmer than the Shieldbearer and 2 px shorter.

Design grid: 24 x 36, column 12 is the pivot, row 36 is the ground line.
The figure stands in rows 2..35 (34 px tall).

How the bow is shown when shooting:
  side   classic profile: bow upright in front, string drawn to the jaw.
  front  the game camera looks down at 43-60 degrees, so a bow aimed at the
         camera is drawn the way it looks from above: a wide arc in front of
         the body with the string pulled up into a V and the arrow pointing
         down-screen.
  back   same idea aimed up-screen: the arc sits behind the head, limbs
         showing either side, draw elbow out to the right.
"""

from pixelkit import P, Canvas, Held
import shieldbearer as sb

CELL = sb.CELL
PIVOT = sb.PIVOT
cv = sb.cv

_BARE = {"A": "a", "B": "b", "C": "b", "D": "c", "E": "d"}   # greaves -> bare shin


# ==========================================================================
# Bow and arrows. Bow anchor = grip.
# ==========================================================================

# Upright, belly to the right, string side on the left. Bronze nocks, leather grip.
BOW_R = P("""
...Bq....
..pqr....
.ppq.....
.pqq.....
..pqq....
..ppqr...
...pqr...
...ppqr..
....pqr..
....pqqr.
....pqqr.
.....sqr.
....pqqr.
....pqqr.
....pqr..
...ppqr..
...pqr...
..ppqr...
..pqq....
.pqq.....
.ppq.....
..pqr....
...Bq....
""", ax=5, ay=11)
BOW_L = BOW_R.flip()
BOW_TIPS_R = ((-4, -9), (-4, 9))      # string nocks, relative to the grip
BOW_TIPS_L = ((4, -9), (4, 9))

# Seen from above, belly toward the camera (down-screen).
BOW_FLAT = P("""
Bp.....................pB
pqq...................qqp
rqqpp...............ppqqr
.rrqqpp...........ppqqrr.
...rrqqppp.....pppqqrr...
.....rrqqqppsppqqqrr.....
.......rrrqqsqqrrr.......
..........rrsrr..........
""", ax=12, ay=5)
BOW_FLAT_UP = BOW_FLAT.vflip()
FLAT_TIPS = ((-11, -4), (11, -4))
FLAT_UP_TIPS = ((-11, 4), (11, 4))

# Arrows carry their own dark edge (bare pixels), so they stay 3 px wide everywhere.
ARROW_DOWN = P("""
ofo
owo
o2o
o2o
o2o
o2o
o2o
o2o
o2o
o2o
oto
oto
.o.
""", ax=1)
ARROW_UP = ARROW_DOWN.vflip()
ARROW_FWD = P("""
oooooooooooo.
fw22222222tto
oooooooooooo.
""", ay=1)

# Fletchings and quiver mouth showing over the shoulder (front view).
F_QUIVER = P("""
2..2
3.23
pqqr
qqrs
""")

# Whole quiver across the back (back view).
B_QUIVER = P("""
.........2..
.........3.2
.........323
.......pqqrs
......pqqrs.
.....pqqrs..
.....pqqrs..
....pqqrs...
...pqqrs....
...pqqrs....
..pqqrs.....
..qqrs......
...rs.......
""")

# Quiver on the back in profile.
S_QUIVER = P("""
.2......
.3.2....
323.....
pqqr....
.pqqr...
.pqqr...
..pqqr..
..pqqr..
...pqqr.
...pqqr.
....qqr.
....rr..
""")


# ==========================================================================
# FRONT
# ==========================================================================

F_HEAD = P("""
...WWXXXY...
..WWXXXXXYZ.
.WWXXXXXXXYZ
.WXXXXXXXXYZ
.qqqqqqqqqrs
.XibbbbbbiYZ
.XbbkaakbbYZ
.XabkaakbcYZ
.YbbbbcbbcZ.
.YYbbccbcYZ.
..YZbbbcZZ..
..YZ.cc.YZ..
""")

F_HEAD_HIT = P("""
...WWXXXY...
..WWXXXXXYZ.
.WWXXXXXXXYZ
.WXXXXXXXXYZ
.qqqqqqqqqrs
.XibbbbbbiYZ
.XbbbaabbbYZ
.XakkaakkcYZ
.YbbbbcbbcZ.
.YYbbkkbcYZ.
..YZbbbcZZ..
..YZ.cc.YZ..
""")

F_TORSO = P("""
.11bccb23.
1qr1bc2233
11qr122334
112qr22334
1122qr2334
.1222qr34.
WXXXXXXYYZ
.XXYXXXYZ.
""")

F_SKIRT = P("""
1XX2122334
1XY2122334
1XY2123334
11Y2123344
2223223344
""")

# Bare legs with sandal straps.
F_LEG = P("""
bccd
abbc
abbc
abbc
qbbr
abbc
qqrs
""")
F_LEG_FWD = sb.F_LEG_FWD.remap(_BARE)
F_LEG_BACK = sb.F_LEG_BACK.remap(_BARE)
F_LEG_LIFT = sb.F_LEG_LIFT.remap(_BARE)

# Free arm (viewer's left), hanging. Anchor = shoulder at (4, 15).
F_ARM_FREE = P("""
abb.
abbc
abbc
abbc
abc.
abbc
aabc
.bc.
""")

# Bow arm (viewer's right), hanging a little out from the body. Anchor = shoulder at (17, 15).
F_ARM_BOW = Held(P("""
bba....
abbc...
.abbc..
..aqqr.
...aqqr
....abc
....abc
....bcc
"""), (5, 6), BOW_R)

# Bow arm reaching down and across to hold the bow level in front. Anchor = shoulder at (17, 15).
F_ARM_BOW_AIM = Held(P("""
.......abb.
.......abbc
........abc
........aqr
.......aqqr
.....aaqqr.
..abbbbbc..
aabbcc.....
abbc.......
.bc........
""", ax=7), (-6, 8), BOW_FLAT)
F_ARM_BOW_AIM.item_front = True

# Draw arm (viewer's left): hand low at the string. Anchor = shoulder at (4, 15).
F_ARM_DRAW_LOW = P("""
.abb.......
abbc.......
abbc.......
.abbc......
.abbbc.....
..abbbbaab.
...bbbbabb.
....cccbbc.
""", ax=1)

# Draw arm: elbow out, hand at the chest.
F_ARM_DRAW_HIGH = P("""
.abb......
abbc......
abbbbbbaab
.bbbbbbabb
..cccccbbc
""", ax=1)

# Draw arm just after the release: hand flung open past the shoulder.
F_ARM_RELEASE = P("""
aa.......
abab.....
.abbbbb..
..bbbbbc.
...ccccc.
""", ax=4, ay=2)


def _front_legs(c, legL, legR):
    for side_, pose in (("L", legL), ("R", legR)):
        x = 7 if side_ == "L" else 13
        foot = sb.F_FOOT_L if side_ == "L" else sb.F_FOOT_R
        big = sb.F_FOOT_L_BIG if side_ == "L" else sb.F_FOOT_R_BIG
        if pose == "stand":
            c.put(F_LEG.tall(2), x, 27).put(foot, x, 34)
        elif pose == "fwd":
            c.put(F_LEG_FWD.tall(2), x, 26).put(big, x, 33)
        elif pose == "back":
            c.put(F_LEG_BACK.tall(2), x, 27).put(sb.F_FOOT_TOE, x, 33)
        elif pose == "lift":
            c.put(F_LEG_LIFT.tall(2), x, 27).put(sb.F_FOOT_TOE, x, 32)
        elif pose == "kneel":
            c.put(F_LEG.rows(3, 7), x, 30).put(foot, x, 34)


def _string(c, grip, tips, nock=None):
    """Bowstring as a bare 1 px line: straight, or drawn back to `nock`."""
    (ax, ay), (bx, by) = [(grip[0] + t[0], grip[1] + t[1]) for t in tips]
    if nock is None:
        c.line(ax, ay, bx, by, "g")
    else:
        c.line(ax, ay, nock[0], nock[1], "g")
        c.line(bx, by, nock[0], nock[1], "g")


def front(legL="stand", legR="stand", body=0, bx=0, head=(0, 0), head_part=F_HEAD, free_d=(0, 0), bow_d=(0, 0),
          lean=(0, 0, 0), aim=None, bow=True):
    """aim: None for the carry pose, else dict(draw='low'|'high'|'release', hand=(dx, dy), nock=row or None,
    arrow=bool, bow_d=(dx, dy))."""
    c = cv()
    kx, tx, hx = bx + lean[0], bx + lean[1], bx + lean[2]
    c.put(F_QUIVER, 2 + tx, 11 + body)
    _front_legs(c, legL, legR)
    c.put(F_SKIRT, 7 + kx, 22 + body, sep="b")
    c.put(F_TORSO, 7 + tx, 14 + body)
    if aim is None:
        c.put(F_ARM_FREE, 4 + tx + free_d[0], 15 + body + free_d[1], sep="r")
        if bow:
            sx, sy = 17 + tx + bow_d[0], 15 + body + bow_d[1]
            F_ARM_BOW.draw(c, sx, sy, sep="l")
            _string(c, (sx + F_ARM_BOW.grip[0], sy + F_ARM_BOW.grip[1]), BOW_TIPS_R)
        else:
            c.put(F_ARM_BOW.arm, 17 + tx + bow_d[0], 15 + body + bow_d[1], sep="l")
        c.put(head_part, 6 + hx + head[0], 2 + body + head[1], sep="b")
        return c

    c.put(head_part, 6 + hx + head[0], 2 + body + head[1], sep="b")
    bd = aim.get("bow_d", (0, 0))
    sx, sy = 17 + tx + bd[0], 15 + body + bd[1]
    grip = (sx + F_ARM_BOW_AIM.grip[0], sy + F_ARM_BOW_AIM.grip[1])
    hd = aim.get("hand", (0, 0))
    draw = {"low": F_ARM_DRAW_LOW, "high": F_ARM_DRAW_HIGH, "release": F_ARM_RELEASE}[aim["draw"]]
    nock = aim.get("nock")
    F_ARM_BOW_AIM.draw(c, sx, sy, sep="all")
    _string(c, grip, FLAT_TIPS, None if nock is None else (grip[0], nock))
    if aim.get("arrow"):
        c.put(ARROW_DOWN, grip[0], nock)
    c.put(draw, 4 + tx + hd[0], 15 + body + hd[1], sep="all")
    return c


# ==========================================================================
# SIDE (facing east)
# ==========================================================================

S_HEAD = P("""
...WWXXXY...
..WWXXXXXYZ.
.WWXXXXXXXYZ
.WXXXXXXXXXY
.qqqqqqqqqqr
.XXXXYibbbb.
.WXXXYbbkab.
.WXXXYabkaa.
.XXXYYbbbbc.
.XXXYZbbcb..
.XYYYZcbb...
..YYZZ.c....
..YZ........
""")

S_HEAD_HIT = P("""
...WWXXXY...
..WWXXXXXYZ.
.WWXXXXXXXYZ
.WXXXXXXXXXY
.qqqqqqqqqqr
.XXXXYibbbb.
.WXXXYbbbab.
.WXXXYabkka.
.XXXYYbbbbc.
.XXXYZbbkb..
.XYYYZcbb...
..YYZZ.c....
..YZ........
""")

S_TORSO = P("""
.111223.
11112233
1q111223
11q11223
111q1233
1112q233
WXXXXYYZ
.XXYXYZ.
""")

S_SKIRT = P("""
11XY2233
11XY2334
112Y2334
11222334
22232344
""")

S_LEGS = {k: v.remap(_BARE) for k, v in sb.S_LEGS.items()}
S_LEG_KNEEL = sb.S_LEG_KNEEL.remap(_BARE)

# Near (draw) arm hanging. Anchor = shoulder at (10, 15).
S_ARM_NEAR = P("""
abb.
abbc
abbc
abbc
.abc
.abbc
.aabc
..bc.
""")

# Far (bow) arm carrying the bow low in front. Anchor at (14, 16).
S_ARM_BOW = Held(P("""
bbc......
bbbcc....
.cbbqq...
...bqqra.
.....rabb
......abc
.......c.
"""), (7, 4), BOW_R)

# Far arm straight out, aiming. Anchor at (14, 14).
S_ARM_BOW_AIM = Held(P("""
bbbbqqqabb
bbbbqqrabc
.cccrrrbc.
"""), (8, 1), BOW_R)

# Near arm reaching forward to nock. Anchor = shoulder at (10, 14); hand centre at (+7, +1).
S_ARM_NOCK = P("""
abbbbbaab
.bbbbbabb
..cccccbc
""")

# Half draw: elbow dropping back. Hand centre at (+4, +1).
S_ARM_HALF = P("""
abbaab
abbabb
.bbbbc
..bcc.
""")

# Full draw: hand at the jaw, elbow high behind. Anchor = shoulder; hand centre at (+1, 0).
S_ARM_FULL = P("""
...aab
abbabb
abbbbc
.bccc.
""", ax=3, ay=1)

# Released: fingers open, hand thrown back past the ear.
S_ARM_RELEASE = P("""
aa.....
abab...
.abbbb.
..bbbbc
...cccc
""", ax=4, ay=2)


def side(near="stand", far="stand", near_x=9, far_x=12, body=0, bx=0, head=(0, 0), head_part=S_HEAD,
         near_d=(0, 0), bow_d=(0, 0), lean=(0, 0, 0), aim=None, bow=True):
    """aim: None for the carry pose, else dict(draw='nock'|'half'|'full'|'release', nock=column or None,
    arrow=bool, bow_d=(dx, dy), hand=(dx, dy))."""
    c = cv()
    kx, tx, hx = bx + lean[0], bx + lean[1], bx + lean[2]
    if far == "kneel":
        c.put(S_LEG_KNEEL.darker(), far_x, 31)
    else:
        c.put(S_LEGS[far].tall(2).darker(), far_x, 27)
    c.put(S_QUIVER, 3 + tx, 10 + body)

    if aim is None:
        if bow:
            sx, sy = 14 + tx + bow_d[0], 16 + body + bow_d[1]
            Held(S_ARM_BOW.arm.darker(), S_ARM_BOW.grip, BOW_R).draw(c, sx, sy)
            _string(c, (sx + S_ARM_BOW.grip[0], sy + S_ARM_BOW.grip[1]), BOW_TIPS_R)
        nock = None
    else:
        bd = aim.get("bow_d", (0, 0))
        sx, sy = 14 + tx + bd[0], 14 + body + bd[1]
        grip = (sx + S_ARM_BOW_AIM.grip[0], sy + S_ARM_BOW_AIM.grip[1])
        nock = aim.get("nock")
        Held(S_ARM_BOW_AIM.arm.darker(), S_ARM_BOW_AIM.grip, BOW_R).draw(c, sx, sy)

    if near == "kneel":
        c.put(S_LEG_KNEEL, near_x, 31, sep="lr")
    else:
        c.put(S_LEGS[near].tall(2), near_x, 27, sep="lr")
    c.put(S_SKIRT, 8 + kx, 22 + body, sep="b")
    c.put(S_TORSO, 8 + tx, 14 + body)
    c.put(head_part, 6 + hx + head[0], 2 + body + head[1], sep="b")

    if aim is None:
        c.put(S_ARM_NEAR, 10 + tx + near_d[0], 15 + body + near_d[1], sep="all")
    else:
        hd = aim.get("hand", (0, 0))
        arm = {"nock": S_ARM_NOCK, "half": S_ARM_HALF, "full": S_ARM_FULL, "release": S_ARM_RELEASE}[aim["draw"]]
        _string(c, grip, BOW_TIPS_R, None if nock is None else (nock, grip[1]))
        if aim.get("arrow"):
            c.put(ARROW_FWD, nock, grip[1])
        c.put(arm, 10 + tx + hd[0], 14 + body + hd[1], sep="all")
    return c


# ==========================================================================
# BACK
# ==========================================================================

B_HEAD = P("""
...WWXXXY...
..WWXXXXXYZ.
.WWXXXXXXXYZ
.WXXXXXXXXYZ
.qqqqqqqqqrs
.XXXXXXXXXYZ
.XXXYXXXYXYZ
.XXXYXXXYXYZ
.XXYXXXXYXYZ
.YXYXXXYYXZZ
..YYXXXYYZZ.
..YZYXXYYZZ.
...ZZYYZZZ..
""")

B_TORSO = P("""
.11222233.
1122222334
1122222334
1122223334
1122223334
.12222334.
WXXXXXXYYZ
.XXYXXXYZ.
""")

B_SKIRT = P("""
1122122334
1122122334
1122123334
1122123344
2223223344
""")

# Free arm from behind (viewer's right). Anchor = shoulder at (17, 15).
B_ARM_FREE = P("""
.bbc
abbc
abbc
abbc
.abc
abbc
abcc
.bc.
""")

# Bow arm from behind (viewer's left). Anchor = shoulder at (4, 15).
B_ARM_BOW = F_ARM_BOW.flip()

# Bow arm raised up-screen, hand hidden behind the head. Anchor = shoulder at (4, 15).
B_ARM_BOW_AIM = P("""
..ab
.abb
.aqq
.aqq
.abb
abbc
abbc
abbc
abbc
bbc.
""", ay=9)

# Draw arm from behind: elbow out to the right, hand by the ear. Anchor = shoulder at (17, 15).
B_ARM_DRAW = P("""
aab....
abbb...
.bbbb..
..abbbc
.abbbcc
abbbc..
bcc....
""", ay=5)

B_ARM_DRAW_HALF = P("""
.aab..
.abbb.
..abbc
.abbbc
abbbc.
bcc...
""", ay=4)

# Released: arm thrown out wide.
B_ARM_RELEASE = P("""
......aa
.....aba
abbbbbb.
bbbbbc..
.cccc...
""", ay=2)


def back(legL="stand", legR="stand", body=0, bx=0, head=(0, 0), free_d=(0, 0), bow_d=(0, 0), lean=(0, 0, 0),
         aim=None, bow=True):
    """aim: None, else dict(draw='half'|'full'|'release', pulled=bool, bow_d=(dx, dy))."""
    c = cv()
    kx, tx, hx = bx + lean[0], bx + lean[1], bx + lean[2]
    if aim is not None:
        bd = aim.get("bow_d", (0, 0))
        grip = (11 + tx + bd[0], 1 + body + bd[1])
        if aim.get("arrow"):
            c.put(ARROW_UP, grip[0], grip[1] + aim.get("arrow_dy", 0) + 6)
        c.put(BOW_FLAT_UP, grip[0], grip[1])
        _string(c, grip, FLAT_UP_TIPS, (11 + tx, 10 + body) if aim.get("pulled") else None)
    sb._back_legs(c, legL, legR)
    c.put(B_SKIRT, 7 + kx, 22 + body, sep="b")
    if aim is None:
        if bow:
            sx, sy = 6 + tx + bow_d[0], 15 + body + bow_d[1]
            B_ARM_BOW.draw(c, sx, sy)
            _string(c, (sx + B_ARM_BOW.grip[0], sy + B_ARM_BOW.grip[1]), BOW_TIPS_L)
        else:
            c.put(B_ARM_BOW.arm, 6 + tx + bow_d[0], 15 + body + bow_d[1])
        c.put(B_ARM_FREE, 17 + tx + free_d[0], 15 + body + free_d[1])
    else:
        c.put(B_ARM_BOW_AIM, 3 + tx, 15 + body)
        arm = {"half": B_ARM_DRAW_HALF, "full": B_ARM_DRAW, "release": B_ARM_RELEASE}[aim["draw"]]
        c.put(arm, 17 + tx, 15 + body)
    c.put(B_TORSO, 7 + tx, 14 + body, sep="lr")
    c.put(B_QUIVER, 8 + tx, 9 + body, sep="lb")
    c.put(B_HEAD, 6 + hx + head[0], 2 + body + head[1], sep="b")
    return c


# ==========================================================================
# DEATH
# ==========================================================================

_seg = sb._seg

# On his back, head to the left. Segments: headcloth, face, neck, tunic, sash, skirt, legs, feet.
CORPSE_UP = P(_seg([
    "..WWXY.. ... . .11222.. .. ..... ...... ...",
    ".WXXXXYq bbc . 11222223 WX 11223 bbbbqb ab.",
    "WXXXXXYq bkb c 1q222233 XX 12123 abbbqb bbc",
    "XXXXXYYq bab c 12q22233 XY 12123 cccccc rs.",
    "XXXXYYZq bab c 122q2233 XY 21233 ...... ...",
    "XYXXYZZq bkb c 1222q334 XY 21234 bbbbqb ab.",
    ".YYYZZZr cbc . 22223344 YZ 22334 abbbqb bbc",
    "..YZZZ.. ... . .233344. .. .334. cccccc rs.",
]))

# Face down: headcloth drape, quiver along the back.
CORPSE_DOWN = P(_seg([
    "..WWXY.. ... . .11222.. .. ..... ...... ...",
    ".WXXXXYq XXY . 11222223 WX 11223 bbbbqb bc.",
    "WXXXXXYq XXY Y 1pqqqrs3 XX 12123 abbbqb bbc",
    "XXXXXYYq XYY Y wfpqqrs3 XY 12123 cccccc rs.",
    "XXXXYYZq XYZ Z fwpqqrs3 XY 21233 ...... ...",
    "XYXXYZZq YYZ . 12222334 XY 21234 bbbbqb bc.",
    ".YYYZZZr YZZ . 22223344 YZ 22334 abbbqb bbc",
    "..YZZZ.. ... . .233344. .. .334. cccccc rs.",
]))

CORPSE_ARM = P("""
abbbbbab
.cccccbc
""")


def corpse(kind, dy=0, bow=(0, 0), dust=False, falling=False):
    c = cv()
    body = CORPSE_UP if kind == "up" else CORPSE_DOWN
    g = (13 + bow[0], 24 + bow[1])
    c.put(BOW_FLAT, g[0], g[1])
    _string(c, g, FLAT_TIPS)
    if falling:                      # feet still near the ground, head and shoulders on the way down
        c.put(body.stair(2), -3, 28 + dy)
        return c
    c.put(body, -6, 28 + dy, sep="t")
    c.put(CORPSE_ARM, 9, 35 + dy, sep="t")
    if dust:
        c.put(sb.DUST, -11, 33, fx=True)
        c.put(sb.DUST.flip(), 28, 33, fx=True)
    return c


# ==========================================================================
# Animation tables
# ==========================================================================

def build():
    fr = {}

    # ---- idle ----
    fr[("idle", "front")] = [front(), front(bow_d=(0, -1)), front(head=(0, -1), bow_d=(0, -1), free_d=(0, -1)), front(head=(0, -1))]
    fr[("idle", "side")] = [side(), side(bow_d=(0, -1)), side(head=(0, -1), bow_d=(0, -1), near_d=(0, -1)), side(head=(0, -1))]
    fr[("idle", "back")] = [back(), back(bow_d=(0, -1)), back(head=(0, -1), bow_d=(0, -1), free_d=(0, -1)), back(head=(0, -1))]

    # ---- walk ----
    fr[("walk", "front")] = [
        front("fwd", "back", body=0, free_d=(0, 1)),
        front("stand", "lift", body=1, free_d=(0, 0), bow_d=(0, 1)),
        front("stand", "lift", body=-1, free_d=(0, -1), bow_d=(0, -1)),
        front("back", "fwd", body=0, free_d=(0, -1)),
        front("lift", "stand", body=1, free_d=(0, 0), bow_d=(0, 1)),
        front("lift", "stand", body=-1, free_d=(0, 1), bow_d=(0, -1)),
    ]
    fr[("walk", "back")] = [
        back("fwd", "back", body=0, free_d=(0, 1)),
        back("stand", "lift", body=1, free_d=(0, 0), bow_d=(0, 1)),
        back("stand", "lift", body=-1, free_d=(0, -1), bow_d=(0, -1)),
        back("back", "fwd", body=0, free_d=(0, -1)),
        back("lift", "stand", body=1, free_d=(0, 0), bow_d=(0, 1)),
        back("lift", "stand", body=-1, free_d=(0, 1), bow_d=(0, -1)),
    ]
    W = dict(near_x=10, far_x=11)
    fr[("walk", "side")] = [
        side("cf", "cb", body=0, near_d=(-1, 0), bow_d=(1, 0), **W),
        side("stand", "lift", body=1, near_d=(0, 1), bow_d=(0, 1), **W),
        side("stand", "pass", body=-1, near_d=(1, -1), bow_d=(-1, -1), **W),
        side("cb", "cf", body=0, near_d=(2, 0), bow_d=(-1, 0), **W),
        side("lift", "stand", body=1, near_d=(1, 1), bow_d=(0, 1), **W),
        side("pass", "stand", body=-1, near_d=(0, -1), bow_d=(1, -1), **W),
    ]

    # ---- attack: 0 nock, 1 half draw, 2 full draw, 3 RELEASE, 4 follow-through, 5 settle ----
    fr[("attack", "side")] = [
        side(aim=dict(draw="nock", nock=17, arrow=True, bow_d=(0, 1))),
        side(aim=dict(draw="half", nock=14, arrow=True)),
        side(bx=-1, head=(0, 0), aim=dict(draw="full", nock=10, arrow=True, bow_d=(1, 0))),
        side(bx=0, aim=dict(draw="release", bow_d=(1, 0))),
        side(aim=dict(draw="release", bow_d=(0, 2), hand=(1, 1))),
        side(bow_d=(1, -2), near_d=(-1, 0)),
    ]
    fr[("attack", "front")] = [
        front(aim=dict(draw="low", nock=20, arrow=True, bow_d=(0, -1))),
        front(aim=dict(draw="low", hand=(0, -1), nock=19, arrow=True)),
        front(body=-1, aim=dict(draw="high", nock=17, arrow=True, bow_d=(0, 2))),
        front(body=0, aim=dict(draw="release", bow_d=(0, 2))),
        front(aim=dict(draw="release", hand=(1, 1), bow_d=(0, 3))),
        front(bow_d=(-1, -1), free_d=(0, -1)),
    ]
    fr[("attack", "back")] = [
        back(aim=dict(draw="half", bow_d=(0, 2), arrow=True, arrow_dy=-3)),
        back(aim=dict(draw="half", pulled=True, bow_d=(0, 1), arrow=True, arrow_dy=-1)),
        back(body=1, aim=dict(draw="full", pulled=True, bow_d=(0, -1), arrow=True, arrow_dy=2)),
        back(body=0, aim=dict(draw="release", bow_d=(0, -2))),
        back(aim=dict(draw="release", bow_d=(0, 0))),
        back(bow_d=(1, -1), free_d=(0, -1)),
    ]

    # ---- hit ----
    fr[("hit", "front")] = [
        front(body=1, head=(0, 1), head_part=F_HEAD_HIT, free_d=(1, 1), bow_d=(-1, 1)),
        front(body=0, head=(0, 1), head_part=F_HEAD_HIT, free_d=(0, 1), bow_d=(0, 1)),
    ]
    fr[("hit", "side")] = [
        side(body=1, bx=-2, head=(-1, 1), head_part=S_HEAD_HIT, near_d=(-1, 1), bow_d=(-1, -1)),
        side(body=0, bx=-1, head=(0, 1), head_part=S_HEAD_HIT, near_d=(0, 1)),
    ]
    fr[("hit", "back")] = [
        back(body=1, head=(0, 1), free_d=(-1, 1), bow_d=(1, 1)),
        back(body=0, head=(0, 1), free_d=(0, 1), bow_d=(0, 1)),
    ]

    # ---- death ----
    fall = dict(dy=-1, bow=(8, -16), falling=True)
    land = dict(dy=1, bow=(1, -1), dust=True)
    fr[("death", "side")] = [
        side(body=0, bx=-1, head=(-1, 0), head_part=S_HEAD_HIT, lean=(0, -1, -2), bow_d=(2, -3), near_d=(-1, -1)),
        side("kneel", "kneel", body=4, bx=-2, head_part=S_HEAD_HIT, lean=(-1, -3, -6), bow_d=(5, -4), near_d=(-2, -1)),
        corpse("up", **fall),
        corpse("up", **land),
        corpse("up"),
    ]
    fr[("death", "front")] = [
        front(body=0, head=(0, 1), head_part=F_HEAD_HIT, lean=(0, -1, -2), bow_d=(2, -3), free_d=(-1, -1)),
        front("kneel", "kneel", body=4, bx=-2, head_part=F_HEAD_HIT, lean=(-1, -3, -6), bow_d=(5, -4), free_d=(-2, -1)),
        corpse("up", **fall),
        corpse("up", **land),
        corpse("up"),
    ]
    fr[("death", "back")] = [
        back(body=0, head=(0, 1), lean=(0, -1, -2), bow_d=(-2, -3), free_d=(1, -1)),
        back("kneel", "kneel", body=4, bx=-2, lean=(-1, -3, -6), bow_d=(-4, -4), free_d=(2, -1)),
        corpse("down", **fall),
        corpse("down", **land),
        corpse("down"),
    ]
    return fr


META = {
    "name": "archer",
    "display_name": "Archer",
    "figure_height_px": 34,
    "attack": {"windup_frames": [0, 1, 2], "strike_frame": 3, "recovery_frames": [3, 4, 5]},
}
