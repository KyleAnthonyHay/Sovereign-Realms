"""ruins: the old stones of Realm v2 (the ruins plateau, the upper terrace, the crossings): an arch, three pillars
(standing, broken, a stump with its fallen drum) and a fallen block. Dry stone in the house style, on the 12.5 cm grid.

    Blender -b --factory-startup --python Tools/blender/assets/ruins.py -- [--no-render]

  SM_Ruin_Arch       two piers 5 m high, 3.5 m apart, a stepped arch over them (6.9 m); one shoulder broken. Units walk
                     through it (its own -Y / +Y)
  SM_Ruin_Pillar_A   a standing column, 5.6 m, its capital chipped
  SM_Ruin_Pillar_B   a broken column, 3.1 m
  SM_Ruin_Pillar_C   a stump (1.4 m) and a drum of it lying beside
  SM_Ruin_Block      a fallen lintel, half sunk
"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import numpy as np
import voxlib as V
from voxlib import Vox

VOX = 0.125
ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
TINTS = ["#ffffff", "#f3eee4", "#e6e1d8", "#dad5cc", "#f1e8d8", "#d0cbc3", "#f8f2e6"]


def courses(v, x0, y0, z0, x1, y1, z1, seed, course=4, mat="stone"):
    """A block of masonry: courses half a metre high, each stone its own shade, a few of them mossy."""
    r = np.random.default_rng(seed)
    z = z0
    while z < z1:
        zt = min(z + course, z1)
        x = x0
        while x < x1:
            w = int(r.integers(3, 7))
            xt = x1 if x1 - (x + w) < 2 else x + w
            v.box(x, y0, z, xt, y1, zt, "mossy_stone" if r.random() < 0.16 else mat, TINTS[int(r.integers(0, len(TINTS)))])
            x = xt
        z = zt


def weather(v, seed):
    v.chunky(["stone", "mossy_stone"], cell=4, depth=1, p=0.22, seed=seed)
    v.erode(["stone", "mossy_stone"], p=0.05, seed=seed + 1)
    return v


def pillar(height, seed, capital=True, ragged=0):
    """A column on its plinth: height in voxels."""
    v = Vox(16, 16, height + 8, VOX, origin=(8, 8, 0), name="pillar", seed=seed)
    courses(v, 2, 2, 0, 14, 14, 4, seed)                                    # the plinth, 1.5 m square
    courses(v, 4, 4, 4, 12, 12, height, seed + 3, course=5)                 # the shaft, 1 m square
    if capital:
        courses(v, 3, 3, height - 5, 13, 13, height - 2, seed + 5, course=3)
        courses(v, 2, 2, height - 2, 14, 14, height, seed + 7, course=2)
        v.clear(2, 2, height - 2, 7, 6, height)                             # a chipped corner
    r = np.random.default_rng(seed + 11)
    for _ in range(ragged):                                                 # the break: steps knocked out of the top
        x, y = int(r.integers(4, 10)), int(r.integers(4, 10))
        v.clear(x, y, height - int(r.integers(2, 7)), x + int(r.integers(2, 5)), y + int(r.integers(2, 5)), height)
    v.box(3, 3, 4, 13, 13, 5, "mossy_stone")
    return weather(v, seed)


def build_pillar_a():
    return V.join([pillar(45, 21)], "SM_Ruin_Pillar_A")


def build_pillar_b():
    return V.join([pillar(25, 33, capital=False, ragged=5)], "SM_Ruin_Pillar_B")


def build_pillar_c():
    a = pillar(11, 47, capital=False, ragged=4)
    d = Vox(24, 12, 10, VOX, origin=(0, 6, 0), name="drum", seed=51)        # the fallen drum: 2.4 m long, lying
    courses(d, 2, 2, 0, 20, 10, 8, 53, course=8)
    d.clear(2, 2, 6, 6, 10, 8)
    weather(d, 55)
    d.at(1.1, 0.4, -0.125)
    return V.join([a, d], "SM_Ruin_Pillar_C")


def build_block():
    v = Vox(28, 14, 10, VOX, origin=(14, 7, 1), name="block", seed=61)
    courses(v, 2, 2, 0, 26, 12, 7, 63, course=7)
    v.clear(2, 2, 5, 9, 6, 7)
    v.clear(20, 8, 4, 26, 12, 7)
    v.box(9, 2, 6, 20, 8, 7, "mossy_stone")
    return V.join([weather(v, 65)], "SM_Ruin_Block")


def build_arch():
    W, D, H = 48, 12, 58                                                    # 6 m wide, 1.5 m deep, 7.25 m high
    v = Vox(W, D, H, VOX, origin=(W // 2, D // 2, 0), name="arch", seed=71)
    courses(v, 1, 1, 0, 11, 11, 4, 73)                                      # the piers' plinths
    courses(v, 37, 1, 0, 47, 11, 4, 75)
    courses(v, 2, 2, 4, 10, 10, 40, 77, course=5)                           # the piers: 1 m square, 5 m high
    courses(v, 38, 2, 4, 46, 10, 40, 79, course=5)
    # the arch: corbelled steps in from both piers, a keystone course over the middle
    for k, (inset, z0, z1) in enumerate(((0, 40, 44), (3, 44, 48), (7, 48, 52), (12, 52, 55))):
        courses(v, 2 + inset, 2, z0, 24, 10, z1, 81 + k, course=4)
        courses(v, 24, 2, z0, 46 - inset, 10, z1, 91 + k, course=4)
    v.clear(10, 2, 40, 38, 10, 44)                                          # the opening under the steps
    v.clear(13, 2, 44, 35, 10, 48)
    v.clear(17, 2, 48, 31, 10, 51)
    v.clear(36, 2, 46, 47, 10, 58)                                          # the east shoulder has fallen
    v.clear(33, 2, 50, 37, 6, 58)
    v.box(2, 2, 4, 10, 10, 5, "mossy_stone")
    v.box(38, 2, 4, 46, 10, 5, "mossy_stone")
    return V.join([weather(v, 99)], "SM_Ruin_Arch")


def main():
    V.reset_scene()
    for fn in (build_arch, build_pillar_a, build_pillar_b, build_pillar_c, build_block):
        ob = fn()
        V.export_gltf(ob, collision="complex")
        if "--no-render" not in ARGS:
            try:
                V.render(os.path.join(V.PREVIEWS, ob.name + ".png"), target=(0, 0, 2.5), az=-35, el=22, dist=22, ground=True)
            except Exception as e:
                print("no preview:", e)
        ob.hide_render = True
        ob.hide_viewport = True


main()
