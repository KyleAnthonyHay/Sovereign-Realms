"""The citadel: the kingdom's seat and its recruitment point. Authored in Unreal cm, front toward -X (bldkit.py).

A square-shouldered, weathered castle that grows on one footprint. Its tops never change their language: square
towers whose heads oversail on a corbel course over a glazed team-coloured frieze, parapets with crow-stepped
merlons, flat roof terraces, a standard on a pole; the hall's flat crenellated roof carries a small roof chamber
with a row of dark windows. Levels grow the castle below and around those tops: a curtain, more and taller towers,
half-timbered storeys jettied out on beam ends, a great tower, timber hoardings, darker stone, iron, banners.
No gold, no pitched tower roofs. Team colour: friezes, hanging banners, standards, the hall awning, the level banner.

States (bldkit.STATES): `complete`; `damaged` is the same build with the hooks below switched on (k.damaged) plus
damage(); `site` and `ruin` are small meshes of their own on the same footprint, shared by every level.

Levels 1-7 (k.level; Sovereign Feel > Buildings > Castle upgrades), each adding to the last:
  1  a one-storey stone hall, crenellated, its standard on the roof, in a low walled yard with a plain plank gate
  2  the curtain: a crenellated stone platform with a roof terrace, a gatehouse with an arched iron-strapped gate;
     the hall stands on the terrace and gains its roof chamber and awning
  3  the hall gains a jettied half-timbered storey under its crenellated roof
  4  four square corner towers, the back pair taller with standards; the curtain and gatehouse rise
  5  a great square tower (the keep) swallows the back-right tower and overtops everything
  6  dark heavy stone below; a second half-timbered storey on the hall, a storey on the gatehouse, timber hoardings
     on the front curtain, fires on the wall; every tower rises
  7  the tallest: a timber hoarding round the keep under its head, the roof chamber grown into a tower, a tower on
     each flank, dark stone walls, iron clasps and bands, long banners, more creeper
The level banner (kit.level_flag) stands on the ground at the front-left, before the curtain between the gatehouse
and the left corner: (-540, -310, 0), 340 high, the same at every level.
"""
import math

from mathutils import Vector

from bldkit import STATES, inset_ring, rect  # noqa: F401

NAME = "castle"
MESH = "SM_Bld_Castle"
SEED = 11
D = 400.0            # curtain half depth (X)
W = 540.0            # curtain half width (Y)
FOOTPRINT = [-560.0, -660.0, 560.0, 660.0]      # x0, y0, x1, y1 of the blocking box
RING_RADIUS = 800.0
LEVELS = 7
PREVIEW_FIGURES = [(-700, 120), (-760, 240), (-640, -430)]
PREVIEW_FOCUS = (0.0, 0.0, 260.0)               # the upper levels are tall: aim the previews higher

FLAG = (-540.0, -310.0, 0.0)
YARD = 190.0                                                                        # level 1: the yard wall
TERRACE = {1: 0.0, 2: 320.0, 3: 320.0, 4: 404.0, 5: 404.0, 6: 440.0, 7: 440.0}      # the roof terrace
GATE_UP = {2: 0.0, 3: 0.0, 4: 0.0, 5: 0.0, 6: 170.0, 7: 170.0}                      # the gatehouse's extra storey
HALL = (-30.0, 300.0, 296.0)                                                        # x0, x1, half width
HALL_STONE = {1: 250.0, 2: 292.0, 3: 292.0, 4: 292.0, 5: 292.0, 6: 292.0, 7: 292.0}
HALL_TIMBER = {1: 0, 2: 0, 3: 1, 4: 1, 5: 1, 6: 2, 7: 2}                            # half-timbered storeys
TIMBER_H = 256.0                                                                    # two tiers of the framing
JETTY = (-57.0, 327.0, 320.0)                   # the timber storeys' ring: 384 x 640, whole bays
FRONT_T = (-D + 34, W - 28, 130.0)              # the front corner towers: x, |y|, half
BACK_T = (D - 40, W - 36, 138.0)
FRONT_H = {4: 596.0, 5: 596.0, 6: 720.0, 7: 820.0}
BACK_H = {4: 716.0, 5: 716.0, 6: 900.0, 7: 1040.0}
KEEP = (330.0, 470.0, 150.0)                    # the great tower: x, y, half
KEEP_H = {5: 1300.0, 6: 1480.0, 7: 1660.0}
GX0, GX1, GHW = -548.0, -380.0, 232.0           # the gatehouse


def base_slot(k):
    """The heavy lower courses: dark granite from level 6."""
    return "Bld_StoneDark" if k.level >= 6 else "Bld_AshlarLarge"


def wall_slot(k):
    """The defences' walls above the base: dark at level 7."""
    return "Bld_StoneDark" if k.level >= 7 else "Bld_Ashlar"


def hall_dims(k):
    """(floor, head of the stone storey, wall head) of the hall at this level."""
    lv = k.level
    zp = 3.0 if lv == 1 else TERRACE[lv] + 36.0
    zs = zp + HALL_STONE[lv]
    return zp, zs, zs + HALL_TIMBER[lv] * (TIMBER_H + 16.0)


def front(hw, ya, yb, **kw):
    """An opening on the front (-X) edge of rect(.., -hw, .., hw): between y = ya and yb."""
    return dict(a=hw - yb, b=hw - ya, **kw)


def fpoly(k, slot, pts, out, uvs=None, shade=1.0):
    """k.poly with the winding chosen so the face looks toward `out`."""
    P = [Vector(p) for p in pts]
    if (P[1] - P[0]).cross(P[2] - P[0]).dot(Vector(out)) < 0:
        pts = list(reversed(pts))
        uvs = list(reversed(uvs)) if uvs else None
    k.poly(slot, pts, uvs, shade=shade)


# ---------------------------------------------------------------------- parts
def annulus(k, slot, outer, inner, z, shade=1.0):
    n = len(outer)
    for i in range(n):
        j = (i + 1) % n
        k.poly(slot, [(outer[i][0], outer[i][1], z), (outer[j][0], outer[j][1], z), (inner[j][0], inner[j][1], z), (inner[i][0], inner[i][1], z)], shade=shade)


def arch_gate(k, xf, slot, hw=128.0, z0=6.0, depth=64.0):
    """Turns the square door recess of the gatehouse front (at x = xf) into a round arch: spandrels, the arch's
    soffit, a ring of pale voussoirs, iron straps and studs across the doors."""
    top = z0 + 2 * hw
    zc = top - hw
    n = 10
    arc = [(hw * math.cos(math.pi * i / n), zc + hw * math.sin(math.pi * i / n)) for i in range(n + 1)]
    out = [((hw + 26) * math.cos(math.pi * i / n), zc + (hw + 26) * math.sin(math.pi * i / n)) for i in range(n + 1)]
    for i in range(n):
        (ya, za), (yb, zb) = arc[i], arc[i + 1]
        pts = [(xf, ya, za), (xf, yb, zb)] + ([(xf, yb, top)] if top - zb > 0.5 else []) + ([(xf, ya, top)] if top - za > 0.5 else [])
        if len(pts) >= 3:
            fpoly(k, slot, pts, (-1, 0, 0))
        ym, zm = (ya + yb) / 2, (za + zb) / 2
        fpoly(k, slot, [(xf, ya, za), (xf, yb, zb), (xf + depth - 2, yb, zb), (xf + depth - 2, ya, za)], (0, -ym, zc - zm - 1), shade=0.6)
        (oa, pa), (ob, pb) = out[i], out[i + 1]
        fpoly(k, "Bld_Trim", [(xf - 5, ya, za), (xf - 5, yb, zb), (xf - 5, ob, pb), (xf - 5, oa, pa)], (-1, 0, 0), shade=1.0 if i % 2 else 0.86)
        fpoly(k, "Bld_Trim", [(xf - 5, oa, pa), (xf - 5, ob, pb), (xf, ob, pb), (xf, oa, pa)], (0, ym, zm - zc + 1), shade=0.8)
        fpoly(k, "Bld_Trim", [(xf - 5, ya, za), (xf - 5, yb, zb), (xf, yb, zb), (xf, ya, za)], (0, -ym, zc - zm - 1), shade=0.6)
    xd = xf + depth - 3
    for d in (24, 122, 214):                                 # iron straps over the doors' own
        k.obox("Bld_Iron", (xd, 0, top - d), (5, 2 * hw - 6, 16))
        for y in range(-104, 105, 52):
            k.obox("Bld_Iron", (xd - 3, y, top - d), (5, 9, 9))
    k.obox("Bld_Iron", (xd, 0, z0 + hw), (6, 8, 2 * hw - 4))  # the meeting stile


def hoard_ring(k, ring, z):
    """A timber hoarding round a square tower (`ring` = its wall there), floor at z: planked breast, an open slot
    between posts, a skirt of slate back to the wall; raking struts under it."""
    ro, ri = inset_ring(ring, -44), inset_ring(ring, -37)
    k.cap("Bld_Beam", ro, z, down=True, shade=0.6)
    k.wall("Bld_Planks", ro, z, z + 74, bleach=False, u0=k.U(0, 256))
    annulus(k, "Bld_Planks", ro, ri, z + 74)
    k.wall("Bld_Dark", ri, z + 74, z + 118, bleach=False)
    rb = inset_ring(ring, -47)
    k.wall("Bld_Beam", rb, z + 118, z + 132, v0=0.0, bleach=False)
    k.cap("Bld_Beam", rb, z + 118, down=True, shade=0.6)
    rs, rw = inset_ring(ring, -54), inset_ring(ring, -1)
    n = len(ring)
    for i in range(n):
        j = (i + 1) % n
        k.poly("Bld_Slate", [(rs[i][0], rs[i][1], z + 128), (rs[j][0], rs[j][1], z + 128), (rw[j][0], rw[j][1], z + 162), (rw[i][0], rw[i][1], z + 162)])
        a, b, w0, w1 = Vector(ro[i]), Vector(ro[j]), Vector(ring[i]), Vector(ring[j])
        m = max(int((b - a).length / 62), 1)
        for t in range(m):
            f = t / m
            p, q = a.lerp(b, f), w0.lerp(w1, f)
            pin = p + (q - p).normalized() * 4 if t else p + (Vector(ri[i]) - p) * 0.6
            k.obox("Bld_Beam", (pin.x, pin.y, z + 96), (9, 9, 46))
            if t % 2 == 0:
                k.cyl("Bld_Beam", (q.x, q.y, z - 110), (pin.x, pin.y, z - 2), 5.0, sides=4)


def hoard_front(k, ya, yb, z):
    """A timber hoarding jutting from the head of the front curtain between ya and yb, floor at z, under a
    lean-to skirt of slate."""
    xf = -D + 14.0
    xo = xf - 46.0
    k.box("Bld_Planks", (xo, ya, z - 8), (xf + 8, yb, z + 62), bottom=True)
    k.box("Bld_Dark", (xo + 6, ya + 4, z + 62), (xf + 8, yb - 4, z + 104))
    n = max(int((yb - ya) / 58), 1)
    for i in range(n + 1):
        y = ya + 5 + (yb - ya - 10) * i / n
        k.obox("Bld_Beam", (xo + 4, y, z + 83), (8, 8, 42))
        if i % 2 == 0 or i == n:
            k.cyl("Bld_Beam", (xf - 2, y, z - 84), (xo + 6, y, z - 6), 4.5, sides=4)
    k.obox("Bld_Beam", (xo + 3, (ya + yb) / 2, z + 108), (10, yb - ya, 10), grain="y")
    fpoly(k, "Bld_Slate", [(xo - 16, ya - 6, z + 104), (xo - 16, yb + 6, z + 104), (xf + 30, yb + 6, z + 150), (xf + 30, ya - 6, z + 150)], (-1, 0, 1))
    fpoly(k, "Bld_Beam", [(xo - 16, ya - 6, z + 96), (xo - 16, yb + 6, z + 96), (xo - 16, yb + 6, z + 104), (xo - 16, ya - 6, z + 104)], (-1, 0, 0))
    for y, s in ((ya, -1), (yb, 1)):
        fpoly(k, "Bld_Planks", [(xo, y, z + 104), (xf + 30, y, z + 104), (xf + 30, y, z + 146)], (0, s, 0))


def barrel(k, pos, s=1.0):
    k.lathe("Bld_Planks", pos, [(15 * s, 0), (20 * s, 16 * s), (21 * s, 32 * s), (20 * s, 48 * s), (15 * s, 64 * s)], sides=8, top="Bld_Beam", rot=k.U(0, 45))
    for z in (15, 49):
        k.lathe("Bld_Iron", pos, [(20.8 * s, (z - 3) * s), (20.8 * s, (z + 3) * s)], sides=8, top=False)


def rod_banner(k, x, y, z, drop=192.0, w=64.0, cloth=True):
    """A team banner hung flat on a face that looks to -X, from an iron rod at z."""
    k.cyl("Bld_Iron", (x, y - w / 2 - 8, z + 2), (x, y + w / 2 + 8, z + 2), 2.6, sides=4)
    if cloth:
        k.hang_cloth((x, y - w / 2, z), (x, y + w / 2, z), drop)


def tower(k, cx, cy, half, h, u0, slits=(2, 3), breach=None, pole=0.0, hoard=False, bands=()):
    """A square tower, its top as ever: the head oversails on a corbel course over the glazed frieze, a parapet
    with crow-stepped merlons round a flat roof (at h - 36), a standard on a pole (`pole` = its height)."""
    r0 = rect(cx - half, cy - half, cx + half, cy + half)
    r1 = k.wall(base_slot(k), r0, 0, 124, inset=14, u0=u0, bleach=False)
    k.band("Bld_Trim", r1, 124, 136, out=4, u0=u0)
    side = 2 * (half - 14)
    top = h - 76
    zs = [h * 0.36, h * 0.36 + 150] if h <= 720 else [230.0 + 170.0 * i for i in range(int((top - (460 if hoard else 300)) / 170))]
    ops = {}
    for e in slits:
        ops[e] = [dict(a=side / 2 - 6, b=side / 2 + 6, z0=z, z1=z + 64, depth=14, back="Bld_Dark", shade=0.5) for z in zs]
    # a lost block or two on the sunlit side
    ops.setdefault(3, []).append(dict(a=side * 0.2, b=side * 0.2 + 32, z0=200, z1=216, depth=9, back="Bld_Dark", shade=0.55))
    if breach:
        ops.setdefault(2, []).extend(k.breach(*breach))
    r2 = k.wall(wall_slot(k), r1, 136, top, inset=5, u0=u0, openings=ops)
    for z in bands:                                        # iron clasps round the shaft
        k.wall("Bld_Iron", inset_ring(r1, -3), z, z + 14, bleach=False)
    if hoard:
        hoard_ring(k, r1, top - 250)
    k.band("Bld_Trim", r2, top, top + 12, out=9, u0=u0)
    r3 = inset_ring(r2, -10)                               # the head oversails on the corbel course
    k.cap("Bld_AshlarLarge", r3, top + 12, down=True, shade=0.55)
    k.wall("Bld_Frieze", r3, top + 12, top + 76, v0=0.0, bleach=False, u0=u0)
    k.parapet("Bld_Ashlar", r3, h - 36, h, thick=26, top="Bld_Trim")
    k.stepped_merlons("Bld_Ashlar", r3, h, width=52, gap=30, thick=26, h1=28, h2=24, broken=0.12, cap="Bld_Trim")
    if pole:
        k.pole_banner((cx, cy, h - 36), height=pole)
    return r3


# ---------------------------------------------------------------------- the castle
def yard(k):
    """Level 1: a low yard wall and a plain plank gate."""
    hc = YARD
    r0 = rect(-D, -W, D, W)
    ops = {2: [front(W, -120, 120, z0=4, z1=hc - 22, depth=30, back="Bld_Planks", reveal="Bld_Trim", shade=0.62, back_shade=0.8, no_sill=True)]
           + k.breach(W - 372, W - 256, 30, 150, depth=30)}
    r1 = k.wall("Bld_AshlarLarge", r0, 0, hc, inset=8, u0=96.0, openings=ops)
    inner = inset_ring(r1, 42)
    annulus(k, "Bld_Trim", r1, inner, hc)
    k.wall("Bld_AshlarLarge", list(reversed(inner)), 3, hc, bleach=False, u0=40.0)
    k.cap("Bld_Dirt", inner, 3)
    for s in (-1, 1):                                      # gate piers and a timber lintel
        k.box("Bld_AshlarLarge", (-D - 14, s * 150 - 30, 0), (-D + 44, s * 150 + 30, hc + 60), top="Bld_Trim", u0=10.0)
        k.band("Bld_Trim", rect(-D - 14, s * 150 - 30, -D + 44, s * 150 + 30), hc + 60, hc + 70, out=5)
    k.obox("Bld_Beam", (-D + 4, 0, hc - 8), (22, 250, 26), grain="y")
    for z in (56, 128):                                    # the gate's ledges
        k.obox("Bld_Beam", (-D + 30, 0, z), (6, 236, 14), grain="y")


def curtain(k):
    lv = k.level
    H = TERRACE[lv]
    r0 = rect(-D, -W, D, W)
    u0 = 96.0
    ws = wall_slot(k)
    r1 = k.wall(base_slot(k), r0, 0, 124, inset=16, u0=u0, bleach=False)
    k.band("Bld_Trim", r1, 124, 136, out=4, u0=u0)
    hw = W - 16
    sz = 196 if H > 330 else 170
    ops = {2: [front(hw, y - 6, y + 6, z0=sz, z1=sz + 64, depth=14, back="Bld_Dark", shade=0.5) for y in (-305, 305)]
           + ([front(hw, -290, -262, z0=292, z1=308, depth=9, back="Bld_Dark", shade=0.55)] if H > 330 else []),
           3: [dict(a=x, b=x + 12, z0=sz, z1=sz + 64, depth=14, back="Bld_Dark", shade=0.5) for x in (250, 520)]}
    ops[2] += k.breach(hw - 372, hw - 256, 150, H - 98)    # damaged: the right-hand curtain is breached
    r2 = k.wall(ws, r1, 136, H - 24, inset=4, u0=u0, openings=ops)
    k.band("Bld_Trim", r2, H - 24, H - 12, out=8, u0=u0)
    r3 = inset_ring(r2, -6)
    k.cap("Bld_AshlarLarge", r3, H - 12, down=True, shade=0.55)
    k.wall("Bld_AshlarLarge", r3, H - 12, H + 36, u0=u0)
    k.parapet("Bld_AshlarLarge", r3, H, H + 36, thick=30, top="Bld_Trim")
    lx, ly = 2 * (D - 14), 2 * (W - 14)
    skip = {0: [], 1: [], 2: [(ly / 2 - 250, ly / 2 + 250)], 3: []}
    if lv >= 4:
        skip[0] += [(0, 190), (ly - 190, ly)]
        skip[1] += [(0, 190), (lx - 180, lx)]
        skip[2] += [(0, 180), (ly - 180, ly)]
        skip[3] += [(0, 180), (lx - 190, lx)]
    if lv >= 5:
        skip[0] += [(ly - 250, ly)]
        skip[1] += [(0, 250)]
    if lv >= 6:
        skip[2] = [(0, ly)]
    if lv >= 7:
        skip[1] += [(lx / 2 - 60, lx / 2 + 170)]
        skip[3] += [(lx / 2 - 170, lx / 2 + 60)]
    k.stepped_merlons("Bld_Ashlar", r3, H + 36, width=56, gap=30, thick=30, h1=28, h2=24, broken=0.1, cap="Bld_Trim", skip_spans=skip)
    if lv >= 6:                                            # timber hoardings on the front curtain
        for s in (-1, 1):
            a, b = sorted((s * (GHW + 8), s * (FRONT_T[1] - FRONT_T[2] - 4)))
            hoard_front(k, a, b, H)


def gatehouse(k):
    lv = k.level
    g = TERRACE[lv] - 404.0 + GATE_UP[lv]                  # how far the head stands above the first design's
    slot = "Bld_StoneDark" if lv >= 6 else "Bld_AshlarLarge"
    x0, hw = GX0, GHW
    r0 = rect(x0, -hw, GX1, hw)
    u0 = 24.0
    ops = {2: [front(hw, -128, 128, z0=6, z1=262, depth=64, back="Bld_Door", reveal=slot, shade=0.62, back_shade=0.82)]}
    if 388 + g > 400:
        ops[2] += [front(hw, s * 92 - 14, s * 92 + 14, z0=318 + g * 0.5, z1=366 + g * 0.5, depth=16, back="Bld_Dark", shade=0.5) for s in (-1, 1)]
    if GATE_UP[lv]:                                        # the upper storey's shuttered windows
        ops[2] += [front(hw, y - 22, y + 22, z0=300 + g, z1=366 + g, depth=14, back="Bld_Shutter", reveal="Bld_Trim", shade=0.7, back_shade=0.8)
                   for y in (-150, -50, 50, 150)]
    k.wall(slot, r0, 0, 388 + g, u0=u0, openings=ops, bleach=False)
    arch_gate(k, x0, slot)
    if GATE_UP[lv]:
        k.band("Bld_Trim", r0, 270 + g, 282 + g, out=5, u0=u0)
    k.wall("Bld_Frieze", r0, 388 + g, 452 + g, v0=0.0, bleach=False, u0=u0)
    k.band("Bld_Trim", r0, 452 + g, 468 + g, out=9, u0=u0)
    r1 = inset_ring(r0, -4)
    k.cap("Bld_AshlarLarge", r1, 468 + g, down=True, shade=0.55)
    k.wall("Bld_AshlarLarge", r1, 468 + g, 508 + g, u0=u0)
    k.parapet("Bld_AshlarLarge", r1, 476 + g, 508 + g, thick=28, top="Bld_Trim")
    k.stepped_merlons("Bld_Ashlar", r1, 508 + g, width=56, gap=30, thick=28, h1=28, h2=24, cap="Bld_Trim", edges=(1, 2, 3))
    k.box("Bld_Trim", (x0 - 26, -150, 0), (x0 + 6, 150, 6), v0=0.0)       # threshold slab
    zb = min(368.0 + g, 368.0) if not GATE_UP[lv] else 368.0 + g * 0.5
    zb = max(zb, 300.0)
    for s in (-1, 1):                                      # banners on the piers, hung from iron rods
        rod_banner(k, x0 - 8, s * 190, zb, drop=min(192.0, zb - 110), cloth=not (k.damaged and s > 0))   # damaged: one has burnt off
    for s in (-1, 1):                                      # braziers on the roof corners
        k.brazier((x0 + 46, s * (hw - 52), 476 + g), h=64)


def hall(k):
    lv = k.level
    H = TERRACE[lv]
    x0, x1, hw = HALL
    zp, zs, top = hall_dims(k)
    if lv >= 2:                                            # the podium on the terrace
        k.box("Bld_Ashlar", (x0 - 40, -hw - 34, H), (x1 + 16, hw + 34, zp - 10), top="Bld_Trim", u0=30.0)
        k.band("Bld_Trim", rect(x0 - 40, -hw - 34, x1 + 16, hw + 34), zp - 10, zp, out=4)
        k.steps("Bld_Trim", x0 - 76, x0 - 40, -76, 76, H, zp, 3)
    r0 = rect(x0, -hw, x1, hw)
    u0 = 60.0
    st = HALL_STONE[lv]
    win = dict(z0=zp + st * 0.41, z1=zp + st * 0.67, depth=14, back="Bld_Shutter", reveal="Bld_Trim", shade=0.75, back_shade=0.8)
    wins = (-212, -124, 124, 212) if not k.damaged else (-212, -124)       # damaged: a breach takes the right pair
    ops = {2: [front(hw, -50, 50, z0=zp, z1=zp + st * 0.67, depth=22, back="Bld_Planks", reveal="Bld_Trim", shade=0.7, back_shade=0.7, no_sill=True)]
           + [front(hw, y - 26, y + 26, **win) for y in wins] + k.breach(hw - 248, hw - 96, zp + st * 0.29, zp + st * 0.81),
           3: [dict(a=s - 26, b=s + 26, **win) for s in (90, 240)]}
    k.wall("Bld_Ashlar", r0, zp, zs, u0=u0, openings=ops)
    for y in wins:                                         # sills and the door lintel
        k.obox("Bld_Trim", (x0 - 4, y, win["z0"] - 4), (14, 64, 8))
    k.obox("Bld_Beam", (x0 - 5, 0, zp + st * 0.67 + 10), (18, 132, 20), grain="y")
    head, rr = "Bld_Ashlar", r0
    nt = HALL_TIMBER[lv]
    if nt:                                                 # half-timbered storeys, the first jettied out on beam ends
        head = "Bld_Plaster"
        jx0, jx1, jw = JETTY
        rr = rect(jx0, -jw, jx1, jw)
        k.beam_ends("Bld_Beam", (x0, hw - 24), (x0, -hw + 24), zs - 13, 10, size=(16, 20), out=30)
        k.beam_ends("Bld_Beam", (x0 + 30, -hw), (x1 - 30, -hw), zs - 13, 5, size=(16, 20), out=28)
        k.beam_ends("Bld_Beam", (x1 - 30, hw), (x0 + 30, hw), zs - 13, 5, size=(16, 20), out=28)
        z = zs
        for i in range(nt):
            k.band("Bld_Beam", rr, z, z + 16, out=3)
            zt = z + 16 + TIMBER_H
            tw = dict(z0=zt - 104, z1=zt - 30, depth=10, back="Bld_Dark", reveal="Bld_Beam", shade=0.6)
            tops = {2: [dict(a=128 * n + 38, b=128 * n + 90, **tw) for n in ((0, 1, 3, 4) if i % 2 == 0 else (0, 2, 4))],
                    3: [dict(a=128 * n + 38, b=128 * n + 90, **tw) for n in (0, 2)]}
            if i == nt - 1:
                tops[2] += k.breach(266, 374, zt - 200, zt - 110, depth=20)
            k.wall("Bld_Timber", rr, z + 16, zt, v0=0.0, bleach=False, u0=0.0, openings=tops)
            z = zt
    else:                                                  # roof beams poking through under the cornice
        k.beam_ends("Bld_Beam", (x0, hw - 30), (x0, -hw + 30), top - 26, 9, size=(16, 16), out=22)
        k.beam_ends("Bld_Beam", (x0 + 30, -hw), (x1 - 30, -hw), top - 26, 5, size=(16, 16), out=22)
    # the top, as ever: cornice, parapet, crow-stepped merlons round a flat roof
    k.band("Bld_Trim", rr, top, top + 16, out=8, u0=u0)
    r1 = inset_ring(rr, -2)
    k.wall(head, r1, top + 16, top + 44, u0=u0, bleach=False)
    k.parapet(head, r1, top + 20, top + 44, thick=22, top="Bld_Trim")
    k.stepped_merlons(head, r1, top + 44, width=44, gap=28, thick=22, h1=20, h2=18, cap="Bld_Trim")
    if lv == 1:
        top_k = top + 20
        k.pole_banner((x1 - 88, 0, top_k), height=250.0)
    elif lv < 7:
        top_k = roof_chamber(k, x1, top)
    else:
        top_k = chamber_tower(k, x1, top)
    if lv >= 2:                                            # striped awning over the door on two poles
        za, zb, ax = zp + st - 42, zp + st - 86, x0 - 124
        k.cloth("Bld_Awning", [(x0 - 2, 112, za), (x0 - 2, -112, za), (ax, -112, zb), (ax, 112, zb)],
                [(224, 0), (0, 0), (0, 132), (224, 132)], w=[0.0, 0.0, 0.5, 0.5])
        for s in (-1, 1):
            k.cyl("Bld_Beam", (ax + 8, s * 104, H), (ax + 8, s * 104, zb + 4), 4.0, sides=5)
        k.obox("Bld_Beam", (ax + 8, 0, zb + 2), (6, 232, 6), grain="y")
    if lv >= 6 and not k.damaged:                          # long banners down the timber front
        for y in (-256, 256):
            rod_banner(k, JETTY[0] - 7, y, top - 20, drop=230.0)
    return top_k


def roof_chamber(k, x1, top):
    """A roof chamber at the back of the hall, the third step of the silhouette, carrying the standard."""
    kx0, kx1, kw, kz = x1 - 150, x1 - 24, 112.0, top + 20
    kr = rect(kx0, -kw, kx1, kw)
    kwin = dict(z0=kz + 44, z1=kz + 100, depth=12, back="Bld_Dark", reveal="Bld_Trim", shade=0.6)
    k.wall("Bld_Plaster", kr, kz, kz + 132, u0=200.0, openings={2: [front(kw, y - 14, y + 14, **kwin) for y in (-60, 0, 60)]})
    k.beam_ends("Bld_Beam", (kx0, kw - 16), (kx0, -kw + 16), kz + 112, 5, size=(14, 14), out=18)
    k.band("Bld_Trim", kr, kz + 132, kz + 146, out=7)
    k.cap("Bld_RoofClay", inset_ring(kr, 6), kz + 147)
    top_k = kz + 146
    k.pole_banner((x1 - 88, 0, top_k), height=250.0)       # the hall's standard
    return top_k


def chamber_tower(k, x1, top):
    """Level 7: the roof chamber grown into a tower of its own: two rows of dark windows, the glazed frieze, an
    oversailing crenellated head, the standard."""
    kx0, kx1, kw = x1 - 170, x1 - 14, 124.0
    z0, zt = top + 20, top + 330
    kr = rect(kx0, -kw, kx1, kw)
    kwin = dict(depth=12, back="Bld_Dark", reveal="Bld_Trim", shade=0.6)
    ops = {2: [front(kw, y - 14, y + 14, z0=z, z1=z + 56, **kwin) for y in (-66, 0, 66) for z in (z0 + 44, z0 + 150)],
           3: [dict(a=s - 14, b=s + 14, z0=z0 + 150, z1=z0 + 206, **kwin) for s in (50, 106)]}
    k.wall("Bld_Plaster", kr, z0, zt - 76, u0=200.0, openings=ops)
    k.beam_ends("Bld_Beam", (kx0, kw - 16), (kx0, -kw + 16), z0 + 122, 6, size=(14, 14), out=18)
    k.band("Bld_Trim", kr, zt - 76, zt - 64, out=9)
    r3 = inset_ring(kr, -10)
    k.cap("Bld_AshlarLarge", r3, zt - 64, down=True, shade=0.55)
    k.wall("Bld_Frieze", r3, zt - 64, zt, v0=0.0, bleach=False, u0=200.0)
    k.parapet("Bld_Plaster", r3, zt - 30, zt, thick=22, top="Bld_Trim")
    k.stepped_merlons("Bld_Plaster", r3, zt, width=44, gap=26, thick=22, h1=20, h2=18, cap="Bld_Trim")
    k.pole_banner(((kx0 + kx1) / 2, 0, zt - 30), height=240.0)
    return zt - 30


def towers(k):
    lv = k.level
    fx, fy, fh = FRONT_T
    bx, by, bh = BACK_T
    fhh, bhh = FRONT_H[lv], BACK_H[lv]
    clasp = (300.0, fhh - 150) if lv >= 7 else ()
    for sy in (-1, 1):
        tower(k, fx, sy * fy, fh, fhh, u0=40.0 + sy * 130, breach=(22, 96, fhh - 196, fhh - 88) if sy > 0 else None, bands=clasp)
        zb = fhh - 126
        rod_banner(k, fx - fh - 6, sy * fy, zb, drop=192.0 if lv < 7 else 260.0)       # banner on the front towers' faces
        if sy < 0 or lv == 4:
            tower(k, bx, sy * by, bh, bhh, u0=300.0 + sy * 90, pole=260.0, bands=(300.0, bhh - 150) if lv >= 7 else ())
        if lv >= 7:                                        # a tower in the middle of each flank
            tower(k, 56.0 * -sy, sy * (W + 2), 96, 700, u0=180.0 + sy * 60, slits=(2,), pole=200.0)
    if lv >= 5:                                            # the great tower
        cx, cy, half = KEEP
        kh = KEEP_H[lv]
        tower(k, cx, cy, half, kh, u0=500.0, pole=240.0, hoard=lv >= 7, bands=(300.0, 700.0) if lv >= 7 else (),
              breach=(60, 170, 560, 700))
        zb = kh - 126 if lv < 7 else kh - 350
        if not k.damaged:
            rod_banner(k, cx - half - (8 if lv < 7 else 52), cy, zb, drop=300.0, w=72.0)
        else:
            k.hang_cloth((cx - half - 8, cy - 36, zb), (cx - half - 8, cy + 36, zb), 300.0)


def dressing(k):
    lv = k.level
    H = TERRACE[lv]
    if lv == 1:                                            # a working yard
        k.crate((-180, -392, 3), (56, 56, 44), yaw=8)
        k.crate((-178, -330, 3), (48, 52, 40), yaw=-5)
        barrel(k, (-150, 330, 3))
        barrel(k, (-194, 372, 3), 0.9)
        k.sack((-110, 250, 3), 1.0, yaw=30)
        k.sack((-84, 218, 3), 0.9, yaw=-40)
        k.timber_pile((-280, 440, 3), yaw=90, length=150, base=3, planks=False)
        k.pot((-452, 220, 0), 1.0)
        k.patch("Bld_Leaves", (-D + 2, -W, 0), (1, 0, 0), (0, 0, 1), 200, 150, cells=12, fill=0.55, out=17)
        return
    # roof terrace: stores stacked against the hall podium and the parapet
    k.crate((-110, -392, H), (56, 56, 44), yaw=8)
    k.crate((-108, -330, H), (48, 52, 40), yaw=-5)
    k.crate((-112, -366, H + 44), (44, 44, 36), yaw=20)
    k.pot((-120, 398, H), 1.0)
    k.pot((-150, 446, H), 0.8)
    barrel(k, (-84, 452, H))
    k.sack((-300, -470, H), 1.0, yaw=30)
    k.sack((-268, -438, H), 0.9, yaw=-40)
    # at the foot of the walls
    barrel(k, (-470, -256, 0))
    barrel(k, (-506, -272, 0), 0.9)
    if not k.damaged:                                      # buried under the fallen curtain
        k.crate((-470, 300, 0), (60, 60, 48), yaw=12)
        barrel(k, (-492, 252, 0))
        k.sack((-500, 342, 0), 1.0, yaw=70)
    for s in (-1, 1):
        k.brazier((-568, s * 204, 0), h=92)
    if lv >= 6:                                            # fires on the wall
        for (x, y) in ((-150, -490), (-150, 490), (-330, -330), (-330, 330)):
            k.brazier((x, y, H), h=70)
    # creeper on the old walls
    fx, fy, fh = FRONT_T
    creep = [((-D + 16, -150 if lv < 4 else -330, 0), (0, -1, 0), 110, 130), ((-D + 2, -W - (0 if lv < 4 else 100), 0), (1, 0, 0), 200, 180)]
    if lv >= 3:
        creep += [((-D + 16, 330, 0), (0, -1, 0), 130, 200)]
    if lv >= 4:
        creep += [((fx - fh + 4, fy + 8, 0), (0, -1, 0), 190, 250)]
    if lv >= 5:
        creep += [((KEEP[0] - KEEP[2] + 4, KEEP[1] + 30, H), (0, -1, 0), 170, 330)]
    if lv >= 6:
        creep += [((fx - fh + 4, -fy - 40, 0), (0, -1, 0), 130, 330), ((GX0, 196, 0), (0, -1, 0), 60, 300)]
    if lv >= 7:
        creep += [((KEEP[0] - KEEP[2] + 4, KEEP[1] - 50, H + 300), (0, -1, 0), 130, 420), ((fx - fh + 4, fy - 40, 240), (0, -1, 0), 120, 300),
                  ((HALL[0], -180, H + 36), (0, -1, 0), 160, 250)]
    for o, r, w, h in creep:
        k.patch("Bld_Leaves", o, r, (0, 0, 1), w, h, cells=12, fill=0.6, out=17)


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
    if lv == 1:
        yard(k)
    else:
        curtain(k)
        gatehouse(k)
    top = hall(k)
    if lv >= 4:
        towers(k)
    dressing(k)
    k.level_flag(FLAG, height=340.0)
    k.collider((FOOTPRINT[0], FOOTPRINT[1], 0), (FOOTPRINT[2], FOOTPRINT[3], 620))
    k.sockets["gate"] = (-600.0, 0.0, 0.0)          # where a recruit appears: just outside the doors
    k.sockets["rally"] = (-780.0, 800.0, 0.0)       # default rally point: the court, clear of the right-hand tower
    k.sockets["label"] = (0.0, 0.0, top + 270.0)    # just over the hall's standard


def damage(k):
    """Added to the finished build on the damaged mesh: soot, burnt roofs, what fell. Every mark sits on a surface
    that exists at this level."""
    lv = k.level
    H = TERRACE[lv]
    x0 = HALL[0]
    zp, zs, top = hall_dims(k)
    st = HALL_STONE[lv]
    k.scorch("smear", (x0, 172, zp + st - 134 if lv == 1 else zp + st * 0.76), out=5)   # the hall, over its breach
    k.scorch("lick", (x0, -250, zp + 16) if lv > 1 else (x0, -250, zp))
    k.burn_hole((70, -196, top + 20), (190, 140), yaw=8)     # the hall roof
    if HALL_TIMBER[lv]:
        k.scorch("plume_s", (JETTY[0], 20, top - 196), out=5)                # the timber storey, over its breach
    if lv == 1:
        k.scorch("blot_s", (-D + 4, 314, 124), out=7)        # the yard wall, over its breach
        k.scorch("blot_s", (-D + 4, -210, 122), out=7)
        k.scorch("blot_l", (-180, 60, 3), "up", out=2.0)     # the yard
        k.rubble((-450, 314, 0), (120, 140), 26, blocks=6, beams=0)
        k.rubble((-110, 170, 3), (150, 170), 26, slot="Bld_Ashlar", blocks=6, beams=1)
        k.charred((-D - 20, -50, 4), (-D - 6, 70, 120), size=13)
        return
    g = H - 404.0 + GATE_UP[lv]
    gx = GX0
    if 388 + g > 400:
        k.scorch("plume_m", (gx, -66, 300 + g))              # licking up the gatehouse over the frieze
    else:
        k.scorch("blot_s", (gx - 2, -180, 420 + g))          # the gatehouse's frieze
    k.scorch("lick", (gx, 170, 20), flip=True)
    k.scorch("smear", (-384, 314, H - 96), out=6)            # over the curtain breach
    k.scorch("blot_s", (-384, -150, 282), out=7) if H < 400 else k.scorch("plume_m2", (-384, -150, 140), out=7)
    k.burn_hole((-226, 322, H), (170, 130), yaw=15)          # the roof terrace
    k.burn_hole((-250, -210, H), (120, 100), yaw=-30, soot="blot_m")
    k.burn_hole((gx + 84, 40, 476 + g), (110, 150), yaw=0, soot="blot_m")
    if lv >= 4:
        fx, fy, fh = FRONT_T
        fhh = FRONT_H[lv]
        k.scorch("smear", (fx - fh + 9, fy, fhh - 66))                  # the right-hand tower's frieze, over its breach
        k.scorch("plume_m", (fx - fh + 18, -fy, 142), out=6, flip=True)
        k.scorch("streak", (fx - fh + 18, fy + 70, 240), out=6)
        k.burn_hole((fx, -fy, fhh - 36), (110, 100), yaw=20, soot="blot_s")  # the left-hand tower's roof
        k.rubble((fx - fh - 32, -fy, 0), (80, 190), 28, blocks=6, beams=0)
    if lv >= 5:
        k.scorch("plume_l", (KEEP[0] - KEEP[2] + 18, KEEP[1], 700), out=6)   # the great tower, over its breach
    k.rubble((-476, 312, 0), (170, 150), 46, blocks=9, beams=1)
    k.rubble((-566, 160, 0), (40, 110), 0, blocks=4, beams=0, mound=False)
    k.rubble((-110, 150, zp), (150, 170), 26, slot="Bld_Ashlar", blocks=6, beams=1)
    k.charred((gx - 14, -40, 4), (gx - 2, 60, 150), size=14)                 # a beam fallen across the gate


def site(k):
    fp = FOOTPRINT
    k.footings(fp[0], fp[1], fp[2], fp[3], width=40, height=16)
    g = 6.0
    k.scaffold(fp[0] - g, fp[1] - g, fp[2] + g, fp[3] + g, height=470, lift=160, bay=245, depth=46, ladder=(2, 1))
    k.stone_stack((-474, 312, 0), yaw=90)                    # in the angle between the gatehouse and the towers
    k.stone_stack((-470, -250, 0), yaw=84, courses=(2, 2))
    k.timber_pile((-476, -330, 0), yaw=90, length=130, base=3)
    k.hoist((-612, 712, 0), height=600, reach=220, yaw=-49, load_z=330)
    k.hoist((612, -712, 0), height=560, reach=200, yaw=131, load_z=380)


def ruin(k):
    k.poly("Bld_Dirt", [(-380, -520, 2.5), (380, -520, 2.5), (380, 520, 2.5), (-380, 520, 2.5)])
    k.ruin_rect("Bld_AshlarLarge", -384, -524, 384, 524, hmax=196, hmin=36, thick=34, seg=66, gaps=0.16)
    for sy in (-1, 1):                                       # the towers' stumps, the back pair higher
        cx, cy = -D + 34, sy * (W - 28)
        k.ruin_rect("Bld_AshlarLarge", cx - 114, cy - 114, cx + 114, cy + 114, hmax=220, hmin=48, thick=32, seg=58, gaps=0.1,
                    corners=(1, 0.6, 0.4, 0.9) if sy < 0 else (0.5, 1, 0.8, 0.3))
        cx, cy = D - 40, sy * (W - 36)
        k.ruin_rect("Bld_AshlarLarge", cx - 122, cy - 122, cx + 122, cy + 122, hmax=280, hmin=64, thick=32, seg=62, gaps=0.08,
                    corners=(0.6, 1, 0.9, 0.4) if sy < 0 else (1, 0.5, 0.6, 1))
        k.rubble((cx - 20, cy, 0), (190, 190), 70, blocks=5, beams=1)
        # the gatehouse: its two piers either side of the way in
        k.stub("Bld_AshlarLarge", (-532, sy * 232), (-532, sy * 128), thick=34, hmax=250, hmin=80, seg=52, ends=(0.5, 1.0), gaps=0)
        k.stub("Bld_AshlarLarge", (-515, sy * 216), (-400, sy * 216), thick=32, hmax=200, hmin=48, seg=58, ends=(1.0, 0.3))
    k.rubble((-80, 0, 0), (560, 800), 104, blocks=18, beams=4)
    k.rubble((150, -30, 40), (380, 520), 96, slot="Bld_Ashlar", blocks=10, beams=3)       # where the hall came down
    k.ruin_rect("Bld_Plaster", 10, -250, 270, 250, hmax=110, hmin=24, thick=26, seg=58, gaps=0.5, z=84, corners=(0.4, 1, 0.7, 0.2))
    k.rubble((-470, 0, 0), (150, 300), 50, blocks=8, beams=2)                              # the gate passage, choked
    k.rubble((-490, 310, 0), (120, 130), 0, blocks=6, beams=1, mound=False)
    k.rubble((-480, -310, 0), (130, 130), 24, blocks=5, beams=0)
    for (x, y) in ((-220, 60), (-150, 330), (100, -380)):
        k.scorch("blot_l", (x, y, 3), "up", out=2.0)
    k.charred((-300, -200, 30), (-120, -330, 190), size=16)
    k.charred((60, 240, 60), (250, 120, 200), size=15)
