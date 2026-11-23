"""windmill: the windmill of the town (References/Remake/town.png, top right).

  SM_Windmill        a round tower on a stepped stone plinth: a stone foot, boarded timber above it bound with beam
                     rings and posts, a green tiled cap with a timber rim, a door with a hood and a lantern on the
                     front (-Y), small glowing windows, the axle housing sticking out of the cap's front. No sails.
                     Sidecar "hub": [x, y, z] = where the sails mount (the middle of the sail plane), metres.
  SM_Windmill_Sails  the four sails: timber spars with lattice frames and cream cloth, in the XZ plane, origin at the
                     hub (the scene turns it about its Y axis). They stand as a + here; turn them 45 degrees for the X
                     of the picture. No collision.

Pivot of the mill: the centre of its footprint, ground z = 0.

Run:  Blender -b --factory-startup --python Tools/blender/assets/windmill.py -- [--no-render] [--cpu] [--samples N]
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import math
import numpy as np
import voxlib as V
import voxkit as K
from voxlib import Vox

ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
NO_RENDER = "--no-render" in ARGS
CPU = "--cpu" in ARGS
SAMPLES = int(ARGS[ARGS.index("--samples") + 1]) if "--samples" in ARGS else 32

VX = 0.125
NX, NY, NZ = 60, 64, 92
OX, OY = 30, 34                       # the voxel corner that becomes (0, 0)

BOARDS = ["#f0d6a4", "#e2c48e", "#ead0a0", "#d8b880", "#f4dcae", "#e6c896"]
STONES = [None, "#e6dfd2", "#cfc7ba", "#f2ece0", "#d8d0c0"]
PLINTH_R, PLINTH_Z = 27.0, 4          # the wide stone foot
STEP_R, STEP_Z = 23.5, 8              # its second course: the floor the tower stands on (1 m)
STONE_TOP = 26                        # the stone part of the tower ends here (3.25 m)
WALL_TOP = 62                         # under the cap (7.75 m)
R_FOOT, R_TOP = 18.5, 14.5            # the tower tapers
CAP_TOP = 84                          # 10.5 m
HUB_Z = 60                            # the axle (7.5 m)
SAIL_Y = -23.5                        # voxels: the middle of the sail plane, in front of the cap's rim


def radius(z):
    t = np.clip((z - STEP_Z) / float(WALL_TOP - STEP_Z), 0.0, 1.0)
    return R_FOOT + (R_TOP - R_FOOT) * t


def build_mill():
    v = Vox(NX, NY, NZ, VX, origin=(OX, OY, 0), name="mill", seed=11)
    X, Y, Z = v.grid()
    dx, dy = X + 0.5 - OX, Y + 0.5 - OY
    d = np.hypot(dx, dy)
    ang = np.arctan2(dy, dx)
    rng = np.random.default_rng(5)

    # ---- the plinth: two round courses of big stones, steps up the front
    stone_col = np.array([V.rgb(c or "#ffffff") for c in STONES])
    seg = (np.floor((ang + np.pi) / (2 * np.pi) * 22) + (Z // 4) * 7).astype(int)
    pick = stone_col[rng.integers(0, len(STONES), 400)[seg % 400]]
    for (r, z0, z1) in ((PLINTH_R, 0, PLINTH_Z), (STEP_R, PLINTH_Z, STEP_Z)):
        m = (d <= r) & (Z >= z0) & (Z < z1)
        v.where(m, "stone")
        v.c[m] = pick[m]
    v.box(OX - 7, OY - 28, 0, OX + 7, OY - 20, 2, "stone", "#e6dfd2")               # the steps
    v.box(OX - 7, OY - 27, 2, OX + 7, OY - 20, 4, "stone")
    v.box(OX - 6, OY - 26, 4, OX + 6, OY - 20, 6, "stone", "#e6dfd2")
    v.box(OX - 6, OY - 24, 6, OX + 6, OY - 18, 8, "stone")

    # ---- the tower: stone foot, boarded timber above
    R = radius(Z)
    body = (d <= R) & (Z >= STEP_Z) & (Z < WALL_TOP)
    low = body & (Z < STONE_TOP)
    v.where(low, "brick")
    seg2 = (np.floor((ang + np.pi) / (2 * np.pi) * 18 + (Z // 3 % 2) * 0.5) + (Z // 3) * 5).astype(int)
    v.c[low] = stone_col[rng.integers(0, len(STONES), 400)[seg2 % 400]][low]
    up = body & (Z >= STONE_TOP)
    v.where(up, "plaster")                                                           # pale boards, as in the picture
    bf = (ang + np.pi) / (2 * np.pi) * 36
    board = np.floor(bf).astype(int) % 36
    bcol = np.array([V.rgb(c) for c in BOARDS])[rng.integers(0, len(BOARDS), 36)]
    v.c[up] = bcol[board][up]
    gap = up & ((bf - np.floor(bf)) * (2 * np.pi * d / 36) < 0.7) & (d > R - 1.0)     # the dark joint between two boards
    v.where(gap, "plank", "#b9844a")
    # beam rings standing proud, and eight posts up the timber part
    for (z0, z1, grow) in ((STONE_TOP - 1, STONE_TOP + 2, 1.2), (43, 45, 1.0), (WALL_TOP - 3, WALL_TOP, 1.4)):
        v.where((d <= R + grow) & (d > R - 1.5) & (Z >= z0) & (Z < z1), "beam")
    post = (np.abs(((ang + np.pi / 8) % (np.pi / 4)) - np.pi / 8) * d < 1.2)
    v.where(post & (d <= R + 1.0) & (d > R - 1.5) & (Z >= STONE_TOP) & (Z < WALL_TOP), "post")
    v.chunky("brick", cell=3, p=0.3, seed=3, region=(0, 0, STEP_Z, NX, NY, STONE_TOP - 1))
    v.chunky("stone", cell=4, p=0.35, seed=4, region=(0, 0, 0, NX, NY, STEP_Z))

    # ---- the door (front, -Y): a flat timber porch set into the round wall, a hood over it
    yf = OY - 19
    v.box(OX - 7, yf, STEP_Z, OX + 7, OY - 10, STEP_Z + 20, "brick", "#d8d0c0")
    v.box(OX - 6, yf - 1, STEP_Z, OX - 4, yf + 1, STEP_Z + 19, "post")
    v.box(OX + 4, yf - 1, STEP_Z, OX + 6, yf + 1, STEP_Z + 19, "post")
    v.box(OX - 6, yf - 1, STEP_Z + 17, OX + 6, yf + 1, STEP_Z + 19, "beam")
    v.box(OX - 4, yf, STEP_Z, OX + 4, yf + 1, STEP_Z + 17, "plank", "#d09a5c")
    for xx in range(OX - 4, OX + 4, 2):
        v.box(xx, yf, STEP_Z, xx + 1, yf + 1, STEP_Z + 17, "plank", "#b9844a")
    for zz in (STEP_Z + 3, STEP_Z + 13):
        v.box(OX - 4, yf - 1, zz, OX + 4, yf, zz + 1, "metal")
    v.box(OX + 2, yf - 1, STEP_Z + 8, OX + 3, yf, STEP_Z + 10, "gold")
    for i in range(3):                                                              # the hood: three stepped tile rows
        v.box(OX - 8, yf - 2 + i, STEP_Z + 20 + i, OX + 8, yf + 3, STEP_Z + 21 + i, "roof")   # (shallow: the sails pass in front)
    v.box(OX - 8, yf - 2, STEP_Z + 19, OX + 8, yf - 1, STEP_Z + 20, "plank")
    for xx in (OX - 8, OX + 7):
        v.box(xx, yf - 1, STEP_Z + 16, xx + 1, yf, STEP_Z + 20, "beam")
    K.wall_lantern(v, OX + 9, yf + 2, STEP_Z + 15, out=(0, -1))

    # ---- windows: small glowing ones in timber frames, on the sides and the back, one high on the front
    def window(cx, cy, z0, nx_, ny_, w=4, h=6):
        """A window on the wall at (cx, cy) looking along (nx_, ny_)."""
        tx, ty = -ny_, nx_
        for a in range(-w // 2 - 1, w // 2 + 1):
            for b in range(-1, h + 1):
                edge = a in (-w // 2 - 1, w // 2) or b in (-1, h)
                for depth in range(-3, 2 if edge else 1):
                    x = int(round(cx + tx * (a + 0.5) + nx_ * depth - 0.5))
                    y = int(round(cy + ty * (a + 0.5) + ny_ * depth - 0.5))
                    v.set(x, y, z0 + b, "beam" if edge else "window")
        v.set(int(round(cx + nx_ * 0.5 - 0.5)), int(round(cy + ny_ * 0.5 - 0.5)), z0 + h // 2, "beam")

    for (a_deg, z0) in ((0, 32), (180, 32), (90, 34), (0, 50), (180, 50), (270, 46)):
        a = math.radians(a_deg)
        r = float(radius(z0 + 3))
        window(OX + math.cos(a) * r, OY + math.sin(a) * r, z0, math.cos(a), math.sin(a))

    # ---- the cap: a timber rim, then rounds of green tiles stepping in to a finial
    v.where((d <= R_TOP + 4.5) & (Z >= WALL_TOP) & (Z < WALL_TOP + 2), "plank", "#e6bc8a")
    v.where((d <= R_TOP + 4.5) & (d > R_TOP + 3.0) & (Z >= WALL_TOP) & (Z < WALL_TOP + 3), "beam")
    n_rows = (CAP_TOP - WALL_TOP - 2) // 3
    for i in range(n_rows):
        r = (R_TOP + 4.0) * (1.0 - (i / float(n_rows)) ** 1.25) + 1.5
        z0 = WALL_TOP + 2 + i * 3
        m = (d <= r) & (Z >= z0) & (Z < z0 + 3)
        v.where(m, "roof")
        v.where((d <= r) & (d > r - 1.2) & (Z == z0), "roof", "#c8e0a0")           # the lip of each round, lighter
    v.box(OX - 1, OY - 1, CAP_TOP - 2, OX + 1, OY + 1, CAP_TOP + 3, "beam")
    v.box(OX - 2, OY - 2, CAP_TOP, OX + 2, OY + 2, CAP_TOP + 1, "gold")
    v.scatter("roof", "moss", p=0.07, seed=9, direction="+z")

    # ---- the axle housing: a timber nose out of the cap's front, the axle through it to the sails
    ys = int(SAIL_Y + 2)                                                             # the nose ends just behind the sails
    v.box(OX - 5, OY + ys + 3, HUB_Z - 5, OX + 5, OY - 6, HUB_Z + 5, "plank", "#dcae7c")
    v.frame(OX - 5, OY + ys + 3, HUB_Z - 5, OX + 5, OY - 6, HUB_Z + 5, "beam")
    for i in range(4):                                                               # its own little tiled gable
        v.box(OX - 6 + i, OY + ys + 2, HUB_Z + 5 + i, OX + 6 - i, OY - 8 + i * 2, HUB_Z + 6 + i, "roof")
    v.box(OX - 6, OY + ys + 2, HUB_Z + 4, OX + 6, OY + ys + 3, HUB_Z + 5, "plank")
    v.box(OX - 2, OY + ys, HUB_Z - 2, OX + 2, OY + ys + 3, HUB_Z + 2, "beam")       # the axle's end, behind the hub
    for xx in (OX - 5, OX + 4):                                                      # braces under the nose
        for i in range(5):
            v.box(xx, OY + ys + 4 + i, HUB_Z - 6 - i, xx + 1, OY + ys + 6 + i, HUB_Z - 5 - i, "beam")

    # ---- vines and moss, flowers at the foot
    for (a_deg, zt, zb) in ((40, 40, 10), (150, 34, 8), (215, 46, 12), (320, 30, 8)):
        a = math.radians(a_deg)
        for z in range(zb, zt):
            r = float(radius(z)) + 0.6
            wob = math.sin(z * 0.7 + a_deg) * 1.6
            for k in range(-1, 2):
                if rng.random() < 0.72:
                    x = int(OX + math.cos(a) * r - math.sin(a) * (wob + k))
                    y = int(OY + math.sin(a) * r + math.cos(a) * (wob + k))
                    if v.get(x, y, z) is None:
                        v.set(x, y, z, "leaves", [None, "#e4f29a", "#c4e08a"][int(rng.integers(0, 3))])
    v.scatter("stone", "mossy_stone", p=0.16, seed=6, direction="+z", region=(0, 0, 0, NX, NY, STEP_Z))
    v.scatter("stone", "moss", p=0.06, seed=7, region=(0, 0, 0, NX, NY, STEP_Z))
    for k in range(14):
        a = rng.uniform(0, 2 * math.pi)
        if abs(math.degrees(a) % 360 - 270) < 35:
            continue                                                                 # not on the steps
        r = STEP_R + rng.uniform(0.5, 2.5)
        x, y = int(OX + math.cos(a) * r), int(OY + math.sin(a) * r)
        v.set(x, y, PLINTH_Z, "leaves", "#c4e08a")
        v.set(x, y, PLINTH_Z + 1, "paint", ["flower_yellow", "flower_white", "flower_orange", "flower_pink"][k % 4])
    return v


def build_windmill():
    ob = V.join([build_mill()], "SM_Windmill")
    return ob


HUB = [0.0, round(SAIL_Y * VX, 4), HUB_Z * VX]


def build_sails():
    n = 84
    c = n // 2
    v = Vox(n, 3, n, VX, origin=(c, 1.5, c), name="sails", seed=2)

    def put(k, r0, r1, s0, s1, mat, color=None, y0=0, y1=3):
        """A box in arm k's own frame: r along the arm, s across it (the cloth side is +s)."""
        for r in range(r0, r1):
            for s in range(s0, s1):
                x, z = [(r, s), (-s - 1, r), (-r - 1, -s - 1), (s, -r - 1)][k]
                v.box(c + x, y0, c + z, c + x + 1, y1, c + z + 1, mat, color)

    LEN, W = 39, 10
    for k in range(4):
        put(k, 2, LEN, -1, 1, "beam")                                        # the spar
        put(k, 9, LEN - 1, 1, W, "paint", "#fff0c8", 1, 2)                     # the cloth
        for r in range(9, LEN - 1):
            for s in range(1, W):
                if (r * 3 + s * 5 + k) % 13 == 0:
                    x, z = [(r, s), (-s - 1, r), (-r - 1, -s - 1), (s, -r - 1)][k]
                    v.box(c + x, 1, c + z, c + x + 1, 2, c + z + 1, "paint", "#f0dca8")
        put(k, 8, LEN, W, W + 1, "plank", "#dcae7c")                         # the frame round it
        for r in (8, LEN - 1):
            put(k, r, r + 1, 1, W + 1, "plank", "#dcae7c")
        for r in range(15, LEN - 2, 7):                                      # battens across the cloth, on the front
            put(k, r, r + 1, 1, W, "plank", "#e6bc8a", 0, 1)
        put(k, 8, LEN, 5, 6, "plank", "#e6bc8a", 2, 3)                       # one along the back
        for i in range(6):                                                   # a strut from the hub to the frame
            put(k, 3 + i, 4 + i, 1 + i, 2 + i, "beam")
    v.box(c - 3, 0, c - 3, c + 3, 3, c + 3, "beam")
    v.box(c - 2, 0, c - 2, c + 2, 1, c + 2, "metal")
    v.box(c - 1, 0, c - 1, c + 1, 1, c + 1, "gold")
    return V.join([v], "SM_Windmill_Sails")


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
    mill = build_windmill()
    V.export_gltf(mill, collision="complex", extra=dict(hub=HUB))
    sails = build_sails()
    V.export_gltf(sails, collision="none")
    for ob in (mill, sails):
        co = np.array([p.co[:] for p in ob.data.vertices])
        print("%-20s %6d faces  bounds %s .. %s" % (ob.name, ob["voxel_faces"], np.round(co.min(axis=0), 3), np.round(co.max(axis=0), 3)))
    print("hub", HUB)
    if NO_RENDER:
        return
    sails.location = HUB
    sails.rotation_euler = (0.0, math.radians(38.0), 0.0)                    # the X of the picture
    for tag, az, el in (("", -30, 32), ("_right", 40, 24), ("_back", 160, 26)):
        render(os.path.join(V.PREVIEWS, "windmill%s.png" % tag), target=(0, 0, 5.6), az=az, el=el, dist=44, res=(900, 1100))


main()
