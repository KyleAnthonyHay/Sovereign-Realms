"""Build the Sovereign Realms character sprite sheets.

    Tools/.venv/bin/python Tools/sprites/build.py            # everything
    Tools/.venv/bin/python Tools/sprites/build.py --no-gif   # skip the animated previews

Writes to SourceArt/Characters/:
    <name>_color.png      RGBA sheet, team regions left as a neutral grey ramp
    <name>_teammask.png   8-bit mask, white where the material tints by TeamColor
    <name>.json           layout, pivot, timing and palette metadata
    previews/             contact sheets, animated GIFs and the line-up

Sheet layout (both characters): 512 x 1024, 64 px cells, 8 columns x 16 rows.
Row = animation * 3 + facing, animations in ANIMS order, facings in FACINGS order.
"""

import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

import pixelkit as pk
import shieldbearer
import archer

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.normpath(os.path.join(HERE, "..", "..", "SourceArt", "Characters"))
PREV = os.path.join(OUT, "previews")

CELL = 64
COLS, ROWS = 8, 16
PIVOT = (32, 60)
CM_PER_PX = 4.0

FACINGS = ["front", "side", "back"]
ANIMS = ["idle", "walk", "attack", "hit", "death"]
FRAME_COUNT = {"idle": 4, "walk": 6, "attack": 6, "hit": 2, "death": 5}

# Team colours as the game passes them (linear), from Docs/VISUAL_CONTRACT.md.
TEAMS = {"blue": (0.05, 0.22, 0.80), "red": (0.72, 0.07, 0.05)}
BACKGROUNDS = {"olive": (104, 122, 62), "sand": (196, 172, 124)}

# Timings read from Source/SovereignRealms/Common/SRFeelSettings.cpp, for previews and metadata.
UNIT = {
    "shieldbearer": dict(windup=0.26, recovery=0.34, max_speed=390.0, body_height_cm=142.0, radius_cm=44.0),
    "archer": dict(windup=0.42, recovery=0.24, max_speed=440.0, body_height_cm=134.0, radius_cm=36.0),
}
HIT_STOP = 0.045
DEATH_TOPPLE = 0.42
WALK_CYCLE_CM = 160.0

# Normalised phase progress at which each attack frame starts.
WINDUP_MAP = [(0.0, 0), (0.34, 1), (0.68, 2)]
RECOVERY_MAP = [(0.0, 3), (0.40, 4), (0.72, 5)]


def row_of(anim, facing):
    return ANIMS.index(anim) * len(FACINGS) + FACINGS.index(facing)


def render(mod):
    """-> {(anim, facing): [indexed grid with outline, ...]} after validation."""
    frames = mod.build()
    out = {}
    for anim in ANIMS:
        for facing in FACINGS:
            seq = frames[(anim, facing)]
            if len(seq) != FRAME_COUNT[anim]:
                raise SystemExit("%s %s/%s: %d frames, expected %d" % (mod.META["name"], anim, facing, len(seq), FRAME_COUNT[anim]))
            grids = []
            for i, c in enumerate(seq):
                g = c.outlined().g
                # 1 px of clear space on every side so point sampling can never bleed a neighbour in.
                if g[0].any() or g[-1].any() or g[:, 0].any() or g[:, -1].any():
                    raise SystemExit("%s %s/%s frame %d touches the cell edge" % (mod.META["name"], anim, facing, i))
                grids.append(g)
            out[(anim, facing)] = grids
    # Feet must not jitter: every upright frame rests on the same ground line.
    for anim in ("idle", "walk", "attack", "hit"):
        for facing in FACINGS:
            for i, g in enumerate(out[(anim, facing)]):
                body = np.isin(g, [ord(c) for c in "mnuv"], invert=True) & (g > 0)
                low = int(np.nonzero(body.any(axis=1))[0].max())
                if low > PIVOT[1] + 3 or low < PIVOT[1]:
                    raise SystemExit("%s %s/%s frame %d: lowest pixel row %d, ground line %d" % (mod.META["name"], anim, facing, i, low, PIVOT[1]))
    return out


def build_sheet(grids):
    sheet = np.zeros((ROWS * CELL, COLS * CELL), dtype=np.uint8)
    for (anim, facing), seq in grids.items():
        r = row_of(anim, facing)
        for i, g in enumerate(seq):
            sheet[r * CELL:(r + 1) * CELL, i * CELL:(i + 1) * CELL] = g
    return sheet


def cell_image(g, team, bg=None):
    rgba = pk.to_rgba(g)
    if team is not None:
        rgba = pk.apply_team(rgba, pk.to_mask(g), TEAMS[team])
    im = Image.fromarray(rgba, "RGBA")
    return pk.on_background(im, bg) if bg is not None else im


def palette_json():
    pal = {}
    for name, ramp in pk.RAMPS.items():
        pal[name] = ["#%02x%02x%02x" % rgb for _, rgb in ramp]
    pal["outline"] = {str(k): "#%02x%02x%02x" % v for k, v in pk.OUTLINE.items()}
    pal["accents"] = {k: "#%02x%02x%02x" % v for k, v in pk.EXTRA.items()}
    return pal


def write_meta(mod, grids):
    name = mod.META["name"]
    u = UNIT[name]
    anims = {
        "idle": {"frames": 4, "loop": True, "drive": "time", "fps": 4.0},
        "walk": {"frames": 6, "loop": True, "drive": "distance", "cycle_distance_cm": WALK_CYCLE_CM,
                 "fps_at_max_speed": round(u["max_speed"] / WALK_CYCLE_CM * 6, 2),
                 "frame_roles": ["contact", "down", "passing", "contact", "down", "passing"]},
        "attack": {"frames": 6, "loop": False, "drive": "attack_phase",
                   "windup_frames": [0, 1, 2], "strike_frame": 3, "recovery_frames": [3, 4, 5],
                   "windup_phase_map": [{"from": t, "frame": f} for t, f in WINDUP_MAP],
                   "recovery_phase_map": [{"from": t, "frame": f} for t, f in RECOVERY_MAP],
                   "notes": "Show windup frames by PhaseTime/WindupTime. The strike frame is the first frame of "
                            "Recovery (the frame damage lands / the arrow spawns) and is the pose held during hit-stop."},
        "hit": {"frames": 2, "loop": False, "drive": "time", "fps": 12.5,
                "notes": "Cosmetic overlay for about 0.16 s (HitFlashTime). Never play it over an attack."},
        "death": {"frames": 5, "loop": False, "drive": "time", "fps": round(5 / DEATH_TOPPLE, 2), "hold_last": True,
                  "authored_facings": FACINGS,
                  "notes": "Frames 0-1 are authored per facing. Frames 2-4 (airborne, impact, corpse) are one lying "
                           "pose, head to the left: face-up for front and side, face-down for back. The corpse row "
                           "must keep the flip state the unit had when it died."},
    }
    rows = []
    for anim in ANIMS:
        for facing in FACINGS:
            rows.append({"row": row_of(anim, facing), "animation": anim, "facing": facing,
                         "frames": FRAME_COUNT[anim], "loop": anims[anim]["loop"]})
    for a in anims.values():
        a["rows"] = {}
    for r in rows:
        anims[r["animation"]]["rows"][r["facing"]] = r["row"]

    meta = {
        "name": name,
        "display_name": mod.META["display_name"],
        "sheet": {"color": name + "_color.png", "teammask": name + "_teammask.png",
                  "width": COLS * CELL, "height": ROWS * CELL, "cell": [CELL, CELL], "columns": COLS, "rows": ROWS,
                  "row_order": "row = animation_index * 3 + facing_index; column = frame"},
        "pivot_px": list(PIVOT),
        "pivot_uv_in_cell": [PIVOT[0] / CELL, PIVOT[1] / CELL],
        "pivot_notes": "Feet stand on the line y = 60 px from the top of the cell, x = 32. "
                       "The 1 px outline under the soles is row 60; rows 61-63 only hold the sword tip of the "
                       "front strike and gear lying beside a corpse.",
        "figure_height_px": mod.META["figure_height_px"],
        "cm_per_px": CM_PER_PX,
        "quad_size_cm": [CELL * CM_PER_PX, CELL * CM_PER_PX],
        "gameplay_reference": u,
        "facings": {"front": "unit faces the camera (world -X, south)",
                    "side": "unit faces screen right (world +Y, east); mirror horizontally for west",
                    "back": "unit faces away from the camera (world +X, north)"},
        "facing_selection": {
            "camera_yaw_assumed_deg": 0,
            "rule": "rel = unit FacingYaw - camera yaw, wrapped to -180..180. |rel| <= 45: back. |rel| >= 135: front. "
                    "Otherwise side, mirrored horizontally when rel < 0 (unit faces screen left / world -Y).",
            "hysteresis_deg": 10,
        },
        "projectile_origin_cm": {"forward": 40, "up": 84} if name == "archer" else None,
        "animations": anims,
        "rows": rows,
        "team": {"mask": name + "_teammask.png", "boost": pk.TEAM_BOOST,
                 "formula": "rgb = lerp(color.rgb, color.rgb * TeamColor * 2, mask), in linear space",
                 "notes": "Team pixels are a neutral grey ramp; linear 0.5 (sRGB 188) reproduces TeamColor exactly."},
        "palette": palette_json(),
    }
    with open(os.path.join(OUT, name + ".json"), "w") as f:
        json.dump(meta, f, indent=2)
        f.write("\n")


# --------------------------------------------------------------------------
# Previews
# --------------------------------------------------------------------------

def contact_sheet(grids, team, bg_name, k=6):
    bg = BACKGROUNDS[bg_name]
    label_w = 0
    W = 6 * CELL
    H = len(ANIMS) * len(FACINGS) * CELL
    im = Image.new("RGB", (W, H), bg)
    for (anim, facing), seq in grids.items():
        r = row_of(anim, facing)
        for i, g in enumerate(seq):
            im.paste(cell_image(g, team, bg), (label_w + i * CELL, r * CELL))
    big = pk.upscale(im, k)
    d = ImageDraw.Draw(big)
    for anim in ANIMS:
        for facing in FACINGS:
            r = row_of(anim, facing)
            d.text((6, r * CELL * k + 6), "%s / %s" % (anim, facing), fill=(20, 20, 20))
            d.line([(0, r * CELL * k), (W * k, r * CELL * k)], fill=tuple(int(c * 0.85) for c in bg))
    return big


def attack_durations(name):
    u = UNIT[name]
    w, r = u["windup"], u["recovery"]
    wd = [w * (WINDUP_MAP[1][0]), w * (WINDUP_MAP[2][0] - WINDUP_MAP[1][0]), w * (1 - WINDUP_MAP[2][0])]
    rd = [r * RECOVERY_MAP[1][0] + HIT_STOP, r * (RECOVERY_MAP[2][0] - RECOVERY_MAP[1][0]), r * (1 - RECOVERY_MAP[2][0])]
    return [int(round(x * 1000)) for x in wd + rd]


def save_gif(path, frames, durations):
    # GIF timing is in 1/100 s and browsers clamp anything under 20 ms.
    durations = [max(20, int(round(d / 10.0)) * 10) for d in durations]
    pal = frames[0].convert("P", palette=Image.ADAPTIVE, colors=128)
    seq = [f.quantize(palette=pal, dither=Image.NONE) for f in frames]
    seq[0].save(path, save_all=True, append_images=seq[1:], duration=durations, loop=0, disposal=1, optimize=False)


def anim_gif(name, grids, anim, k=6):
    """Three facings side by side, played at the speed the game will use."""
    bg = BACKGROUNDS["olive"]
    n = FRAME_COUNT[anim]
    u = UNIT[name]
    if anim == "idle":
        order, dur = list(range(n)), [250] * n
    elif anim == "walk":
        order, dur = list(range(n)), [int(round(1000 * WALK_CYCLE_CM / u["max_speed"] / 6))] * n
    elif anim == "attack":
        order, dur = list(range(n)), attack_durations(name)
    elif anim == "hit":
        order, dur = [0, 1], [80, 80]
    else:
        order, dur = list(range(n)), [int(round(1000 * DEATH_TOPPLE / 5))] * (n - 1) + [1600]
    idle = grids[("idle", "front")], grids[("idle", "side")], grids[("idle", "back")]
    out, durs = [], []

    def compose(cells):
        im = Image.new("RGB", (3 * CELL, CELL), bg)
        for j, g in enumerate(cells):
            im.paste(cell_image(g, "blue" if j != 1 else "red", bg), (j * CELL, 0))
        return pk.upscale(im, k)

    if anim in ("attack", "hit"):        # start and end on the idle pose so the action reads in context
        out.append(compose([s[0] for s in idle]))
        durs.append(500)
    for i, d in zip(order, dur):
        out.append(compose([grids[(anim, f)][i] for f in FACINGS]))
        durs.append(d)
    if anim in ("attack", "hit"):
        out.append(compose([s[0] for s in idle]))
        durs.append(450)
    save_gif(os.path.join(PREV, "%s_%s.gif" % (name, anim)), out, durs)


def crop_fig(im, x0=10, y0=14, w=44, h=50):
    return im.crop((x0, y0, x0 + w, y0 + h))


def lineup(all_grids):
    """Both characters, both teams, three facings: big for craft, true size for readability."""
    k = 8
    cw, ch = 44, 50
    names = ["shieldbearer", "archer"]
    blocks = []
    for bg_name in ("olive", "sand"):
        bg = BACKGROUNDS[bg_name]
        big = Image.new("RGB", (cw * 12, ch), bg)
        x = 0
        for team in ("blue", "red"):
            for nm in names:
                for facing in FACINGS:
                    im = crop_fig(cell_image(all_grids[nm][("idle", facing)][0], team, bg))
                    big.paste(im, (x, 0))
                    x += cw
        blocks.append((bg, big))

    pad = 16
    W = cw * 12 * 4 + pad * 2          # x4 for the big rows keeps the sheet a sane size
    scale_big = 4
    rows = []
    for bg, strip in blocks:
        rows.append(("x%d" % k, bg, pk.upscale(strip.crop((0, 0, cw * 6, ch)), k)))
        rows.append(("x%d" % k, bg, pk.upscale(strip.crop((cw * 6, 0, cw * 12, ch)), k)))
    for bg, strip in blocks:
        rows.append(("x2", bg, pk.upscale(strip, 2)))
        rows.append(("x1 (true size)", bg, strip))

    # A small mixed skirmish at true size: the tactical-zoom readability test.
    def skirmish(bg_name):
        bg = BACKGROUNDS[bg_name]
        im = Image.new("RGB", (cw * 12, 70), bg)
        picks = [("shieldbearer", "blue", "side", "walk", 0, False), ("shieldbearer", "blue", "side", "attack", 3, False),
                 ("shieldbearer", "red", "side", "attack", 1, True), ("shieldbearer", "red", "side", "idle", 0, True),
                 ("archer", "blue", "side", "attack", 2, False), ("archer", "blue", "back", "idle", 0, False),
                 ("shieldbearer", "blue", "back", "walk", 2, False), ("archer", "red", "front", "attack", 2, False),
                 ("archer", "red", "side", "attack", 3, True), ("shieldbearer", "red", "front", "walk", 3, False),
                 ("archer", "blue", "front", "idle", 0, False), ("shieldbearer", "red", "side", "death", 4, True),
                 ("archer", "red", "side", "death", 4, False)]
        xs = [4, 40, 78, 112, 150, 186, 220, 258, 296, 334, 372, 410, 456]
        ys = [2, 6, 4, 0, 8, 2, 6, 0, 4, 8, 2, 6, 4]
        for (nm, team, facing, anim, i, flip), x, y in zip(picks, xs, ys):
            cell = cell_image(all_grids[nm][(anim, facing)][i], team)
            if flip:
                cell = cell.transpose(Image.FLIP_LEFT_RIGHT)
            im.paste(cell, (x - 10, y), cell)
        return im

    for bg_name in ("olive", "sand"):
        rows.append(("skirmish x1", BACKGROUNDS[bg_name], skirmish(bg_name)))
        rows.append(("skirmish x2", BACKGROUNDS[bg_name], pk.upscale(skirmish(bg_name), 2)))

    W = max(r[2].width for r in rows) + pad * 2
    H = sum(r[2].height + pad for r in rows) + pad
    sheet = Image.new("RGB", (W, H), (34, 32, 38))
    d = ImageDraw.Draw(sheet)
    y = pad
    for label, bg, im in rows:
        sheet.paste(im, (pad, y))
        d.text((pad + 4, y + 2), label, fill=(20, 20, 20))
        y += im.height + pad
    sheet.save(os.path.join(PREV, "lineup.png"))


def main():
    os.makedirs(PREV, exist_ok=True)
    all_grids = {}
    for mod in (shieldbearer, archer):
        name = mod.META["name"]
        grids = render(mod)
        all_grids[name] = grids
        sheet = build_sheet(grids)
        Image.fromarray(pk.to_rgba(sheet), "RGBA").save(os.path.join(OUT, name + "_color.png"))
        Image.fromarray(pk.to_mask(sheet), "L").save(os.path.join(OUT, name + "_teammask.png"))
        write_meta(mod, grids)
        for team, bg in (("blue", "olive"), ("red", "sand"), ("blue", "sand"), ("red", "olive")):
            contact_sheet(grids, team, bg).save(os.path.join(PREV, "%s_contact_%s_on_%s.png" % (name, team, bg)))
        if "--no-gif" not in sys.argv:
            for anim in ANIMS:
                anim_gif(name, grids, anim)
        used = int(np.count_nonzero(sheet))
        print("%-13s sheet %dx%d, %d opaque px, %d colours" % (name, sheet.shape[1], sheet.shape[0], used, len(np.unique(sheet)) - 1))
    lineup(all_grids)
    print("wrote", OUT)


if __name__ == "__main__":
    import warnings
    warnings.simplefilter("ignore", DeprecationWarning)
    main()
