"""The loading screen's art (Source/SovereignRealms/VLLoadingScreen.cpp): King David running, and what he jumps.

    Tools/.venv/Scripts/python Tools/blender/assets/king_run_sprite.py

    -> SourceArt/UI/T_UI_KingRun.png        the run: 8 cells side by side, he runs to the right
       SourceArt/UI/T_UI_RunnerProps.png    the runner's obstacles: a rock, a barrel, stakes, an arrow, a crow (2 frames)
       SourceArt/UI/T_UI_Emblem.png         the emblem of References/Branding at 256 px
       Source/SovereignRealms/VLLoadingArt.inl   the cells' sizes and places, for the widget (generated: do not edit)
       SourceArt/Previews/kingdavid_run_8bit.gif, .png   the cycle and the sheet at 3x, on the loading screen's background

The run is the owner's pack, References/KingRunSprite (see its README.txt): king_run_strip.png, 8 cells of 128 x 128
side by side, binary alpha, one palette, played 0..7 at 12 fps. It goes in as it is (no trimming, no re-centring: the
cells share their registration), and the widget puts the pack's pivot, pixel (84, 120) of every cell, on the ground at
his column. On screen a pixel of it is a whole number of the screen's (2 at 1080p: the cell is 256 px).
Ducking he runs crouched: References/KingCrouchRunSprite, the same format and pivot, as T_UI_KingCrouchRun (frame for
frame with the run, so the widget switches between them at the same frame).
What can be hit of him is measured here from his silhouette, frame by frame: the columns his body fills (at least
BODY_ROWS of the cell's rows opaque: the trailing cape and the sword's tip do not count), from his crown to his soles.
The obstacles are our own, painted by hand below (PROPS) at half that resolution, to sit with his fat pixels.

Everything goes into the game with Tools/ue/import_loading.py (point filtered, no mips, UI group). No Blender needed
(the script lives here beside king_b.py, whose figure the first version of it drew).
"""
import os

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
PACK = os.path.join(ROOT, "References", "KingRunSprite")
CROUCH_PACK = os.path.join(ROOT, "References", "KingCrouchRunSprite")
UI = os.path.join(ROOT, "SourceArt", "UI")
SHEET = os.path.join(UI, "T_UI_KingRun.png")
CROUCH_SHEET = os.path.join(UI, "T_UI_KingCrouchRun.png")
PROPS_SHEET = os.path.join(UI, "T_UI_RunnerProps.png")
INL = os.path.join(ROOT, "Source", "SovereignRealms", "VLLoadingArt.inl")
GIF = os.path.join(ROOT, "SourceArt", "Previews", "kingdavid_run_8bit.gif")

FPS = 12                        # the pack's (king_run_animation.json)
CELL = 128
PIVOT = (84, 120)               # the pack's shared pivot, from the cell's top left: his feet on the ground line
BODY_ROWS = 60
BACKGROUND = (11, 18, 32)       # the loading screen's (VLLoadingScreen.cpp)

# The obstacles, a character a pixel (each twice the run's pixels on the sheet). They come at him from the right.
PROP_COLOURS = {
    "k": "#120D0B",
    "m": "#69676F", "M": "#8A888E", "W": "#C4C0C0",       # stone, steel
    "g": "#4F6E1F",                                       # moss
    "b": "#5A3418", "B": "#7B4A24", "L": "#96602F",       # a barrel's staves
    "t": "#7E4E2B", "T": "#A46C3E", "Y": "#C9965E",       # cut wood
    "R": "#D8551C", "F": "#F7D6A4",                       # an arrow's feathers
    "c": "#2B3147", "C": "#4A5478", "G": "#FFB616", "e": "#ECE7E1",   # a crow
}
PROPS = [
    ("Rock", [
        "....kkkkk....",
        "..kkWWMMMkk..",
        ".kWWMMMMMMMk.",
        "kWMMMMMmMMMMk",
        "kMMgMMMmmMMMk",
        "kMggMMMMmMMmk",
        "kMMMMmMMMMmmk",
        "kmMMmmmMMmmmk",
        ".kkkkkkkkkkk.",
    ]),
    ("Barrel", [
        "..kkkkkkk..",
        ".kLLLLLLLk.",
        "kkMMWMMMMkk",
        "kLBLBBLBBbk",
        "kLBLBBLBBbk",
        "kLBLBBLBBbk",
        "kLBLBBLBBbk",
        "kLBLBBLBBbk",
        "kLBLBBLBBbk",
        "kLBLBBLBBbk",
        "kkMMWMMMMkk",
        "kLBLBBLBBbk",
        ".kbBbbBbbk.",
        "..kkkkkkk..",
    ]),
    ("Stakes", [
        ".......k.......",
        "..k...kYk...k..",
        ".kYk..kTk..kYk.",
        ".kTTk.kTk.kTTk.",
        "..kTk.kTk.kTk..",
        "..kTTkkTkkTTk..",
        "...kTkkTkkTk...",
        "...kTTkTkTTk...",
        ".kkkkTTTTTkkkk.",
        "kttttTTTTTttttk",
        ".kkkkTtTtTkkkk.",
        "....kTkTkTk....",
        "...kTTkTkTTk...",
        "...kTkkTkkTk...",
        "..kTTkkTkkTTk..",
        "..kkk.kkk.kkk..",
    ]),
    ("Arrow", [
        "..k.........kkk.",
        ".kWkkkkkkkkkRFRk",
        "kWWTTTTTTTTTFRFk",
        ".kWkkkkkkkkkRFRk",
        "..k.........kkk.",
    ]),
    ("CrowA", [                 # wings up
        ".......kk......",
        "......kcCk.....",
        ".....kcCCk.....",
        "..kkkkCCCkk....",
        ".kcckcCCCcckkk.",
        "kGGcecccccccCck",
        ".kkccccccccckk.",
        "...kkccccckk...",
        ".....kkkkk.....",
        "...............",
    ]),
    ("CrowB", [                 # wings down
        "...............",
        "...............",
        "..kkk..........",
        ".kcckkkkkkkkkk.",
        "kGGcecccccccCck",
        ".kkccCCCcccckk.",
        "...kkCCCkkkk...",
        "....kcCCk......",
        ".....kcCk......",
        "......kk.......",
    ]),
]


def hex_rgb(h):
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))


def run_sheet(pack=PACK, name="king_run_animation.json", out=SHEET):
    import json
    anim = json.load(open(os.path.join(pack, name), encoding="utf-8"))
    assert anim["frame_size"] == {"w": CELL, "h": CELL} and anim["fps"] == FPS, anim
    assert (anim["pivot_pixels_top_left_origin"]["x"], anim["pivot_pixels_top_left_origin"]["y"]) == PIVOT, anim
    im = Image.open(os.path.join(pack, anim["sheet"])).convert("RGBA")
    sheet = np.asarray(im)
    n = anim["frame_count"]
    assert sheet.shape == (CELL, CELL * n, 4), sheet.shape
    assert set(np.unique(sheet[..., 3])) <= {0, 255}, "the pack's alpha is binary"
    im.save(out)
    boxes = []
    for i in range(n):
        m = sheet[:, i * CELL:(i + 1) * CELL, 3] > 0
        cols = np.where(m.sum(axis=0) >= BODY_ROWS)[0]
        rows = np.where(m.any(axis=1))[0]
        # as the widget wants it: behind / in front of the pivot's column, the soles and the crown above the ground
        boxes.append((PIVOT[0] - int(cols.min()), int(cols.max()) + 1 - PIVOT[0], max(0, PIVOT[1] - 1 - int(rows.max())), PIVOT[1] - int(rows.min())))
        print("  frame %d: body columns %d..%d, rows %d..%d" % (i, cols.min(), cols.max(), rows.min(), rows.max()))
    print("wrote %s: %d frames of %d x %d (copied from the pack)" % (out, n, CELL, CELL))
    air = max(range(n), key=lambda i: boxes[i][2])         # the frame with his soles highest: the jump's pose
    return sheet, n, air, boxes


def props_sheet():
    cells = []
    for name, rows in PROPS:
        w = len(rows[0])
        assert all(len(r) == w for r in rows), name
        g = np.zeros((len(rows), w, 4), np.uint8)
        for y, row in enumerate(rows):
            for x, k in enumerate(row):
                if k != ".":
                    g[y, x] = hex_rgb(PROP_COLOURS[k]) + (255,)
        cells.append((name, np.repeat(np.repeat(g, 2, axis=0), 2, axis=1)))
    H = max(c.shape[0] for _, c in cells)
    W = sum(c.shape[1] + 2 for _, c in cells)
    sheet = np.zeros((H, W, 4), np.uint8)
    where, x = [], 0
    for name, c in cells:
        sheet[:c.shape[0], x:x + c.shape[1]] = c
        where.append((name, x, c.shape[1], c.shape[0]))
        x += c.shape[1] + 2
    Image.fromarray(sheet, "RGBA").save(PROPS_SHEET)
    print("wrote %s: %d x %d, %s" % (PROPS_SHEET, W, H, ", ".join(n for n, *_ in where)))
    return sheet, where


def main():
    os.makedirs(UI, exist_ok=True)
    sheet, n, air, boxes = run_sheet()
    _, cn, _, crouch = run_sheet(CROUCH_PACK, "king_crouch_run_animation.json", CROUCH_SHEET)
    assert cn == n, "the crouch-run has as many frames as the run (it takes over at the same one)"
    cw = ch = CELL
    props, where = props_sheet()
    emblem = os.path.join(ROOT, "References", "Branding", "sovereign_realms_emblem.png")
    if os.path.exists(emblem):
        Image.open(emblem).convert("RGBA").resize((256, 256), Image.LANCZOS).save(os.path.join(UI, "T_UI_Emblem.png"))

    lines = ["// Generated by Tools/blender/assets/king_run_sprite.py from the sheets it writes: do not edit.",
             "// The cells of /Game/Voxel/UI/T_UI_KingRun and T_UI_RunnerProps, in the run's pixels.",
             "namespace VLLoadingArt",
             "{",
             "	constexpr int32 RunFrames = %d;" % n,
             "	constexpr float RunFps = %d.f;" % FPS,
             "	constexpr float CellW = %d.f, CellH = %d.f;" % (cw, ch),
             "	constexpr float PivotX = %d.f, PivotY = %d.f;   // the pack's pivot: on the ground, at his column" % PIVOT,
             "	constexpr int32 AirFrame = %d;          // his soles highest: the jump's pose" % air,
             "	struct FHit { float Back, Front, Foot, Head; };   // what can be hit of him in a frame: from the pivot's column, above the ground",
             "	constexpr FHit Hit[] = { %s };" % ", ".join("{ %d.f, %d.f, %d.f, %d.f }" % b for b in boxes),
             "	constexpr FHit CrouchHit[] = { %s };   // the crouch-run (T_UI_KingCrouchRun): the same cells, pivot and frame count" % ", ".join("{ %d.f, %d.f, %d.f, %d.f }" % b for b in crouch),
             "\tconstexpr float PropsW = %d.f, PropsH = %d.f;" % (props.shape[1], props.shape[0]),
             "\tstruct FProp { float X, W, H; };       // its cell: from X, W wide, H tall from the sheet's top",
             "\tenum EProp : int32 { %s };" % ", ".join(n for n, *_ in where),
             "\tconstexpr FProp Props[] = { %s };" % ", ".join("{ %d.f, %d.f, %d.f }" % (x, w, h) for _, x, w, h in where),
             "}", ""]
    with open(INL, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines))
    print("wrote", INL)

    Z = 3                                      # the previews, on the loading screen's background
    os.makedirs(os.path.dirname(GIF), exist_ok=True)
    im = Image.fromarray(sheet, "RGBA")
    bg = Image.new("RGBA", im.size, BACKGROUND + (255,))
    bg.alpha_composite(im)
    bg.convert("RGB").resize((im.width * Z, im.height * Z), Image.NEAREST).save(GIF[:-4] + ".png")
    gif = [bg.crop((i * cw, 0, (i + 1) * cw, ch)).convert("RGB").resize((cw * Z, ch * Z), Image.NEAREST) for i in range(n)]
    gif[0].save(GIF, save_all=True, append_images=gif[1:], duration=int(round(1000.0 / FPS)), loop=0)
    pb = Image.new("RGBA", (props.shape[1], props.shape[0]), BACKGROUND + (255,))
    pb.alpha_composite(Image.fromarray(props, "RGBA"))
    pb.convert("RGB").resize((pb.width * Z * 2, pb.height * Z * 2), Image.NEAREST).save(GIF[:-4] + "_props.png")
    print("wrote", GIF)


if __name__ == "__main__":
    main()
