"""Quick look: python peek.py <character> <anim> <facing> [scale] -> strip PNG in the scratch dir (iteration aid)."""
import sys, importlib, os
import numpy as np
from PIL import Image
import pixelkit as pk

def strip(frames, team, bg, k):
    cells = []
    for c in frames:
        g = c.outlined().g
        rgba = pk.apply_team(pk.to_rgba(g), pk.to_mask(g), team)
        cells.append(pk.on_background(Image.fromarray(rgba, "RGBA"), bg))
    w, h = cells[0].size
    out = Image.new("RGB", (w * len(cells), h), bg)
    for i, im in enumerate(cells):
        out.paste(im, (i * w, 0))
    return pk.upscale(out, k)

if __name__ == "__main__":
    name, anim, facing = sys.argv[1:4]
    k = int(sys.argv[4]) if len(sys.argv) > 4 else 8
    out_dir = sys.argv[5] if len(sys.argv) > 5 else "."
    mod = importlib.import_module(name)
    frames = mod.build()
    blue, red = (0.05, 0.22, 0.80), (0.72, 0.07, 0.05)
    rows = []
    for a in anim.split(","):
        for f in facing.split(","):
            rows.append(strip(frames[(a, f)], blue if len(rows) % 2 == 0 else red, (104, 122, 62) if len(rows) % 2 == 0 else (196, 172, 124), k))
    W = max(r.width for r in rows)
    sheet = Image.new("RGB", (W, sum(r.height for r in rows)), (40, 40, 40))
    y = 0
    for r in rows:
        sheet.paste(r, (0, y)); y += r.height
    path = os.path.join(out_dir, "peek_%s.png" % name)
    sheet.save(path)
    print(path, sheet.size)
