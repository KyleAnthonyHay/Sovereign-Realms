"""How each building sits in the postcard compared with References/village.png, and the placement that would match.

    python3 Tools/blender/fit.py            (plain Python: no numpy needed)

TARGETS are bounding boxes read off the reference picture (pixels, 1600 x 900): the whole asset including flags and
steps. For each, the asset's 3D box (SourceArt/Meshes/<name>.json) is projected through the postcard camera at a
trial position and uniform scale, and the position / scale are solved so that the projected box has the target's
centre and size. village_layout.py reads the result (SourceArt/fit.json).
"""
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import village_cam as C

MESHES = os.path.join(HERE, "..", "..", "SourceArt", "Meshes")
OUT = os.path.join(HERE, "..", "..", "SourceArt", "fit.json")

#  asset: (x0, y0, x1, y1) in the reference, ground height z, yaw, (scale min, max)
TARGETS = {
    "SM_TownHall":      ((572, 12, 1008, 468), 0.0, 0.0, (0.75, 1.1)),
    "SM_Barracks":      ((1092, 128, 1548, 490), 0.0, 0.0, (0.8, 1.2)),
    "SM_ArcheryRange":  ((100, 298, 528, 548), 1.0, 0.0, (0.8, 1.3)),
    "SM_FarmCottage_A": ((383, 483, 648, 702), 0.0, 0.0, (0.8, 1.2)),
    "SM_FarmCottage_B": ((962, 472, 1208, 648), 0.0, 0.0, (0.8, 1.2)),
    "SM_PlazaBanner":   ((742, 418, 815, 592), 0.0, 0.0, (0.8, 1.3)),
}


_points = {}


def points(name):
    """A sample of the asset's vertices (metres, Blender axes), read straight from its glTF."""
    if name in _points:
        return _points[name]
    import struct
    with open(os.path.join(MESHES, name + ".gltf")) as f:
        g = json.load(f)
    pts = []
    for mesh in g["meshes"]:
        for prim in mesh["primitives"]:
            acc = g["accessors"][prim["attributes"]["POSITION"]]
            view = g["bufferViews"][acc["bufferView"]]
            with open(os.path.join(MESHES, g["buffers"][view["buffer"]]["uri"]), "rb") as f:
                f.seek(view.get("byteOffset", 0) + acc.get("byteOffset", 0))
                stride = view.get("byteStride", 12)
                raw = f.read(stride * acc["count"])
            step = max(1, acc["count"] // 4000)
            for i in range(0, acc["count"], step):
                gx, gy, gz = struct.unpack_from("<fff", raw, i * stride)
                pts.append((gx, -gz, gy))                       # glTF is Y up: Blender (x, y, z) = (x, -z, y)
    _points[name] = pts
    return pts


def box(name, x, y, z, yaw, s):
    """The asset's outline in the picture: the pixel box of its vertices."""
    ca, sa = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
    xs, ys = [], []
    for (bx, by, bz) in points(name):
        px, py = C.project(x + (bx * ca - by * sa) * s, y + (bx * sa + by * ca) * s, z + bz * s)
        xs.append(px)
        ys.append(py)
    return min(xs), min(ys), max(xs), max(ys)


def solve(name):
    (tx0, ty0, tx1, ty1), z, yaw, (smin, smax) = TARGETS[name]
    x, y = C.unproject((tx0 + tx1) / 2.0, (ty0 + ty1) / 2.0 + (ty1 - ty0) * 0.2, z)
    s = 1.0
    for _ in range(30):
        x0, y0, x1, y1 = box(name, x, y, z, yaw, s)
        # scale from the diagonal of the box, then put the centre where the target's is
        s = min(smax, max(smin, s * math.hypot(tx1 - tx0, ty1 - ty0) / math.hypot(x1 - x0, y1 - y0)))
        x0, y0, x1, y1 = box(name, x, y, z, yaw, s)
        cx, cy = C.project(x, y, z)
        nx, ny = C.unproject(cx + ((tx0 + tx1) - (x0 + x1)) / 2.0, cy + ((ty0 + ty1) - (y0 + y1)) / 2.0, z)
        x, y = nx, ny
    x0, y0, x1, y1 = box(name, x, y, z, yaw, s)
    return dict(pos=[round(x, 2), round(y, 2)], scale=round(s, 3), box=[round(v) for v in (x0, y0, x1, y1)], target=[tx0, ty0, tx1, ty1])


def main():
    fit = {}
    for name in TARGETS:
        if not os.path.exists(os.path.join(MESHES, name + ".json")):
            continue
        r = solve(name)
        fit[name] = r
        tw, th = r["target"][2] - r["target"][0], r["target"][3] - r["target"][1]
        bw, bh = r["box"][2] - r["box"][0], r["box"][3] - r["box"][1]
        print("%-18s pos (%6.2f, %6.2f) scale %.2f | box %s vs target %s | w %d/%d h %d/%d" % (name, r["pos"][0], r["pos"][1], r["scale"], r["box"], r["target"], bw, tw, bh, th))
    with open(OUT, "w") as f:
        json.dump(fit, f, indent=1)


if __name__ == "__main__":
    main()
