"""Battlefield FX flipbooks and the catapult stone, drawn procedurally in the troops' pixel style.

    Tools/.venv/bin/python Tools/blender/make_fx.py

Writes  SourceArt/FX/fx_<name>.png      one horizontal strip, RGBA, alpha 0 or 255 only
        SourceArt/FX/fx_<name>.json     frame size, frame count, fps, loop, pivot, scale
        SourceArt/FX/previews/          x4 strips on olive and sand, and a GIF at game speed
        SourceArt/Characters/stone_color.png, stone_teammask.png              the catapult stone (like the arrow)
        SourceArt/Characters/stone_smear_color.png, stone_smear_teammask.png  the same with a motion smear, flying +X
        SourceArt/Characters/stone.json

Everything is made of a few soft blobs per frame, thresholded into flat bands of a hand-picked ramp (the same
ramps as srmats.py where a material exists: stone, wood, leather_dark), lit from the top-left like the sprites,
with the troops' dark plum outline on solid chips and none on fire, smoke and dust. No blending, no soft alpha:
a frame is a handful of flat colours, so it sits with the sprites at 1.75 cm per pixel.
"""

import json
import math
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
OUT = os.path.join(ROOT, "SourceArt", "FX")
PREV = os.path.join(OUT, "previews")
CHAR = os.path.join(ROOT, "SourceArt", "Characters")

import srmats  # noqa: E402

CM_PER_PX = 1.75
OUTLINE = srmats.hex_to_rgb(srmats.OUTLINE)


def ramp(*hexes):
    return [srmats.hex_to_rgb(h) for h in hexes]


FIRE = ramp("#6a1f1c", "#a8321a", "#dc5a18", "#f58f1e", "#fdc93c", "#fff2a8")
SMOKE = ramp("#1f181d", "#342b2f", "#4b4144", "#655a58")
DUST = ramp("#6e5d4a", "#96826a", "#bba88a", "#dccdac")
DIRT = ramp("#1a1218", "#2b1d1f", "#412d28", "#594032", "#755642")          # srmats leather_dark
STONE = ramp(*srmats.BY_NAME["stone"]["ramp"])
WOOD = ramp(*srmats.BY_NAME["wood"]["ramp"])
FLASH = ramp("#f3e6c0", "#fffbea")                                           # srmats smear


def grid(w, h):
    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    return x + 0.5, y + 0.5


def blobs_field(w, h, blobs):
    """Sum of soft discs. blobs = [(x, y, r)] or [(x, y, r, tall)]: tall > 1 stretches the disc upward."""
    x, y = grid(w, h)
    f = np.zeros((h, w), np.float32)
    for bl in blobs:
        bx, by, r = bl[:3]
        tall = bl[3] if len(bl) > 3 else 1.0
        if r <= 0.3:
            continue
        f += np.clip(1.0 - ((x - bx) ** 2 + ((y - by) / tall) ** 2) / (r * r), 0, 1)
    return f


def paint_bands(img, value, thresholds, colours):
    """value >= thresholds[k] -> colours[k]; below thresholds[0] stays empty."""
    for t, c in zip(thresholds, colours):
        m = value >= t
        img[m, :3] = c
        img[m, 3] = 255


def despeckle(img):
    """Drop opaque pixels with no opaque 4-neighbour."""
    a = img[..., 3] > 0
    p = np.pad(a, 1)
    n = p[:-2, 1:-1] | p[2:, 1:-1] | p[1:-1, :-2] | p[1:-1, 2:]
    img[a & ~n] = 0
    return img


def outline(img, colour=OUTLINE):
    a = img[..., 3] > 0
    p = np.pad(a, 1)
    n = p[:-2, 1:-1] | p[2:, 1:-1] | p[1:-1, :-2] | p[1:-1, 2:]
    ring = n & ~a
    img[ring, :3] = colour
    img[ring, 3] = 255
    return img


def puffs(w, h, items, pal, light=(-0.6, -0.75)):
    """Round puffs shaded like little spheres from the top-left. items = [(x, y, r)]. Later items draw on top."""
    img = np.zeros((h, w, 4), np.uint8)
    x, y = grid(w, h)
    for bx, by, r in items:
        if r < 0.8:
            continue
        d2 = ((x - bx) ** 2 + (y - by) ** 2) / (r * r)
        inside = d2 <= 1.0
        hx, hy = bx + light[0] * r * 0.42, by + light[1] * r * 0.42     # highlight centre, toward the light
        s = 1.0 - np.sqrt((x - hx) ** 2 + (y - hy) ** 2) / r
        band = np.digitize(s, [-0.12, 0.25, 0.62])                      # 0 dark .. 3 light
        band = np.minimum(band, len(pal) - 1)
        for k in range(len(pal)):
            m = inside & (band == k)
            img[m, :3] = pal[k]
            img[m, 3] = 255
    return img


def dissolve(img, amount, seed=0):
    """Ordered-dither holes for a fade without soft alpha. amount 0 = solid, 1 = gone."""
    if amount <= 0:
        return img
    bayer = np.array([[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]], np.float32) / 16.0
    h, w = img.shape[:2]
    t = np.tile(bayer, (h // 4 + 1, w // 4 + 1))[:h, :w]
    t = np.roll(t, seed, 1)
    img[t < amount] = 0
    return img


def chip(img, cx, cy, r, pal, seed, ang=None, long=1.0):
    """A small solid chip: a lumpy stone (ang None) or a splinter of length `long` x r at angle ang."""
    h, w = img.shape[:2]
    x, y = grid(w, h)
    dx, dy = x - cx, y - cy
    if ang is None:
        th = np.arctan2(dy, dx)
        rr = r * (1 + 0.20 * np.sin(3 * th + seed) + 0.12 * np.sin(5 * th + seed * 2.3))
        inside = dx * dx + dy * dy <= rr * rr
    else:
        ca, sa = math.cos(ang), math.sin(ang)
        u, v = dx * ca + dy * sa, -dx * sa + dy * ca
        inside = (np.abs(u) <= r * long) & (np.abs(v) <= max(r * 0.42, 0.75))
    s = (dx * -0.6 + dy * -0.75) / max(r, 1.0)
    band = np.clip(np.digitize(s, [-0.35, 0.25]) + (len(pal) - 3) // 2, 0, len(pal) - 1)
    for k in range(len(pal)):
        m = inside & (band == k)
        img[m, :3] = pal[k]
        img[m, 3] = 255


def over(dst, src):
    m = src[..., 3] > 0
    dst[m] = src[m]
    return dst


# ---------------------------------------------------------------------------------------------- fire

def fx_fire(n=8, w=64, h=96):
    """Looping flames for a burning building. Tongues are born at the base and rise once per loop."""
    rng = np.random.default_rng(11)
    tongues = [(rng.uniform(0, 1), rng.uniform(-15, 15), rng.uniform(0.75, 1.15)) for _ in range(9)]
    sparks = [(rng.uniform(0, 1), rng.uniform(-14, 14), rng.uniform(0.7, 1.0)) for _ in range(6)]
    frames = []
    x, y = grid(w, h)
    for i in range(n):
        t = i / n
        bl = [(32 + 2.5 * math.sin(2 * math.pi * t), 82, 15), (22 + 2 * math.sin(2 * math.pi * (t + 0.3)), 84, 11),
              (43 + 2 * math.sin(2 * math.pi * (t + 0.6)), 84, 11)]
        for ph, x0, k in tongues:
            u = (t + ph) % 1.0
            bx = 32 + x0 * (1 - 0.55 * u) + 5.0 * u * math.sin(2 * math.pi * (1.5 * u + ph))
            by = 82 - 64 * k * u ** 0.85
            bl.append((bx, by, 10.5 * (1 - u) ** 0.8 + 1.2, 1.9))
        f = blobs_field(w, h, bl)
        heat = f * (0.45 + 0.75 * (y / h))                       # hotter toward the base
        img = np.zeros((h, w, 4), np.uint8)
        paint_bands(img, heat, [0.16, 0.34, 0.60, 1.0, 1.55, 2.3], FIRE)
        img[int(88):, :] = 0                                     # flat base: it sits on a wall top / ground line
        despeckle(img)
        for ph, x0, k in sparks:
            u = (t + ph) % 1.0
            sx = int(32 + x0 + 6 * math.sin(2 * math.pi * (u + ph)))
            sy = int(70 - 62 * k * u)
            if 0 <= sx < w and 2 <= sy < h and u < 0.85:
                img[sy, sx] = (*FIRE[4 if u < 0.5 else 2], 255)
        frames.append(img)
    return frames, dict(fps=10, loop=True, pivot_px=[32, 88],
                        notes="Flames for a burning building. Pivot = base centre. Unlit / emissive in the material.")


# ---------------------------------------------------------------------------------------------- smoke

def fx_smoke(n=8, w=64, h=96):
    """Looping dark smoke column. Each puff is born small at the base, swells as it climbs, thins out at the top."""
    rng = np.random.default_rng(5)
    ps = [((k + rng.uniform(-0.2, 0.2)) / 7.0, rng.uniform(-5, 5), rng.uniform(0.85, 1.1)) for k in range(7)]
    frames = []
    for i in range(n):
        t = i / n
        items = []
        for ph, x0, k in ps:
            u = (t + ph) % 1.0
            grow = min(1.0, u / 0.15)
            fade = 1.0 if u < 0.72 else max(0.0, 1 - (u - 0.72) / 0.28) ** 0.6
            r = (5.5 + 11.5 * u ** 0.7) * k * grow * fade
            bx = 27 + x0 + 12 * u + 3.5 * math.sin(2 * math.pi * (u + ph))
            by = 84 - 70 * u
            items.append((u, bx, by, r))
        items.sort(key=lambda it: -it[0])                         # oldest (highest) first, young puffs on top
        img = despeckle(puffs(w, h, [(bx, by, r) for _, bx, by, r in items], SMOKE))
        # the top of the column breaks up instead of ending in a hard ball
        top = np.zeros((h, w), np.float32)
        top[:26, :] = np.linspace(0.75, 0.0, 26)[:, None]
        bayer = np.tile(np.array([[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]], np.float32) / 16.0,
                        (h // 4, w // 4))
        img[bayer < top] = 0
        frames.append(img)
    return frames, dict(fps=8, loop=True, pivot_px=[32, 88],
                        notes="Dark smoke column for a burning or ruined building. Pivot = base centre. Drifts to +X.")


# ---------------------------------------------------------------------------------------------- dust

def fx_dust(n=6, w=64, h=40):
    """One-shot dust puff: hooves, footfalls, a stone landing. Spreads low along the ground and breaks up."""
    rng = np.random.default_rng(3)
    ps = [(rng.uniform(-1, 1), rng.uniform(0.2, 1.0), rng.uniform(0.8, 1.2)) for _ in range(8)]
    frames = []
    for i in range(n):
        t = (i + 0.4) / n
        e = 1 - (1 - t) ** 2.2
        items = []
        for d, up, k in ps:
            r = k * (3.5 + 6.5 * min(1.0, t / 0.45)) * (1.0 if t < 0.55 else max(0.0, 1 - (t - 0.55) / 0.9) ** 0.7)
            items.append((32 + d * 21 * e, 31 - up * 11 * e - r * 0.35, r))
        items.sort(key=lambda it: it[1])
        img = puffs(w, h, items, DUST)
        img[34:, :] = 0
        despeckle(img)
        dissolve(img, max(0.0, (t - 0.45) / 0.55) * 0.9, seed=i)
        frames.append(img)
    return frames, dict(fps=12, loop=False, pivot_px=[32, 33],
                        notes="Dust puff for hooves, footfalls and impacts. Pivot = the ground point. Scale it up for a stone impact.")


# ---------------------------------------------------------------------------------------------- debris

def ballistic(rng, count, speed, up, grav, spread=math.pi):
    out = []
    for _ in range(count):
        a = -math.pi / 2 + rng.uniform(-spread / 2, spread / 2)
        v = rng.uniform(*speed)
        out.append(dict(vx=math.cos(a) * v, vy=math.sin(a) * v * up, g=grav, r=rng.uniform(1.2, 2.8),
                        seed=rng.uniform(0, 6.28), spin=rng.uniform(-9, 9), kind=rng.integers(0, 3)))
    return out


def fx_debris(n=6, w=96, h=96):
    """One-shot: stone and wood chips bursting from a struck building. Pivot = the point that was hit."""
    rng = np.random.default_rng(21)
    parts = ballistic(rng, 16, (40, 120), 1.0, 300.0, spread=math.pi * 1.15)
    cx, cy = 48, 60
    frames = []
    for i in range(n):
        t = (i + 0.35) / 12.0
        img = np.zeros((h, w, 4), np.uint8)
        # a short puff of mortar dust at the hit point
        if i < 4:
            k = [1.0, 1.25, 1.1, 0.7][i]
            d = puffs(w, h, [(cx - 6 - 2 * i, cy - 1 - i, 5 * k), (cx + 6 + 2 * i, cy - 2 - i, 5.5 * k), (cx, cy - 5 - 2 * i, 6.5 * k)], DUST)
            dissolve(d, [0.0, 0.15, 0.45, 0.72][i], seed=i)
            over(img, d)
        chips = np.zeros((h, w, 4), np.uint8)
        for j, p in enumerate(parts):
            if i == n - 1 and j % 3 == 0:
                continue                                           # the burst thins out on the last frame
            px = cx + p["vx"] * t
            py = cy + p["vy"] * t + 0.5 * p["g"] * t * t
            r = p["r"] * (1.0 if i < 4 else 0.8)
            if p["kind"] == 0:
                chip(chips, px, py, r, WOOD[1:6], p["seed"], ang=p["seed"] + p["spin"] * t, long=2.2)
            else:
                chip(chips, px, py, r, STONE[1:6], p["seed"])
        over(img, outline(chips))
        if i == 0:
            fl = np.zeros((h, w, 4), np.uint8)
            paint_bands(fl, blobs_field(w, h, [(cx, cy, 7)]), [0.15, 0.6], FLASH)
            over(img, fl)
        frames.append(img)
    return frames, dict(fps=12, loop=False, pivot_px=[cx, cy],
                        notes="Stone and wood chips from a struck building. Pivot = the hit point on the wall.")


# ---------------------------------------------------------------------------------------------- impact

def fx_impact(n=6, w=128, h=96):
    """One-shot: a catapult stone hits the ground. Flash, a jet of dirt, clods thrown up and out, a low dust ring."""
    rng = np.random.default_rng(8)
    clods = ballistic(rng, 20, (60, 190), 1.0, 520.0, spread=math.pi * 0.95)
    ring = [(rng.uniform(0, 2 * math.pi), rng.uniform(0.8, 1.2)) for _ in range(12)]
    cx, cy = 64, 78
    frames = []
    for i in range(n):
        t = (i + 0.35) / 12.0
        u = (i + 0.4) / n
        e = 1 - (1 - u) ** 2.0
        img = np.zeros((h, w, 4), np.uint8)
        # dust ring: puffs on an ellipse on the ground, far side first
        items = []
        for a, k in ring:
            R = 9 + 37 * e
            r = k * (4.5 + 5.5 * min(1.0, u / 0.4)) * (1.0 if u < 0.55 else max(0.0, 1 - (u - 0.55) / 0.55) ** 0.7)
            items.append((cx + math.cos(a) * R, cy + math.sin(a) * R * 0.34 - r * 0.45, r))
        items.sort(key=lambda it: it[1])
        d = puffs(w, h, items, DUST)
        d[cy + 8:, :] = 0
        dissolve(d, max(0.0, (u - 0.45) / 0.55) * 0.85, seed=i)
        over(img, d)
        # the jet of dirt thrown straight up, tallest on frame 1
        jet_h = [16, 34, 40, 30, 0, 0][i]
        if jet_h:
            js = [(cx + 2.5 * math.sin(k * 1.9 + i), cy - 2 - jet_h * k / 5.0, (7.5 - 0.9 * k) * [1, 1, 0.85, 0.55, 0, 0][i])
                  for k in range(6)]
            j = puffs(w, h, js, DIRT[1:5])
            dissolve(j, [0.0, 0.0, 0.2, 0.55, 1, 1][i], seed=i + 2)
            over(img, j)
        cl = np.zeros((h, w, 4), np.uint8)
        for jn, p in enumerate(clods):
            px = cx + p["vx"] * t * 0.9
            py = cy - 3 + p["vy"] * t + 0.5 * p["g"] * t * t
            if py > cy + 6 + (jn % 5) or (i == n - 1 and jn % 2 == 0):
                continue                                           # landed
            if p["kind"] == 2:
                chip(cl, px, py, p["r"] * 0.9, STONE[1:6], p["seed"])
            else:
                chip(cl, px, py, p["r"] * 1.15, DIRT[1:5], p["seed"])
        over(img, outline(cl))
        if i == 0:
            fl = np.zeros((h, w, 4), np.uint8)
            x, y = grid(w, h)
            star = np.clip(1 - (((x - cx) / 20.0) ** 2 + ((y - cy) / 7.0) ** 2), 0, 1) + \
                np.clip(1 - (((x - cx) / 6.0) ** 2 + ((y - cy + 8) / 16.0) ** 2), 0, 1)
            paint_bands(fl, star, [0.12, 0.5], FLASH)
            over(img, fl)
        frames.append(img)
    return frames, dict(fps=12, loop=False, pivot_px=[cx, cy],
                        notes="Catapult stone hitting the ground: flash, dirt jet, clods, dust ring. Pivot = the impact point.")


# ---------------------------------------------------------------------------------------------- stone projectile

def stone_sprite():
    """The catapult's stone, about 30 cm across at the troops' scale (oversized, like the arrow, so it reads far out).
    Two files: the stone alone, and the stone flying toward +X with a short broken smear behind it."""
    def rock(w, h, cx, cy):
        img = np.zeros((h, w, 4), np.uint8)
        x, y = grid(w, h)
        dx, dy = x - cx, y - cy
        th = np.arctan2(dy, dx)
        rr = 7.6 * (1 + 0.10 * np.sin(3 * th + 0.7) + 0.07 * np.sin(5 * th + 2.1) + 0.05 * np.sin(2 * th + 4.0))
        inside = dx * dx + dy * dy <= rr * rr
        s = (dx * -0.55 + dy * -0.75) / 7.6 + 0.10 * np.sin(dx * 1.3 + dy * 0.7) * (np.abs(dx + dy) % 3 < 1)
        band = np.digitize(s, [-0.55, -0.15, 0.25, 0.62])
        pal = STONE[0:5] if False else [STONE[1], STONE[2], STONE[3], STONE[4], STONE[5]]
        for k in range(5):
            m = inside & (band == k)
            img[m, :3] = pal[k]
            img[m, 3] = 255
        # two cracks / pits so it is a rock and not a ball
        for px, py in ((cx + 1, cy + 2), (cx + 2, cy + 3), (cx - 3, cy - 1), (cx + 3, cy - 3)):
            if inside[int(py), int(px)]:
                img[int(py), int(px), :3] = STONE[1]
        return outline(img)

    plain = rock(20, 20, 10, 10)
    sm = np.zeros((20, 44, 4), np.uint8)
    for row, (x0, x1, c) in {5: (16, 26, 1), 7: (8, 27, 0), 9: (3, 27, 1), 10: (6, 27, 0), 12: (10, 27, 1), 14: (17, 26, 0)}.items():
        for xx in range(x0, x1):
            if (xx + row) % 5 != 0 or xx > 20:                     # broken toward the tail
                sm[row, xx] = (*[STONE[5], STONE[4]][c], 255)
    over(sm, rock(44, 20, 33, 10))
    Image.fromarray(plain).save(os.path.join(CHAR, "stone_color.png"))
    Image.fromarray(np.zeros((20, 20), np.uint8)).save(os.path.join(CHAR, "stone_teammask.png"))
    Image.fromarray(sm).save(os.path.join(CHAR, "stone_smear_color.png"))
    Image.fromarray(np.zeros((20, 44), np.uint8)).save(os.path.join(CHAR, "stone_smear_teammask.png"))
    meta = dict(name="stone", cm_per_px=CM_PER_PX,
                stone=dict(color="stone_color.png", teammask="stone_teammask.png", size_px=[20, 20],
                           size_cm=[20 * CM_PER_PX, 20 * CM_PER_PX], pivot_px=[10, 10]),
                smear=dict(color="stone_smear_color.png", teammask="stone_smear_teammask.png", size_px=[44, 20],
                           size_cm=[44 * CM_PER_PX, 20 * CM_PER_PX], pivot_px=[33, 10],
                           notes="Flying toward +X (like arrow_color.png). Pivot = the stone's centre. Use while it is "
                                 "moving fast, or alternate with the plain stone."),
                team="The mask is empty: the stone is not tinted. It exists so the stone can use the arrow's material.",
                notes="Spawn at catapult.json projectile_origin_cm on attack frame 5.")
    with open(os.path.join(CHAR, "stone.json"), "w") as f:
        json.dump(meta, f, indent=2)
        f.write("\n")
    return plain, sm


# ---------------------------------------------------------------------------------------------- output

def ground(w, h, base, seed=3):
    rng = np.random.default_rng(seed)
    n1 = rng.random((h // 8 + 2, w // 8 + 2)).repeat(8, 0).repeat(8, 1)[:h, :w]
    n2 = rng.random((h // 2 + 1, w // 2 + 1)).repeat(2, 0).repeat(2, 1)[:h, :w]
    v = np.rint(((n1 - 0.5) * 0.10 + (n2 - 0.5) * 0.10) * 14) / 14
    return Image.fromarray(np.clip(np.array(base, np.float32)[None, None, :] * (1 + v[..., None]), 0, 255).astype(np.uint8))


def write(name, frames, info):
    h, w = frames[0].shape[:2]
    strip = np.concatenate(frames, 1)
    assert set(np.unique(strip[..., 3])) <= {0, 255}
    Image.fromarray(strip).save(os.path.join(OUT, name + ".png"), optimize=True)
    touch = [i for i, f in enumerate(frames) if (f[0, :, 3].any() or f[-1, :, 3].any() or f[:, 0, 3].any() or f[:, -1, 3].any())]
    cols = np.unique(strip[strip[..., 3] > 0][:, :3], axis=0)
    meta = dict(name=name, file=name + ".png", layout="single horizontal strip, frame k at x = k * frame_size[0]",
                frame_size=[w, h], frames=len(frames), fps=info["fps"], loop=info["loop"],
                duration_s=round(len(frames) / info["fps"], 3), strip_size=[w * len(frames), h],
                pivot_px=info["pivot_px"], pivot_uv_in_frame=[info["pivot_px"][0] / w, info["pivot_px"][1] / h],
                cm_per_px=CM_PER_PX, quad_size_cm=[w * CM_PER_PX, h * CM_PER_PX],
                alpha="binary (0 or 255): masked material, nearest filtering, no mips, like the troop sheets",
                palette_size=int(len(cols)), notes=info["notes"])
    with open(os.path.join(OUT, name + ".json"), "w") as f:
        json.dump(meta, f, indent=2)
        f.write("\n")
    # previews
    k = 4
    prev = Image.new("RGB", (w * len(frames) * k, h * 2 * k))
    for r, base in enumerate(((104, 120, 64), (190, 166, 120))):
        g = ground(w * len(frames), h, base, seed=4 + r)
        g.paste(Image.fromarray(strip), (0, 0), Image.fromarray(strip))
        prev.paste(g.resize((g.width * k, g.height * k), Image.NEAREST), (0, r * h * k))
    prev.save(os.path.join(PREV, name + "_x4.png"))
    gifs = []
    for fr in frames:
        g = ground(w, h, (104, 120, 64), seed=4)
        g.paste(Image.fromarray(fr), (0, 0), Image.fromarray(fr))
        gifs.append(g.resize((w * k, h * k), Image.NEAREST).convert("P", palette=Image.ADAPTIVE, colors=64))
    dur = [int(round(100.0 / info["fps"])) * 10] * len(frames)
    if not info["loop"]:
        dur[-1] += 500
    gifs[0].save(os.path.join(PREV, name + ".gif"), save_all=True, append_images=gifs[1:], duration=dur, loop=0, disposal=1)
    print("%s: %d frames of %dx%d, %d fps, %d colours%s" % (name, len(frames), w, h, info["fps"], len(cols),
                                                           ("  PROBLEM: touches the frame edge on %s" % touch) if touch else ""))


def main():
    os.makedirs(PREV, exist_ok=True)
    for name, fn in (("fx_fire", fx_fire), ("fx_smoke", fx_smoke), ("fx_dust", fx_dust), ("fx_debris", fx_debris),
                     ("fx_impact", fx_impact)):
        write(name, *fn())
    plain, sm = stone_sprite()
    k = 8
    g = ground(80, 24, (104, 120, 64), seed=2)
    g.paste(Image.fromarray(plain), (4, 2), Image.fromarray(plain))
    g.paste(Image.fromarray(sm), (30, 2), Image.fromarray(sm))
    arrow = os.path.join(CHAR, "arrow_color.png")
    g.resize((g.width * k, g.height * k), Image.NEAREST).save(os.path.join(PREV, "stone_x8.png"))
    print("stone: 20x20 and 44x20 (smear)", "arrow present" if os.path.exists(arrow) else "")


if __name__ == "__main__":
    main()
