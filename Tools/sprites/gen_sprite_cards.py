#!/usr/bin/env python3
"""Offline half of the troop-sprite import: the card meshes and the arrow sprite.

    Tools/.venv/bin/python Tools/sprites/gen_sprite_cards.py

Writes into SourceArt/Characters/:
  cards.gltf (+ .bin)   SM_UnitCard   the quad every troop sprite is drawn on, cut along the pivot row
                        SM_ArrowCard  the quad an arrow is drawn on
  arrow_color.png       the arrow, pointing right, same pixel treatment as the troops (plum outline)
  arrow_teammask.png    255 on the fletching, which is tinted by TeamColor like the troops' cloth

The unit card is sized from the sheet metadata (shieldbearer.json: quad size, pivot), so it follows a
re-render with another cell size or pivot. Then run Tools/import_character_sprites.py in the editor.

Mesh axes (Unreal, cm). Both cards lie in a plane of their local frame and are oriented by code:
  SM_UnitCard   plane X = 0. +Y = sprite right, +Z = sprite up, origin = the pivot (the unit's feet).
                Three rows of vertices: bottom, pivot row, top. The material keeps the top row on an
                upright plane through the feet and lays the part below the pivot on the ground.
  SM_ArrowCard  plane Z = 0. +X = toward the arrowhead, origin = the middle of the shaft.
"""
import json
import os
import sys

import numpy as np
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "Tools", "world"))
from meshlib import Mesh, write_gltf  # noqa: E402

OUT = os.path.join(ROOT, "SourceArt", "Characters")
META = json.load(open(os.path.join(OUT, "shieldbearer.json")))
CM_PER_PX = float(META["cm_per_px"])


def unit_card():
    w, h = META["quad_size_cm"]
    pu, pv = META["pivot_uv_in_cell"]
    m = Mesh("SM_UnitCard")
    n = (-1.0, 0.0, 0.0)                               # toward the viewer once the card faces the camera
    rows = [(-(1.0 - pv) * h, 1.0), (0.0, pv), (pv * h, 0.0)]            # (z, v): bottom, pivot, top
    ids = []
    for z, v in rows:
        ids.append((m.vert((0.0, -pu * w, z), n, (0.0, v)), m.vert((0.0, (1.0 - pu) * w, z), n, (1.0, v))))
    for (a, b), (c, d) in zip(ids[:-1], ids[1:]):
        m.quad(a, b, d, c)
    return m


# ---------------------------------------------------------------------------------------- arrow
def hexc(s):
    s = s.lstrip("#")
    return tuple(int(s[i:i + 2], 16) for i in (0, 2, 4))


OUTLINE = hexc("1b1220")                     # the troops' outline colour
WOOD = [hexc("d9b27a"), hexc("9c6f3f")]      # lit, shaded
BRONZE = [hexc("f6e3a0"), hexc("dba94a"), hexc("9a6a2a")]
GREY = [179, 123, 80]                        # team ramp: about linear 0.45, 0.20, 0.08 (see SPRITE_SPEC.md, Team colour)
ARROW_W, ARROW_H = 44, 9                     # px; 77 cm long at 1.75 cm per px: oversized so a shot reads at the far zoom


def arrow_sprite():
    col = np.zeros((ARROW_H, ARROW_W, 4), np.uint8)
    mask = np.zeros((ARROW_H, ARROW_W), np.uint8)
    mid = ARROW_H // 2

    def put(x, y, rgb, team=False):
        if 0 <= x < ARROW_W and 0 <= y < ARROW_H:
            col[y, x] = (*rgb, 255)
            mask[y, x] = 255 if team else 0

    for x in range(3, 36):                                           # shaft, one pixel, lit toward the head
        put(x, mid, WOOD[0] if x > 12 else WOOD[1])
    head = {0: (33, 41), -1: (34, 39), 1: (34, 39), -2: (35, 37), 2: (35, 37)}        # leaf-shaped bronze head
    for dy, (x0, x1) in head.items():
        for x in range(x0, x1 + 1):
            shade = 0 if dy < 0 else (1 if dy == 0 else 2)
            put(x, mid + dy, BRONZE[shade])
    put(41, mid, BRONZE[0])
    for dy in (-2, -1, 1, 2):                                         # fletching: two swept vanes in the team colour
        x0 = 2 + (abs(dy) - 1)
        x1 = 11 - (abs(dy) - 1) * 2
        for x in range(x0, x1 + 1):
            g = GREY[0] if dy == -2 else (GREY[1] if abs(dy) == 1 else GREY[2])
            put(x, mid + dy, (g, g, g), team=True)
    put(2, mid, WOOD[1]); put(1, mid, WOOD[1])                       # nock
    # one-pixel outline outside the silhouette
    a = col[..., 3] > 0
    grown = a.copy()
    for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        grown |= np.roll(np.roll(a, dy, 0), dx, 1)
    edge = grown & ~a
    edge[0, :] &= ~a[-1, :]                                          # undo wrap-around from np.roll (nothing touches the border, but be exact)
    col[edge] = (*OUTLINE, 255)
    Image.fromarray(col).save(os.path.join(OUT, "arrow_color.png"))
    Image.fromarray(mask).save(os.path.join(OUT, "arrow_teammask.png"))
    return ARROW_W * CM_PER_PX, ARROW_H * CM_PER_PX


def arrow_card(length, width):
    m = Mesh("SM_ArrowCard")
    n = (0.0, 0.0, 1.0)
    a = m.vert((-length / 2, -width / 2, 0.0), n, (0.0, 0.0))
    b = m.vert((length / 2, -width / 2, 0.0), n, (1.0, 0.0))
    c = m.vert((length / 2, width / 2, 0.0), n, (1.0, 1.0))
    d = m.vert((-length / 2, width / 2, 0.0), n, (0.0, 1.0))
    m.quad(a, b, c, d)
    return m


if __name__ == "__main__":
    length, width = arrow_sprite()
    count = write_gltf(os.path.join(OUT, "cards.gltf"), [unit_card(), arrow_card(length, width)])
    print("wrote", count, "card meshes, arrow %d x %d px (%.1f x %.1f cm)" % (ARROW_W, ARROW_H, length, width))
