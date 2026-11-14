"""The citadel: the kingdom's seat and its recruitment point. Authored in Unreal cm, front toward -X (bldkit.py).

A compact bronze-age keep, not a medieval castle: a battered sandstone curtain with crow-stepped merlons, four
square towers (the back pair taller, so the silhouette climbs away from the camera), a gatehouse of big ashlar
with a bronze-strapped double gate under a timber lintel, and a plastered upper hall on the roof terrace with an
awning, shutters and beam ends. Team colour: glazed-brick friezes on the towers and gatehouse, hanging banners,
the hall awning, flags on the back towers and the hall.
"""
from bldkit import inset_ring, rect

NAME = "castle"
MESH = "SM_Bld_Castle"
SEED = 11
D = 400.0            # curtain half depth (X)
W = 540.0            # curtain half width (Y)
H = 404.0            # roof terrace
FOOTPRINT = [-560.0, -660.0, 560.0, 660.0]      # x0, y0, x1, y1 of the blocking box
RING_RADIUS = 800.0
PREVIEW_FIGURES = [(-700, 120), (-760, 240), (-640, -330)]


def front(hw, ya, yb, **kw):
    """An opening on the front (-X) edge of rect(.., -hw, .., hw): between y = ya and yb."""
    return dict(a=hw - yb, b=hw - ya, **kw)


def tower(k, cx, cy, half, h, u0, slits=(2, 3), frieze=True):
    r0 = rect(cx - half, cy - half, cx + half, cy + half)
    r1 = k.wall("Bld_AshlarLarge", r0, 0, 124, inset=14, u0=u0, bleach=False)
    k.band("Bld_Trim", r1, 124, 136, out=4, u0=u0)
    side = 2 * (half - 14)
    ops = {}
    for e in slits:
        ops[e] = [dict(a=side / 2 - 6, b=side / 2 + 6, z0=z, z1=z + 64, depth=14, back="Bld_Dark", shade=0.5) for z in (h * 0.36, h * 0.36 + 150)]
    # a lost block or two on the sunlit side
    ops.setdefault(3, []).append(dict(a=side * 0.2, b=side * 0.2 + 32, z0=200, z1=216, depth=9, back="Bld_Dark", shade=0.55))
    top = h - 76
    r2 = k.wall("Bld_Ashlar", r1, 136, top, inset=5, u0=u0, openings=ops)
    k.band("Bld_Trim", r2, top, top + 12, out=9, u0=u0)
    r3 = inset_ring(r2, -10)                               # the head oversails on the corbel course
    k.cap("Bld_AshlarLarge", r3, top + 12, down=True, shade=0.55)
    if frieze:
        k.wall("Bld_Frieze", r3, top + 12, top + 76, v0=0.0, bleach=False, u0=u0)
    else:
        k.wall("Bld_AshlarLarge", r3, top + 12, top + 76, u0=u0)
    k.parapet("Bld_Ashlar", r3, h - 36, h, thick=26, top="Bld_Trim")
    k.stepped_merlons("Bld_Ashlar", r3, h, width=52, gap=30, thick=26, h1=28, h2=24, broken=0.12, cap="Bld_Trim")
    return r3


def curtain(k):
    r0 = rect(-D, -W, D, W)
    u0 = 96.0
    r1 = k.wall("Bld_AshlarLarge", r0, 0, 124, inset=16, u0=u0, bleach=False)
    k.band("Bld_Trim", r1, 124, 136, out=4, u0=u0)
    hw = W - 16
    ops = {2: [front(hw, y - 6, y + 6, z0=196, z1=260, depth=14, back="Bld_Dark", shade=0.5) for y in (-305, 305)]
           + [front(hw, 262, 290, z0=292, z1=308, depth=9, back="Bld_Dark", shade=0.55)],
           3: [dict(a=x, b=x + 12, z0=196, z1=260, depth=14, back="Bld_Dark", shade=0.5) for x in (250, 520)]}
    r2 = k.wall("Bld_Ashlar", r1, 136, 380, inset=4, u0=u0, openings=ops)
    k.band("Bld_Trim", r2, 380, 392, out=8, u0=u0)
    r3 = inset_ring(r2, -6)
    k.cap("Bld_AshlarLarge", r3, 392, down=True, shade=0.55)
    k.wall("Bld_AshlarLarge", r3, 392, 440, u0=u0)
    k.parapet("Bld_AshlarLarge", r3, H, 440, thick=30, top="Bld_Trim")
    lx, ly = 2 * (D - 14), 2 * (W - 14)
    k.stepped_merlons("Bld_Ashlar", r3, 440, width=56, gap=30, thick=30, h1=28, h2=24, broken=0.1, cap="Bld_Trim",
                      skip_spans={0: [(0, 190), (ly - 190, ly)], 1: [(0, 190), (lx - 180, lx)],
                                  2: [(0, 180), (ly / 2 - 250, ly / 2 + 250), (ly - 180, ly)], 3: [(0, 180), (lx - 190, lx)]})


def gatehouse(k):
    x0, x1, hw = -548.0, -380.0, 232.0
    r0 = rect(x0, -hw, x1, hw)
    u0 = 24.0
    ops = {2: [front(hw, -128, 128, z0=6, z1=262, depth=64, back="Bld_Door", reveal="Bld_AshlarLarge", shade=0.62, back_shade=0.82),
               front(hw, -106, -78, z0=318, z1=366, depth=16, back="Bld_Dark", shade=0.5),
               front(hw, 78, 106, z0=318, z1=366, depth=16, back="Bld_Dark", shade=0.5)]}
    k.wall("Bld_AshlarLarge", r0, 0, 388, u0=u0, openings=ops, bleach=False)
    k.wall("Bld_Frieze", r0, 388, 452, v0=0.0, bleach=False, u0=u0)
    k.band("Bld_Trim", r0, 452, 468, out=9, u0=u0)
    r1 = inset_ring(r0, -4)
    k.cap("Bld_AshlarLarge", r1, 468, down=True, shade=0.55)
    k.wall("Bld_AshlarLarge", r1, 468, 508, u0=u0)
    k.parapet("Bld_AshlarLarge", r1, 476, 508, thick=28, top="Bld_Trim")
    k.stepped_merlons("Bld_Ashlar", r1, 508, width=56, gap=30, thick=28, h1=28, h2=24, cap="Bld_Trim", edges=(1, 2, 3))
    # timber lintel on stone corbels, bronze caps on its ends, a bronze sun disc over it
    k.obox("Bld_Beam", (x0 - 6, 0, 280), (28, 292, 34), grain="y")
    for s in (-1, 1):
        k.obox("Bld_Bronze", (x0 - 7, s * 141, 280), (32, 12, 38))
        k.obox("Bld_Trim", (x0 - 5, s * 134, 250), (22, 20, 26))
    k.cyl("Bld_Bronze", (x0 - 9, 0, 338), (x0, 0, 338), 30.0, sides=8, grain="ring")
    k.cyl("Bld_Bronze", (x0 - 14, 0, 338), (x0 - 9, 0, 338), 13.0, sides=8, grain="ring")
    # threshold slab
    k.box("Bld_Trim", (x0 - 26, -150, 0), (x0 + 6, 150, 6), v0=0.0)
    # banners on the piers, hung from bronze rods
    for s in (-1, 1):
        y = s * 190
        k.cyl("Bld_Bronze", (x0 - 8, y - 40, 368), (x0 - 8, y + 40, 368), 2.6, sides=4)
        k.hang_cloth((x0 - 8, y - 32, 366), (x0 - 8, y + 32, 366), 192.0)
    # braziers on the roof corners
    for s in (-1, 1):
        k.brazier((x0 + 46, s * (hw - 52), 476), h=64)


def hall(k):
    x0, x1, hw = -30.0, 300.0, 296.0
    zp = H + 36                                            # podium top
    k.box("Bld_Ashlar", (x0 - 40, -hw - 34, H), (x1 + 16, hw + 34, zp - 10), top="Bld_Trim", u0=30.0)
    k.band("Bld_Trim", rect(x0 - 40, -hw - 34, x1 + 16, hw + 34), zp - 10, zp, out=4)
    k.steps("Bld_Trim", x0 - 76, x0 - 40, -76, 76, H, zp, 3)
    r0 = rect(x0, -hw, x1, hw)
    u0 = 60.0
    top = zp + 292
    win = dict(z0=zp + 120, z1=zp + 196, depth=14, back="Bld_Shutter", reveal="Bld_Trim", shade=0.75, back_shade=0.8)
    ops = {2: [front(hw, -50, 50, z0=zp, z1=zp + 196, depth=22, back="Bld_Planks", reveal="Bld_Trim", shade=0.7, back_shade=0.7, no_sill=True)]
           + [front(hw, y - 26, y + 26, **win) for y in (-212, -124, 124, 212)],
           3: [dict(a=s - 26, b=s + 26, **win) for s in (90, 240)]}
    k.wall("Bld_Plaster", r0, zp, top, u0=u0, openings=ops)
    # sills and the door lintel
    for y in (-212, -124, 124, 212):
        k.obox("Bld_Trim", (x0 - 4, y, zp + 116), (14, 64, 8))
    k.obox("Bld_Beam", (x0 - 5, 0, zp + 206), (18, 132, 20), grain="y")
    # roof beams poking through under the cornice, front and sunlit side
    k.beam_ends("Bld_Beam", (x0, hw - 30), (x0, -hw + 30), top - 26, 9, size=(16, 16), out=22)
    k.beam_ends("Bld_Beam", (x0 + 30, -hw), (x1 - 30, -hw), top - 26, 5, size=(16, 16), out=22)
    k.band("Bld_Trim", r0, top, top + 16, out=8, u0=u0)
    r1 = inset_ring(r0, -2)
    k.wall("Bld_Plaster", r1, top + 16, top + 44, u0=u0, bleach=False)
    k.parapet("Bld_Plaster", r1, top + 20, top + 44, thick=22, top="Bld_Trim")
    k.stepped_merlons("Bld_Plaster", r1, top + 44, width=44, gap=28, thick=22, h1=20, h2=18, cap="Bld_Trim")
    # a roof chamber at the back: the third step of the silhouette, carrying the standard
    kx0, kx1, kw, kz = x1 - 150, x1 - 24, 112.0, top + 20
    kr = rect(kx0, -kw, kx1, kw)
    kwin = dict(z0=kz + 44, z1=kz + 100, depth=12, back="Bld_Dark", reveal="Bld_Trim", shade=0.6)
    k.wall("Bld_Plaster", kr, kz, kz + 132, u0=200.0, openings={2: [front(kw, y - 14, y + 14, **kwin) for y in (-60, 0, 60)]})
    k.beam_ends("Bld_Beam", (kx0, kw - 16), (kx0, -kw + 16), kz + 112, 5, size=(14, 14), out=18)
    k.band("Bld_Trim", kr, kz + 132, kz + 146, out=7)
    k.cap("Bld_RoofClay", inset_ring(kr, 6), kz + 147)
    top_k = kz + 146
    # striped awning over the door on two poles
    za, zb, ax = zp + 250, zp + 206, x0 - 124
    k.poly("Bld_Awning", [(x0 - 2, 112, za), (x0 - 2, -112, za), (ax, -112, zb), (ax, 112, zb)],
           [(224, 0), (0, 0), (0, 132), (224, 132)], w=[0.0, 0.0, 0.5, 0.5])
    for s in (-1, 1):
        k.cyl("Bld_Beam", (ax + 8, s * 104, H), (ax + 8, s * 104, zb + 4), 4.0, sides=5)
    k.obox("Bld_Beam", (ax + 8, 0, zb + 2), (6, 232, 6), grain="y")
    # the hall's standard
    k.pole_banner((x1 - 88, 0, top_k), height=250.0)
    return top_k


def dressing(k):
    # roof terrace: stores stacked against the hall podium and the parapet
    k.crate((-110, -392, H), (56, 56, 44), yaw=8)
    k.crate((-108, -330, H), (48, 52, 40), yaw=-5)
    k.crate((-112, -366, H + 44), (44, 44, 36), yaw=20)
    k.pot((-120, 398, H), 1.0)
    k.pot((-150, 446, H), 0.8)
    k.pot((-84, 452, H), 0.7)
    k.sack((-300, -470, H), 1.0, yaw=30)
    k.sack((-268, -438, H), 0.9, yaw=-40)
    # at the foot of the walls
    k.pot((-470, 314, 0), 1.1)
    k.pot((-500, 264, 0), 0.85)
    k.crate((-470, -300, 0), (60, 60, 48), yaw=12)
    k.sack((-492, -250, 0), 1.0, yaw=70)
    for s in (-1, 1):
        k.brazier((-590, s * 292, 0), h=92)
    # creeper climbing the right-hand tower and the curtain beside it
    k.patch("Bld_Leaves", (-496, 520, 0), (0, -1, 0), (0, 0, 1), 190, 250, cells=12, fill=0.6, out=17)
    k.patch("Bld_Leaves", (-400, 330, 0), (0, -1, 0), (0, 0, 1), 110, 130, cells=12, fill=0.5, out=17)
    k.patch("Bld_Leaves", (-380, -640, 0), (1, 0, 0), (0, 0, 1), 200, 180, cells=12, fill=0.55, out=17)


def build(k):
    curtain(k)
    gatehouse(k)
    top = hall(k)
    for sy in (-1, 1):
        tower(k, -D + 34, sy * (W - 28), 130, 596, u0=40.0 + sy * 130)
        r = tower(k, D - 40, sy * (W - 36), 138, 716, u0=300.0 + sy * 90)
        k.pole_banner((D - 40, sy * (W - 36), 716 - 36), height=260.0)
        # banner on the front towers' faces
        cx, cy = -D + 34, sy * (W - 28)
        k.cyl("Bld_Bronze", (cx - 136, cy - 40, 470), (cx - 136, cy + 40, 470), 2.6, sides=4)
        k.hang_cloth((cx - 136, cy - 32, 468), (cx - 136, cy + 32, 468), 192.0)
    dressing(k)
    k.collider((FOOTPRINT[0], FOOTPRINT[1], 0), (FOOTPRINT[2], FOOTPRINT[3], 620))
    k.sockets["gate"] = (-640.0, 0.0, 0.0)          # where a recruit appears
    k.sockets["rally"] = (-800.0, 420.0, 0.0)       # default rally point
    k.sockets["label"] = (0.0, 0.0, top + 270.0)
