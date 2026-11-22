"""ports: the harbour of each side on Realm v2 (References/RealmV2/port.png), in the house style on the 12.5 cm grid.
The quay itself is the island's rock (realmv2_layout.PORTS), the pier is SM_Dock; these stand on and by the quay:

    Blender -b --factory-startup --python Tools/blender/assets/ports.py -- [--no-render]

  SM_Port_Warehouse  a timber store on a stone footing, green roof, an awning over crates and barrels, an anchor banner
  SM_Port_Crane      a timber harbour crane on a stone foot, a crate on its rope
  SM_Port_Tower      the harbour watch tower: stone, a green roof in two tiers, a lit lantern room, anchor banners
  SM_Port_Arch       the arch of the tunnel into the cliff (its back stands against the rock)
Fronts face -Y. Scenery: nothing in the game reads them.
"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import numpy as np
import voxlib as V
from voxlib import Vox, PAL

VOX = 0.125
ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
STONE = ["#ffffff", "#f3eee4", "#e6e1d8", "#dad5cc", "#f1e8d8", "#d0cbc3"]
GREEN, GREEN_D, GREEN_L = "#2f7a3a", "#235c2c", "#3f9448"
CREAM, NAVY = PAL["cream"], "#27456e"


def masonry(v, x0, y0, z0, x1, y1, z1, seed, course=4):
    r = np.random.default_rng(seed)
    z = z0
    while z < z1:
        zt = min(z + course, z1)
        x = x0
        while x < x1:
            w = int(r.integers(3, 8))
            xt = x1 if x1 - (x + w) < 2 else x + w
            v.box(x, y0, z, xt, y1, zt, "mossy_stone" if r.random() < 0.1 else "stone", STONE[int(r.integers(0, len(STONE)))])
            x = xt
        z = zt


def roof(v, x0, y0, z0, x1, y1, rise, over=2):
    """A gabled roof, its ridge along x: courses of green, a darker one every third."""
    half = (y1 - y0) // 2 + over
    for k in range(half):
        zz = z0 + int(k * rise / half)
        col = GREEN_D if k % 3 == 2 else (GREEN_L if k % 3 == 0 else GREEN)
        v.box(x0 - over, y0 - over + k, zz, x1 + over, y0 - over + k + 2, zz + 2, "paint", col)
        v.box(x0 - over, y1 + over - k - 2, zz, x1 + over, y1 + over - k, zz + 2, "paint", col)
    v.box(x0 - over, (y0 + y1) // 2 - 1, z0 + rise, x1 + over, (y0 + y1) // 2 + 1, z0 + rise + 2, "paint", GREEN_D)


def anchor(v, x, y, z, axis="y"):
    """A banner (5 x 9 voxels) with an anchor on it, hanging at (x, y, z) = its top left, one voxel thick."""
    rows = ["..#..", ".###.", "..#..", "..#..", "#.#.#", "#.#.#", ".###.", "..#..", "....."]
    for j, row in enumerate(rows):
        for i, ch in enumerate(row):
            col = "#f3efe6" if ch == "#" else NAVY
            if axis == "y":
                v.set(x + i, y, z - j, "paint", col)
            else:
                v.set(x, y + i, z - j, "paint", col)


def build_warehouse():
    W, D, H = 72, 52, 60                                                    # 9 x 6.5 m
    v = Vox(W + 8, D + 16, H, VOX, origin=((W + 8) // 2, (D + 16) // 2, 0), name="warehouse", seed=3)
    x0, y0, x1, y1 = 4, 10, 4 + W, 10 + D
    masonry(v, x0, y0, 0, x1, y1, 8, 5)
    v.box(x0 + 1, y0 + 1, 8, x1 - 1, y1 - 1, 30, "plank")
    for x in range(x0, x1 + 1, 12):                                         # posts
        v.box(min(x, x1 - 2), y0, 8, min(x, x1 - 2) + 2, y0 + 2, 30, "beam")
        v.box(min(x, x1 - 2), y1 - 2, 8, min(x, x1 - 2) + 2, y1, 30, "beam")
    v.box(x0, y0, 28, x1, y1, 30, "beam")
    for k in range(0, 14):                                                  # the gable ends
        v.box(x0 + 1, y0 + 1 + 2 * k, 30 + k, x0 + 3, y1 - 1 - 2 * k, 31 + k, "plank")
        v.box(x1 - 3, y0 + 1 + 2 * k, 30 + k, x1 - 1, y1 - 1 - 2 * k, 31 + k, "plank")
    roof(v, x0, y0, 30, x1, y1, 14)
    v.box(x0 + 26, y0, 8, x0 + 46, y0 + 2, 26, "paint", "#3a2a1c")           # the great door
    v.box(x0 + 25, y0 - 1, 8, x0 + 26, y0 + 2, 27, "beam"); v.box(x0 + 46, y0 - 1, 8, x0 + 47, y0 + 2, 27, "beam")
    v.box(x0 + 25, y0 - 1, 26, x0 + 47, y0 + 2, 28, "beam")
    for (wx) in (x0 + 8, x0 + 56):                                          # windows
        v.box(wx, y0, 16, wx + 8, y0 + 1, 24, "window")
    # the awning over the goods: cream and green stripes on two posts
    for i in range(0, 22):
        v.box(x0 + 48 + i, y0 - 9, 25 - (0 if i < 20 else 1), x0 + 49 + i, y0, 26, "paint", CREAM if (i // 3) % 2 == 0 else GREEN)
    v.box(x0 + 48, y0 - 9, 8, x0 + 49, y0 - 8, 25, "post"); v.box(x0 + 69, y0 - 9, 8, x0 + 70, y0 - 8, 25, "post")
    for (cx, cy, cs, cz) in ((x0 + 50, y0 - 8, 7, 8), (x0 + 58, y0 - 7, 6, 8), (x0 + 52, y0 - 7, 5, 15), (x0 + 6, y0 - 7, 7, 8), (x0 + 14, y0 - 6, 5, 8)):
        v.box(cx, cy, cz, cx + cs, cy + cs, cz + cs, "plank", "#e2c8a6")
        v.frame(cx, cy, cz, cx + cs, cy + cs, cz + cs, "beam")
    v.cylinder(x0 + 66, y0 - 5, 8, 15, 3, "plank", "#d8bc98"); v.cylinder(x0 + 20, y0 - 4, 8, 15, 3, "plank", "#d8bc98")
    v.box(x0 - 4, y0 - 10, 0, x1 + 4, y0, 8, "plank")                       # the loading deck before it
    v.box(x0 - 4, y0 - 10, 0, x1 + 4, y0 - 9, 8, "beam")
    anchor(v, x0 + 34, y0 - 1, 44)                                          # the anchor banner on the gable... over the door
    v.box(x0 + 33, y0 - 1, 45, x0 + 40, y0, 46, "beam")
    return V.join([v], "SM_Port_Warehouse")


def build_crane():
    v = Vox(56, 24, 64, VOX, origin=(12, 12, 0), name="crane", seed=5)
    masonry(v, 4, 4, 0, 20, 20, 6, 7, course=3)
    v.box(10, 10, 6, 14, 14, 54, "post")                                    # the king post
    v.box(6, 10, 6, 18, 14, 8, "beam"); v.box(10, 6, 6, 14, 18, 8, "beam")
    for k in range(0, 10):                                                  # braces
        v.box(14 + k, 11, 8 + k, 15 + k, 13, 10 + k, "beam")
        v.box(9 - min(k, 5), 11, 8 + k, 10 - min(k, 5), 13, 10 + k, "beam")
    v.box(2, 11, 50, 50, 13, 53, "beam")                                    # the jib
    for k in range(0, 14):
        v.box(14 + 2 * k, 11, 36 + k, 16 + 2 * k, 13, 38 + k, "beam")       # its strut
    v.box(2, 10, 44, 6, 14, 50, "stone", "#d0cbc3")                         # the counterweight
    v.box(46, 12, 22, 47, 13, 50, "paint", "#3a2a1c")                       # the rope
    v.box(42, 8, 12, 51, 17, 21, "plank", "#e2c8a6"); v.frame(42, 8, 12, 51, 17, 21, "beam")
    v.box(45, 11, 21, 48, 14, 23, "metal")
    return V.join([v], "SM_Port_Crane")


def build_tower():
    S, H = 40, 120                                                          # 5 m square
    v = Vox(S + 24, S + 24, H, VOX, origin=((S + 24) // 2, (S + 24) // 2, 0), name="porttower", seed=9)
    a, b = 12, 12 + S
    masonry(v, a - 2, a - 2, 0, b + 2, b + 2, 8, 11)                        # the footing
    masonry(v, a, a, 8, b, b, 64, 13)
    v.box(a + 14, a, 8, a + 26, a + 2, 28, "paint", "#3a2a1c")               # the door
    v.box(a + 13, a - 1, 28, a + 27, a + 2, 30, "beam")
    for z in (36, 52):
        v.box(a + 17, a, z, a + 23, a + 1, z + 8, "window")
        v.box(b - 1, a + 17, z, b, a + 23, z + 8, "window")
    v.box(a - 3, a - 3, 64, b + 3, b + 3, 67, "beam")                        # the gallery
    for x in range(a - 3, b + 3, 6):
        for (px, py) in ((x, a - 3), (x, b + 2), (a - 3, x), (b + 2, x)):
            v.box(px, py, 67, px + 1, py + 1, 73, "post")
    v.box(a - 3, a - 3, 73, b + 3, a - 2, 74, "beam"); v.box(a - 3, b + 2, 73, b + 3, b + 3, 74, "beam")
    v.box(a - 3, a - 3, 73, a - 2, b + 3, 74, "beam"); v.box(b + 2, a - 3, 73, b + 3, b + 3, 74, "beam")
    # the lower roof (a skirt), the lantern room, the upper roof
    for k in range(6):
        col = GREEN_D if k % 3 == 2 else (GREEN_L if k % 3 == 0 else GREEN)
        v.box(a - 8 + 2 * k, a - 8 + 2 * k, 78 + k, b + 8 - 2 * k, b + 8 - 2 * k, 80 + k, "paint", col)
    v.box(a - 3, a - 3, 74, b + 3, b + 3, 78, "beam")
    c0, c1 = a + 8, b - 8
    v.box(c0, c0, 84, c1, c1, 98, "beam")
    v.box(c0 + 2, c0, 86, c1 - 2, c0 + 1, 96, "window"); v.box(c0 + 2, c1 - 1, 86, c1 - 2, c1, 96, "window")
    v.box(c0, c0 + 2, 86, c0 + 1, c1 - 2, 96, "window"); v.box(c1 - 1, c0 + 2, 86, c1, c1 - 2, 96, "window")
    v.box(c0 + 4, c0 + 4, 88, c1 - 4, c1 - 4, 94, "glow")
    for k in range(10):
        col = GREEN_D if k % 3 == 2 else (GREEN_L if k % 3 == 0 else GREEN)
        v.box(c0 - 8 + 2 * k, c0 - 8 + 2 * k, 98 + k, c1 + 8 - 2 * k, c1 + 8 - 2 * k, 100 + k, "paint", col)
    v.box((a + b) // 2 - 1, (a + b) // 2 - 1, 108, (a + b) // 2 + 1, (a + b) // 2 + 1, 118, "gold")
    anchor(v, a + 17, a - 1, 62)
    anchor(v, b, a + 17, 62, axis="x")
    return V.join([v], "SM_Port_Tower")


def build_arch():
    W, D, H = 56, 14, 46                                                    # 7 m wide, 1.75 m deep, 5.75 m high
    v = Vox(W, D, H, VOX, origin=(W // 2, D // 2, 0), name="portarch", seed=15)
    masonry(v, 0, 2, 0, W, D, H - 4, 17)
    for k, (inset, z0, z1) in enumerate(((0, 0, 24), (2, 24, 28), (5, 28, 32), (9, 32, 35))):      # the opening: 4.5 m wide, arched
        v.clear(10 + inset, 0, z0, W - 10 - inset, D - 3, z1)
    v.box(10, D - 3, 0, W - 10, D - 2, 35, "paint", "#17130f")               # the dark of the tunnel
    for k in range(4):                                                      # a rail track's sleepers going in
        v.box(18, 3 + 3 * k, 0, W - 18, 4 + 3 * k, 1, "beam")
    v.box(4, 0, 0, 10, 4, 30, "stone", "#dad5cc"); v.box(W - 10, 0, 0, W - 4, 4, 30, "stone", "#dad5cc")      # the jambs
    v.box(2, 1, H - 6, W - 2, D, H - 2, "stone", "#e6e1d8")                  # the coping
    v.box(W // 2 - 3, 0, 34, W // 2 + 3, 3, 40, "stone", "#f3eee4")          # the keystone
    v.chunky(["stone", "mossy_stone"], cell=4, depth=1, p=0.15, seed=19)
    return V.join([v], "SM_Port_Arch")


def main():
    V.reset_scene()
    for fn in (build_warehouse, build_crane, build_tower, build_arch):
        ob = fn()
        V.export_gltf(ob, collision="complex")
        if "--no-render" not in ARGS:
            try:
                V.render(os.path.join(V.PREVIEWS, ob.name + ".png"), target=(0, 0, 4.0), az=-35, el=24, dist=34, ground=True)
            except Exception as e:
                print("no preview:", e)
        ob.hide_render = True
        ob.hide_viewport = True


main()
