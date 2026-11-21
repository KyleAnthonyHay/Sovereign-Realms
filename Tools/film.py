#!/usr/bin/env python3
"""Cuts the loading film together from a recording made in the game (run with Tools/.venv/bin/python):

    1. write the shots to Saved/Film.txt (the format is in sr.Film's help, Source/.../Battle/SRDebugCommands.cpp;
       the take that shipped is kept as SourceArt/Movies/LoadingBattle.film.txt)
    2. in PIE at 1920 x 1080 (sr.WindowSize 1920 1080):  sr.Film record     -> Saved/Film/Frames/FNNNNN.png
    3. Tools/.venv/bin/python Tools/film.py [out.mp4] [--sheet name]

sr.Film logs where each shot's frames start ("FILM shot i frame a count c head h tail t"). Each shot was recorded with
a head (the picture settling after the cut: thrown away, all but its last `tail` frames) and a tail; consecutive shots
are cross-faded over those `tail` frames, so no cut lands on a moving camera. The film is the main menu's backdrop and
loops there (ASRHUD::UpdateMenuFilm): its last LOOP frames dissolve into the frames that led up to its first, so the
loop has no seam. --fade makes it fade in from black and out to it instead (a film to be played once).
Output: H.264, 30 fps, yuv420p, faststart; default Content/Movies/LoadingBattle.mp4 with a copy in SourceArt/Movies.
--sheet also saves a contact sheet of the middle frame of every shot under Saved/Screenshots/SR.
"""
import os, re, shutil, subprocess, sys
import numpy as np
from PIL import Image
import imageio_ffmpeg

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRAMES = os.path.join(ROOT, "Saved", "Film", "Frames")
LOG = os.path.expanduser("~/Library/Logs/Unreal Engine/SovereignRealmsEditor/SovereignRealms.log")
W, H, FPS = 1920, 1080, 30
FADE_IN, FADE_OUT = 12, 24
LOOP = 24


def shots():
    lines = [l for l in open(LOG, errors="replace") if "FILM " in l]
    start = max(i for i, l in enumerate(lines) if "FILM start" in l)
    out = []
    for l in lines[start:]:
        m = re.search(r"FILM shot (\d+) frame (\d+) count (\d+) head (\d+) tail (\d+)", l)
        if m:
            out.append(tuple(int(x) for x in m.groups()[1:]))
    return out


def load(i):
    im = Image.open(os.path.join(FRAMES, "F%05d.png" % i)).convert("RGB")
    if im.size != (W, H):
        # (a window a little off 16:9: fill the frame, crop the overhang evenly)
        s = max(W / im.size[0], H / im.size[1])
        im = im.resize((round(im.size[0] * s), round(im.size[1] * s)), Image.LANCZOS)
        x, y = (im.size[0] - W) // 2, (im.size[1] - H) // 2
        im = im.crop((x, y, x + W, y + H))
    return np.asarray(im, dtype=np.float32)


def main(argv):
    args = [a for a in argv if not a.startswith("--")]
    if "--sheet" in argv:
        args.remove(argv[argv.index("--sheet") + 1])
    out = args[0] if args else os.path.join(ROOT, "Content", "Movies", "LoadingBattle.mp4")
    sheet = argv[argv.index("--sheet") + 1] if "--sheet" in argv else None
    have = len([f for f in os.listdir(FRAMES) if f.endswith(".png")])
    seq = []                                   # (frame a, frame b or None, weight of b)
    sh = shots()
    mids = []
    for k, (a, count, head, tail) in enumerate(sh):
        if a + count > have + 1:
            print("shot %d is not all on disk (%d frames there): stopping before it" % (k, have))
            sh = sh[:k]
            break
    for k, (a, count, head, tail) in enumerate(sh):
        first = a + head - (tail if k > 0 else 0)
        last = min(a + count, have)
        body_end = last - (tail if k < len(sh) - 1 else 0)
        if k > 0:                              # cross-fade from the previous shot's tail
            pa, pc, ph, pt = sh[k - 1]
            for j in range(tail):
                seq.append((pa + pc - pt + j, first + j, (j + 1) / (tail + 1)))
            first += tail
        mids.append(len(seq) + (body_end - first) // 2)
        seq += [(i, None, 0.0) for i in range(first, body_end)]
    fade = "--fade" in argv
    if not fade and sh and sh[0][2] >= LOOP and len(seq) > LOOP:
        # the loop: the end dissolves into the first shot's own run-up, which arrives exactly at the first frame
        a0 = sh[0][0] + sh[0][2]
        for j in range(LOOP):
            a, b, w = seq[len(seq) - LOOP + j]
            if b is None:
                seq[len(seq) - LOOP + j] = (a, a0 - LOOP + j, (j + 1) / (LOOP + 1))
    n = len(seq)
    print("%d shots, %d frames, %.1f s" % (len(sh), n, n / FPS))
    cmd = [imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", "%dx%d" % (W, H), "-r", str(FPS), "-i", "-",
           "-c:v", "libx264", "-preset", "slow", "-crf", "19", "-maxrate", "8M", "-bufsize", "16M", "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-an", out]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    picks = []
    for t, (a, b, w) in enumerate(seq):
        f = load(a)
        if b is not None:
            f = f * (1.0 - w) + load(b) * w
        g = min(1.0, (t + 1) / FADE_IN, (n - t) / FADE_OUT) if fade else 1.0
        if g < 1.0:
            f = f * (g * g * (3 - 2 * g))
        frame = np.clip(f + 0.5, 0, 255).astype(np.uint8)
        if t in mids:
            picks.append(Image.fromarray(frame))
        p.stdin.write(frame.tobytes())
    p.stdin.close()
    p.wait()
    print(out, "%.1f MB" % (os.path.getsize(out) / 1e6))
    if out.startswith(os.path.join(ROOT, "Content", "Movies")):
        keep = os.path.join(ROOT, "SourceArt", "Movies", os.path.basename(out))
        shutil.copyfile(out, keep)
        shutil.copyfile(os.path.join(ROOT, "Saved", "Film.txt"), os.path.splitext(keep)[0] + ".film.txt")
    if sheet and picks:
        cols = 2
        rows = (len(picks) + 1) // 2
        s = Image.new("RGB", (cols * 960, rows * 540))
        d = os.path.join(ROOT, "Saved", "Screenshots", "SR")
        for i, im in enumerate(picks):
            im.save(os.path.join(d, "%s_shot%d.png" % (sheet, i)))
            s.paste(im.resize((960, 540)), ((i % cols) * 960, (i // cols) * 540))
        s.save(os.path.join(d, sheet + "_sheet.png"))
        print(os.path.join(d, sheet + "_sheet.png"))


if __name__ == "__main__":
    main(sys.argv[1:])
