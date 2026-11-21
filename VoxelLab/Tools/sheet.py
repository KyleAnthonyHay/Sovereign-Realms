#!/usr/bin/env python3
"""Contact sheets and GIFs from Saved/Screenshots/VL (run with ../Tools/.venv/bin/python: needs PIL).

  sheet.py sheet <out.png> <shot> [<shot> ...] [--crop x0,y0,x1,y1] [--cols N] [--width W]
  sheet.py gif <out.gif> <record name> [--crop x0,y0,x1,y1] [--step N] [--fps F] [--width W] [--from A] [--to B] [--skip i,j]
  sheet.py strip <out.png> <record name> [--crop ...] [--step N] [--cols N] [--width W] [--from A] [--to B]
Crop is in shares of the picture (0..1). A record name is the Name of vl.Record (frames Name_000.png ..).
"""
import glob, os, sys
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHOTS = os.path.join(ROOT, "Saved", "Screenshots", "VL")


def opt(a, name, default):
    if name in a:
        i = a.index(name)
        v = a[i + 1]
        del a[i:i + 2]
        return v
    return default


def load(path, crop):
    im = Image.open(path).convert("RGB")
    if crop:
        x0, y0, x1, y1 = [float(v) for v in crop.split(",")]
        im = im.crop((int(x0 * im.width), int(y0 * im.height), int(x1 * im.width), int(y1 * im.height)))
    return im


def frames(name, a):
    step, lo, hi = int(opt(a, "--step", 1)), int(opt(a, "--from", 0)), int(opt(a, "--to", 100000))
    skip = [int(v) for v in str(opt(a, "--skip", "")).split(",") if v]       # frames to replace with the one before
    files = sorted(glob.glob(os.path.join(SHOTS, name + "_[0-9][0-9][0-9].png")))
    files = [files[i - 1] if i in skip and i > 0 else f for i, f in enumerate(files)]
    return [f for i, f in enumerate(files) if lo <= i <= hi][::step]


def grid(ims, cols, width):
    w = width // cols
    ims = [im.resize((w, max(1, int(im.height * w / im.width)))) for im in ims]
    h = ims[0].height
    rows = (len(ims) + cols - 1) // cols
    out = Image.new("RGB", (w * cols, h * rows), (20, 20, 20))
    for i, im in enumerate(ims):
        out.paste(im, ((i % cols) * w, (i // cols) * h))
    return out


def main(a):
    if len(a) < 3:
        print(__doc__)
        return 1
    crop, width = opt(a, "--crop", None), int(opt(a, "--width", 0))
    mode, out = a[0], a[1]
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    if mode == "sheet":
        cols = int(opt(a, "--cols", 0))
        ims = [load(os.path.join(SHOTS, n + ".png"), crop) for n in a[2:]]
        grid(ims, cols or len(ims), width or 1600).save(out)
    elif mode == "strip":
        cols = int(opt(a, "--cols", 8))
        ims = [load(f, crop) for f in frames(a[2], a)]
        grid(ims, cols, width or 1800).save(out)
    elif mode == "gif":
        fps = float(opt(a, "--fps", 15))
        ims = [load(f, crop) for f in frames(a[2], a)]
        w = width or 480
        ims = [im.resize((w, int(im.height * w / im.width)), Image.LANCZOS) for im in ims]
        pal = ims[len(ims) // 2].quantize(colors=128, method=Image.MEDIANCUT, dither=Image.NONE)
        ims = [im.quantize(palette=pal, dither=Image.NONE) for im in ims]
        ims[0].save(out, save_all=True, append_images=ims[1:], duration=int(round(1000 / fps)), loop=0, optimize=True)
        print(out, len(ims), "frames", os.path.getsize(out) // 1024, "KB")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
