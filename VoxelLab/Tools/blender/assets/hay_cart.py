"""hay_cart: the two-wheeled cart loaded with hay (References/Remake/town.png, by the crop fields on the right).

  SM_HayCart   a plank bed with low side rails on two big spoked wheels, a stack of tied hay bales on the back, a
               bare front deck with two shafts running out forwards (+X) and a prop leg under them, so it stands level.
               About 3.4 x 2 x 2.2 m. Origin: the centre of its footprint on the ground. Long axis X, shafts to +X.

Run:  Blender -b --factory-startup --python Tools/blender/assets/hay_cart.py -- [--no-render] [--cpu] [--samples N]
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import numpy as np
import voxlib as V
from voxlib import Vox

ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
NO_RENDER = "--no-render" in ARGS
CPU = "--cpu" in ARGS
SAMPLES = int(ARGS[ARGS.index("--samples") + 1]) if "--samples" in ARGS else 32

VX = 0.125
WOOD = ["#f6d6aa", "#e2b684", "#eec696", "#d6a674"]
HAY = [None, "#fff0b0", "#f0d890", "#ffe8a0", "#e8cc80"]


def build_cart():
    NX, NY, NZ = 28, 16, 18
    v = Vox(NX, NY, NZ, VX, origin=(NX / 2.0, NY / 2.0, 0), name="cart", seed=4)
    rng = np.random.default_rng(3)
    X, Y, Z = v.grid()
    BED = 8                                                   # the bed's top (0.75 m)
    x0, x1, y0, y1 = 1, 21, 3, 13                             # the bed: 2.5 x 1.25 m
    wood = np.array([V.rgb(c) for c in WOOD])
    for y in range(y0, y1, 2):                                # boards along it
        v.box(x0, y, BED - 1, x1, y + 2, BED, "plank", wood[rng.integers(0, len(wood))])
    for x in (x0, 10, x1 - 1):                                # bearers under it
        v.box(x, y0, BED - 2, x + 1, y1, BED - 1, "beam")
    for y in (y0, y1 - 1):                                    # the two long frame beams, running on as the shafts
        v.box(x0, y, BED - 2, NX, y + 1, BED, "beam")
        v.box(NX - 1, y, BED - 2, NX, y + 1, BED + 1, "metal")
    v.box(NX - 3, y0, BED - 1, NX - 2, y1, BED, "beam")       # the cross bar between the shafts
    v.box(NX - 6, 7, 0, NX - 5, 9, BED - 2, "post")           # the prop leg
    v.box(NX - 7, 6, 0, NX - 4, 10, 1, "beam")
    v.box(NX - 6, y0, BED - 2, NX - 5, y1, BED - 1, "beam")
    # side rails: posts and two rails, a tail board
    for y in (y0, y1 - 1):
        for x in (x0, 7, 13, x1 - 1):
            v.box(x, y, BED, x + 1, y + 1, BED + 4, "post")
        v.box(x0, y, BED + 3, x1, y + 1, BED + 4, "plank", "#e2b684")
        v.box(x0, y, BED + 1, x1, y + 1, BED + 2, "plank", "#d6a674")
    v.box(x0, y0, BED, x0 + 1, y1, BED + 4, "plank", "#e2b684")
    # the hay: two tiers of bales over the back two thirds, tied with cord
    hx0, hx1 = x0 + 1, 15
    hay = np.array([V.rgb(c or "#ffffff") for c in HAY])
    for (z0, z1, inset) in ((BED, BED + 5, 0), (BED + 5, BED + 9, 1)):
        m = (X >= hx0 + inset) & (X < hx1 - inset) & (Y >= y0 + 1 - (1 - inset)) & (Y < y1 - 1 + (1 - inset)) & (Z >= z0) & (Z < z1)
        v.where(m, "hay")
        v.c[m] = hay[rng.integers(0, len(HAY), v.n)][m]
    top = (X >= hx0 + 2) & (X < hx1 - 2) & (Y >= y0 + 2) & (Y < y1 - 2) & (Z == BED + 9) & (rng.random(v.n) < 0.6)
    v.where(top, "hay", "#fff0b0")
    solid_hay = v.mask("hay")
    for xs in (hx0 + 3, hx1 - 4):                              # the cords, flush in the surface
        v.where(solid_hay & (X == xs) & ((Y == y0) | (Y == y1 - 1) | (Z >= BED + 8) | (Y == y0 + 1) | (Y == y1 - 2)), "hay", "#a07840")
    v.where(solid_hay & (Z == BED + 4), "hay", "#d8b868")       # the dark line between the tiers
    # stray stalks hanging over the rails
    for _ in range(14):
        x = int(rng.integers(hx0, hx1))
        y = y0 - 1 if rng.random() < 0.5 else y1
        z = int(rng.integers(BED + 2, BED + 5))
        v.set(x, y, z, "hay", "#fff0b0")
    # the wheels: 1.1 m across, outside the frame, spoked, an iron tyre, on an axle
    ax, az, r = 9.0, 6.0, 6.0
    v.box(8, 1, 5, 10, NY - 1, 7, "beam")                      # the axle
    for (ya, yb) in ((1, 2), (NY - 2, NY - 1)):
        d = np.hypot(X + 0.5 - ax, Z + 0.5 - az)
        ring = (d <= r) & (d > r - 2.0) & (Y >= ya) & (Y < yb)
        v.where(ring, "plank", "#c99a66")
        v.where((d <= r) & (d > r - 0.9) & (Y >= ya) & (Y < yb), "metal")
        diag = np.abs(np.abs(X + 0.5 - ax) - np.abs(Z + 0.5 - az)) < 0.75
        spoke = (d <= r - 1.0) & (Y >= ya) & (Y < yb) & ((np.abs(X + 0.5 - ax) < 0.6) | (np.abs(Z + 0.5 - az) < 0.6) | diag)
        v.where(spoke, "post")
        yo = 0 if ya == 1 else NY - 1                          # the hub, standing out
        v.box(8, yo, 5, 10, yo + 1, 7, "metal")
    return V.join([v], "SM_HayCart")


def render(path, **kw):
    import time
    import bpy
    if CPU:
        bpy.app.handlers.render_pre.append(lambda scene, *a: setattr(scene.cycles, "device", "CPU"))
    for attempt in range(4):
        try:
            return V.render(path, samples=SAMPLES, **kw)
        except RuntimeError as e:
            print("render failed (%s); retrying" % str(e).splitlines()[0][:80])
            time.sleep(15)
            if attempt >= 1:
                bpy.app.handlers.render_pre.append(lambda scene, *a: setattr(scene.cycles, "device", "CPU"))
    raise RuntimeError("could not render " + path)


def main():
    V.reset_scene()
    ob = build_cart()
    V.export_gltf(ob, collision="complex")
    co = np.array([p.co[:] for p in ob.data.vertices])
    print("%-10s %6d faces  bounds %s .. %s" % (ob.name, ob["voxel_faces"], np.round(co.min(axis=0), 3), np.round(co.max(axis=0), 3)))
    if NO_RENDER:
        return
    render(os.path.join(V.PREVIEWS, "hay_cart.png"), target=(0, 0, 0.8), az=-35, el=30, dist=16, res=(900, 700))
    render(os.path.join(V.PREVIEWS, "hay_cart_back.png"), target=(0, 0, 0.8), az=150, el=24, dist=16, res=(900, 700))


main()
