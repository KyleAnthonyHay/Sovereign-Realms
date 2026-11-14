"""Quick look at rendered cells: python peek.py cells.npz out.png [scale] [team] [crop_margin]
One row per (animation, facing), one column per frame."""
import json
import sys

import numpy as np
from PIL import Image

import srpost

path, out = sys.argv[1], sys.argv[2]
scale = int(sys.argv[3]) if len(sys.argv) > 3 else 4
team = sys.argv[4] if len(sys.argv) > 4 else "blue"
margin = int(sys.argv[5]) if len(sys.argv) > 5 else 16
d = np.load(path)
meta = json.loads(str(d["meta"]))
cell = d["id"].shape[1]
crop = (margin, margin, cell - margin, cell - 4)
cw, ch = crop[2] - crop[0], crop[3] - crop[1]
rows = []
for an, fc, fr in meta["index"]:
    if (an, fc) not in rows:
        rows.append((an, fc))
cols = max(fr for _, _, fr in meta["index"]) + 1
sheet = Image.new("RGB", (cols * cw * scale, len(rows) * ch * scale), (40, 40, 46))
for i, (an, fc, fr) in enumerate(meta["index"]):
    c = {k: d[k][i] for k in ("id", "L", "ao", "z", "n")}
    rgba, mask, nm = srpost.stylise(c, meta["key_dir_cam"], meta["render"]["cm_per_px"])
    im = Image.fromarray(srpost.tint(rgba, mask, team)).crop(crop).resize((cw * scale, ch * scale), Image.NEAREST)
    r = rows.index((an, fc))
    bg = (110, 124, 70) if r % 2 == 0 else (190, 168, 122)
    tile = Image.new("RGB", im.size, bg)
    tile.paste(im, (0, 0), im)
    sheet.paste(tile, (fr * cw * scale, r * ch * scale))
sheet.save(out)
print(out, sheet.size, rows)
