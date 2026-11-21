"""Turn rendered cells into the shipped sprite sheets and metadata.

    Tools/.venv/bin/python Tools/blender/make_sheets.py [shieldbearer archer]

Reads   SourceArt/Characters/_build/<name>_cells.npz      (from render_sprites.py)
Writes  SourceArt/Characters/<name>_color.png             RGBA, binary alpha, team regions as a neutral grey ramp
        SourceArt/Characters/<name>_teammask.png          8-bit, 255 where the pixel is tinted by TeamColor
        SourceArt/Characters/<name>_normal.png            RGB camera-facing tangent-space normals (Unreal / DirectX)
        SourceArt/Characters/<name>.json                  layout, pivot, scale, timing, palette

Layout: six animation blocks, three across and two down (spawn, idle, walk / attack, hit, death). Inside a
block: row = facing (S, SW, W, NW, N, NE, E, SE), column = frame.
"""

import json
import os
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
OUT = os.path.normpath(os.path.join(HERE, "..", "..", "SourceArt", "Characters"))

import srmats  # noqa: E402
import srpost  # noqa: E402

ANIMS = ["spawn", "idle", "walk", "attack", "hit", "death"]
BLOCK = {"spawn": (0, 0), "idle": (1, 0), "walk": (2, 0), "attack": (0, 1), "hit": (1, 1), "death": (2, 1)}
BLOCK_COLS, BLOCK_ROWS = 8, 8

# Read from Source/SovereignRealms/Common/SRFeelSettings.{h,cpp} when this was written; only used for metadata
# and preview timing, the sheets do not depend on them.
GAMEPLAY = {
    "shieldbearer": dict(display_name="Shieldbearer", windup=0.26, recovery=0.34, attack_interval=1.15,
                         max_speed=390.0, body_height_cm=142.0, radius_cm=44.0),
    "archer": dict(display_name="Archer", windup=0.42, recovery=0.24, attack_interval=1.5,
                   max_speed=440.0, body_height_cm=134.0, radius_cm=36.0),
    # workers (cosmetic): "attack" is the work swing, looped by ASRWorker at its own pace
    "miner": dict(display_name="Miner", windup=0.5, recovery=0.5, attack_interval=1.1,
                  max_speed=170.0, body_height_cm=132.0, radius_cm=30.0),
    "farmer": dict(display_name="Farmhand", windup=0.5, recovery=0.5, attack_interval=1.2,
                   max_speed=160.0, body_height_cm=132.0, radius_cm=30.0),
    "builder": dict(display_name="Builder", windup=0.45, recovery=0.45, attack_interval=1.3,
                    max_speed=360.0, body_height_cm=132.0, radius_cm=34.0),
    "scout": dict(display_name="Scout", windup=0.32, recovery=0.36, attack_interval=1.2,
                  max_speed=820.0, body_height_cm=132.0, radius_cm=34.0),
    # the healer: "attack" is the heal, looped while it tends the wounded
    "medic": dict(display_name="Medic", windup=0.45, recovery=0.45, attack_interval=2.0,
                  max_speed=360.0, body_height_cm=132.0, radius_cm=34.0),
    # cavalry and siege (256 px cells). Suggested values: nothing in SRFeelSettings existed for them when written.
    "horseman": dict(display_name="Horse Rider", windup=0.30, recovery=0.40, attack_interval=1.3,
                     max_speed=620.0, body_height_cm=202.0, radius_cm=70.0),
    "catapult": dict(display_name="Catapult", windup=1.6, recovery=0.6, attack_interval=4.0,
                     max_speed=130.0, body_height_cm=200.0, radius_cm=120.0),
    # wildlife (ASRWildlife; cosmetic): the blocks are graze / stand / walk / bolt / start / look round, see char_deer.py.
    # max_speed is the bolt's (Sovereign Feel > World > Wildlife).
    "deer": dict(display_name="Stag", windup=0.0, recovery=0.0, attack_interval=0.0,
                 max_speed=620.0, body_height_cm=128.0, radius_cm=50.0),
    "doe": dict(display_name="Hind", windup=0.0, recovery=0.0, attack_interval=0.0,
                max_speed=620.0, body_height_cm=118.0, radius_cm=46.0),
}
FEEL = dict(stride_length_cm=62.0, spawn_pop_time=0.38, hit_flash_time=0.16, death_topple_time=0.42,
            corpse_linger_time=2.2, hit_stop_time=0.045, melee_lunge_cm=30.0)


def build(name):
    src = os.path.join(OUT, "_build", name + "_cells.npz")
    d = np.load(src)
    meta = json.loads(str(d["meta"]))
    r = meta["render"]
    cell, pivot, cmpp = r["cell"], r["pivot"], r["cm_per_px"]
    facings = meta["facings"]
    W, H = 3 * BLOCK_COLS * cell, 2 * BLOCK_ROWS * cell
    color = np.zeros((H, W, 4), np.uint8)
    mask = np.zeros((H, W), np.uint8)
    normal = np.zeros((H, W, 3), np.uint8)
    normal[...] = (128, 128, 255)
    problems = []
    seen = set()
    for i, (an, fc, fr) in enumerate(meta["index"]):
        c = {k: d[k][i] for k in ("id", "L", "ao", "z", "n")}
        rgba, m, nm = srpost.stylise(c, meta["key_dir_cam"], cmpp)
        a = rgba[..., 3] > 0
        if a[0].any() or a[-1].any() or a[:, 0].any() or a[:, -1].any():
            problems.append("%s %s frame %d touches the cell edge" % (an, fc, fr))
        bx, by = BLOCK[an]
        x0 = (bx * BLOCK_COLS + fr) * cell
        y0 = (by * BLOCK_ROWS + facings.index(fc)) * cell
        color[y0:y0 + cell, x0:x0 + cell] = rgba
        mask[y0:y0 + cell, x0:x0 + cell] = m
        normal[y0:y0 + cell, x0:x0 + cell] = nm
        seen.add((an, fc, fr))
    for an in ANIMS:
        if an not in meta["actions"]:
            problems.append("missing animation " + an)
            continue
        for fc in facings:
            for fr in range(meta["actions"][an]["frames"]):
                if (an, fc, fr) not in seen:
                    problems.append("missing cell %s %s %d" % (an, fc, fr))

    Image.fromarray(color).save(os.path.join(OUT, name + "_color.png"), optimize=True)
    Image.fromarray(mask).save(os.path.join(OUT, name + "_teammask.png"), optimize=True)
    Image.fromarray(normal).save(os.path.join(OUT, name + "_normal.png"), optimize=True)

    # --- measurements from the idle S frame 0: body only (weapons, bow and arrows excluded)
    i0 = meta["index"].index(["idle", "S", 0])
    gear = [srmats.BY_NAME[n]["id"] for n in ("blade", "wood", "string", "shaft", "feather")]
    body = (d["id"][i0] != 255) & ~np.isin(d["id"][i0], gear)
    ys = np.nonzero(body.any(1))[0]
    top, bottom = int(ys[0]) - 1, int(ys[-1]) + 1          # plus the outline
    used = np.unique(color[color[..., 3] > 0][:, :3], axis=0)
    palette = {}
    usedset = {tuple(int(v) for v in u) for u in used}
    for mdef in srmats.MATERIALS:
        cols = [h for h in mdef["ramp"] if srmats.hex_to_rgb(h) in usedset]
        if cols:
            palette[mdef["name"]] = cols
    palette["outline"] = [srmats.OUTLINE, srmats.OUTLINE_TEAM_GREY]

    g = GAMEPLAY[name]
    anims = {}
    rows = []
    for an in ANIMS:
        if an not in meta["actions"]:
            continue
        a = dict(meta["actions"][an])
        bx, by = BLOCK[an]
        entry = dict(frames=a.pop("frames"), loop=a.pop("loop"), drive=a.pop("drive", "time"),
                     origin_cell=[bx * BLOCK_COLS, by * BLOCK_ROWS])
        entry.update(a)
        if entry["drive"] == "distance":
            entry["cycle_distance_cm"] = round(entry.pop("cycle_cm"), 2)
            entry["fps_at_max_speed"] = round(g["max_speed"] / entry["cycle_distance_cm"] * entry["frames"], 2)
            entry["frame_rule"] = "frame = floor(frac(distance_walked_cm / cycle_distance_cm) * frames)"
        if entry["drive"] == "attack_phase":
            entry["frame_rule"] = ("wind-up: last windup frame whose windup_phase_map value <= PhaseTime / WindupTime; "
                                   "recovery: last recovery frame whose recovery_phase_map value <= PhaseTime / "
                                   "RecoveryTime. strike_frame is the first recovery frame, shown the moment Strike() runs.")
        entry["rows"] = {fc: by * BLOCK_ROWS + k for k, fc in enumerate(facings)}
        anims[an] = entry
        for k, fc in enumerate(facings):
            rows.append(dict(row=by * BLOCK_ROWS + k, first_column=bx * BLOCK_COLS, animation=an, facing=fc,
                             frames=entry["frames"], loop=entry["loop"]))

    out = dict(
        name=name, display_name=g["display_name"],
        generator="Tools/blender (Blender %s scripted build -> EEVEE passes -> make_sheets.py)" % "5.3",
        sheet=dict(color=name + "_color.png", teammask=name + "_teammask.png", normal=name + "_normal.png",
                   width=W, height=H, cell=[cell, cell], columns=W // cell, rows=H // cell,
                   block=[BLOCK_COLS, BLOCK_ROWS],
                   layout="six animation blocks of 8 columns x 8 rows, laid out 3 across and 2 down; "
                          "column = animations[a].origin_cell[0] + frame, row = animations[a].origin_cell[1] + facing_index"),
        pivot_px=pivot, pivot_uv_in_cell=[pivot[0] / cell, pivot[1] / cell],
        pivot_notes="The unit's ground position (actor origin, between the feet). Same pixel in every cell.",
        cm_per_px=cmpp, quad_size_cm=[cell * cmpp, cell * cmpp],
        scale_notes="cm_per_px is measured in the camera plane. The figure is rendered at its true height from "
                    "render_elevation_deg, so a camera-facing quad of quad_size_cm with its pivot on the ground "
                    "shows it at world scale.",
        render_elevation_deg=r["elev"], supersample=r["ss"],
        figure_height_px=bottom - top + 1, figure_top_row=top, figure_bottom_row=bottom,
        figure_notes="standing body in idle S frame 0 including the outline, weapons excluded",
        body_height_cm=meta["body_height_cm"],
        facings=dict(order=facings,
                     meaning="direction the unit faces as seen on screen: S = toward the camera (down-screen), "
                             "N = away (up-screen), E = screen right, W = screen left",
                     camera_yaw_assumed_deg=0,
                     selection="rel = FacingYaw - CameraYaw (deg); index = round(((rel + 180) mod 360) / 45) mod 8 "
                               "into [S, SW, W, NW, N, NE, E, SE]; i.e. rel 0 -> N, 90 -> E, 180 -> S, -90 -> W",
                     hysteresis_deg=8, mirrored=False),
        animations=anims, rows=rows,
        team=dict(mask=name + "_teammask.png", boost=2.0,
                  formula="rgb = lerp(color.rgb, color.rgb * TeamColor * 2, mask), in linear space"),
        normal=dict(file=name + "_normal.png", space="tangent space of the camera-facing quad",
                    convention="R = +X screen right, G = +Y screen DOWN (Unreal / DirectX, no green flip needed), "
                               "B = toward the camera; empty pixels are (128, 128, 255)"),
        lighting_baked="warm key from the top-left and toward the camera, cool fill from the right, rim from behind-right",
        key_light_dir_tangent=[round(v, 4) for v in (meta["key_dir_cam"][0], -meta["key_dir_cam"][1], meta["key_dir_cam"][2])],
        gameplay_reference=dict(g, **FEEL),
        palette=palette, palette_size=int(len(used)),
    )
    if "projectile_origin_cm" in anims.get("attack", {}):
        out["projectile_origin_cm"] = anims["attack"]["projectile_origin_cm"]
    with open(os.path.join(OUT, name + ".json"), "w") as f:
        json.dump(out, f, indent=2)
        f.write("\n")
    print("%s: %dx%d, %d cells, figure %d px tall (rows %d..%d, pivot row %d), %d colours"
          % (name, W, H, len(meta["index"]), bottom - top + 1, top, bottom, pivot[1], len(used)))
    for p in problems:
        print("  PROBLEM:", p)
    return not problems


if __name__ == "__main__":
    names = sys.argv[1:] or ["shieldbearer", "archer"]
    ok = all([build(n) for n in names])
    sys.exit(0 if ok else 1)
