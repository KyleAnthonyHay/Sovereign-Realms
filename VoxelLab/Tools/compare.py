#!/usr/bin/env python3
"""Put a postcard screenshot next to the reference:  ../Tools/.venv/bin/python Tools/compare.py <shot name> [out name] [reference]

The reference is References/village.png unless given (a path under the project, e.g. References/Remake/town.png for the town).

Writes Saved/Screenshots/VL/<out>_side.png (reference above, ours below, both 1600 x 900) and <out>_blend.png
(the two at half strength over each other: misplaced buildings show as doubles)."""
import os
import sys

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHOTS = os.path.join(ROOT, "Saved", "Screenshots", "VL")


def load_shot(name):
    im = Image.open(os.path.join(SHOTS, name + ".png")).convert("RGB")
    w, h = im.size
    want = int(round(w * 900 / 1600.0))
    if h > want:                                    # letterbox bars from the constrained camera
        top = (h - want) // 2
        im = im.crop((0, top, w, top + want))
    return im.resize((1600, 900), Image.LANCZOS)


def main(a):
    name = a[0]
    out = a[1] if len(a) > 1 else name
    ref = Image.open(os.path.join(ROOT, a[2]) if len(a) > 2 else os.path.join(ROOT, "References", "village.png")).convert("RGB").resize((1600, 900))
    shot = load_shot(name)
    side = Image.new("RGB", (1600, 1800))
    side.paste(ref, (0, 0))
    side.paste(shot, (0, 900))
    side.save(os.path.join(SHOTS, out + "_side.png"))
    Image.blend(ref, shot, 0.5).save(os.path.join(SHOTS, out + "_blend.png"))
    shot.save(os.path.join(SHOTS, out + "_fit.png"))
    print(os.path.join(SHOTS, out + "_side.png"))


if __name__ == "__main__":
    main(sys.argv[1:])
