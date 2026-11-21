#!/usr/bin/env python3
"""Draws the building texture set (castle, farm, mine) into SourceArt/Textures as T_Bld_*.png.

Run with the tools venv:   Tools/.venv/bin/python Tools/textures/gen_building_textures.py

Same rules as gen_world_textures.py, whose canvas, helpers and palettes it reuses: every texture is drawn
deliberately from a small fixed palette, noise only chooses between authored options, and the density is
4 cm per texel. `*_N.png` are tangent-space normal maps from the height the drawing code lays down.

Alpha is a MASK, not opacity, on the opaque textures (M_Building): 255 = plain, 153 = the texel takes the
team colour (frieze) or glints (gold ore). On the card textures (M_BuildingCard: wheat, banner, awning,
leaves, flame) alpha 0 is a hole, 153 is opaque and team-coloured, 255 is opaque and plain.
A contact sheet per texture is written to Saved/TexturePreview/.
"""
import math
import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gen_world_textures import (BARK, EARTH, GRASS_MOSS, SAND, WOOD, Tile, mix, partition, rgb,  # noqa: E402
                                stone_block, value_noise)

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(ROOT, "SourceArt", "Textures")
PREVIEW = os.path.join(ROOT, "Saved", "TexturePreview")
TEAM = 153                    # alpha of a team-coloured / glinting texel


def pal(*hexes):
    return [rgb(h) for h in hexes]


# ---------------------------------------------------------------------------------------- palettes
# All sit inside the world's sandstone / earth / wood ranges (gen_world_textures.py), a step warmer or paler.
ROSE = pal("#5e4532", "#86654a", "#a98560", "#c2a078", "#d6b98f", "#e4cda6")       # rosier sandstone, a few blocks
PALE = pal("#6a5a42", "#93825f", "#b5a57c", "#cfc096", "#e0d4ae", "#ece3c4")       # sun-bleached sandstone, dressed trim
MUD = pal("#3f3122", "#5c4730", "#786042", "#927853", "#a98f66", "#bfa67c")        # mudbrick
PLASTER = pal("#7d6c50", "#a39171", "#c0b08c", "#d3c5a2", "#e1d6b8", "#ece4cc")    # mud-lime plaster
CLAY = pal("#6c5a40", "#8a7654", "#a38f68", "#b8a57d", "#c9b891", "#d8c9a4")       # packed-clay roof
THATCH = pal("#3e3219", "#5c4b24", "#7d6830", "#9c853f", "#b9a253", "#d2bd6e")     # reed thatch, hay
WHEAT = pal("#5f4c1c", "#8a6f24", "#b59230", "#d6b444", "#ecd067", "#f8e596")      # ripe barley
SOIL = pal("#231a13", "#33271b", "#463625", "#5a4631", "#705a40")                  # tilled earth
BRONZE = pal("#33230f", "#5c3e1a", "#876026", "#b08336", "#d3a84e", "#efd27e")
GOLD = pal("#7a5612", "#b5841c", "#e2b634", "#fbe06c", "#fff6b8")
ORE = pal("#1f1c19", "#2f2b26", "#433d35", "#585147", "#6f675b")                   # dark host rock
TERRA = pal("#4f2c1c", "#74432a", "#96593a", "#b3744c", "#cb9166", "#dfb088")      # terracotta
OLIVE = pal("#232c1c", "#354229", "#4b5b38", "#64774a", "#82935f", "#a7b384")      # olive leaves, silvery tips
GREY = pal("#6b6b6b", "#838383", "#9c9c9c", "#b4b4b4", "#cacaca")                  # team cloth / glaze: tinted by TeamColor
CREAM = pal("#8f7f5e", "#b7a680", "#d6c8a2", "#e9dfc0")
FLAME = pal("#8a2a0c", "#d2561a", "#f39a2c", "#ffd45a", "#fff4b8")
DARK = pal("#0f0c09", "#17120d", "#211a12")


def put_a(t, x, y, col, a=255, wrap_y=False):
    """Tile.put with an explicit alpha."""
    x %= t.w
    if wrap_y:
        y %= t.h
    elif y < 0 or y >= t.h:
        return
    t.c[y, x] = col
    t.a[y, x] = a


def stain(t, rng, n, tone, lo=5, hi=16, amt=0.4):
    """Rain stains running down the face."""
    for _ in range(n):
        x, y = int(rng.integers(t.w)), int(rng.integers(t.h))
        for d in range(int(rng.integers(lo, hi))):
            c = t.get(x, y + d)
            t.put(x, y + d, mix(c, tone, amt * (1.0 - d / hi * 0.6)), t.hgt[(y + d) % t.h, x % t.w])
            if rng.random() < 0.25:
                x += int(rng.choice([-1, 1]))


# ---------------------------------------------------------------------------------------- fine grain (detail pass)
# The second, smaller scale of every surface: mineral speckle, pits, hairline cracks, grit in the joints, drips,
# moss and lichen flecks, grain and splits. Rules: a texel only ever moves along its OWN palette ramp (`nudge`) or
# takes one of a few fixed grime tones, so the result is still whole palette texels; most moves are a single
# tone, so the courses / blocks / boards stay the read from the far camera; every pass draws from its own seeded
# rng (the big shapes are laid exactly as before); colours are written straight into Tile.c, so the alpha masks
# (team, glint, holes) are never touched; height moves with the colour so the normal maps follow.
LICHEN = rgb("#a7a37a")                                   # dry grey-green lichen, mixed into the stone it sits on
VERDIGRIS = rgb("#5f7f66")


def _key(c):
    return tuple(int(v) for v in c)


def ramp_look(*ramps, skip=()):
    """colour -> (ramp, index) for every tone of the given palettes; `skip` tones (joints) are left out."""
    out = {}
    banned = {_key(c) for c in skip}
    for ramp in ramps:
        for i, c in enumerate(ramp):
            if _key(c) not in banned:
                out.setdefault(_key(c), (ramp, i))
    return out


def nudge(t, look, x, y, d, dh=0.0, lo=0, hi=99, mask=None):
    """Moves one texel `d` tones along its own ramp, clamped to lo..hi. False if the texel is not a plain tone of
    those ramps (a joint, a mask, another material, a stain) or is masked out: it is then left alone."""
    x %= t.w; y %= t.h
    if mask is not None and not mask[y, x]:
        return False
    hit = look.get(tuple(t.c[y, x].tolist()))
    if hit is None:
        return False
    ramp, i = hit
    j = min(max(i + d, min(lo, i)), max(min(hi, len(ramp) - 1), i))
    if j != i:
        t.c[y, x] = ramp[j]
        t.hgt[y, x] += dh
    return True


def paint(t, x, y, col, dh=0.0, mask=None, look=None):
    """One texel of a fixed grime tone (moss, lichen, rust); only over plain ramp texels when `look` is given."""
    x %= t.w; y %= t.h
    if mask is not None and not mask[y, x]:
        return False
    if look is not None and tuple(t.c[y, x].tolist()) not in look:
        return False
    t.c[y, x] = col
    t.hgt[y, x] += dh
    return True


def speckle(t, rng, look, p, dark=0.62, dh=0.07, lo=0, hi=99, mask=None, step=1):
    """Mineral grain: scattered single texels one tone darker (sunk a little) or lighter. `p` may be a map."""
    r = rng.random((t.h, t.w))
    side = rng.random((t.h, t.w))
    for y, x in np.argwhere(r < p):
        if side[y, x] < dark:
            nudge(t, look, x, y, -step, -dh, lo, hi, mask)
        else:
            nudge(t, look, x, y, step, dh * 0.6, lo, hi, mask)


def pits(t, rng, look, n, lo=0, mask=None, depth=2):
    """Small pits: a dark texel with a lit lower lip."""
    for _ in range(n):
        x, y = int(rng.integers(t.w)), int(rng.integers(t.h))
        if nudge(t, look, x, y, 0, mask=mask) and nudge(t, look, x, y + 1, 0, mask=mask):
            nudge(t, look, x, y, -depth, -0.35, lo)
            nudge(t, look, x, y + 1, 1, 0.0, lo)


def hairlines(t, rng, look, n, lmin, lmax, d=-1, dh=-0.25, lo=0, hi=99, mask=None, vertical=True, wander=0.5, starts=None):
    """Hairline cracks / scratches: thin wandering runs that stop at the first texel that is not this material
    (or, begun from given `starts` (rows, cols), pass over it)."""
    for _ in range(n):
        if starts is not None and len(starts):
            y, x = (int(v) for v in starts[int(rng.integers(len(starts)))])
        else:
            x, y = int(rng.integers(t.w)), int(rng.integers(t.h))
        side = int(rng.choice([-1, 1]))
        for _ in range(int(rng.integers(lmin, lmax + 1))):
            if not nudge(t, look, x, y, d, dh, lo, hi, mask) and starts is None:
                break
            if vertical:
                y += 1
                if rng.random() < wander:
                    x += side if rng.random() < 0.8 else -side
            else:
                x += 1
                if rng.random() < wander:
                    y += side if rng.random() < 0.8 else -side


def dashes(t, rng, look, n, lmin, lmax, vertical=False, dark=0.6, d=1, lo=0, hi=99, mask=None):
    """Grain: short straight runs along the fibre, a tone darker or lighter."""
    for _ in range(n):
        x, y = int(rng.integers(t.w)), int(rng.integers(t.h))
        s = -d if rng.random() < dark else d
        for i in range(int(rng.integers(lmin, lmax + 1))):
            if not nudge(t, look, x + (0 if vertical else i), y + (i if vertical else 0), s, 0.0, lo, hi, mask):
                break


def drips(t, rng, look, starts, n, lmin, lmax, d=-1, lo=0, mask=None, through=False):
    """Dirt washed down a face: short streaks hanging from the given start texels (rows, cols)."""
    if not len(starts):
        return
    for k in rng.choice(len(starts), size=min(n, len(starts)), replace=False):
        y, x = int(starts[k][0]), int(starts[k][1])
        for i in range(int(rng.integers(lmin, lmax + 1))):
            if not nudge(t, look, x, y + i, d, 0.0, lo, 99, mask) and not through:
                break
            if rng.random() < 0.12:
                x += int(rng.choice([-1, 1]))


def flecks(t, rng, n, cols, look=None, mask=None, lmax=3, dh=0.0, where=None):
    """Moss / lichen / rust: tiny runs of 1..lmax texels of a fixed tone, optionally begun only where `where`."""
    spots = np.argwhere(where) if where is not None else None
    if spots is not None and not len(spots):
        return
    for _ in range(n):
        if spots is not None:
            y, x = (int(v) for v in spots[int(rng.integers(len(spots)))])
        else:
            x, y = int(rng.integers(t.w)), int(rng.integers(t.h))
        col = cols[int(rng.integers(len(cols)))]
        for i in range(int(rng.integers(1, lmax + 1))):
            paint(t, x + i, y + (1 if i == 2 and rng.random() < 0.5 else 0), col, dh, mask, look)


def stone_detail(t, seed, ramps, gap, speck=0.07, pit=110, cracks=24, crack_len=(3, 8), drip=40, grit=0.2, crumb=0.06,
                 moss=0.66, lichen=10, soot=0):
    """The fine grain of a laid wall, inside the blocks `ashlar` set: speckle and pits in the faces, hairline cracks,
    dirt hanging from the bed joints, grit and crumbled mortar in the joints, moss where the joints stay damp, a few
    lichen blotches, soot streaks. `gap` is the joint colour: joints only ever take the joint tones below."""
    rng = np.random.default_rng(seed)
    W, H = t.w, t.h
    look = ramp_look(*ramps, skip=[gap])
    lo = 1 if any(_key(r[0]) == _key(gap) for r in ramps) else 0
    joint = np.all(t.c == gap, axis=-1)
    clump = value_noise(rng, W, H, 16)
    speckle(t, rng, look, speck * (0.25 + 1.5 * clump), lo=lo)
    pits(t, rng, look, W * H // pit, lo=lo)
    hairlines(t, rng, look, cracks, crack_len[0], crack_len[1], lo=lo)
    under = np.argwhere(joint & ~np.roll(joint, -1, 0))             # a joint with stone under it
    drips(t, rng, look, under + [1, 0], drip, 2, 6, lo=lo, through=True)
    body = ramps[0]
    dirt = mix(gap, DARK[1], 0.5); crumbs = mix(gap, body[2], 0.5)
    mossj = (mix(gap, GRASS_MOSS[2], 0.6), mix(gap, GRASS_MOSS[3], 0.6)); mossf = mix(body[2], GRASS_MOSS[3], 0.55)
    damp = value_noise(rng, W, H, 32) * 0.6 + value_noise(rng, W, H, 8) * 0.4
    r = rng.random((H, W)); r2 = rng.random((H, W))
    for y, x in np.argwhere(joint):
        if damp[y, x] > moss and r2[y, x] < 0.6:
            t.c[y, x] = mossj[int(r[y, x] < 0.5)]
            if r[y, x] < 0.22:                                      # the moss spills onto the ledge below
                paint(t, x, y + 1, mossf, look=look)
        elif r[y, x] < grit:
            t.c[y, x] = dirt
        elif r[y, x] < grit + crumb:
            t.c[y, x] = crumbs
    pale = [mix(body[3], LICHEN, 0.45), mix(body[2], LICHEN, 0.45)]
    for _ in range(lichen):                                         # lichen: a blotch of three or four texels
        x, y = int(rng.integers(W)), int(rng.integers(H))
        for dx, dy in ((0, 0), (1, 0), (0, 1), (1, 1), (2, 1)):
            if rng.random() < 0.7:
                paint(t, x + dx, y + dy, pale[int(rng.integers(2))], look=look)
    if soot:
        stain(t, rng, soot, DARK[1], lo=8, hi=26, amt=0.22)


# ---------------------------------------------------------------------------------------- masonry
def ashlar(seed, courses, wmin, wmax, sets, probs, chip=0.4, missing=1, stains=12, holes=0, detail=None):
    """Coursed sandstone. `courses` are the course heights (texels), summing to the tile height; block widths vary
    within a course and no joint lines up with the one below. `missing` blocks leave shadowed sockets (0 in the
    shipped tiles: a socket in a tiling texture repeats every 5 m, so the buildings cut theirs as real recesses).
    `detail`: keyword arguments for `stone_detail` (the fine grain inside the blocks), None for bare blocks."""
    rng = np.random.default_rng(seed)
    W, H = 128, int(sum(courses))
    gap = SAND[0]
    t = Tile(W, H, gap)
    y = 0
    last_off = None
    gone = set(int(v) for v in rng.choice(len(courses), size=missing, replace=False)) if missing else set()
    for r, ch in enumerate(courses):
        off = int(rng.integers(0, 16))
        while last_off is not None and not (4 <= abs(off - last_off) <= 12):
            off = int(rng.integers(0, 16))
        last_off = off
        x = off
        widths = partition(rng, W, wmin, wmax)
        hole_at = int(rng.integers(len(widths))) if r in gone else -1
        for k, bw in enumerate(widths):
            tones = sets[int(rng.choice(len(sets), p=probs))]
            if k == hole_at and bw >= 10:
                # the socket of a lost block: dark, with rubble and a lit lower lip
                for j in range(ch - 1):
                    for i in range(bw - 1):
                        c = DARK[2] if j < ch - 3 else mix(DARK[2], SAND[1], 0.5)
                        t.put(x + i, y + j, c, 0.15)
                for i in range(1, bw - 2):
                    if rng.random() < 0.6:
                        t.put(x + i, y + ch - 2, SAND[2] if rng.random() < 0.5 else SAND[1], 0.4)
                for j in range(ch - 1):
                    t.put(x, y + j, DARK[0], 0.1)
                for i in range(bw - 1):
                    t.put(x + i, y, DARK[0], 0.1)
            else:
                stone_block(t, rng, x, y, bw, ch, tones, gap, base_h=1.0 + rng.uniform(-0.08, 0.1), chip=chip, tilt=False)
            x += bw
        y += ch
    if detail is not None:
        stone_detail(t, seed + 7000, (SAND, ROSE, PALE), gap, **detail)
    stain(t, rng, stains, SAND[1])
    for _ in range(holes):                                 # putlog holes / weep holes: small dark squares
        x, y = int(rng.integers(W)), int(rng.integers(H))
        t.rect(x, y, 2, 2, DARK[1], 0.2)
        t.put(x, y + 2, SAND[5]); t.put(x + 1, y + 2, SAND[5])
    return t


def trim(seed):
    """Dressed coping / string course, 64 x 16: long pale slabs, a lit arris, a cut groove, a shadowed drip edge.
    v = 0 is the top edge of the band (the kit aligns it)."""
    rng = np.random.default_rng(seed)
    W, H = 64, 16
    t = Tile(W, H, PALE[3])
    for x in range(W):
        for y in range(H):
            if y == 0:
                c, h = PALE[5], 0.8
            elif y == 1:
                c, h = PALE[4], 1.0
            elif y in (9, 10):
                c, h = (PALE[1], 0.35) if y == 9 else (PALE[4], 0.9)        # groove and its lit lower lip
            elif y >= H - 2:
                c, h = (PALE[2], 0.8) if y == H - 2 else (PALE[0], 0.2)
            else:
                c, h = PALE[3], 1.0
            t.put(x, y, c, h)
    for x0 in (int(rng.integers(8, 24)), int(rng.integers(40, 56))):      # slab ends
        for y in range(H - 1):
            t.put(x0, y, PALE[1], 0.3)
            t.put(x0 + 1, y, PALE[4] if y not in (9,) else PALE[1], 0.9)
    for _ in range(26):                                                   # tooling dabs
        x, y = int(rng.integers(W)), int(rng.choice([3, 4, 5, 6, 7, 12]))
        for d in range(int(rng.integers(2, 6))):
            t.put(x + d, y, PALE[2] if rng.random() < 0.6 else PALE[4], 1.0)
    for _ in range(3):                                                    # chips out of the top arris
        x = int(rng.integers(W))
        t.put(x, 0, PALE[2], 0.4); t.put(x + 1, 0, PALE[2], 0.4); t.put(x, 1, PALE[2], 0.6)
    # fine grain: speckle and pits in the dressed faces, grime packed in the groove and hanging under it, lichen
    g = np.random.default_rng(seed + 7000)
    look = ramp_look(PALE)
    face = np.zeros((H, W), bool)
    face[2:9] = True; face[11:14] = True
    speckle(t, g, look, 0.09, lo=2, hi=4, mask=face)
    pits(t, g, look, 7, lo=1, mask=face)
    hairlines(t, g, look, 3, 3, 6, lo=1, mask=face)
    for x in range(W):
        if g.random() < 0.3:
            t.c[9, x] = PALE[0]
        if g.random() < 0.22:
            for d in range(int(g.integers(1, 4))):
                nudge(t, look, x, 11 + d, -1, 0.0, 2, mask=face)
    flecks(t, g, 4, [mix(PALE[3], LICHEN, 0.5), mix(PALE[2], LICHEN, 0.5)], look=look, mask=face, lmax=2)
    return t


def mudbrick(seed):
    """Sun-dried brick, 8 x 4 texel bricks in running bond; straw flecks, a few eroded bricks."""
    rng = np.random.default_rng(seed)
    W = H = 128
    gap = MUD[0]
    t = Tile(W, H, gap)
    damp = value_noise(rng, W, H, 32)
    for r in range(H // 4):
        y = r * 4
        x = (0 if r % 2 == 0 else 4) + int(rng.integers(0, 2))
        for bw in partition(rng, W, 7, 10):
            k = 2 + (1 if rng.random() < 0.3 else 0) - (1 if damp[y, x % W] < 0.35 else 0)
            k = int(np.clip(k + int(rng.choice([-1, 0, 0, 0, 1])), 1, 4))
            eroded = rng.random() < 0.07
            for j in range(3):
                for i in range(bw - 1):
                    c = MUD[k]
                    if j == 0:
                        c = MUD[min(k + 1, 5)]
                    if j == 2 or i == bw - 2:
                        c = MUD[max(k - 1, 0)]
                    if eroded and (j == 2 or (i in (0, bw - 2))):
                        c = gap
                    t.put(x + i, y + j, c, 0.0 if c is gap else 1.0 - (0.3 if j != 1 else 0.0))
            if rng.random() < 0.35:                         # chopped straw in the mud
                t.put(x + int(rng.integers(1, max(bw - 2, 2))), y + 1, PLASTER[2], 1.0)
            x += bw
    # fine grain: pitted, crumbling brick faces, more chopped straw, washed-out and dirt-packed joints
    g = np.random.default_rng(seed + 7000)
    look = ramp_look(MUD, skip=[gap])
    for _ in range(56):                                     # straws lying in the face of a brick
        x, y = int(g.integers(W)), int(g.integers(H // 4)) * 4 + 1
        col = PLASTER[2] if g.random() < 0.6 else THATCH[3]
        for d in range(int(g.integers(1, 3))):
            paint(t, x + d, y, col, look=look)
    stone_detail(t, seed + 7001, (MUD,), gap, speck=0.05, pit=130, cracks=0, drip=44, grit=0.16,
                 crumb=0.07, moss=0.79, lichen=4)
    stain(t, rng, 10, MUD[1], amt=0.35)
    return t


def plaster(seed, brick):
    """Mud-lime render over brick: trowel strokes, hairline cracks, and patches fallen away to the brick."""
    rng = np.random.default_rng(seed)
    W = H = 128
    t = Tile(W, H, PLASTER[3])
    t.hgt[:] = 1.0
    n = value_noise(rng, W, H, 32)
    t.c[n < 0.38] = PLASTER[2]
    t.c[n > 0.74] = PLASTER[4]
    for gy in range(H // 4):                                 # trowel strokes
        for gx in range(W // 10):
            if rng.random() < 0.45:
                continue
            x = gx * 10 + int(rng.integers(0, 10)) + (5 if gy % 2 else 0)
            y = gy * 4 + int(rng.integers(0, 4))
            L = int(rng.integers(3, 9))
            for d in range(L):
                t.put(x + d, y, PLASTER[4] if rng.random() < 0.8 else PLASTER[5], 1.05)
                t.put(x + d, y + 1, PLASTER[2], 0.95)
    for _ in range(7):                                       # cracks
        x, y = int(rng.integers(W)), int(rng.integers(H))
        for d in range(int(rng.integers(10, 34))):
            t.put(x, y, PLASTER[0], 0.4)
            t.put(x + 1, y, PLASTER[5], 1.0)
            y += 1
            if rng.random() < 0.45:
                x += int(rng.choice([-1, 1]))
    blob = value_noise(rng, W, H, 32) * 0.7 + value_noise(rng, W, H, 8) * 0.3
    hole = blob > 0.81                                       # where the render has fallen off
    for y in range(H):
        for x in range(W):
            if hole[y, x]:
                t.put(x, y, brick.get(x, y), 0.45 * brick.hgt[y % brick.h, x % brick.w])
    for y in range(H):
        for x in range(W):
            if hole[y, x]:
                continue
            if hole[(y - 1) % H, x]:                         # lit lip under a patch
                t.put(x, y, PLASTER[5], 1.0)
            elif hole[(y + 1) % H, x]:                       # the render's thickness, in shadow above the brick
                t.put(x, y, PLASTER[1], 0.8)
            elif hole[y, (x + 1) % W] or hole[y, (x - 1) % W]:
                t.put(x, y, PLASTER[2], 0.9)
    # fine grain: sand in the render, pits, a craze of hairline cracks, dirt hanging under every fallen patch, lichen
    g = np.random.default_rng(seed + 7000)
    look = ramp_look(PLASTER)
    sound = ~hole
    speckle(t, g, look, 0.075 * (0.4 + 1.2 * value_noise(g, W, H, 16)), dh=0.04, lo=2, hi=4, mask=sound)
    pits(t, g, look, 120, lo=1, mask=sound)
    hairlines(t, g, look, 26, 4, 11, d=-2, lo=1, hi=4, mask=sound)
    rim = np.argwhere(sound & np.roll(hole, 1, 0))
    drips(t, g, look, rim, 46, 3, 10, lo=2, mask=sound)
    flecks(t, g, 9, [mix(PLASTER[3], LICHEN, 0.5), mix(PLASTER[2], LICHEN, 0.5)], look=look, mask=sound)
    stain(t, g, 9, mix(PLASTER[0], DARK[2], 0.5), lo=10, hi=30, amt=0.26)        # soot
    stain(t, rng, 14, PLASTER[1], lo=8, hi=26, amt=0.45)
    return t


def roof_clay(seed):
    """Flat roof of rolled clay: pale, crazed with fine cracks, a few pebbles and swept streaks."""
    rng = np.random.default_rng(seed)
    W = H = 128
    t = Tile(W, H, CLAY[3])
    t.hgt[:] = 1.0
    n = value_noise(rng, W, H, 32)
    t.c[n < 0.4] = CLAY[2]
    t.c[n > 0.72] = CLAY[4]
    pts = rng.random((22, 2)) * [W, H]
    ys, xs = np.mgrid[0:H, 0:W]
    best = np.full((H, W), 1e9); second = np.full((H, W), 1e9)
    for px_, py_ in pts:
        dx = np.abs(xs - px_); dx = np.minimum(dx, W - dx)
        dy = np.abs(ys - py_); dy = np.minimum(dy, H - dy)
        d = np.hypot(dx, dy)
        closer = d < best
        second = np.where(closer, best, np.minimum(second, d))
        best = np.where(closer, d, best)
    edge = (second - best) < 0.9
    for y in range(H):
        for x in range(W):
            if edge[y, x] and rng.random() < 0.8:
                t.put(x, y, CLAY[1] if rng.random() < 0.7 else CLAY[0], 0.4)
            elif edge[(y - 1) % H, x] and rng.random() < 0.5:
                t.put(x, y, CLAY[5], 1.0)
    for gy in range(H // 5):                                 # swept streaks
        for gx in range(W // 12):
            if rng.random() < 0.5:
                continue
            x = gx * 12 + int(rng.integers(0, 12)); y = gy * 5 + int(rng.integers(0, 5))
            for d in range(int(rng.integers(3, 8))):
                t.put(x + d, y, CLAY[4] if rng.random() < 0.7 else CLAY[2], 1.0)
    for _ in range(18):                                      # pebbles
        x, y = int(rng.integers(W)), int(rng.integers(H))
        t.put(x, y, CLAY[5], 1.2); t.put(x + 1, y, CLAY[4], 1.2); t.put(x, y + 1, CLAY[1], 0.8); t.put(x + 1, y + 1, CLAY[0], 0.7)
    # fine grain: grit trodden into the clay, pits, small cracks branching off the big ones, dry lichen
    g = np.random.default_rng(seed + 7000)
    look = ramp_look(CLAY)
    speckle(t, g, look, 0.06 * (0.4 + 1.2 * value_noise(g, W, H, 16)), dh=0.05, lo=2, hi=4)
    for _ in range(50):                                      # grit: one pale grain over its own shadow
        x, y = int(g.integers(W)), int(g.integers(H))
        if nudge(t, look, x, y, 2, 0.2, 2, 5):
            nudge(t, look, x, y + 1, -1, -0.1, 1)
    pits(t, g, look, 70, lo=1)
    hairlines(t, g, look, 34, 3, 8, d=-2, dh=-0.4, lo=1, starts=np.argwhere(edge), vertical=False)
    hairlines(t, g, look, 22, 3, 7, d=-2, dh=-0.4, lo=1, starts=np.argwhere(edge))
    flecks(t, g, 8, [mix(CLAY[3], LICHEN, 0.5), mix(CLAY[2], LICHEN, 0.5)], look=look)
    return t


# ---------------------------------------------------------------------------------------- timber
def beam(seed):
    """One squared timber, grain along u, 64 x 16 (v wraps every 64 cm): no board edges, adze marks, checks."""
    rng = np.random.default_rng(seed)
    W, H = 64, 16
    t = Tile(W, H, WOOD[2])
    for y in range(H):
        tone = 2 if y % 5 else 1
        for x in range(W):
            t.put(x, y, WOOD[tone])
    for _ in range(26):                                      # long grain streaks
        x, y = int(rng.integers(W)), int(rng.integers(H))
        col = WOOD[int(rng.choice([1, 1, 3, 3, 4], p=[0.3, 0.2, 0.3, 0.1, 0.1]))]
        for d in range(int(rng.integers(6, 26))):
            t.put(x + d, y, col)
            if rng.random() < 0.08:
                y += int(rng.choice([-1, 1]))
    for _ in range(3):                                       # knots
        x, y = int(rng.integers(W)), int(rng.integers(2, H - 3))
        for dx, dy, c in ((0, 0, 0), (1, 0, 0), (-1, 0, 1), (2, 0, 1), (0, -1, 1), (1, -1, 1), (0, 1, 3), (1, 1, 3)):
            t.put(x + dx, y + dy, WOOD[c])
    for _ in range(5):                                       # drying checks
        x, y = int(rng.integers(W)), int(rng.integers(H))
        for d in range(int(rng.integers(4, 12))):
            t.put(x + d, y, WOOD[0])
            t.put(x + d, y + 1, WOOD[3])
    # fine grain: short fibres, pores, two long splits, worm holes
    g = np.random.default_rng(seed + 7000)
    look = ramp_look(WOOD)
    dashes(t, g, look, 46, 2, 5)
    speckle(t, g, look, 0.05, dark=0.8)
    dashes(t, g, look, 3, 8, 18, dark=1.0, d=2)
    for _ in range(5):
        x, y = int(g.integers(W)), int(g.integers(H))
        t.put(x, y, DARK[2]); nudge(t, look, x, y + 1, 1)
    return t


def planks(seed):
    """Boards along u, 8 texels wide, 64 x 64: nail heads at the board ends, gaps, one split board."""
    rng = np.random.default_rng(seed)
    W = H = 64
    t = Tile(W, H, WOOD[2])
    ends = []
    for b in range(H // 8):
        py = b * 8
        tone = int(rng.choice([1, 2, 2, 3]))
        for y in range(py, py + 8):
            for x in range(W):
                c = WOOD[tone]
                if y == py:
                    c = WOOD[min(tone + 1, 4)]
                if y == py + 7:
                    c = WOOD[0]
                t.put(x, y, c)
        for _ in range(6):
            x, y = int(rng.integers(W)), py + int(rng.integers(1, 7))
            for d in range(int(rng.integers(5, 18))):
                t.put(x + d, y, WOOD[max(tone - 1, 0)] if rng.random() < 0.6 else WOOD[min(tone + 1, 4)])
        x = int(rng.integers(W))                             # board end with two nails
        for y in range(py, py + 8):
            t.put(x, y, WOOD[0])
        for dy in (2, 5):
            t.put(x + 2, py + dy, BRONZE[1]); t.put(x - 2, py + dy, BRONZE[1])
            t.put(x + 2, py + dy - 1, BRONZE[4])
        ends.append((x, py))
    # fine grain: fibres and pores in each board, splits, small knots, damp-darkened board ends, a stain weeping
    # from every nail, dirt packed in the gaps
    g = np.random.default_rng(seed + 7000)
    look = ramp_look(WOOD)
    inner = np.zeros((H, W), bool)
    for y in range(H):
        inner[y] = 1 <= y % 8 <= 6
    for x, py in ends:
        for y in range(py + 1, py + 7):
            for dx in (-3, -2, -1, 1, 2, 3):
                if g.random() < 0.6 - 0.12 * abs(dx):
                    nudge(t, look, x + dx, y, -1, mask=inner)
        for dy in (2, 5):
            for sx in (-2, 2):
                for d in range(1, int(g.integers(2, 4))):
                    nudge(t, look, x + sx, py + dy + d, -1, mask=inner)
    dashes(t, g, look, 90, 2, 6, mask=inner)
    speckle(t, g, look, 0.045, dark=0.8, mask=inner)
    dashes(t, g, look, 5, 8, 16, dark=1.0, d=2, mask=inner)
    for _ in range(4):                                       # knots
        x, y = int(g.integers(W)), int(g.integers(H // 8)) * 8 + int(g.integers(2, 6))
        if nudge(t, look, x, y, -3, mask=inner):
            nudge(t, look, x - 1, y, -1, mask=inner); nudge(t, look, x + 1, y, -1, mask=inner)
            nudge(t, look, x, y + 1, 1, mask=inner); nudge(t, look, x, y - 1, -1, mask=inner)
    for y in range(7, H, 8):
        for x in range(W):
            if g.random() < 0.3:
                t.put(x, y, DARK[2])
    return t


def door(seed):
    """Double-leaf gate, 64 x 64 (256 x 256 cm): upright boards, three bronze straps with studs, ring pulls."""
    rng = np.random.default_rng(seed)
    W = H = 64
    t = Tile(W, H, WOOD[1])
    for x in range(W):
        board = x // 8
        tone = [1, 2, 1, 2, 2, 1, 2, 1][board]
        for y in range(H):
            c = WOOD[tone]
            if x % 8 == 0:
                c = WOOD[min(tone + 1, 4)]
            if x % 8 == 7:
                c = WOOD[0]
            t.put(x, y, c)
    for _ in range(60):                                      # upright grain
        x, y = int(rng.integers(W)), int(rng.integers(H))
        if x % 8 in (0, 7):
            continue
        tone = [1, 2, 1, 2, 2, 1, 2, 1][x // 8]
        for d in range(int(rng.integers(4, 16))):
            t.put(x, y + d, WOOD[max(tone - 1, 0)] if rng.random() < 0.65 else WOOD[tone + 1])
    for y in range(H):                                       # the meeting stiles and the dark seam between the leaves
        t.put(31, y, DARK[1]); t.put(32, y, DARK[2])
        t.put(30, y, WOOD[3]); t.put(33, y, WOOD[1])
    for y0 in (5, 28, 51):                                   # bronze straps
        for x in range(W):
            if x in (31, 32):
                continue
            for j, c in enumerate((BRONZE[4], BRONZE[3], BRONZE[3], BRONZE[2], BRONZE[1])):
                t.put(x, y0 + j, c)
            t.put(x, y0 + 5, DARK[2])                        # the strap's shadow on the boards
        for x in range(3, W, 8):                             # studs
            if x in (27, 35):
                pass
            t.put(x, y0 + 1, BRONZE[5]); t.put(x + 1, y0 + 1, BRONZE[4])
            t.put(x, y0 + 2, BRONZE[4]); t.put(x + 1, y0 + 2, BRONZE[1])
    for cx in (25, 36):                                      # ring pulls
        ring = ["..33..", ".4..2.", "4....1", "3....1", ".2..1.", "..11.."]
        for j, row in enumerate(ring):
            for i, ch in enumerate(row):
                if ch != ".":
                    t.put(cx + i - 2, 36 + j, BRONZE[int(ch) + 1 if int(ch) < 5 else 5])
        t.put(cx, 35, BRONZE[5]); t.put(cx + 1, 35, BRONZE[3])
    for y in range(H - 4, H):                                # scuffed, damp foot
        for x in range(W):
            if rng.random() < 0.55 + 0.1 * (y - (H - 4)):
                t.put(x, y, mix(t.get(x, y), DARK[2], 0.45))
    # fine grain: fibres, pores and splits in the boards; tarnish, pits and verdigris on the straps (the studs and
    # ring pulls stay as drawn); a dark weep on the boards under each strap
    g = np.random.default_rng(seed + 7000)
    look = ramp_look(WOOD); metal = ramp_look(BRONZE)
    boards = np.zeros((H, W), bool)
    for x in range(W):
        boards[:, x] = 1 <= x % 8 <= 6 and x not in (30, 31, 32, 33)
    for y0 in (5, 28, 51):
        boards[y0:y0 + 6] = False
        for x in range(W):
            for j in range(5):
                if x % 8 in (3, 4) and j in (1, 2):
                    continue
                r = g.random()
                if r < 0.16:
                    nudge(t, metal, x, y0 + j, -1, lo=1)
                elif r < 0.2 and j >= 2:
                    paint(t, x, y0 + j, VERDIGRIS, look=metal)
            if g.random() < 0.34:
                for d in range(int(g.integers(1, 5))):
                    nudge(t, look, x, y0 + 6 + d, -1)
    dashes(t, g, look, 120, 2, 6, vertical=True, mask=boards)
    speckle(t, g, look, 0.045, dark=0.8, mask=boards)
    dashes(t, g, look, 6, 6, 14, vertical=True, dark=1.0, d=2, mask=boards)
    return t


def shutter(seed):
    """Small plank shutter / lattice for windows, 16 x 16: slats with a cross batten."""
    rng = np.random.default_rng(seed)
    t = Tile(16, 16, WOOD[1])
    for y in range(16):
        for x in range(16):
            c = WOOD[2] if y % 4 in (0, 1) else (WOOD[1] if y % 4 == 2 else DARK[2])
            if y % 4 == 0:
                c = WOOD[3]
            t.put(x, y, c)
    for x in (3, 12):
        for y in range(16):
            t.put(x, y, WOOD[3]); t.put(x + 1, y, WOOD[0])
    for x, y in ((3, 2), (12, 2), (3, 13), (12, 13)):
        t.put(x, y, BRONZE[4])
    look = ramp_look(WOOD)                                    # fine grain: worn slats, a stain under each nail
    slats = np.zeros((16, 16), bool)
    for y in range(16):
        for x in range(16):
            slats[y, x] = y % 4 in (1, 2) and x not in (3, 4, 12, 13)
    dashes(t, rng, look, 14, 1, 3, mask=slats)
    for x, y in ((3, 2), (12, 2), (3, 13), (12, 13)):
        nudge(t, look, x, y + 1, -1)
    return t


# ---------------------------------------------------------------------------------------- roofs, fields
def thatch(seed, tones=THATCH):
    """Reed thatch laid in overlapping tiers, 64 x 64: v runs down the slope. Each tier is combed strands with a
    ragged, shadowed lower edge."""
    rng = np.random.default_rng(seed)
    W = H = 64
    t = Tile(W, H, tones[2])
    tier = 16
    for ty in range(0, H, tier):
        ragged = [int(rng.choice([0, 0, 1, 1, 2, 3])) for _ in range(W)]
        for x in range(W):
            k = int(rng.choice([2, 3, 3, 4]))
            for j in range(tier):
                if rng.random() < 0.12:
                    k = int(np.clip(k + int(rng.choice([-1, 1])), 1, 5))
                c = tones[k]
                h = 0.35 + 0.65 * j / tier                   # each tier stands proud toward its lower edge
                if j < 2:
                    c, h = tones[max(k - 2, 0)], 0.2         # tucked under the tier above
                elif j == 2:
                    c = tones[max(k - 1, 1)]
                if j >= tier - ragged[x]:
                    c, h = tones[0], 0.1                     # gap between reed ends: the shadow under the tier
                elif j == tier - ragged[x] - 1:
                    c = tones[min(k + 1, 5)]                 # cut reed ends catch the light
                t.put(x, ty + j, c, h)
        for _ in range(5):                                   # binding stitches
            x = int(rng.integers(W)); y = ty + int(rng.integers(5, 10))
            for d in range(int(rng.integers(3, 7))):
                t.put(x + d, y, tones[1], 0.7)
    # fine grain: damp, rotting patches, stray straws lying across the comb, broken reeds, moss under each tier
    g = np.random.default_rng(seed + 7000)
    look = ramp_look(tones, skip=[tones[0]])
    rot = value_noise(g, W, H, 16) > 0.66
    r = g.random((H, W))
    for y, x in np.argwhere(rot & (r < 0.45)):
        nudge(t, look, x, y, -1, lo=1)
    for _ in range(54):                                      # stray straws: short pale diagonals
        x, y, sx = int(g.integers(W)), int(g.integers(H)), int(g.choice([-1, 1]))
        for d in range(int(g.integers(2, 5))):
            nudge(t, look, x + sx * d, y + d, 1, 0.06, lo=1)
    for _ in range(40):                                      # broken reeds: dark nicks
        nudge(t, look, int(g.integers(W)), int(g.integers(H)), -2, -0.15, lo=1)
    damp = np.zeros((H, W), bool)
    for y in range(H):
        damp[y] = y % tier in (2, 3, 4)
    flecks(t, g, 16, [mix(tones[2], GRASS_MOSS[3], 0.55), mix(tones[1], GRASS_MOSS[2], 0.55)], look=look, where=damp & rot)
    return t


def soil(seed):
    """Tilled furrows along u, 64 x 64: a ridge every 8 texels (32 cm), lit crest, dark trough, clods."""
    rng = np.random.default_rng(seed)
    W = H = 64
    t = Tile(W, H, SOIL[2])
    prof = [(4, 1.0), (3, 0.9), (2, 0.7), (1, 0.45), (0, 0.2), (0, 0.2), (1, 0.45), (2, 0.7)]
    for y in range(H):
        k, h = prof[y % 8]
        for x in range(W):
            kk = int(np.clip(k + int(rng.choice([-1, 0, 0, 0, 1])), 0, 4))
            t.put(x, y, SOIL[kk], h)
    for _ in range(40):                                      # clods
        x, y = int(rng.integers(W)), int(rng.integers(H))
        t.put(x, y, SOIL[4], 1.0); t.put(x + 1, y, SOIL[3], 1.0); t.put(x, y + 1, SOIL[0], 0.3); t.put(x + 1, y + 1, SOIL[0], 0.3)
    for _ in range(14):                                      # stubble / straw
        x, y = int(rng.integers(W)), int(rng.integers(H))
        t.put(x, y, WHEAT[2], 0.9)
    # fine grain: small stones, crumbs, straw ends and the odd weed seedling
    g = np.random.default_rng(seed + 7000)
    look = ramp_look(SOIL)
    for _ in range(16):
        x, y = int(g.integers(W)), int(g.integers(H))
        t.put(x, y, EARTH[4] if g.random() < 0.5 else EARTH[3], 1.1); t.put(x, y + 1, SOIL[0], 0.3)
    speckle(t, g, look, 0.05, dark=0.7, dh=0.1)
    for _ in range(9):
        x, y, sx = int(g.integers(W)), int(g.integers(H)), int(g.choice([-1, 1]))
        for d in range(int(g.integers(2, 4))):
            paint(t, x + sx * d, y + d // 2, WHEAT[1], look=look)
    flecks(t, g, 7, [GRASS_MOSS[3], GRASS_MOSS[2]], look=look, lmax=1)
    return t


def wheat(seed):
    """One row of ripe barley as a card strip, 64 x 32 RGBA, tiles along u. Stalks root on the bottom row."""
    rng = np.random.default_rng(seed)
    W, H = 64, 32
    t = Tile(W, H, WHEAT[2], alpha=True)
    for x in range(W):                                        # the dense foot of the row
        for y in range(H - 6, H):
            if rng.random() < 0.55 + 0.09 * (y - (H - 6)):
                put_a(t, x, y, WHEAT[0] if y > H - 3 else WHEAT[1])
    x = 0
    while x < W:
        hgt = int(rng.integers(14, 22))
        lean = float(rng.uniform(-0.12, 0.12))
        fx = float(x)
        for i in range(hgt):
            f = i / hgt
            c = WHEAT[1] if f < 0.35 else (WHEAT[2] if f < 0.7 else WHEAT[3])
            put_a(t, int(round(fx)), H - 1 - i, c)
            fx += lean
        ex = int(round(fx)); ey = H - 1 - hgt
        ear = ["43", "53", "42", "53", "42", "32"]            # the ear: two columns of grains
        for j, row in enumerate(ear):
            for i, ch in enumerate(row):
                put_a(t, ex + i, ey - len(ear) + 1 + j, WHEAT[int(ch)])
        put_a(t, ex, ey - len(ear), WHEAT[5]); put_a(t, ex + 1, ey - len(ear) - 1, WHEAT[4])     # awns
        if rng.random() < 0.5:
            put_a(t, ex - 1, ey - len(ear) - 1, WHEAT[4])
        x += int(rng.integers(2, 4))
    g = np.random.default_rng(seed + 7000)                    # fine grain: dry, bent and darker stalks (colour only)
    speckle(t, g, ramp_look(WHEAT), 0.09, dark=0.7, mask=t.a == 255)
    return t


# ---------------------------------------------------------------------------------------- cloth, glaze, metal
def banner(seed):
    """Hanging banner, 16 x 64 RGBA: the cloth is 16 x 48 (64 x 192 cm), swallow-tailed. Field in team colour
    (grey, alpha TEAM), woven gold border and a sun-over-ramparts device (alpha 255)."""
    W, H = 16, 64
    t = Tile(W, H, GREY[2], alpha=True)
    gold = [BRONZE[2], BRONZE[4], BRONZE[5]]
    for y in range(48):
        notch = max(0, y - 39)
        for x in range(W):
            if abs(x - 7.5) < notch * 0.85:
                continue
            c, a = GREY[2], TEAM
            if x in (3, 12):
                c = GREY[1]                                   # folds
            if x in (4, 11) and y % 7 < 5:
                c = GREY[0]
            if x in (6, 7, 8):
                c = GREY[3]
            if y > 30 and x in (5, 10):
                c = GREY[1]
            if x in (0, W - 1) or y == 0:
                c, a = gold[1], 255
            if x in (1, W - 2) or y == 1:
                c, a = gold[0], 255
            if y == 0 and x % 2:
                c, a = gold[2], 255
            put_a(t, x, y, c, a)
    device = ["...1..1..1...",
              "....1.1.1....",
              ".....222.....",
              ".11.22222.11.",
              ".....222.....",
              "....1.1.1....",
              "...1..1..1...",
              ".............",
              ".22..22..22..",
              ".2222222222..",
              ".2222222222..",
              ".............",
              "..11111111...",]
    for j, row in enumerate(device):
        for i, ch in enumerate(row):
            if ch != ".":
                put_a(t, 2 + i, 9 + j, gold[int(ch)], 255)
    # fine grain (colour only, the layout and masks are as drawn): threadbare weave, a grimy tail, tarnished border
    g = np.random.default_rng(seed + 7000)
    cloth = ramp_look(GREY); braid = ramp_look(gold)
    for y in range(48):
        for x in range(W):
            if t.a[y, x] == TEAM:
                if g.random() < 0.07 + (0.16 if y >= 34 else 0.0):
                    nudge(t, cloth, x, y, -1)
            elif t.a[y, x] == 255 and (x in (0, 1, W - 2, W - 1) or y < 2) and g.random() < 0.13:
                nudge(t, braid, x, y, -1)
    return t


def awning(seed):
    """Striped awning cloth, 32 x 32 RGBA, tiles: broad team stripes and cream, weave shading."""
    rng = np.random.default_rng(seed)
    W = H = 32
    t = Tile(W, H, CREAM[2], alpha=True)
    for y in range(H):
        for x in range(W):
            band = (x // 8) % 2
            if band == 0:
                c, a = GREY[2] if y % 4 else GREY[1], TEAM
                if x % 8 == 0:
                    c = GREY[3]
            else:
                c, a = CREAM[2] if y % 4 else CREAM[1], 255
                if x % 8 == 0:
                    c = CREAM[3]
                if x % 8 == 7:
                    c = CREAM[1]
            put_a(t, x, y, c, a)
    for _ in range(10):                                       # faded, patched spots
        x, y = int(rng.integers(W)), int(rng.integers(H))
        t.c[y, x] = mix(t.c[y, x], CREAM[0], 0.4)
    # fine grain (colour only): frayed threads in the weave, dirt run down the cloth
    g = np.random.default_rng(seed + 7000)
    look = ramp_look(GREY, CREAM)
    speckle(t, g, look, 0.065, dark=0.68)
    drips(t, g, look, np.argwhere(np.ones((H, W), bool)), 9, 3, 8)
    return t


def frieze(seed):
    """Glazed-brick band for the wall heads, 64 x 16 RGBA mask: team-coloured glaze, gold rules, a stepped
    rampart motif and discs in cream / gold every 16 texels. v = 0 is the band's top edge."""
    W, H = 64, 16
    t = Tile(W, H, GREY[2], alpha=True)
    for y in range(H):
        for x in range(W):
            c = GREY[2]
            if (x + (4 if (y // 4) % 2 else 0)) % 8 == 0 or y % 4 == 3:
                c = GREY[0]                                   # brick joints in the glaze
            elif y % 4 == 0:
                c = GREY[3]
            put_a(t, x, y, c, TEAM)
    for x in range(W):
        for y, c in ((0, PALE[4]), (1, BRONZE[4]), (2, BRONZE[2]), (13, BRONZE[4]), (14, BRONZE[2]), (15, PALE[1])):
            put_a(t, x, y, c, 255)
    motif = ["....33....",
             "...3443...",
             "..334433..",
             ".33444433.",
             ".33333333.",
             "3344444433",
             "3333333333"]
    for cx in (3, 35):
        for j, row in enumerate(motif):
            for i, ch in enumerate(row):
                if ch != ".":
                    put_a(t, cx + i, 4 + j, CREAM[3] if ch == "4" else CREAM[1], 255)
    disc = [".22.", "2332", "2332", ".22."]
    for cx in (22, 54):
        for j, row in enumerate(disc):
            for i, ch in enumerate(row):
                if ch != ".":
                    put_a(t, cx + i, 6 + j, BRONZE[5] if ch == "3" else BRONZE[3], 255)
    # fine grain (colour only, masks as drawn): crazed, chipped glaze, tarnished rules, worn cream
    g = np.random.default_rng(seed + 7000)
    glaze = ramp_look(GREY, skip=[GREY[0]]); other = ramp_look(BRONZE, PALE, CREAM)
    for y in range(H):
        for x in range(W):
            r = g.random()
            if t.a[y, x] == TEAM:
                if r < 0.08:
                    nudge(t, glaze, x, y, -1 if r < 0.055 else 1, lo=1)
            elif r < (0.09 if y in (0, 1, 2, 13, 14, 15) else 0.06):
                nudge(t, other, x, y, -1)
    return t


def bronze(seed):
    """Hammered bronze sheet, 32 x 32: planished dimples, rivets on a 16 texel grid, a little verdigris."""
    rng = np.random.default_rng(seed)
    W = H = 32
    t = Tile(W, H, BRONZE[3])
    n = value_noise(rng, W, H, 8)
    t.c[n < 0.4] = BRONZE[2]
    t.c[n > 0.75] = BRONZE[4]
    for _ in range(40):
        x, y = int(rng.integers(W)), int(rng.integers(H))
        t.put(x, y, BRONZE[5] if rng.random() < 0.4 else BRONZE[4]); t.put(x + 1, y + 1, BRONZE[1])
    for gx in (3, 19):
        for gy in (3, 19):
            t.put(gx, gy, BRONZE[5]); t.put(gx + 1, gy, BRONZE[4]); t.put(gx, gy + 1, BRONZE[3]); t.put(gx + 1, gy + 1, BRONZE[0])
    for _ in range(8):
        t.put(int(rng.integers(W)), int(rng.integers(H)), rgb("#5f7f66"))
    # fine grain: tarnish in patches, scratches, pits, verdigris weeping from the rivets
    g = np.random.default_rng(seed + 7000)
    look = ramp_look(BRONZE)
    plate = np.ones((H, W), bool)
    for gx in (3, 19):
        for gy in (3, 19):
            plate[gy:gy + 2, gx:gx + 2] = False
    dull = value_noise(g, W, H, 8) > 0.55
    r = g.random((H, W))
    for y, x in np.argwhere(dull & (r < 0.34)):
        nudge(t, look, x, y, -1, lo=1, mask=plate)
    hairlines(t, g, look, 8, 3, 6, d=1, dh=0.0, hi=4, mask=plate, wander=0.9)
    pits(t, g, look, 10, lo=0, mask=plate)
    for gx in (3, 19):
        for gy in (3, 19):
            for d in range(int(g.integers(1, 4))):
                paint(t, gx + int(g.integers(0, 2)), gy + 2 + d, VERDIGRIS, mask=plate)
    return t


def ore(seed):
    """Broken gold ore, 64 x 64 RGBA mask: dark angular rock, quartz seams, gold veins and nuggets (alpha TEAM =
    glint, picked up by the material's Glow)."""
    rng = np.random.default_rng(seed)
    W = H = 64
    pts = rng.random((22, 2)) * [W, H]
    tone = rng.choice([1, 2, 2, 3, 3, 4], size=len(pts))
    ys, xs = np.mgrid[0:H, 0:W]
    best = np.full((H, W), 1e9); second = np.full((H, W), 1e9); idx = np.zeros((H, W), int)
    for i, (px_, py_) in enumerate(pts):
        dx = np.abs(xs - px_); dx = np.minimum(dx, W - dx)
        dy = np.abs(ys - py_); dy = np.minimum(dy, H - dy)
        d = dx * 0.9 + dy * 1.1 + np.maximum(dx, dy) * 0.4
        closer = d < best
        second = np.where(closer, best, np.minimum(second, d))
        idx = np.where(closer, i, idx)
        best = np.where(closer, d, best)
    t = Tile(W, H, ORE[2], alpha=True)
    t.a[:] = 255
    edge = (second - best) < 1.2
    for y in range(H):
        for x in range(W):
            k = int(tone[idx[y, x]])
            c = ORE[k]
            if edge[y, x]:
                c = ORE[0]
            elif edge[(y - 1) % H, x] or edge[y, (x - 1) % W]:
                c = ORE[min(k + 1, 4)]
            t.c[y, x] = c
    for _ in range(9):                                        # gold veins wandering through the rock
        x, y = int(rng.integers(W)), int(rng.integers(H))
        for d in range(int(rng.integers(6, 20))):
            c = GOLD[int(rng.choice([1, 2, 2, 3]))]
            put_a(t, x, y, c, TEAM if c is not GOLD[1] else 255, wrap_y=True)
            if rng.random() < 0.3:
                put_a(t, x, y + 1, GOLD[0], 255, wrap_y=True)
            x += 1
            if rng.random() < 0.5:
                y += int(rng.choice([-1, 1]))
    for _ in range(16):                                       # nuggets
        x, y = int(rng.integers(W)), int(rng.integers(H))
        put_a(t, x, y, GOLD[3], TEAM, wrap_y=True); put_a(t, x + 1, y, GOLD[2], TEAM, wrap_y=True)
        put_a(t, x, y + 1, GOLD[1], 255, wrap_y=True); put_a(t, x + 1, y + 1, GOLD[0], 255, wrap_y=True)
        if rng.random() < 0.4:
            put_a(t, x, y - 1, GOLD[4], TEAM, wrap_y=True)
    # fine grain (rock texels only: the gold and its glint mask are as drawn): mineral speckle, fractures across the
    # facets, quartz grains, iron staining
    g = np.random.default_rng(seed + 7000)
    look = ramp_look(ORE, skip=[ORE[0]])
    rock = t.a == 255
    speckle(t, g, look, 0.085, lo=1, mask=rock)
    hairlines(t, g, look, 16, 3, 7, lo=1, mask=rock, wander=0.8)
    hairlines(t, g, look, 8, 3, 6, lo=1, mask=rock, vertical=False)
    for _ in range(14):
        nudge(t, look, int(g.integers(W)), int(g.integers(H)), 2, lo=1, mask=rock)
    flecks(t, g, 9, [mix(ORE[2], RUST[1], 0.5), mix(ORE[3], RUST[2], 0.45)], look=look, mask=rock, lmax=2)
    return t


def gold(seed):
    """A heap of washed gold: nuggets shingled over a dark ground, 32 x 32 RGBA mask (alpha TEAM = glint)."""
    rng = np.random.default_rng(seed)
    W = H = 32
    t = Tile(W, H, GOLD[0], alpha=True)
    t.a[:] = 255
    for y in range(H):
        for x in range(W):
            t.c[y, x] = BRONZE[0] if rng.random() < 0.6 else BRONZE[1]
    shapes = [[".43.", "4322", "3221", ".11."], ["43.", "322", "211"], [".4.", "432", "321", ".1."], ["433.", "3221", ".11."], ["43", "21"]]
    for gy in range(H // 4):
        for gx in range(W // 4):
            if rng.random() < 0.08:
                continue
            x = gx * 4 + int(rng.integers(0, 3)) + (2 if gy % 2 else 0); y = gy * 4 + int(rng.integers(0, 2))
            shp = shapes[int(rng.integers(len(shapes)))]
            dull = rng.random() < 0.25
            for j, row in enumerate(shp):
                for i, ch in enumerate(row):
                    if ch == ".":
                        continue
                    k = max(int(ch) - (1 if dull else 0), 0)
                    put_a(t, x + i, y + j, GOLD[k], TEAM if k >= 3 else 255, wrap_y=True)
    # fine grain (each texel stays on its side of the glint mask): dull facets, grit and dirt between the nuggets
    g = np.random.default_rng(seed + 7000)
    lit = ramp_look(GOLD[3:]); dim = ramp_look(GOLD[:3]); ground = ramp_look([DARK[2], BRONZE[0], BRONZE[1]])
    for y in range(H):
        for x in range(W):
            r = g.random()
            if t.a[y, x] == TEAM:
                if r < 0.07:
                    nudge(t, lit, x, y, -1)
            elif r < 0.09:
                nudge(t, dim, x, y, -1 if r < 0.06 else 1)
            elif r < 0.3:
                nudge(t, ground, x, y, -1)
    return t


def pot(seed):
    """Storage jar skin, 32 x 32: u runs round the jar, v from the rim down. A painted zigzag band on the shoulder."""
    rng = np.random.default_rng(seed)
    W = H = 32
    t = Tile(W, H, TERRA[3])
    for y in range(H):
        k = 3
        if y < 2:
            k = 1
        elif y < 4:
            k = 4
        elif y > H - 5:
            k = 2 if y < H - 2 else 1
        for x in range(W):
            kk = int(np.clip(k + (1 if (x + y // 3) % 11 == 0 else 0) - (1 if rng.random() < 0.06 else 0), 0, 5))
            t.put(x, y, TERRA[kk])
    for x in range(W):                                        # shoulder band
        t.put(x, 7, TERRA[0]); t.put(x, 13, TERRA[0])
        for y in range(8, 13):
            t.put(x, y, CREAM[2])
        zy = 8 + [0, 1, 2, 3, 4, 3, 2, 1][x % 8]
        t.put(x, zy, TERRA[1])
        t.put(x, 8 + (4 - (zy - 8)), TERRA[1]) if x % 8 in (0, 4) else None
    for _ in range(8):                                        # firing marks
        x, y = int(rng.integers(W)), int(rng.integers(15, H - 4))
        for d in range(int(rng.integers(2, 5))):
            t.put(x + d, y, TERRA[2])
    # fine grain: grog in the clay, a hairline crack or two, a sooty foot, chipped rim, worn paint on the band
    g = np.random.default_rng(seed + 7000)
    look = ramp_look(TERRA); slip = ramp_look(CREAM)
    belly = np.zeros((H, W), bool)
    belly[4:7] = True; belly[14:H] = True
    speckle(t, g, look, 0.08, mask=belly)
    hairlines(t, g, look, 2, 6, 12, mask=belly, wander=0.35)
    for y in range(H - 6, H):
        for x in range(W):
            if g.random() < 0.12 + 0.05 * (y - (H - 6)):
                nudge(t, look, x, y, -1)
    for _ in range(3):
        nudge(t, look, int(g.integers(W)), int(g.integers(0, 2)), -1)
    for y in range(8, 13):
        for x in range(W):
            if g.random() < 0.13:
                nudge(t, slip, x, y, -1)
    return t


def leaves(seed):
    """Olive canopy, 64 x 64 RGBA: small lance leaves in clusters. On the masked shell alpha 0 is a gap; the opaque
    core under it uses the same texture and shows the dark fill."""
    rng = np.random.default_rng(seed)
    W = H = 64
    t = Tile(W, H, OLIVE[0], alpha=True)
    for y in range(H):
        for x in range(W):
            t.c[y, x] = OLIVE[1] if rng.random() < 0.7 else OLIVE[0]
    strokes = [((0, 0), (1, -1), (2, -2)), ((0, 0), (1, 0), (2, -1), (3, -1)), ((0, 0), (0, -1), (1, -2)),
               ((0, 0), (-1, -1), (-2, -2)), ((0, 0), (1, 0), (2, 0)), ((0, 0), (-1, -1), (-1, -2), (-2, -3))]
    for gy in range(H // 3):
        for gx in range(W // 3):
            if rng.random() < 0.1:
                continue
            x = gx * 3 + int(rng.integers(0, 3)); y = gy * 3 + int(rng.integers(0, 3))
            s = strokes[int(rng.integers(len(strokes)))]
            base = int(rng.choice([2, 2, 3, 3, 3, 4]))
            for i, (dx, dy) in enumerate(s):
                k = min(base + (1 if i == len(s) - 1 else 0), 5)
                put_a(t, x + dx, y + dy, OLIVE[k], 255, wrap_y=True)
    # fine grain (leaf texels only, the gaps are as drawn): shaded leaves, a few dry yellowed ones
    g = np.random.default_rng(seed + 7000)
    look = ramp_look(OLIVE)
    leaf = t.a == 255
    speckle(t, g, look, 0.06, dark=0.75, lo=2, mask=leaf)
    dry = mix(OLIVE[3], THATCH[3], 0.5)
    for y, x in np.argwhere(leaf & (g.random((H, W)) < 0.022)):
        t.c[y, x] = dry
    return t


def flame(seed):
    """A small fire, 16 x 16 RGBA card: authored tongue, hot core."""
    t = Tile(16, 16, FLAME[1], alpha=True)
    art = ["................",
           ".......1........",
           ".......11.......",
           "......121.......",
           "......1221..1...",
           "...1..12321.1...",
           "...1.1233211....",
           "...11233432.....",
           "...122344321....",
           "..12234444321...",
           "..12344554321...",
           "..12345555321...",
           "..12345555421...",
           "...1234554321...",
           "...012344321....",
           "....0122221....."]
    for j, row in enumerate(art):
        for i, ch in enumerate(row):
            if ch != ".":
                put_a(t, i, j, FLAME[min(int(ch), 4)] if ch != "0" else FLAME[0], 255)
    return t


def dark(seed):
    rng = np.random.default_rng(seed)
    t = Tile(16, 16, DARK[1])
    for _ in range(40):
        t.put(int(rng.integers(16)), int(rng.integers(16)), DARK[int(rng.integers(0, 3))])
    return t


# ---------------------------------------------------------------------------------------- battle damage, new roofs
CHAR = pal("#0c0a09", "#171412", "#241f1b", "#342d27", "#4a4138", "#6b645a")       # soot, charred timber, ash
TILE = [mix(a, b, 0.58) for a, b in zip(TERRA, CLAY)]                              # sun-faded terracotta roof tiles

# T_Bld_Scorch is an atlas of soot marks (256 x 128 texels). name -> (x, y, w, h) in texels; plumes have their
# foot on the bottom edge of their cell. Mirrored by SCORCH in Tools/blender/bldkit.py (in cm: x 4).
SCORCH_CELLS = {
    "plume_l": (0, 0, 64, 96), "plume_m": (64, 0, 48, 64), "plume_s": (112, 0, 32, 48), "blot_l": (144, 0, 64, 64),
    "blot_s": (208, 0, 32, 32), "streak": (240, 0, 16, 64), "smear": (0, 96, 64, 32), "plume_m2": (64, 64, 48, 64),
    "blot_m": (112, 64, 48, 48), "lick": (160, 64, 32, 64), "blot_w": (192, 64, 64, 40),
}


def char(seed):
    """Charred timber / burnt thatch, 64 x 64, tiles: alligatored black blocks, grey ash on the lit edges."""
    rng = np.random.default_rng(seed)
    W = H = 64
    t = Tile(W, H, CHAR[1])
    y = 0
    while y < H:
        ch = int(rng.choice([5, 6, 7, 8]))
        ch = min(ch, H - y)
        x = int(rng.integers(0, 6))
        end = x + W
        while x < end:
            bw = min(int(rng.integers(5, 12)), end - x)
            tone = int(rng.choice([1, 1, 2, 2, 3]))
            for j in range(ch):
                for i in range(bw):
                    c = CHAR[tone]
                    if j == 0 or i == 0:
                        c = CHAR[0]                           # the crack
                    elif j == 1 and i > 1 and rng.random() < 0.7:
                        c = CHAR[min(tone + 2, 5)]            # ash on the lit arris
                    elif rng.random() < 0.06:
                        c = CHAR[min(tone + 1, 4)]
                    t.put(x + i, y + j, c)
            x += bw
        y += ch
    for _ in range(10):                                      # flecks of pale ash
        x, y = int(rng.integers(W)), int(rng.integers(H))
        t.put(x, y, CHAR[5]); t.put(x + 1, y, CHAR[4])
    # fine grain: hairline checks inside the blocks, ash dust, pits, a little scorched brown where wood survives
    g = np.random.default_rng(seed + 7000)
    look = ramp_look(CHAR, skip=[CHAR[0]])
    hairlines(t, g, look, 30, 2, 5, d=-5, wander=0.7)
    speckle(t, g, look, 0.05, dark=0.35, lo=1, hi=4)
    pits(t, g, look, 22, lo=0)
    flecks(t, g, 12, [mix(CHAR[3], OAK[3], 0.5), mix(CHAR[2], OAK[3], 0.5)], look=look, lmax=2)
    return t


def scorch(seed):
    """Soot marks as cut-outs (card slot): black hearts, brown-grey fringes that break up in a dither."""
    rng = np.random.default_rng(seed)
    W, H = 256, 128
    t = Tile(W, H, CHAR[1], alpha=True)
    for name, (cx, cy, cw, chh) in SCORCH_CELLS.items():
        n1 = value_noise(rng, cw, chh, 8)
        n2 = value_noise(rng, cw, chh, 4)
        tongues = [(rng.uniform(0.18, 0.82), rng.uniform(0.55, 1.0), rng.uniform(0.10, 0.2)) for _ in range(5)]
        for j in range(1, chh - 1):
            for i in range(1, cw - 1):
                fx = (i + 0.5) / cw - 0.5                     # -0.5 .. 0.5
                fy = 1.0 - (j + 0.5) / chh                    # 0 at the foot .. 1 at the top
                if name.startswith("blot"):
                    d = math.hypot(fx, fy - 0.5) * 2.0
                    f = 1.0 - d
                elif name == "smear":
                    f = min(1.0 - abs(fx) * 2.0, 1.0 - fy) * 1.3
                elif name in ("streak", "lick"):
                    f = (1.0 - abs(fx) * 2.0) * (1.0 - fy * 0.85)
                else:                                         # plume: a broad foot, tongues licking upward
                    f = (1.0 - abs(fx) * 2.0 / (1.0 - 0.45 * fy)) * (1.0 - fy) * 2.2
                    for tx, th, tw in tongues:
                        if fy < th:
                            f = max(f, (1.0 - abs(fx + 0.5 - tx) / tw) * (1.0 - fy / th) * 1.6)
                f += (n1[j, i] - 0.5) * 0.5 + (n2[j, i] - 0.5) * 0.25
                edge = min(i, cw - 1 - i, j, (chh - 1 - j) if name.startswith("blot") else 99) / 3.0
                f = min(f, edge)
                if f <= 0.06:
                    continue
                if f < 0.34 and (i + j) % 2:                  # the fringe breaks up: the wall shows through
                    continue
                if f < 0.16 and (j % 2 or rng.random() < 0.4):
                    continue
                if f < 0.5 and (i % 2 == 0 and j % 2 == 0):
                    continue
                tone = 0 if f > 0.8 else 1 if f > 0.56 else 2 if f > 0.36 else 3
                if rng.random() < 0.12:
                    tone = min(tone + 1, 4)
                put_a(t, cx + i, cy + j, CHAR[tone], 255)
    return t


def target(seed):
    """Face of a straw archery butt, 32 x 32 (128 cm across): coiled straw, painted rings, a bronze-gold centre."""
    rng = np.random.default_rng(seed)
    W = H = 32
    t = Tile(W, H, THATCH[1])
    for y in range(H):
        for x in range(W):
            d = math.hypot(x - 15.5, y - 15.5)
            ring = int(d) % 3
            c = THATCH[3] if ring else THATCH[1]              # the coil
            if rng.random() < 0.2:
                c = THATCH[4] if ring else THATCH[2]
            if d < 3.0:
                c = BRONZE[4] if d < 1.6 else BRONZE[3]
            elif d < 6.5:
                c = TERRA[2] if rng.random() < 0.85 else TERRA[1]
            elif d < 9.5:
                c = CREAM[2] if rng.random() < 0.85 else CREAM[1]
            elif d < 12.5:
                c = TERRA[2] if rng.random() < 0.85 else TERRA[3]
            elif d >= 15.5:
                c = THATCH[0]
            t.put(x, y, c)
    for (x, y) in ((19, 12), (11, 18), (22, 20)):             # arrow holes
        t.put(x, y, DARK[1])
    # fine grain: paint flaked off the straw, frayed coils, more arrow holes, a dirty lower half
    g = np.random.default_rng(seed + 7000)
    straw = ramp_look(THATCH, skip=[THATCH[0]]); paintl = ramp_look(TERRA, CREAM)
    for y in range(H):
        for x in range(W):
            d = math.hypot(x - 15.5, y - 15.5)
            r = g.random()
            if 3.0 <= d < 12.5:
                if r < 0.065:
                    paint(t, x, y, THATCH[3] if r < 0.04 else THATCH[2], look=paintl)
                elif r < 0.12 + (0.08 if y > 18 else 0.0):
                    nudge(t, paintl, x, y, -1)
            elif d < 15.5 and r < 0.1:
                nudge(t, straw, x, y, -1 if r < 0.06 else 1, lo=1)
    for _ in range(6):
        a, rad = g.uniform(0, math.tau), g.uniform(2.0, 11.0)
        x, y = int(15.5 + math.cos(a) * rad), int(15.5 + math.sin(a) * rad)
        t.put(x, y, DARK[1]); nudge(t, paintl, x, y + 1, 1)
    return t


def roof_tile(seed):
    """Terracotta pan-and-cover tiles, 64 x 64, v runs down the slope: pans 5 texels wide between raised covers,
    each course 8 texels with a shadowed lower lip."""
    rng = np.random.default_rng(seed)
    W = H = 64
    t = Tile(W, H, TILE[2])
    for row in range(H // 8):
        for col in range(W // 8):
            tone = int(rng.choice([2, 2, 3, 3, 1, 4], p=[0.36, 0.26, 0.16, 0.1, 0.08, 0.04]))
            for j in range(8):
                for i in range(8):
                    if i < 5:                                 # the pan
                        c, h = TILE[tone], 0.5
                        if i == 0:
                            c, h = TILE[max(tone - 2, 0)], 0.3       # in the cover's shadow
                        if j == 7:
                            c, h = TILE[max(tone - 2, 0)], 0.2       # under the next course
                        elif j == 6:
                            c = TILE[min(tone + 1, 5)]
                    else:                                     # the cover
                        k = (tone + 1, tone + 2, tone)[i - 5]
                        c, h = TILE[int(np.clip(k, 0, 5))], 1.0
                        if j == 7:
                            c, h = TILE[max(tone - 1, 0)], 0.5
                    t.put(col * 8 + i, row * 8 + j, c, h)
        for _ in range(3):                                    # lichen and chips
            x, y = int(rng.integers(W)), row * 8 + int(rng.integers(1, 6))
            t.put(x, y, mix(TILE[1], GRASS_MOSS[3], 0.5) if rng.random() < 0.5 else TILE[5])
    # fine grain: gritty fired clay, hairline cracks, chipped lips, soot run down the pans, lichen, moss in the
    # shadowed channels
    g = np.random.default_rng(seed + 7000)
    look = ramp_look(TILE)
    speckle(t, g, look, 0.06 * (0.4 + 1.2 * value_noise(g, W, H, 16)), dh=0.05)
    hairlines(t, g, look, 12, 3, 6, wander=0.6)
    for _ in range(16):                                       # chips out of a lower lip
        x, y = int(g.integers(W // 8)) * 8 + int(g.integers(1, 5)), int(g.integers(H // 8)) * 8 + 6
        nudge(t, look, x, y, -3, -0.2)
        if g.random() < 0.5:
            nudge(t, look, x + 1, y, -2, -0.2)
    pans = np.argwhere(np.ones((H, W), bool))
    pans = pans[(pans[:, 1] % 8 >= 1) & (pans[:, 1] % 8 <= 4)]
    drips(t, g, look, pans, 14, 4, 10)
    flecks(t, g, 9, [mix(TILE[3], LICHEN, 0.5), mix(TILE[2], LICHEN, 0.5)], look=look)
    damp = value_noise(g, W, H, 16) > 0.62
    ch = np.zeros((H, W), bool)
    for y in range(H):
        for x in range(W):
            ch[y, x] = x % 8 == 0 or y % 8 == 7
    flecks(t, g, 26, [mix(TILE[0], GRASS_MOSS[2], 0.55), mix(TILE[1], GRASS_MOSS[3], 0.55)], look=look, where=ch & damp, lmax=2)
    return t


WATER = pal("#1c3a3c", "#28524f", "#376b63", "#4c887a", "#7fb3a0", "#c8e2cf")     # still trough water, muted teal


def water(seed):
    """Still water in a trough, 32 x 32, tiles: dark teal with a few short pale ripples and glints."""
    rng = np.random.default_rng(seed)
    W = H = 32
    t = Tile(W, H, WATER[1])
    n = value_noise(rng, W, H, 8)
    for y in range(H):
        for x in range(W):
            t.put(x, y, WATER[0] if n[y, x] < 0.3 else (WATER[2] if n[y, x] > 0.68 else WATER[1]))
    for _ in range(11):                                       # ripples: short horizontal dashes, lit above, dark below
        x, y, L = int(rng.integers(W)), int(rng.integers(H)), int(rng.integers(3, 8))
        for i in range(L):
            t.put(x + i, y, WATER[3])
            t.put(x + i, y + 1, WATER[0])
        if rng.random() < 0.5:
            t.put(x + L // 2, y, WATER[4])
    for _ in range(4):
        t.put(int(rng.integers(W)), int(rng.integers(H)), WATER[5])
    # fine grain: faint single-texel ripples, a few straws and specks of scum afloat
    g = np.random.default_rng(seed + 7000)
    look = ramp_look(WATER)
    speckle(t, g, look, 0.035, dark=0.5, hi=3)
    for _ in range(3):
        x, y = int(g.integers(W)), int(g.integers(H))
        t.put(x, y, THATCH[4]); t.put(x + 1, y, THATCH[3])
    flecks(t, g, 4, [mix(WATER[1], GRASS_MOSS[2], 0.5)], look=look, lmax=2)
    return t



# ---------------------------------------------------------------------------------------- build
# ---------------------------------------------------------------------------------------- medieval upgrades
SLATE = pal("#1b2026", "#262c34", "#333b45", "#424b57", "#545e6b", "#6c7684")      # wet blue-grey roof slate
IRON = pal("#121212", "#1c1b1a", "#282624", "#36332f", "#47423c", "#615a52")       # blackened wrought iron
RUST = pal("#3d2416", "#5a3320", "#784429")
GRANITE = pal("#2e2c29", "#3e3b36", "#504c45", "#645f56", "#79736a", "#8f897e")     # grimy dark rubble stone
OAK = pal("#1d140d", "#2a1d13", "#38281a", "#4a3523", "#5d442e")                  # old dark oak (half-timbering)


def slate(seed):
    """Slate shingles, 64 x 64, v runs down the slope: courses 6 texels deep, staggered slates 4-8 wide with a dark
    lower lip and a lit upper edge, a few chipped or slipped ones, lichen and moss in the joints."""
    rng = np.random.default_rng(seed)
    W = H = 64
    t = Tile(W, H, SLATE[1])
    for row in range(H // 6 + 1):
        y0 = row * 6
        if y0 >= H:
            break
        x = int(rng.integers(0, 6))
        for bw in partition(rng, W, 4, 8):
            tone = int(rng.choice([1, 2, 2, 3, 3, 4], p=[0.12, 0.26, 0.2, 0.22, 0.12, 0.08]))
            slip = int(rng.random() < 0.07)
            for j in range(6):
                for i in range(bw):
                    c, h = SLATE[tone], 0.6 + 0.06 * j
                    if j == 0:
                        c = SLATE[min(tone + 1, 5)]
                    if i == bw - 1:
                        c, h = SLATE[0], 0.2                      # the joint
                    if j == 5 - slip:
                        c, h = SLATE[0], 0.1                      # shadow under the course below's lip
                    elif j > 5 - slip:
                        c, h = SLATE[max(tone - 1, 0)], 0.3
                    if rng.random() < 0.06:
                        c = SLATE[max(tone - 1, 0)] if rng.random() < 0.6 else SLATE[min(tone + 1, 5)]
                    t.put(x + i, y0 + j, c, h, wrap_y=False)
            if rng.random() < 0.08:                               # a chipped corner
                t.put(x + bw - 2, y0 + 4, SLATE[0], 0.1, wrap_y=False); t.put(x + bw - 2, y0 + 3, SLATE[0], 0.1, wrap_y=False)
            x += bw
    for _ in range(44):                                           # lichen spots and moss in the joints
        x, y = int(rng.integers(W)), int(rng.integers(H))
        col = mix(SLATE[2], GRASS_MOSS[3], 0.55) if rng.random() < 0.6 else mix(SLATE[3], rgb("#a7a37a"), 0.45)
        for d in range(int(rng.integers(1, 4))):
            t.put(x + d, y, col)
    # fine grain: cleavage scratches, flaked faces, chipped lips, damp run down the courses, rust from the nails,
    # moss packed in the joints
    g = np.random.default_rng(seed + 7000)
    look = ramp_look(SLATE, skip=[SLATE[0]])
    hairlines(t, g, look, 30, 2, 3, d=1, dh=0.05, lo=1, wander=1.0)
    pits(t, g, look, 26, lo=1, depth=1)
    for _ in range(14):
        x, y = int(g.integers(W)), int(g.integers(H // 6)) * 6 + 4
        paint(t, x, y, SLATE[0], -0.3, look=look)
        if g.random() < 0.5:
            paint(t, x + 1, y, SLATE[0], -0.3, look=look)
    drips(t, g, look, np.argwhere(np.ones((H, W), bool)), 14, 4, 9, lo=1, through=True)
    flecks(t, g, 6, [mix(SLATE[2], RUST[1], 0.45), mix(SLATE[2], RUST[2], 0.4)], look=look, lmax=1)
    for _ in range(6):                                            # a nail's rust weeping down a slate
        x, y = int(g.integers(W)), int(g.integers(H))
        for d in range(int(g.integers(2, 5))):
            paint(t, x, y + d, mix(SLATE[2], RUST[1], 0.45), look=look)
    joints = np.all(t.c == SLATE[0], axis=-1) & (value_noise(g, W, H, 16) > 0.6)
    r = g.random((H, W))
    for y, x in np.argwhere(joints & (r < 0.4)):
        t.c[y, x] = mix(SLATE[0], GRASS_MOSS[2], 0.6) if r[y, x] < 0.2 else mix(SLATE[1], GRASS_MOSS[3], 0.6)
    return t


def iron(seed):
    """Blackened wrought iron, 32 x 32: hammered plate, a rivet grid every 16 texels, rust weeping from the rivets."""
    rng = np.random.default_rng(seed)
    W = H = 32
    t = Tile(W, H, IRON[2])
    n = value_noise(rng, W, H, 6)
    t.c[n < 0.35] = IRON[1]
    t.c[n > 0.72] = IRON[3]
    for _ in range(60):                                           # hammer marks
        x, y = int(rng.integers(W)), int(rng.integers(H))
        t.put(x, y, IRON[4] if rng.random() < 0.5 else IRON[3]); t.put(x + 1, y + 1, IRON[0])
    for gx in (4, 20):
        for gy in (4, 20):
            t.put(gx, gy, IRON[5]); t.put(gx + 1, gy, IRON[4]); t.put(gx, gy + 1, IRON[3]); t.put(gx + 1, gy + 1, IRON[0])
            y = gy + 2
            for d in range(int(rng.integers(3, 8))):                # rust runs down
                t.put(gx + (1 if d > 3 else 0), y + d, RUST[int(rng.integers(0, 3))])
    for _ in range(14):
        x, y = int(rng.integers(W)), int(rng.integers(H))
        t.put(x, y, RUST[int(rng.integers(0, 3))])
    # fine grain: scratches, pits, rust blooming in patches
    g = np.random.default_rng(seed + 7000)
    look = ramp_look(IRON)
    plate = np.ones((H, W), bool)
    for gx in (4, 20):
        for gy in (4, 20):
            plate[gy:gy + 2, gx:gx + 2] = False
    hairlines(t, g, look, 9, 3, 6, d=1, dh=0.0, hi=4, mask=plate, wander=0.9)
    pits(t, g, look, 12, mask=plate)
    bloom = value_noise(g, W, H, 8) > 0.66
    r = g.random((H, W))
    for y, x in np.argwhere(bloom & (r < 0.3)):
        paint(t, x, y, RUST[0] if r[y, x] < 0.2 else RUST[1], look=look, mask=plate)
    return t


def stone_dark(seed):
    """Rough coursed granite, 128 x 128: big squarish blocks in grey-brown tones, sooty and rain-streaked, moss in
    the lower joints. The heavy lower courses and the top levels' walls."""
    G1 = (GRANITE[1], GRANITE[2], GRANITE[3], GRANITE[4]); G2 = (GRANITE[0], GRANITE[1], GRANITE[2], GRANITE[3])
    G3 = (GRANITE[2], GRANITE[3], GRANITE[4], GRANITE[5]); G4 = (GRANITE[1], GRANITE[2], GRANITE[2], GRANITE[3])
    t = ashlar(seed, [12, 10, 14, 12, 10, 14, 12, 10, 12, 12, 10], 12, 26, [G1, G2, G3, G4], [0.38, 0.22, 0.2, 0.2],
               chip=0.8, missing=0, stains=0)
    rng = np.random.default_rng(seed + 1)
    joint = np.all(t.c == SAND[0], axis=-1)
    gap = GRANITE[0] // 2 + DARK[1] // 2
    t.c[joint] = gap
    stone_detail(t, seed + 7000, (GRANITE,), gap, speck=0.085, pit=90, cracks=34, crack_len=(3, 10), drip=60, grit=0.24,
                 crumb=0.07, moss=0.6, lichen=16)                   # the fine grain, before the stains run over it
    stain(t, rng, 30, DARK[1], lo=6, hi=22, amt=0.35)               # soot and rain
    for _ in range(70):                                             # moss and lichen flecks
        x, y = int(rng.integers(t.w)), int(rng.integers(t.h))
        t.put(x, y, mix(GRANITE[2], GRASS_MOSS[3], 0.6) if rng.random() < 0.6 else mix(GRANITE[4], rgb("#b0ab84"), 0.4))
    return t


def timber_frame(seed):
    """Half-timbering, 64 x 64 (256 x 256 cm, one storey): dark oak posts every 32 texels, a sill at the bottom, a
    mid rail, a brace in some panels; lime plaster panels between, grimy at the edges, cracked and patched."""
    rng = np.random.default_rng(seed)
    W = H = 64
    t = Tile(W, H, PLASTER[4])
    n = value_noise(rng, W, H, 8)
    t.c[n < 0.3] = PLASTER[3]
    t.c[n > 0.8] = PLASTER[5]
    oak = set()

    def beam_px(x, y, tone):
        t.put(x, y, OAK[tone], 1.0); oak.add((x % W, y % H))
    for x in list(range(0, 4)) + list(range(32, 36)):               # posts
        for y in range(H):
            beam_px(x, y, 2 if x % 32 in (1, 2) else (3 if x % 32 == 0 else 1))
    for y in list(range(0, 4)) + list(range(30, 33)):               # sill / mid rail
        for x in range(W):
            beam_px(x, y, 2 if y in (1, 2, 31) else (3 if y in (0, 30) else 1))
    for (px, up) in ((4, True), (36, False)):                       # braces in the lower panels
        for d in range(28):
            for w in range(3):
                x = px + d
                y = (59 - d) if up else (33 + d)
                beam_px(x, y - w if up else y + w, 2 if w == 1 else 1)
    for _ in range(40):                                             # grain in the oak
        x, y = int(rng.integers(W)), int(rng.integers(H))
        if (x, y) in oak:
            t.put(x, y, OAK[0] if rng.random() < 0.6 else OAK[4])
    for (x, y) in list(oak):                                        # grime on the plaster beside the timbers
        for dx, dy in ((1, 0), (-1, 0), (0, 1)):
            q = ((x + dx) % W, (y + dy) % H)
            if q not in oak and rng.random() < 0.5:
                t.put(q[0], q[1], PLASTER[2])
    for _ in range(6):                                              # cracks
        x, y = int(rng.integers(W)), int(rng.integers(H))
        for d in range(int(rng.integers(3, 9))):
            if (x % W, y % H) not in oak:
                t.put(x, y, PLASTER[1])
            x += int(rng.choice([0, 1])); y += 1
    # fine grain: sandy, pitted, crazed daub with dirt hanging under every timber; fibres, splits and pegs in the oak
    g = np.random.default_rng(seed + 7000)
    look = ramp_look(PLASTER); wood = ramp_look(OAK)
    daub = np.ones((H, W), bool)
    for (x, y) in oak:
        daub[y, x] = False
    speckle(t, g, look, 0.085, dh=0.04, lo=3, hi=5, mask=daub)
    pits(t, g, look, 34, lo=1, mask=daub)
    hairlines(t, g, look, 12, 3, 8, d=-2, lo=1, hi=4, mask=daub)
    drips(t, g, look, np.argwhere(daub & ~np.roll(daub, 1, 0)), 46, 1, 6, lo=2, mask=daub)
    flecks(t, g, 5, [mix(PLASTER[3], LICHEN, 0.5)], look=look, mask=daub, lmax=2)
    posts = np.zeros((H, W), bool); rails = np.zeros((H, W), bool)
    posts[:, 0:4] = True; posts[:, 32:36] = True
    rails[0:4] = True; rails[30:33] = True
    dashes(t, g, wood, 26, 2, 6, vertical=True, mask=posts & ~rails)
    dashes(t, g, wood, 30, 2, 6, mask=rails & ~posts)
    dashes(t, g, wood, 4, 6, 12, vertical=True, dark=1.0, d=2, mask=posts & ~rails)
    speckle(t, g, wood, 0.08, dark=0.7, dh=0.0, mask=~daub & ~posts & ~rails)        # the braces
    for px in (1, 33):                                              # pegs where the rails meet the posts
        for py in (1, 31):
            t.put(px, py, OAK[0], 0.8); t.put(px + 1, py, OAK[4], 1.0)
    return t


LEVEL_FLAG_CELL = (32, 64)    # texels per digit cell in T_Bld_LevelFlag (bldkit.Kit.level_flag reads the same layout)
DIGITS = {
    "1": ["..1..", ".11..", "..1..", "..1..", "..1..", "..1..", ".111."],
    "2": [".111.", "1...1", "....1", "...1.", "..1..", ".1...", "11111"],
    "3": ["1111.", "....1", "....1", ".111.", "....1", "....1", "1111."],
    "4": ["...1.", "..11.", ".1.1.", "1..1.", "11111", "...1.", "...1."],
    "5": ["11111", "1....", "1111.", "....1", "....1", "1...1", ".111."],
    "6": ["..11.", ".1...", "1....", "1111.", "1...1", "1...1", ".111."],
    "7": ["11111", "....1", "...1.", "..1..", ".1...", ".1...", ".1..."],
}


def level_flag(seed):
    """The building level banner, 256 x 64 RGBA: eight 32 x 64 cells, cell n carries the numeral n (cell 0 none).
    The cloth is 23 x 48 texels (92 x 192 cm) at the cell's x 4..26, swallow-tailed below y 40. Field in team colour
    (grey, alpha TEAM), a woven gold border, and the numeral 3 texels to the pixel in cream with a dark outline
    (alpha 255), so it reads on either team's colour from the far camera."""
    CW, CH = LEVEL_FLAG_CELL
    t = Tile(CW * 8, CH, GREY[2], alpha=True)
    gold = [BRONZE[2], BRONZE[4], BRONZE[5]]
    x0, w, h = 4, 23, 48
    for cell in range(8):
        ox = cell * CW
        for y in range(h):
            notch = max(0, y - 39)
            for x in range(w):
                if abs(x - (w - 1) / 2) < notch * 1.25:
                    continue
                c, a = GREY[2], TEAM
                if x in (5, 17):
                    c = GREY[1]                               # folds
                if x in (6, 16) and y % 7 < 5:
                    c = GREY[3]
                if x in (0, w - 1) or y == 0:
                    c, a = gold[1], 255
                if x in (1, w - 2) or y in (1, 2):
                    c, a = gold[0], 255
                if y == 0 and x % 2:
                    c, a = gold[2], 255
                if y == 2:
                    c, a = (gold[1], 255) if x % 3 else (BRONZE[1], 255)
                put_a(t, ox + x0 + x, y, c, a)
        rows = DIGITS.get(str(cell))
        if not rows:
            continue
        S = 3
        nx, ny = ox + x0 + (w - 5 * S) // 2, 9
        ink = set()
        for j, row in enumerate(rows):
            for i, ch in enumerate(row):
                if ch == "1":
                    for dy in range(S):
                        for dx in range(S):
                            ink.add((nx + i * S + dx, ny + j * S + dy))
        for (x, y) in ink:                                    # dark outline, then the cream numeral
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    q = (x + dx, y + dy)
                    if q not in ink:
                        put_a(t, q[0], q[1], DARK[2], 255)
        for (x, y) in ink:
            lit = (x - nx) % S == 0 or (y - ny) % S == 0       # a lighter edge on each pixel block: a woven, stitched look
            put_a(t, x, y, CREAM[3] if not lit else (250, 244, 222), 255)
    return t


def build():
    os.makedirs(OUT, exist_ok=True)
    os.makedirs(PREVIEW, exist_ok=True)
    A = (SAND[2], SAND[3], SAND[4], SAND[5]); B = (SAND[1], SAND[2], SAND[3], SAND[4]); C = (SAND[2], SAND[3], SAND[4], SAND[4])
    R = (ROSE[2], ROSE[3], ROSE[4], ROSE[5]); P = (PALE[2], PALE[3], PALE[4], PALE[5]); D = (SAND[0], SAND[1], SAND[2], SAND[3])
    brick = mudbrick(111)
    tiles = {
        # curtain walls: mixed course heights, long and short blocks
        "T_Bld_Ashlar": ashlar(101, [8, 8, 10, 6, 8, 8, 8, 10, 6, 8, 8, 8, 10, 6, 8, 8], 10, 22, [A, B, C, R, P], [0.4, 0.17, 0.18, 0.13, 0.12], missing=0, holes=3,
                               detail=dict(cracks=30, crack_len=(2, 6), soot=7)),
        # towers and the battered base: big, darker, more weathered blocks
        "T_Bld_AshlarLarge": ashlar(102, [16, 14, 18, 16, 16, 14, 18, 16], 20, 34, [B, C, D, R, A], [0.36, 0.22, 0.14, 0.12, 0.16], chip=0.7, missing=0, stains=22,
                                    detail=dict(speck=0.08, pit=95, cracks=30, crack_len=(4, 12), drip=50, grit=0.24, moss=0.62, lichen=14, soot=12)),
        "T_Bld_Trim": trim(103),
        "T_Bld_Mudbrick": brick,
        "T_Bld_Plaster": plaster(112, brick),
        "T_Bld_RoofClay": roof_clay(113),
        "T_Bld_Beam": beam(121),
        "T_Bld_Planks": planks(122),
        "T_Bld_Door": door(123),
        "T_Bld_Shutter": shutter(124),
        "T_Bld_Thatch": thatch(131),
        "T_Bld_Soil": soil(132),
        "T_Bld_Wheat": wheat(133),
        "T_Bld_Banner": banner(141),
        "T_Bld_Awning": awning(142),
        "T_Bld_Frieze": frieze(143),
        "T_Bld_Bronze": bronze(144),
        "T_Bld_Ore": ore(151),
        "T_Bld_Gold": gold(156),
        "T_Bld_Pot": pot(152),
        "T_Bld_Leaves": leaves(153),
        "T_Bld_Flame": flame(154),
        "T_Bld_Dark": dark(155),
        "T_Bld_Char": char(161),
        "T_Bld_Scorch": scorch(162),
        "T_Bld_Target": target(163),
        "T_Bld_RoofTile": roof_tile(164),
        "T_Bld_Water": water(165),
        "T_Bld_LevelFlag": level_flag(166),
        "T_Bld_Slate": slate(167),
        "T_Bld_Iron": iron(168),
        "T_Bld_StoneDark": stone_dark(169),
        "T_Bld_Timber": timber_frame(170),
    }
    normals = {"T_Bld_Ashlar": 1.7, "T_Bld_AshlarLarge": 1.9, "T_Bld_Trim": 1.4, "T_Bld_Mudbrick": 1.3, "T_Bld_Plaster": 1.2,
               "T_Bld_RoofClay": 1.0, "T_Bld_Thatch": 1.6, "T_Bld_Soil": 1.8,
               "T_Bld_RoofTile": 1.5, "T_Bld_Slate": 1.6, "T_Bld_StoneDark": 1.9, "T_Bld_Timber": 1.2}
    for name, t in tiles.items():
        t.image().save(os.path.join(OUT, name + ".png"))
        if name in normals:
            t.normal_image(normals[name]).save(os.path.join(OUT, name + "_N.png"))
    Image.fromarray(np.full((4, 4, 3), (128, 128, 255), np.uint8)).save(os.path.join(OUT, "T_Bld_Flat_N.png"))
    # contact sheet: every tile 2 x 2 (seams), 3x nearest, on a dark ground; masks shown as-is
    cells = []
    for name, t in tiles.items():
        im = t.image().convert("RGBA")
        if t.a is not None:
            arr = np.array(im)
            arr[..., 3] = np.where(arr[..., 3] > 0, 255, 0)
            im = Image.fromarray(arr)
        bg = Image.new("RGBA", im.size, (52, 46, 70, 255))
        bg.alpha_composite(im)
        rep = Image.new("RGBA", (im.width * 2, im.height * 2))
        for j in range(2):
            for i in range(2):
                rep.paste(bg, (i * im.width, j * im.height))
        k = 3 if im.width >= 64 else 6
        big = rep.resize((rep.width * k, rep.height * k), Image.NEAREST).convert("RGB")
        big.save(os.path.join(PREVIEW, name + ".png"))
        cells.append(big)
    w = sum(c.width + 8 for c in cells[:8])
    rows = [cells[i:i + 6] for i in range(0, len(cells), 6)]
    sheet = Image.new("RGB", (max(sum(c.width + 8 for c in r) for r in rows), sum(max(c.height for c in r) + 8 for r in rows)), (30, 28, 40))
    y = 0
    for r in rows:
        x = 0
        for c in r:
            sheet.paste(c, (x, y)); x += c.width + 8
        y += max(c.height for c in r) + 8
    sheet.save(os.path.join(PREVIEW, "buildings_sheet.png"))
    print("wrote %d building textures to %s" % (len(tiles) + len(normals) + 1, OUT))


if __name__ == "__main__":
    build()
