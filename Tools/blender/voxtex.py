"""Paints the tiling 64 x 64 pixel-art textures of the voxel style: SourceArt/Textures/T_Vox_<slot>.png

    Tools/.venv/bin/python Tools/blender/voxtex.py         (needs numpy + Pillow; not run inside Blender)

Every texture is albedo only (the light comes from the engine), tiles in both directions, and is laid out for
8 texels to a 50 cm block. Row 0 of the arrays here is the BOTTOM of the texture (v = 0), so "up" in the code is up
on a wall; the image is flipped when saved.
"""
import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import voxmats

N = voxmats.TEX_SIZE
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "SourceArt", "Textures")


def hexc(h):
    h = h.lstrip("#")
    return np.array([int(h[i:i + 2], 16) for i in (0, 2, 4)], dtype=np.float32)


SOFT = 0.5        # how much of a palette's spread is kept: the reference's blocks are calm faces with clean seams, not speckle


def pal(*hexes, k=None):
    """A palette, pulled towards its own mean so that the shades inside one surface stay close (k = 1 keeps them as written)."""
    c = np.stack([hexc(h) for h in hexes])
    k = SOFT if k is None else k
    return c.mean(axis=0, keepdims=True) * (1.0 - k) + c * k


def clumps(rng, weights, size=2, n=N):
    """Index map (n x n): random palette indices in clumps of roughly `size` texels, tiling."""
    w = np.asarray(weights, dtype=np.float64)
    w = w / w.sum()
    coarse = rng.choice(len(w), size=(n // size + 1, n // size + 1), p=w)
    idx = np.repeat(np.repeat(coarse, size, axis=0), size, axis=1)[:n, :n]
    # break the clump grid up: a third of the texels take their own value
    own = rng.choice(len(w), size=(n, n), p=w)
    take = rng.random((n, n)) < 0.16
    idx = np.where(take, own, idx)
    return idx


def mosaic(rng, colors, weights, size=2):
    return colors[clumps(rng, weights, size)]


def shade(img, amount):
    """amount: array (n, n) or scalar, multiplies brightness (1 = unchanged)."""
    return img * np.asarray(amount, dtype=np.float32)[..., None] if np.ndim(amount) else img * amount


def save(name, img):
    os.makedirs(OUT, exist_ok=True)
    arr = np.clip(np.round(img), 0, 255).astype(np.uint8)[::-1]          # row 0 = bottom -> flip for the file
    Image.fromarray(arr, "RGB").save(os.path.join(OUT, "T_Vox_%s.png" % name))


def block_edges(img, block=8, dark=0.80, light=1.10, offset_rows=False):
    """Darker bottom/right seam and lighter top/left edge on every block x block cell."""
    out = img.copy()
    for y in range(N):
        for x in range(N):
            bx = (x + (block // 2 if offset_rows and (y // block) % 2 else 0)) % block
            by = y % block
            f = 1.0
            if by == 0 or bx == block - 1:
                f = dark
            elif by == block - 1 or bx == 0:
                f = light
            out[y, x] *= f
    return out


def tex_stone(rng, mossy=False):
    cols = pal("#9b968b", "#aca79b", "#868178", "#a79e8e", "#9f9c95", "#79756e", k=0.7)
    img = np.zeros((N, N, 3), np.float32)
    for by in range(0, N, 8):
        for bx in range(0, N, 8):
            base = rng.choice(6, p=[0.34, 0.2, 0.14, 0.14, 0.12, 0.06])
            w = np.full(6, 0.06)
            w[base] = 0.62
            w[(base + 1) % 6] += 0.14
            idx = clumps(rng, w, 2, 8)
            img[by:by + 8, bx:bx + 8] = cols[idx] * rng.uniform(0.94, 1.06)
    moss = pal("#6f8f2c", "#84a836", "#5c7a26", k=1)
    spots = rng.random((N, N)) < (0.008 if not mossy else 0.03)
    img[spots] = moss[rng.integers(0, 3, spots.sum())]
    img = block_edges(img, 8, 0.74, 1.09)
    if mossy:                                             # moss hangs down from the top of every block
        mcol = pal("#79b021", "#8fc62c", "#63941d", "#a3d43a", k=0.8)
        for bx in range(0, N):
            for by in range(0, N, 8):
                drop = int(rng.choice([1, 2, 2, 3, 3, 4, 5, 6], p=[0.1, 0.18, 0.18, 0.16, 0.14, 0.12, 0.07, 0.05]))
                if (bx // 2) % 5 == 4:
                    drop = max(1, drop - 2)
                for k in range(drop):
                    img[by + 7 - k, bx] = mcol[rng.choice(4, p=[0.45, 0.25, 0.2, 0.1])] * (1.0 - 0.05 * k)
    return img


def tex_brick(rng):
    cols = pal("#a8a297", "#b7b1a5", "#948e84", "#ab9f8a", "#9c968e", "#847e75", k=0.7)
    img = np.zeros((N, N, 3), np.float32)
    for row in range(N // 4):
        off = 4 if row % 2 else 0
        for bx in range(0, N, 8):
            base = rng.choice(6, p=[0.36, 0.22, 0.14, 0.1, 0.12, 0.06])
            f = rng.uniform(0.94, 1.06)
            for dx in range(8):
                for dy in range(4):
                    x = (bx + dx + off) % N
                    y = row * 4 + dy
                    c = cols[base] if rng.random() > 0.2 else cols[rng.integers(0, 6)]
                    k = 1.0
                    if dy == 0 or dx == 7:
                        k = 0.72
                    elif dy == 3 or dx == 0:
                        k = 1.08
                    img[y, x] = c * f * k
    moss = pal("#6f8f2c", "#84a836", k=1)
    spots = rng.random((N, N)) < 0.005
    img[spots] = moss[rng.integers(0, 2, spots.sum())]
    return img


def tex_cobble(rng):
    cols = pal("#c0a27e", "#cfb28e", "#b0926e", "#dabf9b", "#a38560", "#c2a78c", "#c8a184", k=0.9)
    img = mosaic(rng, cols, [0.26, 0.2, 0.16, 0.1, 0.08, 0.1, 0.1], 2)
    # scattered stones: 3x3 and 4x3 pads with a light top-left and dark bottom-right pixel
    for _ in range(46):
        x, y = rng.integers(0, N, 2)
        w, h = rng.integers(3, 5), rng.integers(2, 4)
        c = cols[rng.integers(0, 7)] * rng.uniform(0.92, 1.1)
        for dy in range(h):
            for dx in range(w):
                k = 1.0
                if dy == 0 or dx == w - 1:
                    k = 0.82
                elif dy == h - 1 or dx == 0:
                    k = 1.08
                img[(y + dy) % N, (x + dx) % N] = c * k
    dark = rng.random((N, N)) < 0.03
    img[dark] *= 0.72
    return img


def tex_grass(rng):
    cols = pal("#4f7c29", "#5c8a2e", "#436e24", "#6c9834", "#3a621e", "#7ea83e", k=0.7)
    img = mosaic(rng, cols, [0.34, 0.26, 0.17, 0.12, 0.06, 0.05], 3)
    for _ in range(18):                                   # little blades: a light pixel over a dark one
        x, y = rng.integers(0, N, 2)
        img[y, x] = cols[4]
        img[(y + 1) % N, x] = cols[5]
    return img


def tex_dirt(rng):
    cols = pal("#8f6c40", "#9e7a4a", "#7c5c36", "#6c4e2c", "#ab8854", "#8a7050", k=0.7)
    img = mosaic(rng, cols, [0.32, 0.24, 0.2, 0.1, 0.08, 0.06], 2)
    return img


def tex_grass_side(rng):
    """The side of the turf. The ground is built of quarter blocks (4 texels), and only the top one is turf, so every
    4-texel band is one turf edge: grass hanging over earth."""
    img = tex_dirt(rng)
    g = pal("#4f7c29", "#5c8a2e", "#436e24", "#6c9834", k=0.8)
    for x in range(N):
        for by in range(0, N, 4):
            drop = int(rng.choice([1, 2, 2, 3], p=[0.2, 0.4, 0.25, 0.15]))
            for k in range(drop):
                img[by + 3 - k, x] = g[rng.choice(4, p=[0.4, 0.3, 0.2, 0.1])] * (1.0 - 0.06 * k)
            if drop < 4:
                img[by + 3 - drop, x] *= 0.82
    return img


def tex_plank(rng, vertical=False, dark=False):
    cols = pal("#74502c", "#845c34", "#644424", "#916638", "#523618", k=0.7) if dark else pal("#a8743a", "#b88446", "#986632", "#c49250", "#86582a", k=0.7)
    img = np.zeros((N, N, 3), np.float32)
    for row in range(N // 4):                             # planks 4 texels wide, grain runs along them
        base = rng.choice(5, p=[0.36, 0.26, 0.2, 0.12, 0.06])
        f = rng.uniform(0.93, 1.07)
        x = 0
        while x < N:
            run = int(rng.integers(3, 9))
            c = cols[base] if rng.random() > 0.3 else cols[rng.integers(0, 5)]
            for dy in range(4):
                k = 0.70 if dy == 0 else (1.07 if dy == 3 else 1.0)
                g = cols[rng.integers(0, 5)] if rng.random() < 0.18 else c
                img[row * 4 + dy, x:min(N, x + run)] = g * f * k
            x += run
        for _ in range(2):                                # butt joints
            jx = int(rng.integers(0, N))
            img[row * 4:row * 4 + 4, jx] *= 0.68
    return img.transpose(1, 0, 2).copy() if vertical else img


def tex_bark(rng):
    cols = pal("#7f5227", "#96642f", "#66411d", "#a87336", "#523315", "#8b6a3a")
    img = np.zeros((N, N, 3), np.float32)
    for x in range(N):                                    # vertical streaks of varying length
        y = 0
        while y < N:
            run = int(rng.integers(3, 12))
            c = cols[rng.choice(6, p=[0.3, 0.22, 0.18, 0.12, 0.1, 0.08])]
            img[y:min(N, y + run), x] = c
            y += run
    for x in range(0, N, 1):                              # fissures: dark vertical lines here and there
        if rng.random() < 0.16:
            y0 = int(rng.integers(0, N))
            for k in range(int(rng.integers(6, 20))):
                img[(y0 + k) % N, x] = cols[4] * 0.9
    return img


def tex_log_end(rng):
    cols = pal("#c79a58", "#b58647", "#d6ac6a", "#a47439")
    img = mosaic(rng, cols, [0.4, 0.3, 0.2, 0.1], 2)
    for by in range(0, N, 8):                             # rings per 8-texel block
        for bx in range(0, N, 8):
            for k in (1, 3):
                img[by + k:by + 8 - k, bx + k] *= 0.84
                img[by + k:by + 8 - k, bx + 7 - k] *= 0.84
                img[by + k, bx + k:bx + 8 - k] *= 0.84
                img[by + 7 - k, bx + k:bx + 8 - k] *= 0.84
    return img


def tex_roof(rng):
    """Roof tiles as in the reference: wide flat slabs (8 x 4 texels: a block wide), each its own green, a light upper
    edge and a dark lower seam; every other row is offset by half a tile."""
    cols = pal("#40722f", "#4c8036", "#36632a", "#588a3d", "#2f5824", "#6c943e", k=0.8)
    img = np.zeros((N, N, 3), np.float32)
    for row in range(N // 4):
        off = 4 if row % 2 else 0
        for bx in range(0, N, 8):
            c = cols[rng.choice(6, p=[0.34, 0.24, 0.18, 0.12, 0.07, 0.05])] * rng.uniform(0.96, 1.04)
            for dy in range(4):
                for dx in range(8):
                    k = 1.0
                    if dy == 0 or dx == 7:
                        k = 0.76
                    elif dy == 3:
                        k = 1.10
                    img[row * 4 + dy, (bx + dx + off) % N] = c * k
    return img


def tex_plaster(rng):
    cols = pal("#cfc1a1", "#dccfb1", "#bcad8d", "#c5b596", "#a99a7c")
    img = mosaic(rng, cols, [0.42, 0.24, 0.16, 0.13, 0.05], 2)
    return img


def tex_leaves(rng):
    cols = pal("#6f9a2a", "#82ad32", "#587f22", "#48701c", "#9cc040", "#3a5c18", k=0.75)
    img = mosaic(rng, cols, [0.32, 0.24, 0.2, 0.12, 0.07, 0.05], 2)
    return img


def tex_wheat(rng, top=False):
    cols = pal("#eebf2f", "#f8d64e", "#d29c21", "#b47f19", "#fbe37a")
    if top:
        return mosaic(rng, cols, [0.34, 0.3, 0.18, 0.06, 0.12], 1)
    img = np.zeros((N, N, 3), np.float32)
    for x in range(N):
        c = cols[rng.choice(5, p=[0.36, 0.26, 0.2, 0.1, 0.08])]
        for y in range(N):
            k = 0.78 + 0.3 * ((y % 16) / 15.0)            # darker at the foot of each stalk, lighter at the ear
            g = c if rng.random() > 0.15 else cols[rng.integers(0, 5)]
            img[y, x] = g * k
    return img


def tex_hay(rng):
    cols = pal("#deae2f", "#ecc247", "#c59324", "#a97a1b", "#f3d267")
    img = np.zeros((N, N, 3), np.float32)
    for y in range(N):
        x = 0
        while x < N:
            run = int(rng.integers(2, 7))
            img[y, x:min(N, x + run)] = cols[rng.choice(5, p=[0.34, 0.24, 0.2, 0.1, 0.12])]
            x += run
    img = block_edges(img, 8, 0.78, 1.06)
    return img


def tex_flat(rng, hexes, weights, size=2):
    return mosaic(rng, pal(*hexes), weights, size)


def tex_window(rng):
    """Glowing panes: 4 x 4 texel panes (two 12.5 cm voxels) with a thin amber lead between them."""
    hot = hexc("#ffe07a")
    mid = hexc("#ffbe45")
    edge = hexc("#f08a1c")
    lead = hexc("#8a4a14")
    img = np.zeros((N, N, 3), np.float32)
    for y in range(N):
        for x in range(N):
            px, py = x % 4, y % 4
            if px == 3 or py == 0:
                img[y, x] = lead
            elif (px, py) == (1, 2):
                img[y, x] = hot
            elif px == 0 or py == 3:
                img[y, x] = mid
            else:
                img[y, x] = mid if rng.random() < 0.6 else hot
            if (px, py) == (2, 1):
                img[y, x] = edge
    return img


def tex_ore(rng):
    img = tex_stone(rng)
    g = pal("#f2bf2e", "#ffdc5c", "#c58f1c", k=1)
    for _ in range(40):
        x, y = rng.integers(0, N, 2)
        for dx, dy in ((0, 0), (1, 0), (0, 1), (1, 1), (2, 1), (1, 2))[:int(rng.integers(2, 7))]:
            img[(y + dy) % N, (x + dx) % N] = g[rng.choice(3, p=[0.5, 0.25, 0.25])]
    return img


def tex_water(rng):
    cols = pal("#2e6fb0", "#3a86c8", "#245a96", "#4a9fd8", "#8fd0ee")
    img = mosaic(rng, cols, [0.4, 0.26, 0.2, 0.1, 0.04], 2)
    for _ in range(26):                                   # short horizontal glints
        x, y = rng.integers(0, N, 2)
        for dx in range(int(rng.integers(2, 6))):
            img[y, (x + dx) % N] = cols[4]
    return img


def main():
    rng = np.random.default_rng(7)
    save("stone", tex_stone(rng))
    save("stone_mossy", tex_stone(rng, mossy=True))
    save("brick", tex_brick(rng))
    save("cobble", tex_cobble(rng))
    save("grass", tex_grass(rng))
    save("grass_side", tex_grass_side(rng))
    save("dirt", tex_dirt(rng))
    save("plank", tex_plank(rng))
    save("beam", tex_plank(rng, dark=True))
    save("beam_v", tex_plank(rng, vertical=True, dark=True))
    save("bark", tex_bark(rng))
    save("log_end", tex_log_end(rng))
    save("roof", tex_roof(rng))
    save("plaster", tex_plaster(rng))
    save("leaves", tex_leaves(rng))
    save("wheat", tex_wheat(rng))
    save("wheat_top", tex_wheat(rng, top=True))
    save("hay", tex_hay(rng))
    save("wool", tex_flat(rng, ["#f1ede1", "#e4ded0", "#faf7ee", "#d6cfbf"], [0.5, 0.22, 0.2, 0.08]))
    save("paint", tex_flat(rng, ["#ffffff", "#f1f1f1", "#e4e4e4"], [0.6, 0.28, 0.12]))
    save("cloth", tex_flat(rng, ["#ffffff", "#f1f1f1", "#e4e4e4"], [0.6, 0.28, 0.12]))
    save("glow", tex_flat(rng, ["#ffffff", "#fff4d8", "#ffe7b0"], [0.5, 0.3, 0.2]))
    save("window", tex_window(rng))
    save("metal", tex_flat(rng, ["#4b4a51", "#5c5b64", "#3b3a40", "#6d6c76"], [0.44, 0.26, 0.2, 0.1]))
    save("gold", tex_flat(rng, ["#e9b42d", "#f8d24c", "#c48f1e", "#fde68a"], [0.44, 0.26, 0.2, 0.1]))
    save("moss", tex_flat(rng, ["#79b021", "#8fc62c", "#63941d", "#a3d43a", "#4f7d18"], [0.36, 0.26, 0.2, 0.1, 0.08]))
    save("ore", tex_ore(rng))
    save("gravel", tex_flat(rng, ["#7d8686", "#929a98", "#687272", "#a3a69c", "#596464"], [0.34, 0.24, 0.2, 0.14, 0.08]))
    save("water", tex_water(rng))
    missing = [s for s in voxmats.SLOTS if not os.path.exists(os.path.join(OUT, "T_Vox_%s.png" % s))]
    print("textures written to", os.path.abspath(OUT), "| missing slots:", missing)
    # a contact sheet for a look at them all
    names = sorted(voxmats.SLOTS)
    cols_n = 7
    rows_n = (len(names) + cols_n - 1) // cols_n
    sheet = Image.new("RGB", (cols_n * 200, rows_n * 200), (30, 30, 30))
    for i, n in enumerate(names):
        im = Image.open(os.path.join(OUT, "T_Vox_%s.png" % n)).resize((192, 192), Image.NEAREST)
        sheet.paste(im, ((i % cols_n) * 200 + 4, (i // cols_n) * 200 + 4))
    sheet.save(os.path.join(OUT, "..", "Previews", "textures.png"))


if __name__ == "__main__":
    main()
