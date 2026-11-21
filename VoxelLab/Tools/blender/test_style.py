"""Style check: a cottage, a rock, a lantern, a banner and a tree, rendered together."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import voxlib as V
import voxkit as K
from voxlib import Vox

V.reset_scene()

# cottage: 5 x 4 m footprint on a 12.5 cm grid
v = Vox(64, 56, 60, 0.125, origin=(32, 28, 0), name="cottage")
x0, y0, x1, y1 = 12, 12, 52, 44
v.box(x0 - 2, y0 - 2, 0, x1 + 2, y1 + 2, 6, "stone")              # footing
v.box(x0, y0, 6, x1, y1, 26, "plaster")
K.timber_wall(v, "y", y0, x0, x1, 6, 26, spacing=13, braces=True)
K.timber_wall(v, "y", y1 - 1, x0, x1, 6, 26, spacing=13)
K.timber_wall(v, "x", x0, y0, y1, 6, 26, spacing=10)
K.timber_wall(v, "x", x1 - 1, y0, y1, 6, 26, spacing=10)
# gable walls
for i in range(8):
    v.box(x0, y0 + i * 2, 26 + i * 2 - 2, x0 + 1, y1 - i * 2, 28 + i * 2, "plaster")
    v.box(x1 - 1, y0 + i * 2, 26 + i * 2 - 2, x1, y1 - i * 2, 28 + i * 2, "plaster")
K.gable_roof(v, x0 - 4, y0 - 4, x1 + 4, y1 + 4, 24, ridge="x", run=4, rise=3)
K.door(v, "y", y0, 28, 6, w=8, h=14)
K.window(v, "y", y0, 16, 12, w=6, h=7)
K.window(v, "y", y0, 42, 12, w=6, h=7)
K.window(v, "x", x1 - 1, 24, 12, w=8, h=7, out=1)
K.wall_lantern(v, 39, y0, 22)
v.box(40, 30, 30, 46, 36, 52, "stone")                             # chimney
v.box(39, 29, 50, 47, 37, 52, "stone")
v.chunky("stone", p=0.35, seed=2)
v.scatter("roof", "moss", p=0.05, seed=4, direction="+z")
cottage = v.to_object("cottage")

# rock pile with moss
r = Vox(40, 36, 30, 0.125, origin=(20, 18, 0), name="rock", seed=5)
rng = np.random.default_rng(3)
for (bx, by, bz, sx, sy, sz) in [(1, 1, 0, 4, 4, 3), (4, 2, 0, 4, 5, 4), (2, 4, 0, 4, 3, 2), (5, 5, 0, 3, 3, 3), (3, 3, 3, 3, 3, 2), (6, 1, 0, 3, 3, 2)]:
    r.box(bx * 4, by * 4, bz * 4, (bx + sx) * 4, (by + sy) * 4, (bz + sz) * 4, "stone")
r.chunky("stone", p=0.4, seed=1)
top = r.exposed("+z") & r.mask("stone")
r.where(top & (V.noise3(r.n, 8, 4) > 0.42), "mossy_stone")
rock = r.to_object("rock")
rock.location = (5.5, -2.5, 0)

lp = K.lantern_post(10).to_object("lantern")
lp.location = (-4.2, -3.2, 0)
pole = Vox(4, 4, 34, 0.125, origin=(2, 2, 0))
pole.box(1, 1, 0, 3, 3, 34, "post")
pole.box(0, 0, 0, 4, 4, 3, "stone")
bn = K.banner("tree").at(0, -0.2, 4.1)
ban = V.join([pole, bn], "banner")
ban.location = (-6.2, -1.0, 0)

# tree: thick trunk, puffy canopy of 25 cm leaf cubes
t = Vox(20, 20, 46, 0.125, origin=(10, 10, 0), name="trunk", seed=3)
for z in range(46):
    rad = 4.6 - 1.6 * min(1.0, z / 14.0) + (1.5 if z < 3 else 0)
    t.cylinder(10, 10, z, z + 1, rad, "log")
t.chunky("log", cell=2, p=0.3, seed=2)
l = Vox(44, 44, 34, 0.25, origin=(22, 22, 0), name="leaves", seed=9)
rng = np.random.default_rng(11)
puffs = [(22, 22, 14, 13, 13, 8)]
for k in range(13):
    a = rng.uniform(0, 6.283)
    d = rng.uniform(6, 13)
    puffs.append((22 + np.cos(a) * d, 22 + np.sin(a) * d, rng.uniform(8, 22), rng.uniform(6, 9), rng.uniform(6, 9), rng.uniform(4, 5.5)))
for (cx, cy, cz, rx, ry, rz) in puffs:
    l.ellipsoid(cx, cy, cz, rx, ry, rz, "leaves", noise=0.35, noise_scale=4, seed=int(cx * 7 + cy))
l.erode("leaves", p=0.22, seed=1)
l.tint("leaves", "#d8e8a0", p=0.25, seed=2)
l.tint("leaves", "#b0c890", p=0.2, seed=5)
tree = V.join([t, l.at(0, 0, 3.8)], "tree")
tree.location = (9.5, 4.0, 0)

if "--export" in sys.argv:
    for ob, nm in ((cottage, "SM_Test_Cottage"), (rock, "SM_Test_Rock"), (lp, "SM_Test_Lantern"), (ban, "SM_Test_Banner"), (tree, "SM_Test_Tree")):
        ob.location = (0, 0, 0)
        ob.name = nm
        V.export_gltf(ob)
    sys.exit(0)
V.render(os.path.join(V.PREVIEWS, "test_style.png"), target=(1.5, 0, 3.0), az=28, el=30, dist=34, lens=70, samples=64)
