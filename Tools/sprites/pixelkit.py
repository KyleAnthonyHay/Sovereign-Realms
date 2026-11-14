"""Pixel paper-doll kit for the Sovereign Realms character sprites.

Everything is authored as indexed pixels: a part is a block of text where each
character is one pixel and names a palette entry. Frames are built by stamping
parts onto an indexed canvas in z-order, then an outline pass adds the 1 px
hue-shifted contour, and only then are colours resolved to RGBA. Working in
palette indices (not RGB) is what makes the team mask, the soft interior lines
and the "one step darker" far-limb shading exact.

No resampling or rotation of pixel data happens anywhere: every pose is a part
drawn by hand, or a hand-placed offset of one.
"""

from __future__ import annotations

import numpy as np
from PIL import Image

# --------------------------------------------------------------------------
# Palette. Ramps run light -> dark; lights lean warm, shadows lean cool/plum.
# --------------------------------------------------------------------------

RAMPS = {
    #          highlight          light              mid                shade              deep
    "skin":   [("a", (242, 196, 146)), ("b", (214, 154, 104)), ("c", (170, 106, 76)), ("d", (118, 68, 62))],
    "bronze": [("A", (255, 242, 178)), ("B", (236, 190, 84)), ("C", (190, 130, 52)), ("D", (130, 80, 44)), ("E", (82, 48, 40))],
    "linen":  [("1", (246, 238, 214)), ("2", (220, 204, 168)), ("3", (170, 152, 130)), ("4", (112, 98, 108))],
    "leather": [("p", (196, 138, 84)), ("q", (146, 94, 56)), ("r", (98, 60, 44)), ("s", (62, 38, 40))],
    "hair":   [("h", (96, 68, 58)), ("i", (60, 42, 48)), ("j", (36, 26, 38))],
    # Team ramp: neutral greys, stored so that linear 0.5 == "exactly TeamColor"
    # (material multiplies by 2). See SPRITE_SPEC.md "Team colour".
    "team":   [("W", (255, 255, 255)), ("X", (188, 188, 188)), ("Y", (137, 137, 137)), ("Z", (99, 99, 99))],
}

# Loose single entries (not part of a shading ramp).
EXTRA = {
    "k": (30, 22, 34),      # eyes, deepest accents
    "o": (40, 26, 36),      # hand-placed outline / interior line
    "w": (250, 246, 236),   # bowstring / eye glint / fletching white
    "f": (200, 70, 52),     # arrow fletching accent (fixed, not team)
    "t": (150, 150, 158),   # dull metal (arrowheads)
    "g": (58, 40, 46),      # bowstring (drawn bare, never outlined)
    "m": (255, 250, 224),   # slash smear, hot core
    "n": (244, 208, 128),   # slash smear, tail
    "u": (214, 198, 170),   # dust puff light
    "v": (160, 142, 122),   # dust puff shade
}

# Outline colour used around each material (hue-shifted dark of that material).
OUTLINE = {
    "skin": (88, 44, 44),
    "bronze": (66, 38, 34),
    "linen": (74, 62, 72),
    "leather": (44, 28, 32),
    "hair": (26, 18, 28),
    "team": (58, 58, 58),   # stays in the team mask: becomes a dark team hue
    None: (40, 26, 36),
}

PAL = {}        # char -> rgb
RAMP_OF = {}    # char -> ramp name
DARKER = {}     # char -> next darker char in its ramp (darkest maps to itself)
LINE_OF = {}    # char -> the char used for a soft interior line on that material
for _name, _ramp in RAMPS.items():
    for _i, (_c, _rgb) in enumerate(_ramp):
        PAL[_c] = _rgb
        RAMP_OF[_c] = _name
        DARKER[_c] = _ramp[min(_i + 1, len(_ramp) - 1)][0]
        LINE_OF[_c] = _ramp[-1][0]
for _c, _rgb in EXTRA.items():
    PAL[_c] = _rgb
    RAMP_OF[_c] = None
    DARKER[_c] = _c
    LINE_OF[_c] = "o" if _c not in ("k",) else "k"

# Outline pseudo-entries, one per material, so outlines stay indexed too.
OUT_CHAR = {"skin": "\x01", "bronze": "\x02", "linen": "\x03", "leather": "\x04", "hair": "\x05", "team": "\x06", None: "\x07"}
for _name, _c in OUT_CHAR.items():
    PAL[_c] = OUTLINE[_name]
    RAMP_OF[_c] = "team" if _name == "team" else None
    DARKER[_c] = _c
    LINE_OF[_c] = _c
OUT_CODES = np.array([ord(c) for c in OUT_CHAR.values()], dtype=np.uint8)
# When an outline pixel touches several materials, the earliest in this list wins.
OUT_PRIORITY = ["hair", None, "leather", "bronze", "linen", "skin", "team"]

TEAM_CODES = np.array([ord(c) for c, r in RAMP_OF.items() if r == "team"], dtype=np.uint8)
BARE_CODES = np.array([ord("o"), ord("g")], dtype=np.uint8)
TEAM_BOOST = 2.0


def srgb_to_lin(v):
    v = np.asarray(v, dtype=np.float64) / 255.0
    return np.where(v <= 0.04045, v / 12.92, ((v + 0.055) / 1.055) ** 2.4)


def lin_to_srgb(v):
    v = np.clip(np.asarray(v, dtype=np.float64), 0.0, 1.0)
    out = np.where(v <= 0.0031308, v * 12.92, 1.055 * np.power(v, 1 / 2.4) - 0.055)
    return np.round(out * 255.0).astype(np.uint8)


# --------------------------------------------------------------------------
# Parts
# --------------------------------------------------------------------------

class Part:
    """A hand-drawn block of pixels. '.' and ' ' are transparent."""

    def __init__(self, text, ax=0, ay=0):
        rows = [r for r in text.split("\n")]
        while rows and not rows[0].strip():
            rows.pop(0)
        while rows and not rows[-1].strip():
            rows.pop()
        # Strip common indentation so parts can sit inside indented code.
        indent = min(len(r) - len(r.lstrip(" ")) for r in rows if r.strip())
        rows = [r[indent:].rstrip() for r in rows]
        w = max(len(r) for r in rows)
        g = np.zeros((len(rows), w), dtype=np.uint8)
        for y, r in enumerate(rows):
            for x, ch in enumerate(r):
                if ch in ". ":
                    continue
                if ch not in PAL:
                    raise ValueError("unknown palette char %r in part row %r" % (ch, r))
                g[y, x] = ord(ch)
        self.g = g
        self.ax, self.ay = ax, ay

    @property
    def w(self):
        return self.g.shape[1]

    @property
    def h(self):
        return self.g.shape[0]

    def _clone(self, g, ax=None, ay=None):
        p = Part.__new__(Part)
        p.g = g
        p.ax = self.ax if ax is None else ax
        p.ay = self.ay if ay is None else ay
        return p

    def flip(self):
        """Mirror left-right (anchor mirrors with it)."""
        return self._clone(self.g[:, ::-1].copy(), ax=self.w - 1 - self.ax)

    def vflip(self):
        """Mirror top-bottom (anchor mirrors with it)."""
        return self._clone(self.g[::-1, :].copy(), ay=self.h - 1 - self.ay)

    def stair(self, run=2):
        """Step the columns up toward the left, one pixel every `run` columns: a lying figure becomes a
        falling one. Columns move whole, so no pixel is resampled. The right-hand end stays put."""
        h, w = self.g.shape
        rise = (w - 1) // run
        g = np.zeros((h + rise, w), dtype=np.uint8)
        for x in range(w):
            up = (w - 1 - x) // run
            g[rise - up:rise - up + h, x] = self.g[:, x]
        return self._clone(g, ay=self.ay + rise)

    def darker(self, steps=1):
        """Every pixel `steps` ramp steps darker: far-side limbs, cast shadow."""
        lut = np.arange(256, dtype=np.uint8)
        for c, d in DARKER.items():
            lut[ord(c)] = ord(d)
        g = self.g
        for _ in range(steps):
            g = lut[g]
        return self._clone(g.copy())

    def remap(self, mapping):
        g = self.g.copy()
        for a, b in mapping.items():
            g[self.g == ord(a)] = ord(b) if b not in ". " else 0
        return self._clone(g)

    def tall(self, n=1):
        """Repeat the top row n times above the part (anchor stays on the old top row): hides bob gaps under a kilt."""
        g = np.vstack([self.g[:1]] * n + [self.g])
        return self._clone(g, ay=self.ay + n)

    def rows(self, y0, y1):
        """Crop to rows [y0, y1) keeping the anchor in the same place."""
        return self._clone(self.g[y0:y1].copy(), ay=self.ay - y0)


def P(text, ax=0, ay=0):
    return Part(text, ax, ay)


class Held:
    """A limb plus the thing in its hand: `arm` is anchored at the shoulder, `grip` is the
    hand position relative to that anchor, `item` is anchored at its own grip point."""

    def __init__(self, arm, grip, item=None, item_front=False):
        self.arm, self.grip, self.item, self.item_front = arm, grip, item, item_front

    def flip(self, relight=None):
        item = self.item.flip() if self.item is not None else None
        if item is not None and relight:
            item = item.remap(relight)
        return Held(self.arm.flip(), (-self.grip[0], self.grip[1]), item, self.item_front)

    def with_item(self, item, item_front=None):
        return Held(self.arm, self.grip, item, self.item_front if item_front is None else item_front)

    def draw(self, c, x, y, sep=None):
        if self.item is not None and not self.item_front:
            c.put(self.item, x + self.grip[0], y + self.grip[1])
        c.put(self.arm, x, y, sep=sep)
        if self.item is not None and self.item_front:
            c.put(self.item, x + self.grip[0], y + self.grip[1])


# --------------------------------------------------------------------------
# Canvas
# --------------------------------------------------------------------------

class Canvas:
    def __init__(self, w, h, ox=0, oy=0):
        self.g = np.zeros((h, w), dtype=np.uint8)
        self.f = np.zeros((h, w), dtype=np.uint8)   # un-outlined overlay: strings, smears, dust
        self.ox, self.oy = ox, oy   # design-grid origin inside the cell

    def put(self, part, x, y, sep=None, erase=False, fx=False):
        """Stamp `part` with its anchor at design coords (x, y).

        sep: None | 'all' | 'br' | 'bl' | 'b' | 'l' | 'r' | 't' -- draw a soft
        interior line on whatever is already underneath, on those sides of the part.
        """
        x0 = self.ox + x - part.ax
        y0 = self.oy + y - part.ay
        H, W = self.g.shape
        ph, pw = part.g.shape
        sx0, sy0 = max(0, -x0), max(0, -y0)
        sx1, sy1 = min(pw, W - x0), min(ph, H - y0)
        if sx0 >= sx1 or sy0 >= sy1:
            return self
        if sx0 > 0 or sy0 > 0 or sx1 < pw or sy1 < ph:
            raise ValueError("part clipped by the cell at (%d,%d)" % (x, y))
        src = part.g
        mask = np.zeros((H, W), dtype=bool)
        mask[y0:y0 + ph, x0:x0 + pw] = src > 0
        if sep:
            self._soft_line(mask, sep)
        if fx:
            region = self.f[y0:y0 + ph, x0:x0 + pw]
            region[src > 0] = src[src > 0]
        elif erase:
            self.g[mask] = 0
        else:
            region = self.g[y0:y0 + ph, x0:x0 + pw]
            region[src > 0] = src[src > 0]
        return self

    def _soft_line(self, mask, sides):
        H, W = mask.shape
        ring = np.zeros_like(mask)
        if sides == "all":
            sides = "tblr"
        if "l" in sides:
            ring[:, :-1] |= mask[:, 1:]
        if "r" in sides:
            ring[:, 1:] |= mask[:, :-1]
        if "t" in sides:
            ring[:-1, :] |= mask[1:, :]
        if "b" in sides:
            ring[1:, :] |= mask[:-1, :]
        ring &= ~mask
        ring &= self.g > 0
        ys, xs = np.nonzero(ring)
        for y, x in zip(ys, xs):
            self.g[y, x] = ord(LINE_OF[chr(self.g[y, x])])

    def px(self, x, y, ch, fx=False):
        cx, cy = self.ox + x, self.oy + y
        if 0 <= cx < self.g.shape[1] and 0 <= cy < self.g.shape[0]:
            (self.f if fx else self.g)[cy, cx] = ord(ch) if ch not in ". " else 0
        else:
            raise ValueError("pixel outside the cell at (%d,%d)" % (x, y))
        return self

    def line(self, x0, y0, x1, y1, ch, fx=False):
        """Bresenham, for strings and shafts between hand-placed end points."""
        dx, dy = abs(x1 - x0), -abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx + dy
        x, y = x0, y0
        while True:
            self.px(x, y, ch, fx)
            if x == x1 and y == y1:
                break
            e2 = 2 * err
            if e2 >= dy:
                err += dy
                x += sx
            if e2 <= dx:
                err += dx
                y += sy
        return self

    def outlined(self):
        """Return a copy with the 1 px contour added (4-neighbourhood, so corners stay crisp)."""
        g = self.g
        solid = g > 0
        H, W = g.shape
        out = g.copy()
        # Hand-placed line pixels (strings, arrow edges) are already "outline": they never grow one.
        src = np.where(np.isin(g, BARE_CODES), 0, g).astype(np.uint8)
        nb = np.zeros((4, H, W), dtype=np.uint8)
        nb[0, 1:, :] = src[:-1, :]    # pixel above
        nb[1, :-1, :] = src[1:, :]    # below
        nb[2, :, 1:] = src[:, :-1]    # left
        nb[3, :, :-1] = src[:, 1:]    # right
        edge = (~solid) & (nb.max(axis=0) > 0)
        ys, xs = np.nonzero(edge)
        for y, x in zip(ys, xs):
            mats = set()
            for k in range(4):
                c = nb[k, y, x]
                if c:
                    mats.add(RAMP_OF[chr(c)] if chr(c) not in ("k", "o") else None)
            for m in OUT_PRIORITY:
                if m in mats:
                    out[y, x] = ord(OUT_CHAR[m])
                    break
        out[self.f > 0] = self.f[self.f > 0]
        c2 = Canvas.__new__(Canvas)
        c2.g, c2.f, c2.ox, c2.oy = out, np.zeros_like(out), self.ox, self.oy
        return c2

    def copy(self):
        c2 = Canvas.__new__(Canvas)
        c2.g, c2.f, c2.ox, c2.oy = self.g.copy(), self.f.copy(), self.ox, self.oy
        return c2

    def bounds(self):
        """(x0, y0, x1, y1) of everything drawn, in cell pixels, inclusive."""
        ys, xs = np.nonzero((self.g > 0) | (self.f > 0))
        return int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())


# --------------------------------------------------------------------------
# Resolve to pixels
# --------------------------------------------------------------------------

_LUT = np.zeros((256, 4), dtype=np.uint8)
for _c, _rgb in PAL.items():
    _LUT[ord(_c)] = (_rgb[0], _rgb[1], _rgb[2], 255)


def to_rgba(g):
    """Indexed grid -> RGBA array (team regions stay as the neutral grey ramp)."""
    return _LUT[g]


def to_mask(g):
    """Indexed grid -> uint8 mask, 255 where the pixel is team-tinted."""
    return (np.isin(g, TEAM_CODES) * 255).astype(np.uint8)


def apply_team(rgba, mask, team_linear):
    """What the game material does: lerp(colour, colour * TeamColor * 2, mask), in linear space."""
    out = rgba.copy()
    m = mask > 127
    lin = srgb_to_lin(rgba[..., :3][m])
    tinted = lin * np.asarray(team_linear, dtype=np.float64)[None, :] * TEAM_BOOST
    out[..., :3][m] = lin_to_srgb(tinted)
    return out


def upscale(img, k):
    return img.resize((img.width * k, img.height * k), Image.NEAREST)


def on_background(rgba_img, bg):
    base = Image.new("RGBA", rgba_img.size, tuple(bg) + (255,))
    base.alpha_composite(rgba_img)
    return base.convert("RGB")
