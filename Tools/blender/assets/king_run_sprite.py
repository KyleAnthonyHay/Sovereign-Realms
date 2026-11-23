"""King David running, as 8-bit pixel art: the loading screen's sprite (Source/SovereignRealms/VLLoadingScreen.cpp).

    Tools/.venv/Scripts/python Tools/blender/assets/king_run_sprite.py [--dump]

    -> SourceArt/UI/T_UI_KingRun.png               the sheet: FRAMES cells of CELL px side by side, he runs to the right
       SourceArt/Previews/kingdavid_run_8bit.gif   the cycle at 6x, on the loading screen's background
       SourceArt/Previews/kingdavid_run_8bit.png   the sheet at 6x
       SourceArt/UI/T_UI_Emblem.png                the emblem of References/Branding at 256 px, for the same screen

Drawn by hand, not rendered: King B (king_b.py) pixelated from a render of the model came out as noise at this size
(the fur mantle swallows the head, and his face is not on the side a profile shows), so he is a paper puppet of pixels
instead, in king_b's own colours and proportions (stocky, a big head under the crown, the fur mantle, the green cape
with its gold hem, steel greaves, the sword in its sheath on the near hip):

  * HEAD, TORSO and MANTLE are grids painted by hand;
  * the limbs are short thick strokes between the joints of a run cycle (LEG, the arms against the legs), the far ones
    in the shade colours;
  * the cape is a band streaming out behind with a ripple running down it;
  * each piece is drawn back to front with a 1 px dark outline of its own, so a near limb stands off what is behind
    it; no anti-aliasing anywhere, 16 colours (PALETTE);
  * FIXES are single pixels painted over a frame afterwards (--dump prints the frames as text to find them by).

The sheet goes into the game with Tools/ue/import_loading.py (point filtered, no mips, UI group). No Blender needed
(it lives here beside king_b.py, whose figure it draws).
"""
import math
import os
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
SHEET = os.path.join(ROOT, "SourceArt", "UI", "T_UI_KingRun.png")
GIF = os.path.join(ROOT, "SourceArt", "Previews", "kingdavid_run_8bit.gif")

FRAMES = 8
CELL = (64, 48)                 # one frame of the sheet (px)
GROUND = 45                     # the row his soles stand on
FPS = 11

# 16 colours, king_b._PAL's: the outline first
PALETTE = {
    "k": "#120D0B",                                       # outline, pupil
    "G": "#FFB616", "g": "#C27A0E", "R": "#D8551C",       # gold, its shade, the crown's gems
    "S": "#C87439", "s": "#98501F",                       # skin, its shade
    "H": "#3E2B20", "h": "#553A2A",                       # hair and beard, dark leather
    "B": "#7B4A24",                                       # belt, sleeves, boots
    "F": "#F7D6A4", "f": "#C79864",                       # the fur mantle, its shade
    "C": "#4F6E1F", "c": "#6B8F2E", "d": "#2F4516",       # the cape and tunic: green, lit, shaded
    "M": "#8A888E", "W": "#CFCAC8",                       # steel, its shine
}
BACKGROUND = "#0B1220"          # the loading screen's (VLLoadingScreen.cpp)
KEYS = list(PALETTE)

HEAD = [                        # he looks right; NECK is the pixel of the grid that sits on the shoulders
    "..G.G.G.G.G..",
    "..GGGGGGGGG..",
    "..GRGGWGGRG..",
    "..ggggggggg..",
    ".HHHHHHSSSS..",
    ".HhHHHSSSSSS.",
    ".HHHHHSSWkSS.",
    ".HhHHsSSSSSSS",
    ".HHHHHsSSSSS.",
    "..HHHhHHHHHH.",
    "..HHHHHhHHHH.",
    "...HHhHHHHH..",
    "....HHHHhH...",
]
NECK = (5, 12)
TORSO = [                       # leaning into the run; HIP is where the legs hang from, SHOULDER the near arm, BACK the cape
    ".............",
    ".............",
    "...CCCCCCC...",
    "...CCCCCCCc..",
    "...CCCCCCCc..",
    "...CCCCGCCc..",
    "...CCCCCCCc..",
    "...dCCCCCCc..",
    "...BBBGBBBB..",
    "...CCCCCCCc..",
    "..CCCdCCCCc..",
    "..CCdCCCCCc..",
    "..CdCCCCdCc..",
    "..GGGGGGGGg..",
]
MANTLE = [                      # the fur over his shoulders, on the torso's grid: over the arm, under the beard
    "...FFFFFFFF..",
    ".FFFFFFFFFFF.",
    "FFFFFFFFFFFFF",
    ".FFfFFFFFfFF.",
    "..ffFfffFff..",
]
HIP, SHOULDER, BACK = (7, 10), (7, 4), (3, 2)

# The run, one stride of the near leg: (thigh, shin) in degrees from straight down, positive swings backwards; the far
# leg is half a stride on.  0 contact, 1 down, 2 passing, 3 push-off, 4 lifted behind, 5 heel up, 6 knee through, 7 reach.
LEG = [(-42, 10), (-20, 44), (8, 24), (36, 6), (44, 60), (20, 100), (-30, 100), (-56, 60)]
LIFT = [0, 0, 0, 2, 0, 0, 0, 2]           # px off the ground (the two frames in the air)
THIGH, SHIN, UPPER, FORE = 6.0, 6.0, 4.5, 4.5

# Painted over by hand: frame -> [(x, y, palette key, or "." for nothing)], x from the left and y from the top of the cell
FIXES = {
}


def hex_rgb(h):
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))


class Canvas:
    def __init__(self):
        self.px = np.full((CELL[1], CELL[0]), -1, np.int32)
        self.layer = None

    def begin(self):
        self.layer = np.full(self.px.shape, -1, np.int32)

    def dot(self, x, y, key):
        x, y = int(round(x)), int(round(y))
        if 0 <= x < CELL[0] and 0 <= y < CELL[1]:
            self.layer[y, x] = KEYS.index(key)

    def stroke(self, a, b, r, key):
        """Every pixel within r of the segment a-b."""
        ax, ay, bx, by = a[0], a[1], b[0], b[1]
        dx, dy = bx - ax, by - ay
        for y in range(int(min(ay, by) - r - 1), int(max(ay, by) + r + 2)):
            for x in range(int(min(ax, bx) - r - 1), int(max(ax, bx) + r + 2)):
                t = 0.0 if dx == dy == 0 else max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / (dx * dx + dy * dy)))
                if (x - ax - t * dx) ** 2 + (y - ay - t * dy) ** 2 <= r * r:
                    self.dot(x, y, key)

    def stamp(self, grid, x0, y0):
        for y, row in enumerate(grid):
            for x, k in enumerate(row):
                if k != ".":
                    self.dot(x0 + x, y0 + y, k)

    def end(self):
        """Lays the piece over what is drawn, a dark line round it."""
        solid = self.layer >= 0
        edge = np.zeros_like(solid)
        edge[1:] |= solid[:-1]
        edge[:-1] |= solid[1:]
        edge[:, 1:] |= solid[:, :-1]
        edge[:, :-1] |= solid[:, 1:]
        self.px[edge & ~solid] = 0
        self.px[solid] = self.layer[solid]
        self.layer = None


def polar(p, deg, length):
    """From p, length px along a limb hanging deg from straight down (positive: backwards, to the left)."""
    a = math.radians(deg)
    return (p[0] - math.sin(a) * length, p[1] + math.cos(a) * length)


def leg_points(hip, thigh, shin):
    knee = polar(hip, thigh, THIGH)
    ankle = polar(knee, thigh + shin, SHIN)
    a = math.radians(thigh + shin)
    toe = (ankle[0] + math.cos(a) * 2.6, ankle[1] + math.sin(a) * 2.6)
    return knee, ankle, toe


def draw_leg(cv, hip, thigh, shin, near):
    knee, ankle, toe = leg_points(hip, thigh, shin)
    cv.begin()
    cv.stroke(hip, knee, 2.0, "B" if near else "h")
    cv.stroke(knee, ankle, 1.6, "M")
    if near:                                                   # the greave's shine, down its front
        a = math.radians(thigh + shin)
        f = (math.cos(a) * 0.9, math.sin(a) * 0.9)
        cv.stroke((knee[0] + f[0], knee[1] + f[1]), ((knee[0] + ankle[0]) * 0.5 + f[0], (knee[1] + ankle[1]) * 0.5 + f[1]), 0.5, "W")
    cv.stroke(ankle, toe, 1.2, "B" if near else "h")
    cv.end()


def draw_arm(cv, shoulder, upper, bend, near):
    elbow = polar(shoulder, upper, UPPER)
    fist = polar(elbow, upper - bend, FORE)
    cv.begin()
    cv.stroke(shoulder, elbow, 1.6, "B" if near else "h")
    cv.stroke(elbow, fist, 1.4, "M" if near else "h")
    if near:
        cv.stroke(elbow, ((elbow[0] + fist[0]) * 0.5, (elbow[1] + fist[1]) * 0.5), 0.5, "W")
    cv.stroke(fist, fist, 1.5, "S" if near else "s")
    cv.end()


def draw_cape(cv, root, f):
    """A band from the back of the shoulders streaming out behind, a ripple running down it, the gold hem at its end."""
    cv.begin()
    n = 21
    ph = 2.0 * math.pi * f / 4.0                                # (two ripples a stride: one a step)
    for t in range(n + 1):
        u = t / n
        cy = root[1] + 3.0 + 9.0 * u + 2.4 * u * math.sin(6.0 * u - ph)
        half = 3.4 + 1.9 * u
        top, bot = int(round(cy - half)), int(round(cy + half))
        x = root[0] - t
        hem = t >= n - 1
        for y in range(top, bot + 1):
            if hem:
                k = "g" if y >= bot - 1 else "G"
            elif y == top:
                k = "c"
            elif y >= bot - 1:
                k = "d"
            else:
                k = "C"
            cv.dot(x, y, k)
        if not hem and t % 6 == 4:                               # the gold studs along it
            cv.dot(x, int(round(cy)), "G")
    cv.end()


def frame(f):
    a = 2.0 * math.pi * f / FRAMES
    tl, sl = LEG[f]
    tr, sr = LEG[(f + FRAMES // 2) % FRAMES]
    # the hips as high as the lower foot leaves them (so he rises and sinks as he runs), then the air
    low = max(max(p[1] for p in leg_points((0.0, 0.0), t, s)) for t, s in ((tl, sl), (tr, sr)))
    hip = (37.0, float(round(GROUND - 1.2 - low - LIFT[f])))
    tx, ty = int(hip[0]) - HIP[0], int(hip[1]) - HIP[1]
    shoulder = (tx + SHOULDER[0], ty + SHOULDER[1])
    cv = Canvas()
    draw_cape(cv, (tx + BACK[0], ty + BACK[1]), f)
    draw_arm(cv, (shoulder[0] + 1, shoulder[1]), -40.0 * math.cos(a) + 6.0, 62.0, False)
    draw_leg(cv, (hip[0] + 1, hip[1]), tr, sr, False)
    draw_leg(cv, hip, tl, sl, True)
    cv.begin()
    cv.stamp(TORSO, tx, ty)
    cv.end()
    # the sword in its sheath on the near hip: the grip up and forward, the scabbard down and back
    mouth = (hip[0] + 1.0, hip[1] - 2.0)
    swing = 48.0 + 5.0 * math.sin(2.0 * a)
    cv.begin()
    cv.stroke(mouth, polar(mouth, swing, 11.0), 1.0, "B")
    cv.stroke(polar(mouth, swing, 10.0), polar(mouth, swing, 11.5), 1.0, "G")
    cv.stroke(mouth, polar(mouth, swing + 180.0, 1.0), 1.6, "G")
    cv.stroke(polar(mouth, swing + 180.0, 2.0), polar(mouth, swing + 180.0, 4.0), 0.8, "h")
    cv.stroke(polar(mouth, swing + 180.0, 5.0), polar(mouth, swing + 180.0, 5.0), 1.0, "G")
    cv.end()
    draw_arm(cv, shoulder, 40.0 * math.cos(a) + 6.0, 78.0, True)
    cv.begin()
    cv.stamp(MANTLE, tx, ty)
    cv.end()
    cv.begin()
    cv.stamp(HEAD, tx + 7 - NECK[0], ty + 1 - NECK[1] + (1 if f in (1, 5) else 0))
    cv.end()
    for x, y, k in FIXES.get(f, ()):
        cv.px[y, x] = -1 if k == "." else KEYS.index(k)
    return cv.px


def main():
    pal = np.array([hex_rgb(PALETTE[k]) for k in KEYS], np.uint8)
    W, H = CELL
    out = [frame(f) for f in range(FRAMES)]
    rgba = np.zeros((H, W * FRAMES, 4), np.uint8)
    for f, res in enumerate(out):
        m = res >= 0
        cell = rgba[:, f * W:(f + 1) * W]
        cell[m, :3] = pal[res[m]]
        cell[m, 3] = 255
        box = np.argwhere(m)
        assert box[:, 0].min() > 0 and box[:, 0].max() < H - 1 and box[:, 1].min() > 0 and box[:, 1].max() < W - 1, "frame %d touches its cell's edge" % f
    os.makedirs(os.path.dirname(SHEET), exist_ok=True)
    Image.fromarray(rgba, "RGBA").save(SHEET)
    used = sorted({KEYS[i] for res in out for i in np.unique(res) if i >= 0})
    print("wrote %s: %d x %d, %d frames, %d colours (%s)" % (SHEET, rgba.shape[1], rgba.shape[0], FRAMES, len(used), "".join(used)))

    Z = 6                                      # the previews, on the loading screen's background
    os.makedirs(os.path.dirname(GIF), exist_ok=True)
    sheet = Image.fromarray(rgba, "RGBA")
    bg = Image.new("RGBA", sheet.size, hex_rgb(BACKGROUND) + (255,))
    bg.alpha_composite(sheet)
    bg.convert("RGB").resize((sheet.width * Z, sheet.height * Z), Image.NEAREST).save(GIF[:-4] + ".png")
    gif = [bg.crop((f * W, 0, (f + 1) * W, H)).convert("RGB").resize((W * Z, H * Z), Image.NEAREST) for f in range(FRAMES)]
    gif[0].save(GIF, save_all=True, append_images=gif[1:], duration=int(round(1000.0 / FPS)), loop=0)
    print("wrote", GIF)
    # the emblem that stands over him on the loading screen: the branding's, at 256 px
    emblem = os.path.join(ROOT, "References", "Branding", "sovereign_realms_emblem.png")
    if os.path.exists(emblem):
        small = os.path.join(os.path.dirname(SHEET), "T_UI_Emblem.png")
        Image.open(emblem).convert("RGBA").resize((256, 256), Image.LANCZOS).save(small)
        print("wrote", small)
    if "--dump" in sys.argv:
        for f, res in enumerate(out):
            print("frame", f)
            print("    " + "".join(str(x % 10) for x in range(W)))
            for y in range(H):
                print("%3d %s" % (y, "".join("." if i < 0 else KEYS[i] for i in res[y])))


if __name__ == "__main__":
    main()
