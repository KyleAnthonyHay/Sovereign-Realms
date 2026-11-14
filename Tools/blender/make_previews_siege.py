"""Previews for the big units (horseman, catapult), read back from the shipped sheets like make_previews.py.

    Tools/.venv/bin/python Tools/blender/make_previews_siege.py [--no-gif]

Writes into SourceArt/Characters/previews/:
  lineup_siege.png            Shieldbearer, Archer, Horse Rider, Catapult side by side, both teams, x3 and true size
  skirmish_siege.png (+ _x2)  a mixed fight with the FX strips and the stone in it, at true size
  <name>_<anim>_contact.png   every frame, one row per facing, true size; the strike / release frame is labelled
  <name>_<anim>.gif           all eight facings at game speed, x2
"""

import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import make_previews as MP  # noqa: E402
import srpost  # noqa: E402

PREV = MP.PREV
FX = os.path.normpath(os.path.join(MP.OUT, "..", "FX"))
NAMES = ["horseman", "catapult"]


def fx_frame(name, i):
    meta = json.load(open(os.path.join(FX, name + ".json")))
    im = Image.open(os.path.join(FX, name + ".png")).convert("RGBA")
    w, h = meta["frame_size"]
    return im.crop((i * w, 0, (i + 1) * w, h)), tuple(meta["pivot_px"])


def lineup(sheets):
    shown = ["S", "SE", "E", "N"]
    cw, ch, piv = 190, 200, (95, 150)

    def strip(team, kind, k):
        g = MP.ground(len(sheets) * len(shown) * cw, ch, kind, seed=7)
        x = 0
        for s in sheets:
            for f in shown:
                MP.put(g, s.frame("idle", f, 0, team), s.pivot, (x + piv[0], piv[1]))
                x += cw
        return MP.up(g, k)

    rows = [("blue on olive, x2", strip("blue", "olive", 2)), ("red on sand, x2", strip("red", "sand", 2)),
            ("blue on olive, x1 (true size)", strip("blue", "olive", 1)), ("red on sand, x1 (true size)", strip("red", "sand", 1))]
    W = max(r[1].width for r in rows) + 16
    H = sum(r[1].height + 22 for r in rows) + 8
    out = Image.new("RGB", (W, H), MP.PANEL)
    y = 4
    for text, im in rows:
        MP.label(out, text, (8, y))
        out.paste(im, (8, y + 16))
        y += im.height + 22
    out.save(os.path.join(PREV, "lineup_siege.png"))


def skirmish(sb, ar, hm, ct):
    W, H = 760, 420
    units = [
        (ct, "attack", "E", 4, "blue", 110, 150), (ct, "attack", "E", 5, "blue", 120, 330), (ct, "walk", "NE", 2, "blue", 110, 240),
        (ar, "attack", "E", 5, "blue", 250, 120), (sb, "idle", "E", 2, "blue", 262, 216), (sb, "walk", "E", 1, "blue", 300, 330),
        (hm, "walk", "E", 2, "blue", 380, 110), (hm, "attack", "E", 3, "blue", 420, 230), (sb, "hit", "W", 0, "red", 520, 236),
        (hm, "walk", "W", 6, "red", 610, 130), (hm, "idle", "SW", 0, "red", 660, 250), (hm, "death", "W", 7, "red", 520, 380),
        (ct, "idle", "W", 0, "red", 650, 370), (ar, "attack", "W", 4, "red", 560, 96), (sb, "attack", "E", 3, "blue", 440, 330),
        (hm, "spawn", "S", 1, "blue", 250, 400), (ct, "death", "SW", 7, "red", 400, 60 + 20),
    ]
    stone = Image.open(os.path.join(MP.OUT, "stone_smear_color.png")).convert("RGBA")
    out = []
    for kind in ("olive", "sand"):
        g = MP.ground(W, H, kind, seed=21)
        for s, an, f, fr, team, x, y in sorted(units, key=lambda u: u[6]):
            MP.put(g, s.frame(an, f, fr, team), s.pivot, (x, y))
        for name, i, x, y in (("fx_dust", 2, 352, 112), ("fx_impact", 2, 580, 300), ("fx_debris", 2, 400, 40), ("fx_smoke", 3, 420, 70),
                              ("fx_fire", 1, 396, 76)):
            im, pv = fx_frame(name, i)
            g.paste(im, (x - pv[0], y - pv[1]), im)
        g.paste(stone, (250, 40), stone)
        out.append(g)
    x1 = Image.new("RGB", (W, H * 2 + 4), MP.PANEL)
    x1.paste(out[0], (0, 0))
    x1.paste(out[1], (0, H + 4))
    x1.save(os.path.join(PREV, "skirmish_siege.png"))
    MP.up(out[0], 2).save(os.path.join(PREV, "skirmish_siege_x2.png"))


def contact(s, anim, team, kind):
    a = s.meta["animations"][anim]
    c, n = s.cell, a["frames"]
    g = MP.ground(n * c, 8 * c, kind, seed=5)
    for r, f in enumerate(s.facings):
        for i in range(n):
            MP.put(g, s.frame(anim, f, i, team), s.pivot, (i * c + s.pivot[0], r * c + s.pivot[1]))
    d = ImageDraw.Draw(g)
    for r, f in enumerate(s.facings):
        d.text((4, r * c + 3), f, fill=(250, 245, 225))
    for i in range(n):
        d.text((i * c + 22, 3), str(i) + ("  STRIKE" if a.get("strike_frame") == i else ""), fill=(250, 245, 225))
    g.save(os.path.join(PREV, "%s_%s_contact.png" % (s.name, anim)))


def main():
    os.makedirs(PREV, exist_ok=True)
    sb, ar = MP.Sheet("shieldbearer"), MP.Sheet("archer")
    big = [MP.Sheet(n) for n in NAMES]
    lineup([sb, ar] + big)
    skirmish(sb, ar, *big)
    for s in big:
        for an in s.meta["animations"]:
            contact(s, an, "blue" if s.name == "horseman" else "red", "olive" if s.name == "horseman" else "sand")
            if "--no-gif" not in sys.argv:
                MP.gif(s, an, "blue" if s.name == "horseman" else "red", "olive", k=2)
    print("previews in", PREV)


if __name__ == "__main__":
    main()
