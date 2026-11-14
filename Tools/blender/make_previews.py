"""Previews from the shipped sheets: line-up, contact sheets, animated GIFs, skirmish mock.

    Tools/.venv/bin/python Tools/blender/make_previews.py [--no-gif]

Everything is read back from SourceArt/Characters/<name>_color.png / _teammask.png / .json, so the previews show
exactly what the game will sample, tinted with the in-game team formula.
"""

import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
OUT = os.path.normpath(os.path.join(HERE, "..", "..", "SourceArt", "Characters"))
PREV = os.path.join(OUT, "previews")
REFERENCE = os.path.expanduser(
    "~/.t3/userdata/attachments/a8ef9e7b-e88a-43d9-9917-cdfb78dcfb46-a4bc9626-82af-4791-aaa3-b1d2f21bf4b9.png")

import srpost  # noqa: E402

NAMES = ["shieldbearer", "archer"]
BG = {"olive": (104, 120, 64), "sand": (190, 166, 120)}
PANEL = (30, 28, 34)


class Sheet:
    def __init__(self, name):
        self.name = name
        self.meta = json.load(open(os.path.join(OUT, name + ".json")))
        self.color = np.array(Image.open(os.path.join(OUT, self.meta["sheet"]["color"])).convert("RGBA"))
        self.mask = np.array(Image.open(os.path.join(OUT, self.meta["sheet"]["teammask"])).convert("L"))
        self.cell = self.meta["sheet"]["cell"][0]
        self.pivot = tuple(self.meta["pivot_px"])
        self.facings = self.meta["facings"]["order"]
        self._tinted = {}

    def frame(self, anim, facing, fr, team):
        if team not in self._tinted:
            self._tinted[team] = srpost.tint(self.color, self.mask, team)
        a = self.meta["animations"][anim]
        c = self.cell
        x0 = (a["origin_cell"][0] + fr) * c
        y0 = (a["origin_cell"][1] + self.facings.index(facing)) * c
        return Image.fromarray(self._tinted[team][y0:y0 + c, x0:x0 + c])


def ground(w, h, kind, seed=3):
    """A quiet pixel-textured ground at sprite resolution, so the sprites are judged on something like the map."""
    rng = np.random.default_rng(seed)
    base = np.array(BG[kind], np.float32)
    n1 = rng.random((h // 8 + 2, w // 8 + 2)).repeat(8, 0).repeat(8, 1)[:h, :w]
    n2 = rng.random((h // 2 + 1, w // 2 + 1)).repeat(2, 0).repeat(2, 1)[:h, :w]
    n3 = rng.random((h, w))
    v = (n1 - 0.5) * 0.10 + (n2 - 0.5) * 0.10 + (n3 - 0.5) * 0.06
    v = np.rint(v * 14) / 14
    img = np.clip(base[None, None, :] * (1 + v[..., None]), 0, 255).astype(np.uint8)
    return Image.fromarray(img)


def shadow_of(sprite, pivot):
    """Ground shadow thrown up-screen and to the right, as the top-left key light would."""
    a = sprite.split()[3]
    px, py = pivot
    kx, ky = 0.62, 0.34
    # output (x, y) samples input: height above feet dy = (py - y) / ky ; x_in = x - kx * dy
    coef = (1, kx / ky, -kx / ky * py, 0, 1 / ky, py - py / ky)
    return a.transform(a.size, Image.AFFINE, coef, Image.NEAREST)


def put(canvas, sprite, pivot, at, shadow=True):
    x, y = at[0] - pivot[0], at[1] - pivot[1]
    if shadow:
        sh = shadow_of(sprite, pivot)
        dark = Image.new("RGB", sprite.size, (22, 20, 30))
        canvas.paste(dark, (x, y), sh.point(lambda v: 96 if v else 0))
    canvas.paste(sprite, (x, y), sprite)


def up(im, k):
    return im.resize((im.width * k, im.height * k), Image.NEAREST)


def label(im, text, xy=(4, 3), fill=(235, 230, 215)):
    ImageDraw.Draw(im).text(xy, text, fill=fill)


# ---------------------------------------------------------------------------------------------- line-up

def lineup(sheets):
    crop = (26, 22, 134, 142)                 # region of the cell shown for standing figures
    cw, ch = crop[2] - crop[0], crop[3] - crop[1]
    piv = (sheets[0].pivot[0] - crop[0], sheets[0].pivot[1] - crop[1])
    shown = ["S", "SE", "E", "N", "W"]
    figs = [(s, f) for s in sheets for f in shown]
    cols = len(figs)

    def strip(team, kind, k):
        g = ground(cols * cw, ch, kind, seed=7 if kind == "olive" else 11)
        for i, (s, f) in enumerate(figs):
            put(g, s.frame("idle", f, 0, team).crop(crop), piv, (i * cw + piv[0], piv[1]))
        return up(g, k)

    ref = Image.open(REFERENCE).convert("RGB") if os.path.exists(REFERENCE) else None
    fig_px = sheets[0].meta["figure_height_px"]
    rows = [("blue on olive, x4", strip("blue", "olive", 4)), ("red on sand, x4", strip("red", "sand", 4)),
            ("red on olive, x2", strip("red", "olive", 2)), ("blue on sand, x2", strip("blue", "sand", 2)),
            ("blue on olive, x1 (true size)", strip("blue", "olive", 1)),
            ("red on sand, x1 (true size)", strip("red", "sand", 1))]
    refw = 0
    if ref is not None:
        # the reference figure is about 186 px tall in its 234 px crop; match that to our figure at x4
        k = fig_px * 4 / 186.0
        ref4 = ref.resize((int(ref.width * k), int(ref.height * k)), Image.BICUBIC)
        ref1 = ref.resize((max(1, int(ref.width * k / 4)), max(1, int(ref.height * k / 4))), Image.LANCZOS)
        refw = ref4.width + 16
    W = max(r[1].width for r in rows) + refw + 16
    H = sum(r[1].height + 22 for r in rows) + 8
    out = Image.new("RGB", (W, H), PANEL)
    y = 4
    for i, (text, im) in enumerate(rows):
        label(out, text, (8 + refw, y))
        out.paste(im, (8 + refw, y + 16))
        if ref is not None and i == 0:
            label(out, "reference, figure scaled to match x4", (8, y))
            out.paste(ref4, (8, y + 16))
        if ref is not None and i == 4:
            label(out, "reference at x1", (8, y))
            out.paste(ref1, (8, y + 16))
        y += im.height + 22
    out.save(os.path.join(PREV, "lineup.png"))
    return out.size


# ---------------------------------------------------------------------------------------------- contact sheets

def contact(s, anim, team="blue", kind="olive", k=2):
    a = s.meta["animations"][anim]
    c = s.cell
    n = a["frames"]
    g = ground(n * c, 8 * c, kind, seed=5)
    for r, f in enumerate(s.facings):
        for i in range(n):
            put(g, s.frame(anim, f, i, team), s.pivot, (i * c + s.pivot[0], r * c + s.pivot[1]))
    g = up(g, k)
    d = ImageDraw.Draw(g)
    for r, f in enumerate(s.facings):
        d.text((4, r * c * k + 3), f, fill=(250, 245, 225))
    for i in range(n):
        tag = str(i)
        if a.get("strike_frame") == i:
            tag += "  STRIKE"
        d.text((i * c * k + 22, 3), tag, fill=(250, 245, 225))
    g.save(os.path.join(PREV, "%s_%s_contact.png" % (s.name, anim)))


# ---------------------------------------------------------------------------------------------- GIFs

def durations(s, anim):
    a = s.meta["animations"][anim]
    g = s.meta["gameplay_reference"]
    n = a["frames"]
    if a["drive"] == "distance":
        return [1000.0 * a["cycle_distance_cm"] / g["max_speed"] / n] * n
    if a["drive"] == "attack_phase":
        out = []
        for frames, pm, total in ((a["windup_frames"], a["windup_phase_map"], g["windup"]),
                                  (a["recovery_frames"], a["recovery_phase_map"], g["recovery"])):
            edges = list(pm) + [1.0]
            out += [1000.0 * total * (edges[i + 1] - edges[i]) for i in range(len(frames))]
        out[-1] += 1000.0 * (g["attack_interval"] - g["windup"] - g["recovery"])     # waits in idle; held here
        return out
    d = [1000.0 / a["fps"]] * n
    if a.get("hold_last"):
        d[-1] += 1200
    elif not a["loop"]:
        d[-1] += 500
    return d


def gif(s, anim, team="blue", kind="olive", k=4):
    a = s.meta["animations"][anim]
    c = s.cell
    order = ["S", "SE", "E", "NE", "SW", "W", "NW", "N"]
    frames = []
    for i in range(a["frames"]):
        g = ground(4 * c, 2 * c, kind, seed=9)
        for j, f in enumerate(order):
            put(g, s.frame(anim, f, i, team), s.pivot, ((j % 4) * c + s.pivot[0], (j // 4) * c + s.pivot[1]))
        g = up(g, k)
        d = ImageDraw.Draw(g)
        for j, f in enumerate(order):
            d.text(((j % 4) * c * k + 6, (j // 4) * c * k + 4), f, fill=(250, 245, 225))
        frames.append(g.convert("P", palette=Image.ADAPTIVE, colors=128))
    dur = [max(20, int(round(v / 10.0)) * 10) for v in durations(s, anim)]
    frames[0].save(os.path.join(PREV, "%s_%s.gif" % (s.name, anim)), save_all=True, append_images=frames[1:],
                   duration=dur, loop=0, disposal=1)
    return dur


# ---------------------------------------------------------------------------------------------- skirmish

def skirmish(sheets):
    sb, ar = sheets
    W, H = 640, 300
    units = [
        # sheet, anim, facing, frame, team, x, y
        (ar, "attack", "E", 3, "blue", 70, 110), (ar, "attack", "E", 5, "blue", 96, 176), (ar, "attack", "NE", 1, "blue", 60, 244),
        (ar, "walk", "E", 2, "blue", 150, 84),
        (sb, "walk", "E", 1, "blue", 196, 246), (sb, "idle", "E", 2, "blue", 208, 128),
        (sb, "attack", "E", 3, "blue", 300, 120), (sb, "hit", "W", 0, "red", 366, 126),
        (sb, "attack", "SE", 1, "blue", 288, 196), (sb, "attack", "NW", 4, "red", 352, 232),
        (sb, "death", "E", 7, "blue", 262, 268), (ar, "death", "W", 7, "red", 432, 84),
        (sb, "walk", "W", 5, "red", 448, 176), (sb, "idle", "SW", 5, "red", 500, 262),
        (ar, "attack", "W", 4, "red", 560, 120), (ar, "attack", "W", 6, "red", 584, 196), (ar, "idle", "SW", 0, "red", 520, 92),
        (sb, "spawn", "S", 1, "blue", 140, 186),
    ]
    out = []
    for kind in ("olive", "sand"):
        g = ground(W, H, kind, seed=21)
        for s, an, f, fr, team, x, y in sorted(units, key=lambda u: u[6]):
            put(g, s.frame(an, f, fr, team), s.pivot, (x, y))
        out.append(g)
    x1 = Image.new("RGB", (W, H * 2 + 4), PANEL)
    x1.paste(out[0], (0, 0))
    x1.paste(out[1], (0, H + 4))
    x1.save(os.path.join(PREV, "skirmish_x1.png"))
    up(x1, 2).save(os.path.join(PREV, "skirmish_x2.png"))


# ---------------------------------------------------------------------------------------------- normal map check

def normal_check(sheets):
    """Baked colour | the normal sheet | the same sprite half-relit from the right, as the Unreal material would."""
    tiles = []
    for s in sheets:
        nrm = np.array(Image.open(os.path.join(OUT, s.meta["sheet"]["normal"])).convert("RGB"))
        for anim, f, fr in (("idle", "S", 0), ("idle", "E", 0), ("attack", "SE", s.meta["animations"]["attack"]["strike_frame"])):
            a = s.meta["animations"][anim]
            c = s.cell
            x0, y0 = (a["origin_cell"][0] + fr) * c, (a["origin_cell"][1] + s.facings.index(f)) * c
            col = np.array(s.frame(anim, f, fr, "blue"))
            n = nrm[y0:y0 + c, x0:x0 + c].astype(np.float32) / 127.5 - 1.0
            n[..., 1] *= -1                                    # stored green is +down
            alpha = Image.fromarray(col[..., 3])
            outs = [Image.fromarray(col), Image.fromarray(nrm[y0:y0 + c, x0:x0 + c]).convert("RGBA")]
            outs[1].putalpha(alpha)
            for light in ((0.75, 0.35, 0.56), (-0.2, -0.5, 0.84)):
                l = np.array(light, np.float32)
                l /= np.linalg.norm(l)
                k = np.clip(n @ l, 0, 1) * 1.5 + 0.3
                lin = srpost._lin(col[..., :3]) * (0.5 + 0.5 * k[..., None])
                outs.append(Image.fromarray(np.dstack([srpost._srgb(lin), col[..., 3]])))
            row = ground(4 * c, c, "olive", seed=13)
            for i, im in enumerate(outs):
                row.paste(im, (i * c, 0), im)
            tiles.append(row)
    out = Image.new("RGB", (4 * sheets[0].cell, sum(t.height for t in tiles)), PANEL)
    y = 0
    for t in tiles:
        out.paste(t, (0, y))
        y += t.height
    out = up(out, 3)
    label(out, "baked colour", (6, 4))
    label(out, "normal sheet", (6 + 480, 4))
    label(out, "50% relit, light from right", (6 + 960, 4))
    label(out, "50% relit, light from front-below", (6 + 1440, 4))
    out.save(os.path.join(PREV, "normal_check.png"))


def main():
    os.makedirs(PREV, exist_ok=True)
    sheets = [Sheet(n) for n in NAMES]
    print("lineup", lineup(sheets))
    skirmish(sheets)
    normal_check(sheets)
    for s in sheets:
        for an in s.meta["animations"]:
            contact(s, an, "blue" if s.name == "shieldbearer" else "red", "olive" if s.name == "shieldbearer" else "sand")
            if "--no-gif" not in sys.argv:
                print(s.name, an, "gif frame ms", gif(s, an))
    print("previews in", PREV)


if __name__ == "__main__":
    main()
