#!/usr/bin/env python3
"""Water-wall test (needs PIE running on the map): troops are ordered straight at and across deep water from several
sides, in formation, and shoved by a fight on the bank; the game's own count of troops standing in deep water
(sr.Status: inwater=) must stay 0.

  Tools/.venv/bin/python Tools/water_wall_test.py two|four [cases per body] [--case=startX,startY,waterX,waterY ...]

Deep spots are read from the map's own water map (SourceArt/Textures/T_WaterMap<sfx>.png: R = distance in from the
bank, G = ford), so the test follows the generator.
"""
import json, math, os, re, subprocess, sys, time
import numpy as np
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PIE = [sys.executable, os.path.join(ROOT, "Tools", "pie.py")]
LOG = os.path.expanduser("~/Library/Logs/Unreal Engine/SovereignRealmsEditor/SovereignRealms.log")
Image.MAX_IMAGE_PIXELS = None


def run(*cmds):
    subprocess.run(PIE + ["run"] + list(cmds), capture_output=True)


def status():
    """(inwater, [(label, x, y)]) from a fresh sr.Status."""
    mark = "WWT%d" % int(time.time() * 1000)
    run("sr.Status")
    time.sleep(0.6)
    with open(LOG, errors="replace") as f:
        lines = f.readlines()[-400:]
    last = max((i for i, l in enumerate(lines) if "STATUS t=" in l), default=None)
    if last is None:
        return -1, []
    m = re.search(r"inwater=(\d+)", lines[last])
    units = re.findall(r"LogSovereign:\s+(\S.*?)\s+pos=\(\s*(-?\d+),\s*(-?\d+),", "".join(lines[last:]))
    return int(m.group(1)), [(u[0], float(u[1]), float(u[2])) for u in units]


def main(map_id, per_body=3):
    sfx = "" if map_id == "two" else "4"
    L = json.load(open(os.path.join(ROOT, "SourceArt", "World", "layout%s.json" % sfx)))
    img = np.asarray(Image.open(os.path.join(ROOT, "SourceArt", "Textures", "T_WaterMap%s.png" % sfx)))
    res = img.shape[0]
    ox, oy = L["water"]["map"]["origin"]
    size = L["water"]["map"]["size"]
    px = size / res
    B = L["map"]["half_extent"]
    deep = (img[..., 0] > 150) & (img[..., 1] < 20)
    dry = img[..., 0] == 0

    def world(r, c):
        return ox + (c + 0.5) * px, oy + (r + 0.5) * px

    rng = np.random.default_rng(7)
    rows, cols = np.nonzero(deep)
    cases = []
    # spread: bucket the deep texels on a coarse grid, a few per bucket
    cell = 6000.0
    buckets = {}
    for r, c in zip(rows[::37], cols[::37]):
        x, y = world(r, c)
        if abs(x) > B - 300 or abs(y) > B - 300:
            continue
        buckets.setdefault((int(x // cell), int(y // cell)), []).append((r, c))
    for key in sorted(buckets):
        pts = buckets[key]
        for k in rng.choice(len(pts), size=min(per_body, len(pts)), replace=False):
            r, c = pts[k]
            x, y = world(r, c)
            # walk out in a random direction to dry land, then 13 m further
            for a in rng.permutation(8):
                dx, dy = math.cos(a * math.pi / 4), math.sin(a * math.pi / 4)
                d = 0.0
                while d < 4000.0:
                    d += px
                    rr, cc = int(r + dy * d / px), int(c + dx * d / px)
                    if not (0 <= rr < res and 0 <= cc < res) or dry[rr, cc]:
                        break
                sx, sy = x + dx * (d + 1300.0), y + dy * (d + 1300.0)
                rr, cc = int((sy - oy) / px), int((sx - ox) / px)
                if d < 4000.0 and abs(sx) < B - 300 and abs(sy) < B - 300 and 0 <= rr < res and 0 <= cc < res and dry[rr, cc]:
                    cases.append((sx, sy, x, y, x - dx * (d + 900.0), y - dy * (d + 900.0)))
                    break
    if EXPLICIT:                                                # --case=sx,sy,wx,wy (repeatable): just these, from these starts
        cases = [(sx, sy, x, y, 2 * x - sx, 2 * y - sy) for sx, sy, x, y in EXPLICIT]
    print("%s: %d cases" % (map_id, len(cases)))
    run("sr.Fog 0", "sr.Speed 3", "sr.Give gold 9000")
    bad = 0
    for i, (sx, sy, x, y, fx, fy) in enumerate(cases):
        cmds = ["sr.ResetBattle", "sr.Fog 0", "sr.Speed 3"]
        for j in range(6):
            cmds.append("sr.Spawn %s %.0f %.0f" % ("shield" if j < 4 else "archer", sx + (j % 3 - 1) * 110, sy + (j // 3) * 110))
        run(*cmds)
        time.sleep(0.5)
        worst, where = 0, None
        for phase, (tx, ty) in enumerate(((x, y), (fx, fy), (x, y))):
            run("sr.SelectAll", "sr.OrderMove %.0f %.0f" % (tx, ty))
            for _ in range(3 if phase != 1 else 4):
                time.sleep(1.1)
                n, units = status()
                if n > worst:
                    worst, where = n, (phase, tx, ty)
        if phase == 2:                                           # a fight on the bank: enemies arrive at the squad's backs
            run("sr.Spawn shield %.0f %.0f enemy" % (sx, sy), "sr.Spawn shield %.0f %.0f enemy" % (sx + 120, sy), "sr.Spawn horse %.0f %.0f enemy" % (sx, sy + 120),
                "sr.Spawn shield %.0f %.0f enemy" % (sx - 120, sy), "sr.Spawn horse %.0f %.0f enemy" % (sx + 60, sy - 120))
            for _ in range(5):
                time.sleep(1.1)
                n, units = status()
                if n > worst:
                    worst, where = n, ("fight", x, y)
        print("case %2d start (%6.0f,%6.0f) water (%6.0f,%6.0f): %s" % (i, sx, sy, x, y, "ok" if worst == 0 else "IN WATER %d %s" % (worst, where)), flush=True)
        bad += worst > 0
    run("sr.Speed 1")
    print("RESULT %s: %d of %d cases put a troop in deep water" % (map_id, bad, len(cases)))


EXPLICIT = [tuple(float(v) for v in a.split("=", 1)[1].split(",")) for a in sys.argv if a.startswith("--case=")]

if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    main(args[0], int(args[1]) if len(args) > 1 else 3)
