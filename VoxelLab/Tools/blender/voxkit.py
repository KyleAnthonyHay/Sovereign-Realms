"""voxkit: the shared building pieces of the voxel village, so that every building has the same roofs, lanterns,
windows and banners. Everything here works on / returns voxlib.Vox grids at 12.5 cm voxels unless it says otherwise.

Scale: 1 block = 4 voxels = 50 cm. King David is about 1.7 m (14 voxels) tall; a door is 8 voxels wide, 16 high.
"""
import numpy as np

import voxlib as V
from voxlib import Vox

VOX = 0.125
B = 4                    # voxels per 50 cm block


# ---------------------------------------------------------------------------------------------------- roofs

def gable_roof(v, x0, y0, x1, y1, z, ridge="x", run=4, rise=3, thick=3, tile="roof", trim="plank", ridge_mat="beam",
               trim_w=4, trim_up=1, eave="beam"):
    """A stepped gable roof over the rectangle x0..x1, y0..y1 (give it the overhang you want), its eaves at height z.
    ridge='x': the ridge runs along X, the gable ends are at x0 and x1 and the slopes fall towards -Y and +Y.
    Each step is `run` voxels deep and `rise` high. Wooden barge boards (trim) step up the gable ends, a wooden
    board runs along each eave, and a ridge beam caps the top. Returns the z of the top of the ridge."""
    if ridge == "y":
        a0, a1, b0, b1 = y0, y1, x0, x1
    else:
        a0, a1, b0, b1 = x0, x1, y0, y1

    def put(al, ah, bl, bh, zl, zh, mat):
        if ridge == "y":
            v.box(bl, al, zl, bh, ah, zh, mat)
        else:
            v.box(al, bl, zl, ah, bh, zh, mat)

    half = (b1 - b0) / 2.0
    steps = int(np.ceil(half / run))
    top = z
    for i in range(steps):
        lo, hi = b0 + i * run, b1 - i * run
        if hi - lo <= 0:
            break
        zl = z + i * rise
        zh = zl + max(thick, rise)
        put(a0, a1, lo, hi, zl, zh, tile)
        # barge boards on the two gable ends: one voxel proud of the tiles, stepping up with them
        put(a0, a0 + trim_w, lo, hi, zl, zh + trim_up, trim)
        put(a1 - trim_w, a1, lo, hi, zl, zh + trim_up, trim)
        if i == 0 and eave:                                  # eave boards along the low edges
            put(a0, a1, lo, lo + 1, zl, zl + 2, eave)
            put(a0, a1, hi - 1, hi, zl, zl + 2, eave)
        top = zh
    mid = (b0 + b1) // 2
    put(a0, a1, mid - 2, mid + 2, top, top + 2, ridge_mat)   # ridge beam
    put(a0, a0 + trim_w, mid - 2, mid + 2, top, top + 3, trim)
    put(a1 - trim_w, a1, mid - 2, mid + 2, top, top + 3, trim)
    return top + 2


def pyramid_roof(v, x0, y0, x1, y1, z, run=2, rise=3, tile="roof", cap="beam", trim=None):
    """A stepped four-sided roof (tower caps). Returns the z of its top."""
    i = 0
    top = z
    while x1 - x0 - 2 * i * run > 0 and y1 - y0 - 2 * i * run > 0:
        v.box(x0 + i * run, y0 + i * run, z + i * rise, x1 - i * run, y1 - i * run, z + (i + 1) * rise, tile)
        if trim and i == 0:
            v.frame(x0, y0, z, x1, y1, z + 1, trim)
        top = z + (i + 1) * rise
        i += 1
    cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
    v.box(cx - 1, cy - 1, top, cx + 1, cy + 1, top + 2, cap)
    return top + 2


# ---------------------------------------------------------------------------------------------------- openings

def window(v, axis, plane, a0, z0, w=6, h=8, out=-1, frame="beam", sill=True, mullion=True):
    """A glowing window on a wall. The wall's outer face is the voxel layer at coordinate `plane` on `axis` ('x' or
    'y'), facing direction `out` (+1 or -1) along that axis. a0: where it starts along the wall; z0: its sill height.
    The panes replace the wall's outer layer; a wooden frame stands one voxel proud of the wall."""
    def put(al, ah, zl, zh, layer, mat):
        p = plane + (out if layer else 0)
        if axis == "y":
            v.box(al, p, zl, ah, p + 1, zh, mat)
        else:
            v.box(p, al, zl, p + 1, ah, zh, mat)

    put(a0, a0 + w, z0, z0 + h, 0, "window")
    put(a0 - 1, a0 + w + 1, z0 + h, z0 + h + 1, 1, frame)          # lintel
    put(a0 - 1, a0, z0, z0 + h, 1, frame)
    put(a0 + w, a0 + w + 1, z0, z0 + h, 1, frame)
    if sill:
        put(a0 - 2, a0 + w + 2, z0 - 1, z0, 1, frame)
    else:
        put(a0 - 1, a0 + w + 1, z0 - 1, z0, 1, frame)
    if mullion and w >= 5:
        m = a0 + w // 2
        put(m, m + 1, z0, z0 + h, 0, frame)
    if mullion and h >= 7:
        put(a0, a0 + w, z0 + h // 2, z0 + h // 2 + 1, 0, frame)


def door(v, axis, plane, a0, z0, w=8, h=16, out=-1, frame="beam", leaf="plank", arch=False):
    """A plank door on a wall face (same addressing as window). Iron bands and a ring handle."""
    def put(al, ah, zl, zh, layer, mat, color=None):
        p = plane + (out if layer else 0)
        if axis == "y":
            v.box(al, p, zl, ah, p + 1, zh, mat, color)
        else:
            v.box(p, al, zl, p + 1, ah, zh, mat, color)

    put(a0, a0 + w, z0, z0 + h, 0, leaf)
    put(a0 - 2, a0, z0, z0 + h + 2, 1, frame)
    put(a0 + w, a0 + w + 2, z0, z0 + h + 2, 1, frame)
    put(a0 - 2, a0 + w + 2, z0 + h, z0 + h + 2, 1, frame)
    for zz in (z0 + 3, z0 + h - 4):
        put(a0, a0 + w, zz, zz + 1, 0, "metal")
    put(a0 + w - 2, a0 + w - 1, z0 + h // 2 - 1, z0 + h // 2 + 1, 1, "gold")
    if arch:
        put(a0, a0 + 1, z0 + h - 1, z0 + h, 0, frame)
        put(a0 + w - 1, a0 + w, z0 + h - 1, z0 + h, 0, frame)


# ---------------------------------------------------------------------------------------------------- lanterns

def lantern(v, x, y, z, size=4, cap="beam"):
    """A glowing lantern box in a wooden cage, its bottom-centre at voxel (x, y, z) (size 4: x-2 .. x+2). The base and
    lid are flush with the cage, with a small knob on top, so it stays slim. Height size + 3."""
    h = size // 2
    v.box(x - h, y - h, z, x + h, y + h, z + 1, cap)                                  # base
    v.box(x - h, y - h, z + 1, x + h, y + h, z + 1 + size, "glow", "lantern")
    for dx in (x - h, x + h - 1):
        for dy in (y - h, y + h - 1):
            v.box(dx, dy, z + 1, dx + 1, dy + 1, z + 1 + size, cap)                    # corner bars
    v.box(x - h, y - h, z + 1 + size, x + h, y + h, z + 2 + size, cap)                # lid
    v.box(x - 1, y - 1, z + 2 + size, x + 1, y + 1, z + 3 + size, cap)
    return z + 3 + size


def lantern_post(height=10, post="stone", name="lantern_post"):
    """A free-standing lantern: a stone pillar (4 x 4 voxels, `height` tall) with a lantern on top. Origin: bottom centre."""
    v = Vox(10, 10, height + 9, VOX, origin=(5, 5, 0), name=name)
    v.box(2, 2, 0, 8, 8, 2, post)                           # plinth
    v.box(3, 3, 2, 7, 7, height, post)
    v.box(2, 2, height - 1, 8, 8, height, post)
    lantern(v, 5, 5, height, 4)
    return v


def wall_lantern(v, x, y, z, out=(0, -1)):
    """A small lantern hanging on a wall: bracket + 3-voxel glowing box. (x, y, z) is the wall voxel it hangs from; out is
    the outward direction in (x, y)."""
    ox, oy = out
    v.box(x + ox, y + oy, z, x + ox * 3 + (1 if ox == 0 else 0), y + oy * 3 + (1 if oy == 0 else 0), z + 1, "metal")
    cx, cy = x + ox * 2, y + oy * 2
    v.box(cx - 1, cy - 1, z - 4, cx + 2, cy + 2, z - 3, "beam")
    v.box(cx - 1, cy - 1, z - 3, cx + 2, cy + 2, z - 1, "glow", "lantern")
    v.box(cx - 1, cy - 1, z - 1, cx + 2, cy + 2, z, "beam")


# ---------------------------------------------------------------------------------------------------- banners

EMBLEMS = {
    "tree": [
        "...TTTT...",
        ".TTTTTTTT.",
        "TTTTTTTTTT",
        "TTT.TT.TTT",
        "TTTTTTTTTT",
        ".TT.TT.TT.",
        "..TTTTTT..",
        "....TT....",
        "....TT....",
        "....TT....",
        "...TTTT...",
        ".TTTTTTTT.",
    ],
    "swords": [
        "T........T",
        "TT......TT",
        ".TT....TT.",
        "..TT..TT..",
        "...TTTT...",
        "....TT....",
        "...TTTT...",
        ".TTT..TTT.",
        ".TT....TT.",
        "T.T....T.T",
    ],
    "arrows": [
        "TTT....TTT",
        "TT......TT",
        "T.T....T.T",
        "...T..T...",
        "....TT....",
        "....TT....",
        "...T..T...",
        "..T....T..",
        "TT......TT",
        "TT......TT",
    ],
    "star": [
        "....TT....",
        "....TT....",
        "TTTTTTTTTT",
        ".TTTTTTTT.",
        "..TTTTTT..",
        ".TTT..TTT.",
        ".TT....TT.",
    ],
}


def banner(emblem="tree", w=16, h=26, notch=5, rod=True, name="banner", field="banner", edge="gold"):
    """A hanging banner as a pixel-art slab (1 voxel = 6.25 cm, so the default is 1.0 m wide, 1.7 m tall, 6 cm thick):
    green field, gold border, gold emblem, swallow-tail foot, and a wooden rod across the top. It stands in the XZ plane
    facing -Y (and +Y); its origin is the middle of the TOP of the cloth, so place it where it hangs from."""
    rows = []
    pattern = EMBLEMS.get(emblem, [])
    ew = max((len(r) for r in pattern), default=0)
    ex0 = (w - ew) // 2
    ey0 = 4
    inside = np.zeros((h, w), bool)
    for j in range(h):
        for i in range(w):
            k = j - (h - notch)                              # rows into the notch
            cut = k >= 0 and abs(i - (w - 1) / 2.0) < (k + 1) * (w / 2.0 - 2) / notch
            inside[j, i] = not cut
    v = Vox(w + 2, 2, h + 2, V.TEXEL, origin=((w + 2) / 2.0, 1, h + 2), name=name)
    for j in range(h):
        for i in range(w):
            if not inside[j, i]:
                continue
            border = i == 0 or i == w - 1 or j == h - 1 or (j + 1 < h and not inside[j + 1, i]) \
                or (i > 0 and not inside[j, i - 1]) or (i + 1 < w and not inside[j, i + 1])
            col = edge if border else field
            pj, pi = j - ey0, i - ex0
            if not border and 0 <= pj < len(pattern) and 0 <= pi < len(pattern[pj]) and pattern[pj][pi] == "T":
                col = "gold_light" if (pj + pi) % 5 == 0 else "gold"
            elif not border and (i * 7 + j * 3) % 11 == 0:
                col = "banner_dark" if field == "banner" else field
            z = h - 1 - j
            v.box(i + 1, 0, z, i + 2, 1, z + 1, "paint", col)
    if rod:
        v.box(0, 0, h, w + 2, 2, h + 2, "beam")
        v.box(0, 0, h, 1, 2, h + 2, "gold")
        v.box(w + 1, 0, h, w + 2, 2, h + 2, "gold")
    v.hang()
    return v


def flag(emblem="star", w=20, h=12, name="flag", field="banner"):
    """A pennant flying to +X from a pole (pixel-art slab in the XZ plane, 6.25 cm voxels). Origin: bottom of the hoist."""
    v = Vox(w, 1, h, V.TEXEL, origin=(0, 0.5, 0), name=name)
    pattern = EMBLEMS.get(emblem, [])
    for i in range(w):
        for j in range(h):
            taper = (i / float(w)) * 1.5                      # the fly narrows a little
            notch = i >= w - 5 and abs(j - (h - 1) / 2.0) < (i - (w - 6)) * 0.9
            if j < taper or j > h - 1 - taper or notch:
                continue
            border = j - 1 < taper or j + 1 > h - 1 - taper or i == w - 1
            col = "gold" if border else field
            pi, pj = i - 3, (h - 1 - j) - (h - len(pattern)) // 2
            if not border and 0 <= pj < len(pattern) and 0 <= pi < len(pattern[pj]) and pattern[pj][pi] == "T":
                col = "gold"
            v.box(i, 0, j, i + 1, 1, j + 1, "paint", col)
    v.fly()
    return v


# ---------------------------------------------------------------------------------------------------- props

def barrel(name="barrel"):
    """A barrel, 6 voxels wide, 8 tall. Origin: bottom centre."""
    v = Vox(8, 8, 9, VOX, origin=(4, 4, 0), name=name)
    v.cylinder(4, 4, 0, 8, 3.1, "plank")
    v.cylinder(4, 4, 1, 7, 3.6, "plank")
    for z in (1, 6):
        ring = Vox(8, 8, 9, VOX)
        ring.cylinder(4, 4, z, z + 1, 3.9, "metal")
        v.stamp(ring, 0, 0, 0)
    v.cylinder(4, 4, 7, 8, 2.6, "beam")
    return v


def crate(size=6, name="crate"):
    """A wooden crate with a darker frame. Origin: bottom centre."""
    v = Vox(size, size, size, VOX, origin=(size / 2.0, size / 2.0, 0), name=name)
    v.box(0, 0, 0, size, size, size, "plank")
    v.frame(0, 0, 0, size, size, size, "beam")
    return v


def stairs(v, x0, y0, z0, w, steps, direction="-y", run=2, rise=2, mat="stone"):
    """Solid steps `w` wide. direction: the side you walk up FROM ('-y': the low step is at y0 and it climbs towards +y;
    '+y': climbs towards -y; '-x' / '+x' likewise). (x0, y0) is the low corner of the footprint, which is
    w x steps*run (or steps*run x w for the x directions). Returns the height reached."""
    for i in range(steps):
        h = (i + 1) * rise
        if direction == "-y":
            v.box(x0, y0 + i * run, z0, x0 + w, y0 + steps * run, z0 + h, mat)
        elif direction == "+y":
            v.box(x0, y0, z0, x0 + w, y0 + (steps - i) * run, z0 + h, mat)
        elif direction == "-x":
            v.box(x0 + i * run, y0, z0, x0 + steps * run, y0 + w, z0 + h, mat)
        else:
            v.box(x0, y0, z0, x0 + (steps - i) * run, y0 + w, z0 + h, mat)
    return z0 + steps * rise


def timber_wall(v, axis, plane, a0, a1, z0, z1, infill="plaster", post="post", beam="beam", spacing=12, t=2, braces=False):
    """Half-timber dressing on an existing wall face: fills the face layer with infill, then posts every `spacing`
    voxels and beams along the bottom and top (t voxels thick). axis/plane as in window(); the layer written is `plane`."""
    def put(al, ah, zl, zh, mat):
        if axis == "y":
            v.box(al, plane, zl, ah, plane + 1, zh, mat)
        else:
            v.box(plane, al, zl, plane + 1, ah, zh, mat)

    put(a0, a1, z0, z1, infill)
    n = max(1, int(round((a1 - a0 - t) / float(spacing))))
    for i in range(n + 1):
        a = int(round(a0 + i * (a1 - a0 - t) / float(n)))
        put(a, a + t, z0, z1, post)
    put(a0, a1, z0, z0 + t, beam)
    put(a0, a1, z1 - t, z1, beam)
    if braces:
        for i in range(n):
            a = int(round(a0 + i * (a1 - a0 - t) / float(n))) + t
            for k in range(min(4, (z1 - z0) // 2)):
                put(a + k, a + k + 1, z1 - t - 1 - k, z1 - t - k, beam)
