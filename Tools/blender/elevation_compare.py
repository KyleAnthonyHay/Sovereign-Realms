"""Render the idle stance at several camera elevations and write previews/elevation_compare.png.

    Tools/.venv/bin/python Tools/blender/elevation_compare.py [45 40 30 22]

Use it to pick --elev for build_all.sh once the gameplay camera pitch is final.
"""

import json
import os
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
OUT = os.path.normpath(os.path.join(HERE, "..", "..", "SourceArt", "Characters"))
BLENDER = os.environ.get("BLENDER", "/Applications/Blender.app/Contents/MacOS/Blender")

import make_previews as mp  # noqa: E402
import srpost  # noqa: E402

elevs = [float(v) for v in sys.argv[1:]] or [45.0, 40.0, 30.0, 22.0]
facings = ["S", "SE", "E", "N"]
rows = []
for e in elevs:
    tiles = []
    for name in mp.NAMES:
        npz = os.path.join(OUT, "_build", "elev_%s_%g.npz" % (name, e))
        subprocess.run([BLENDER, "-b", os.path.join(OUT, "blender", name + ".blend"), "-P",
                        os.path.join(HERE, "render_sprites.py"), "--", "--anims", "idle", "--frames", "0",
                        "--facings", ",".join(facings), "--elev", str(e), "--out", npz],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        d = np.load(npz)
        meta = json.loads(str(d["meta"]))
        piv = tuple(meta["render"]["pivot"])
        for i in range(len(meta["index"])):
            c = {k: d[k][i] for k in ("id", "L", "ao", "z", "n")}
            rgba, mask, _ = srpost.stylise(c, meta["key_dir_cam"], meta["render"]["cm_per_px"])
            tiles.append((Image.fromarray(srpost.tint(rgba, mask, "blue")), piv))
        os.remove(npz)
    cell = tiles[0][0].width
    g = mp.ground(len(tiles) * 112, cell, "olive", seed=17)
    for i, (im, piv) in enumerate(tiles):
        mp.put(g, im.crop((24, 0, 136, cell)), (piv[0] - 24, piv[1]), (i * 112 + piv[0] - 24, piv[1]))
    g = mp.up(g, 3)
    ImageDraw.Draw(g).text((6, 4), "elevation %g degrees" % e, fill=(255, 250, 230))
    rows.append(g)
out = Image.new("RGB", (rows[0].width, sum(r.height for r in rows)))
y = 0
for r in rows:
    out.paste(r, (0, y))
    y += r.height
out.save(os.path.join(OUT, "previews", "elevation_compare.png"))
print("wrote previews/elevation_compare.png", out.size)
