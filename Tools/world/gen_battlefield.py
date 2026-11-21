#!/usr/bin/env python3
"""Offline generator for the battle maps: the land, the water, the props, the ground splat map and the placement
list. Deterministic. Unreal only imports and places what this writes.

  Tools/.venv/bin/python Tools/world/gen_battlefield.py --map two     THE RIVERLANDS, two kingdoms   (about 1 minute)
  Tools/.venv/bin/python Tools/world/gen_battlefield.py --map four    THE FOUR MARCHES, four corners (about 2 minutes)
  ... --map all       both          ... --plan      only the previews under Saved/ (a third of the time: layout work)
  ... --force         write a map that fails its checks          ... --probe=x,y   the walk grid round a spot

  two  -> SourceArt/Meshes/battlefield.gltf (+ .bin)   every static mesh of the map, Unreal axes, cm (buildings are
          separate: Tools/blender/build_building.py; the plan's kingdoms place them)
          SourceArt/Textures/T_Splat.png              ground blend map (build_splat)
          SourceArt/Textures/T_WaterMap.png           water data map for M_Water (build_water_map)
          SourceArt/Textures/T_WaterFlow.png          each river's current, the water's depth, the damp banks (build_flow_map)
          SourceArt/Textures/T_MinimapBase.png        the HUD minimap's base
          SourceArt/World/layout.json                 where everything goes, and the map's own numbers ("map")
          Saved/WorldPreview/map.png                  top-down picture (+X up, like the game camera)
          Saved/MapPreview/layout.png, report.txt     the plan as the walkability grid will read it, and its checks
  four -> the same with a 4 before the extension: battlefield4.gltf, T_Splat4.png, layout4.json, report4.txt ...
  then, in the editor (MAP = "two" or "four"): Tools/ue_py.py with import_world_assets.py, build_visual_materials.py,
  build_battlefield_visuals.py (see each file's header).

The files: maps.py (the two plans: read it to see or change a map's layout), worldgen.py (the land-shaping tools a plan
calls), terrain.py (the heightfield and its mesh), dressing.py (landmarks, woods, boulders, grass), props.py (the prop
meshes), meshlib.py (mesh and glTF helpers).

The land is a smooth heightfield (terrain.py): no terraces, no vertical walls. What the game's rules need of it:
  * walking: the grid (USRGridSubsystem) closes a 1 m cell whose corners differ by more than a step (45 cm), so ground
    meant for troops is no steeper than about 1 in 5 and a barrier is a mountainside; validate() reads the land exactly
    as the grid will and a map with a vein, a ruin or a kingdom nobody can walk to, or a river that can be crossed
    where it should not, is not written (--force overrides). Ways that exist only hard against a slope are warnings.
  * building: footprints need level ground (30 cm): the kingdoms' tables, the benches, the islands, and a pad under
    every vein and ruin are exactly level.
  * water: any water deeper than 14 cm is a wall, whatever its height (a tarn on a hill, a mere in a hollow); a ford's
    bed lies 8 cm under its surface. The level's water sheets carry the tag SRWater and the grid measures depth.
  * relics and old towers are actors tagged SRRelic / SRRuinTower (the level builder sets the tags from "actors").
Mountain shapes for the far wall: SourceArt/World/Mountains/peak_<n>.npy (Tools/blender/build_mountains.py).
"""
import json
import math
import os
import sys
import time

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage, sparse
from scipy.sparse import csgraph
from shapely.geometry import Point, box

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import terrain as T                                    # noqa: E402
from terrain import N, X, Y                            # noqa: E402
from meshlib import Mesh, write_gltf                   # noqa: E402
import props                                           # noqa: E402
import maps                                            # noqa: E402
from dressing import Dressing                          # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TEXEL = 4.0
FAST = "--plan" in sys.argv
SPLAT_RES = 1024 if FAST else 4096
STEP_H, WADE, FLAT_TOL = 45.0, 14.0, 30.0             # USRFeelSettings: StepHeight, WadeDepth, BuildFlatTolerance
GENTLE, SHEER = 20.0, 70.0                             # USRGridSubsystem::Build's two shortcuts (see walk_grid)
_META = {}


def building_meta(kind):
    if kind not in _META:
        with open(os.path.join(ROOT, "SourceArt", "Buildings", kind + ".json")) as f:
            _META[kind] = json.load(f)
    return _META[kind]


# ============================================================================================ splat map
def smooth_noise(shape, cell, seed):
    r = np.random.default_rng(seed)
    small = r.random((shape[0] // cell + 2, shape[1] // cell + 2)).astype(np.float32)
    return ndimage.zoom(small, cell, order=3)[:shape[0], :shape[1]]


class Splat:
    """The world square the splat and water maps cover, and reading the land's rasters at its texels.
    Image row = world Y, column = world X (the materials read it as (world XY - origin) / size)."""

    def __init__(self, W):
        x0, x1, y0, y1 = W.box
        self.size = float(math.ceil(max(x1 - x0, y1 - y0) / 1024.0) * 1024.0 + 1024.0)
        self.origin = ((x0 + x1) * 0.5 - self.size * 0.5, (y0 + y1) * 0.5 - self.size * 0.5)
        self.res = SPLAT_RES
        self.px = self.size / self.res
        xs = self.origin[0] + (np.arange(self.res) + 0.5) * self.px
        ys = self.origin[1] + (np.arange(self.res) + 0.5) * self.px
        self.X, self.Y = np.meshgrid(xs, ys)
        self._ci = [np.clip((self.X - T.ORG) / T.STEP, 0, N - 1).astype(np.float32), np.clip((self.Y - T.ORG) / T.STEP, 0, N - 1).astype(np.float32)]

    def read(self, A, order=1):
        return ndimage.map_coordinates(np.nan_to_num(A.astype(np.float32), nan=0.0, posinf=1e6), self._ci, order=order, mode="nearest")


def band(d, core, edge):
    return np.clip((edge - d) / (edge - core), 0.0, 1.0)


def kingdom_paths(W):
    """Footpaths (bare earth): each castle court to its farm yard and its mine adit."""
    out = []
    for team in (0, 1):
        cs = [b for b in W.buildings if b[4] == team and b[0] == "castle"]
        if not cs:
            continue
        court = (cs[0][1] - 780.0, cs[0][2])
        for b in W.buildings:
            if b[4] == team and b[0] != "castle":
                front = (b[1] - 520.0, b[2])
                out.append([court, (min(court[0], front[0]) - 250.0, (court[1] + front[1]) * 0.5), front])
    return out


def build_splat(W, S):
    """R = road (0 turf .. 0.5 bare earth .. 1 set stones), G = moss, B = dry straw, A = baked shade (1 = none).
    Rock and snow are not painted here: M_Terrain puts them where the land is steep or high."""
    shape = S.X.shape
    cell = max(int(round(24 * S.res / 4096)), 2)
    wob = (smooth_noise(shape, cell * 4, 1) - 0.5) * 150.0 + (smooth_noise(shape, cell, 2) - 0.5) * 50.0
    wob2 = wob * 0.35
    worn = smooth_noise(shape, cell * 6, 3)
    paved = np.clip((smooth_noise(shape, cell * 5, 8) - 0.34) * 5.0, 0.0, 1.0)             # the old paving survives in stretches
    paved2 = np.clip((smooth_noise(shape, cell * 2, 9) - 0.22) * 4.0, 0.0, 1.0)
    d_paved, d_road = S.read(W.PAVED) + wob, S.read(W.ROAD) + wob
    wd, fd, deckd = S.read(W.WD), S.read(W.FORD), S.read(W.DECKD)
    paved = np.maximum(paved, np.clip((900.0 - deckd) / 400.0, 0.0, 1.0))                  # and is whole on the bridges and up to them
    R = band(d_paved, 55.0, 105.0) * 0.5 * paved + band(d_paved, 100.0, 165.0) * 0.5      # stones inside ~55, earth out to ~165
    R = np.maximum(R, band(d_road, 40.0, 120.0) * 0.52)                                    # the other roads: earth only
    camps = [(x, y, 620.0) for x, y in W.starts.values()] + [(x, y, 420.0) for x, y in W.veins] + [(x, y, 520.0) for x, y, _ in W.relics + W.towers]
    for cx, cy, rad in camps:
        dd = np.hypot(S.X - cx, S.Y - cy)
        R = np.maximum(R, np.clip((rad - dd) / rad, 0, 1) * (0.25 + worn * 0.45))          # trampled ground at camps, veins and ruins
    R = np.maximum(R, np.clip((worn - 0.83) * 4.0, 0, 0.5))                                # a few bare scuffs
    # kingdoms: packed earth under and round each building, a cobbled court before a castle gate, footpaths
    for kind, bx, by, yaw, team, label in W.buildings:
        x0, y0, x1, y1 = building_meta(kind)["footprint"]
        lx, ly = S.X - bx, S.Y - by

        def rect_d(ax0, ay0, ax1, ay1):
            return np.hypot(np.maximum(np.maximum(ax0 - lx, lx - ax1), 0.0), np.maximum(np.maximum(ay0 - ly, ly - ay1), 0.0)) + wob2

        R = np.maximum(R, band(rect_d(x0, y0, x1, y1), 30.0, 150.0) * (0.5 + worn * 0.08))
        if kind == "castle":
            R = np.maximum(R, band(rect_d(x0 - 380, -300, x0 + 20, 300), 0.0, 70.0) * (0.56 + 0.44 * paved2))
        elif kind == "mine":
            R = np.maximum(R, band(rect_d(x0 - 60, -150, x0 + 300, 150), 0.0, 60.0) * (0.56 + 0.3 * paved2))
    for pts in kingdom_paths(W):
        R = np.maximum(R, band(S.read(T.line_dist(pts)) + wob2, 34.0, 100.0) * 0.56)
    R = np.maximum(R, band(np.where(wd > 0, wd, 1e6) + wob2 * 0.6, 25.0, 90.0) * 0.46)    # mud at the water's edge
    R = np.maximum(R, band(fd + wob2, 120.0, 520.0) * (0.56 + 0.44 * paved2))              # gravel on a ford's banks and bed
    R = np.maximum(R, band(deckd, 0.0, 60.0))                                              # the bridge slabs and the dais: set stone
    # moss and straw: the regions. Lush along the water, in the hollows and under the woods; parched on the tables,
    # the benches and the high ground.
    z, flat = S.read(W.H), S.read(W.flat.astype(np.float32))
    wood = np.zeros((N, N), np.float32)
    for fx, fy, rx, ry, count, kinds, turn, sym in W.forests:
        for px, py in (W.orbit((fx, fy)) if sym else [(fx, fy)]):
            wood = np.maximum(wood, np.clip(1.3 - np.hypot((X - px) / rx, (Y - py) / ry), 0.0, 1.0))
    wood = S.read(wood)
    high = np.clip((z - 600.0) / 1500.0, 0.0, 1.0)
    bank = band(np.where(wd > 0, wd, 0.0) + wob * 0.25, 60.0, 520.0)
    moss = smooth_noise(shape, cell * 8, 4) * 0.75 + smooth_noise(shape, cell * 2, 5) * 0.25 + 0.42 * bank + 0.34 * wood - 0.3 * high - 0.2 * flat
    dry = smooth_noise(shape, cell * 10, 6) * 0.7 + smooth_noise(shape, cell * 3, 7) * 0.3 + 0.26 * high + 0.2 * flat - 0.5 * bank - 0.35 * wood
    R = np.maximum(R, flat * np.clip((worn - 0.58) * 1.5, 0.0, 0.42))                      # worn, stony patches on the level ground
    # shade baked into the hollows and at the feet of the slopes
    foot = np.clip((ndimage.gaussian_filter(W.H, 4.0) - W.H) / 140.0, 0.0, 1.0)
    shade = 1.0 - np.clip(S.read(foot) * 0.3, 0.0, 0.15)
    G = np.clip((moss - 0.42) * 2.6, 0, 1)
    G = np.clip(G + S.read(foot) * 0.4, 0, 1)
    Bc = np.clip((dry - 0.6) * 3.2, 0, 1) * (1.0 - G)
    W.DRY = np.clip((ndimage.gaussian_filter(np.clip(W.H - 600.0, 0, 1500.0) / 1500.0, 2.0) * 0.26 + 0.35 - 0.6) * 3.2 + 0.5, 0.0, 1.0).astype(np.float32)
    img = np.dstack([R, G, Bc, shade])
    return (np.clip(img, 0, 1) * 255 + 0.5).astype(np.uint8)


def mist_pool(W):
    """Where ground mist pools (M_Mist's ground mist; T_WaterMap.a), on the land's raster: the hollows (ground lying
    under the land round it, at two sizes) and the wet margins of the water; little on the kingdoms' level tables,
    none on the mountainsides."""
    if getattr(W, "POOL", None) is None:
        hollow = np.clip((ndimage.gaussian_filter(W.H, 22.0) - W.H) / 420.0, 0.0, 1.0) + np.clip((ndimage.gaussian_filter(W.H, 7.0) - W.H) / 160.0, 0.0, 1.0) * 0.6
        hollow *= 1.0 - T.smoothstep((W.SL - 0.3) / 0.3)
        W.POOL = (np.clip(hollow + np.clip(1.0 - np.abs(W.WD) / 900.0, 0.0, 1.0) * 0.55, 0.0, 1.0) * (1.0 - 0.7 * W.flat.astype(np.float32))).astype(np.float32)
    return W.POOL


def build_water_map(W, S):
    """T_WaterMap, read by M_Water and M_Mist. World-aligned over the splat map's square, half its resolution.
    R = distance in from the bank (0 at the bank .. 1 at 256 cm and beyond), G = ford (1 over a ford's gravel bed),
    B = current (1 in the rivers, 0 out in the still lakes, tarns and meres), A = where ground mist pools (the hollows
    and the water's margins)."""
    wd, fd = S.read(W.WD), S.read(W.FORD)
    water = wd < 0.0
    ford = np.clip(1.0 - fd / 160.0, 0.0, 1.0) * water
    cur = np.full((N, N), 1e9, np.float32)
    for line in W.current_lines:
        cur = np.minimum(cur, T.line_dist(line))
    cur = np.clip(1.0 - (S.read(cur) - 700.0) / 900.0, 0.0, 1.0)
    img = np.dstack([np.clip(-wd / 256.0, 0, 1) * water, ford, cur, S.read(mist_pool(W))])
    h = S.res // 2
    img = img.reshape(h, 2, h, 2, 4).mean(axis=(1, 3))
    return (img * 255 + 0.5).astype(np.uint8)


def build_flow_map(W, S):
    """T_WaterFlow, read by M_Water, M_Mist and M_Terrain. The water map's square and resolution.
    RG = the current: the way the water runs (world X, Y; 0.5 = still), each river along its own bed, its length the
    current's strength (full in a river, dying away out in a lake, a tarn or a mere).
    B = how deep the water is (surface down to the bed; 1 = 2 m and deeper). A = damp ground: 1 at the water's edge,
    dry 3 m back from it (M_Terrain darkens the bank with it)."""
    fx, fy = np.zeros((T.FN, T.FN), np.float32), np.zeros((T.FN, T.FN), np.float32)
    m = np.zeros((T.FN, T.FN), bool)
    centre_out = W.sym == 4                                    # the Four Marches' rivers run out from the High Moor
    for line in W.current_lines:
        q, _ = T.dense(line)
        if len(q) < 3:
            continue
        end = q[-1] - q[0]
        down = (np.hypot(*q[-1]) > np.hypot(*q[0])) if centre_out else (end[0] * W.flow[0] + end[1] * W.flow[1] > 0.0)
        if not down:
            q = q[::-1]
        t = np.gradient(q, axis=0)
        t /= np.maximum(np.hypot(t[:, 0], t[:, 1]), 1e-6)[:, None]
        fi = np.rint((q[:, 0] - T.ORG) / T.FSTEP).astype(np.int64)
        fj = np.rint((q[:, 1] - T.ORG) / T.FSTEP).astype(np.int64)
        ok = (fi >= 0) & (fj >= 0) & (fi < T.FN) & (fj < T.FN)
        fx[fi[ok], fj[ok]], fy[fi[ok], fj[ok]], m[fi[ok], fj[ok]] = t[ok, 0], t[ok, 1], True
    if m.any():
        d, idx = ndimage.distance_transform_edt(~m, return_indices=True)
        ii, jj = idx[0][::T.SS, ::T.SS], idx[1][::T.SS, ::T.SS]
        vx, vy = ndimage.gaussian_filter(fx[ii, jj], 2.5), ndimage.gaussian_filter(fy[ii, jj], 2.5)
        strength = np.clip(1.0 - (d[::T.SS, ::T.SS] * T.FSTEP - 700.0) / 900.0, 0.0, 1.0)
    else:
        vx = vy = strength = np.zeros((N, N), np.float32)
    ln = np.maximum(np.hypot(vx, vy), 1e-6)
    vx, vy = S.read(vx / ln * strength), S.read(vy / ln * strength)
    depth = np.where(np.isnan(W.WS), 0.0, np.maximum(W.WS - W.H, 0.0))
    wd = S.read(W.WD)
    damp = np.clip(1.0 - wd / 300.0, 0.0, 1.0) * (wd > -40.0)
    img = np.dstack([vx * 0.5 + 0.5, vy * 0.5 + 0.5, np.clip(S.read(depth) / 200.0, 0.0, 1.0), damp])
    h = S.res // 2
    img = img.reshape(h, 2, h, 2, 4).mean(axis=(1, 3))
    return (np.clip(img, 0.0, 1.0) * 255 + 0.5).astype(np.uint8)


def build_forest_map(W, S, D):
    """T_Forest, read by M_Terrain: the forest floor. The water map's square and resolution.
    R = how closed the canopy is (0 open sky .. 1 deep in a wood: M_Terrain lays leaf litter there texel by texel),
    G = the same spread wider (the soft shade under and round a wood), B = 0."""
    c = getattr(D, "canopy", None)
    if c is None:
        c = np.zeros((N, N), np.float32)
    wide = np.clip(ndimage.gaussian_filter(c, 4.0) * 1.2, 0.0, 1.0)
    img = np.dstack([S.read(c), S.read(wide), np.zeros(S.X.shape, np.float32), np.ones(S.X.shape, np.float32)])
    h = S.res // 2
    img = img.reshape(h, 2, h, 2, 4).mean(axis=(1, 3))
    return (np.clip(img, 0.0, 1.0) * 255 + 0.5).astype(np.uint8)


# ============================================================================================ pictures
def render(W, S, splat, D, rect, scale, plain=False):
    """A top-down picture of rect = (x0, x1, y0, y1): +X up, +Y right, like the game camera. Returns (image, P)."""
    x0, x1, y0, y1 = rect
    w, h = int((y1 - y0) * scale), int((x1 - x0) * scale)
    xs = x1 - (np.arange(h) + 0.5) / scale
    ys = y0 + (np.arange(w) + 0.5) / scale
    Yg, Xg = np.meshgrid(ys, xs)
    z = T.sample(W.H, Xg, Yg)
    gx, gy = T.gradient(ndimage.gaussian_filter(W.H, 0.8))
    sx, sy = T.sample(gx, Xg, Yg), T.sample(gy, Xg, Yg)
    si = np.clip(((Xg - S.origin[0]) / S.size * S.res).astype(int), 0, S.res - 1)
    sj = np.clip(((Yg - S.origin[1]) / S.size * S.res).astype(int), 0, S.res - 1)
    sp = splat[sj, si].astype(np.float32) / 255.0
    col = np.array([96, 112, 52], np.float32) * (1 - sp[..., 1:2] * 0.3) + np.array([40, 30, 0], np.float32) * sp[..., 2:3]
    col = col * (1 - sp[..., 0:1]) + np.array([150, 120, 85], np.float32) * sp[..., 0:1]
    col = col * sp[..., 3:4]
    steep = np.hypot(sx, sy)
    rock = np.maximum(np.clip((steep - 0.5) / 0.25, 0.0, 1.0), np.clip((z - W.relief["rock_line"] + 150.0) / 300.0, 0.0, 1.0))[..., None]
    col = col * (1.0 - rock) + np.array([128, 122, 106], np.float32) * rock
    col = np.where((z > W.relief["snow_line"])[..., None], np.array([226, 232, 238], np.float32), col)
    col = col * np.clip(0.82 + 1.5 * (sy * 0.85 - sx * 0.25), 0.35, 1.6)[..., None]        # the sun, from screen left
    ws = T.nearest(W.WS, Xg, Yg)
    wet = ~np.isnan(ws)
    col = np.where((wet & (ws - z <= WADE))[..., None], np.array([118, 150, 138], np.float32), col)     # a ford's gravel showing through
    col = np.where((wet & (ws - z > WADE))[..., None], np.array([40, 90, 100], np.float32) * np.clip(1.0 + (ws[..., None] + 16.0) / 4000.0, 0.6, 1.4), col)
    img = Image.fromarray(np.clip(col, 0, 255).astype(np.uint8))
    d = ImageDraw.Draw(img)

    def P(x, y):
        return ((y - y0) * scale, (x1 - x) * scale)

    k = scale / 0.04
    for mesh, lst in D.instances.items():
        if mesh.startswith("SM_Conifer"):
            for x, y, zz, yaw, s in lst:
                cx, cy = P(x, y)
                r = max(7 * k, 1.0)
                d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(25, 60, 30), outline=None if plain else (10, 30, 15))
        elif mesh.startswith("SM_Rock") and not plain:
            for x, y, zz, yaw, s in lst:
                cx, cy = P(x, y)
                rr = (2 if "_S" in mesh else (5 if "_M" in mesh else 9)) * k
                if rr >= 0.8:
                    d.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], fill=(150, 145, 130))
    return img, d, P


def write_preview(W, S, splat, D, path, minimap=0):
    """The picture of the whole dressed world, or (minimap = N) the HUD's N x N minimap base: exactly the +/-bound play
    square, land, water and woods only (the HUD draws buildings, troops, veins and ruins live on top)."""
    B = W.B
    if minimap:
        img, d, P = render(W, S, splat, D, (-B, B, -B, B), minimap / (2.0 * B), plain=True)
        img.save(path)
        return
    x0, x1, y0, y1 = W.box
    img, d, P = render(W, S, splat, D, (x0, x1, y0, y1), 1800.0 / (y1 - y0))
    d.rectangle([P(B, -B), P(-B, B)], outline=(255, 255, 255))
    for b in D.blockers:
        cx, cy = P(b["pos"][0], b["pos"][1])
        d.rectangle([cx - 2, cy - 2, cx + 2, cy + 2], outline=(255, 60, 40))
    for a in D.actors:
        cx, cy = P(a["pos"][0], a["pos"][1])
        d.rectangle([cx - 1, cy - 1, cx + 1, cy + 1], outline=(255, 220, 90))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    img.save(path)


# ============================================================================================ checks and the plan view
class Grid:
    """The field as USRGridSubsystem will sample it: 1 m cells over +/-bound, arrays indexed [ix, iy]."""

    def __init__(self, W, D):
        B = W.B
        n = self.n = int(2 * B / 100.0)
        c = -B + (np.arange(n) + 0.5) * 100.0
        self.Xc, self.Yc = np.meshgrid(c, c, indexing="ij")
        self.B = B

        def at(dx, dy):                                         # the ground a trace from above meets: a deck, else the land
            h = T.sample(W.H, self.Xc + dx, self.Yc + dy)
            dk = T.nearest(W.DECK, self.Xc + dx, self.Yc + dy)
            return np.where(np.isnan(dk), h, dk)

        H = self.H = at(0.0, 0.0).astype(np.float32)
        ws = T.nearest(W.WS, self.Xc, self.Yc)
        self.water = (~np.isnan(ws)) & (ws - H > WADE)          # deep water: a wall whatever its height
        # Edges, as the game decides them. A cell is open ground only if all of it is: (a) all four neighbours within
        # 20 cm: open; (b) both neighbours on an axis more than 70 cm off, the same way: a slope steeper than 0.7,
        # closed; (c) otherwise the cell's four corners (45 cm out) are read and a spread taller than a step closes it.
        dxp = np.zeros_like(H); dxm = np.zeros_like(H); dyp = np.zeros_like(H); dym = np.zeros_like(H)
        dxp[:-1] = H[1:] - H[:-1]; dxm[1:] = H[:-1] - H[1:]
        dyp[:, :-1] = H[:, 1:] - H[:, :-1]; dym[:, 1:] = H[:, :-1] - H[:, 1:]
        wn = ndimage.binary_dilation(self.water, structure=np.array([[0, 1, 0], [1, 1, 1], [0, 1, 0]], bool))
        gentle = (np.abs(dxp) <= GENTLE) & (np.abs(dxm) <= GENTLE) & (np.abs(dyp) <= GENTLE) & (np.abs(dym) <= GENTLE) & ~wn
        inner = np.zeros_like(gentle); inner[1:-1, 1:-1] = True
        sheer = (((dxp > SHEER) & (dxm < -SHEER)) | ((dxp < -SHEER) & (dxm > SHEER)) | ((dyp > SHEER) & (dym < -SHEER)) | ((dyp < -SHEER) & (dym > SHEER))) & inner
        cs = np.stack([H] + [at(dx, dy) for dx in (-45.0, 45.0) for dy in (-45.0, 45.0)])
        spread = cs.max(axis=0) - cs.min(axis=0)
        self.edge = ~self.water & ~gentle & (sheer | (spread > STEP_H))
        blocked = self.water | self.edge
        self.boxes = np.zeros_like(blocked)
        for b in D.blockers:                                    # the hidden blocker boxes, grown by half a cell
            ex, ey = b["size"][0] * 0.5 + 50.0, b["size"][1] * 0.5 + 50.0
            rad = math.hypot(ex, ey)
            cx, cy = b["pos"][0], b["pos"][1]
            i0, i1 = max(int((cx - rad + B) / 100.0), 0), min(int((cx + rad + B) / 100.0), n - 1)
            j0, j1 = max(int((cy - rad + B) / 100.0), 0), min(int((cy + rad + B) / 100.0), n - 1)
            if i1 < i0 or j1 < j0:
                continue
            ca, sa = math.cos(math.radians(b["yaw"])), math.sin(math.radians(b["yaw"]))
            dx, dy = self.Xc[i0:i1 + 1, j0:j1 + 1] - cx, self.Yc[i0:i1 + 1, j0:j1 + 1] - cy
            self.boxes[i0:i1 + 1, j0:j1 + 1] |= (np.abs(dx * ca + dy * sa) <= ex) & (np.abs(-dx * sa + dy * ca) <= ey)
        blocked |= self.boxes
        blocked[0, :] = blocked[-1, :] = blocked[:, 0] = blocked[:, -1] = True      # the outermost ring is off limits
        self.blocked = blocked
        self.built = np.zeros_like(blocked)
        for kind, x, y, yaw, team, label in W.buildings:
            self.built |= self.foot(kind, x, y)
        self.solid = self.blocked | self.built
        near = ndimage.binary_dilation(self.solid, structure=np.ones((3, 3), bool))
        for di in (-1, 0, 1):
            for dj in (-1, 0, 1):
                if di or dj:
                    near |= np.abs(H - np.roll(np.roll(H, di, 0), dj, 1)) > STEP_H
        self.wide_solid = self.solid | near                    # also the cells hard against something (FlagNearWall)

    def foot_slice(self, kind, x, y):
        """The cells a footprint reaches into, as index ranges."""
        x0, y0, x1, y1 = building_meta(kind)["footprint"]
        lo = lambda v: max(int(math.floor((v + 5.0 + self.B) / 100.0)), 0)
        hi = lambda v: min(int(math.ceil((v - 5.0 + self.B) / 100.0)), self.n)
        return slice(lo(x + x0), hi(x + x1)), slice(lo(y + y0), hi(y + y1))

    def foot(self, kind, x, y):
        m = np.zeros((self.n, self.n), bool)
        m[self.foot_slice(kind, x, y)] = True
        return m

    def cell(self, p):
        return (int(np.clip((p[0] + self.B) / 100.0, 0, self.n - 1)), int(np.clip((p[1] + self.B) / 100.0, 0, self.n - 1)))

    def mask(self, geoms):
        m = np.zeros((self.n, self.n), bool)
        for g in geoms:
            m |= T.nearest(T.mask(g), self.Xc, self.Yc)
        return m

    def walk(self, solid, start):
        """Distance in metres from `start` to everywhere a troop can walk (eight-way moves, a step at most 45 cm tall,
        no cutting a corner: the grid's own moves): -1 = never."""
        n = self.n
        open_ = ~solid
        H = self.H
        idx = np.arange(n * n).reshape(n, n)
        ok_x = open_[:-1] & open_[1:] & (np.abs(H[1:] - H[:-1]) <= STEP_H)
        ok_y = open_[:, :-1] & open_[:, 1:] & (np.abs(H[:, 1:] - H[:, :-1]) <= STEP_H)
        sq = open_[:-1, :-1] & open_[1:, :-1] & open_[:-1, 1:] & open_[1:, 1:]
        ok_d1 = sq & (np.abs(H[1:, 1:] - H[:-1, :-1]) <= STEP_H)
        ok_d2 = sq & (np.abs(H[1:, :-1] - H[:-1, 1:]) <= STEP_H)
        rows = np.concatenate([idx[:-1][ok_x], idx[:, :-1][ok_y], idx[:-1, :-1][ok_d1], idx[:-1, 1:][ok_d2]])
        cols = np.concatenate([idx[1:][ok_x], idx[:, 1:][ok_y], idx[1:, 1:][ok_d1], idx[1:, :-1][ok_d2]])
        wts = np.concatenate([np.ones(int(ok_x.sum()) + int(ok_y.sum()), np.float32), np.full(int(ok_d1.sum()) + int(ok_d2.sum()), 1.41421356, np.float32)])
        g = sparse.coo_matrix((wts, (rows, cols)), shape=(n * n, n * n)).tocsr()
        i, j = self.cell(start)
        if solid[i, j]:                                         # the nearest open cell to the start
            ii, jj = np.nonzero(open_[max(i - 6, 0):i + 7, max(j - 6, 0):j + 7])
            if len(ii) == 0:
                return np.full((n, n), -1, np.int32)
            k = int(np.argmin((ii - 6) ** 2 + (jj - 6) ** 2))
            i, j = max(i - 6, 0) + int(ii[k]), max(j - 6, 0) + int(jj[k])
        dist = csgraph.dijkstra(g, directed=False, indices=i * n + j)
        return np.where(np.isfinite(dist), dist, -1).astype(np.int32).reshape(n, n)

    def near(self, dist, p, r=5):
        """Shortest distance to any cell within r of p (-1: none can be reached)."""
        i, j = self.cell(p)
        a = dist[max(i - r, 0):i + r + 1, max(j - r, 0):j + r + 1]
        a = a[a >= 0]
        return int(a.min()) if len(a) else -1


def validate(W, D):
    """Checks the map the way the game will use it. Returns (report lines, grid, distances from the player's start)."""
    G = Grid(W, D)
    out = []
    ps, es = W.starts["player"], W.starts["enemy"]
    d_all = G.walk(G.solid, ps)
    d_wide = G.walk(G.wide_solid, ps)
    de = G.near(d_all, es)
    out.append("%s (%s): +/-%.0f m" % (W.name, W.id, W.B / 100.0))
    out.append("player start -> enemy start: %s; a wide way (1 m clear of every slope, bank and box): %s" % (
        "%d m on foot" % de if de >= 0 else "NO ROUTE", "%d m" % G.near(d_wide, es) if G.near(d_wide, es) >= 0 else "NARROW: none"))
    everything = G.mask(W.river_all)
    for name, geoms in W.crossings:
        others = everything & ~G.mask(geoms)
        dd = G.near(G.walk(G.solid | others, ps), es)
        out.append("  only by the %-24s %s" % (name + ":", "%d m" % dd if dd >= 0 else "no way (the other crossings carry it)"))
    for name, geoms, a, b in W.checks:
        frm = W.starts[a] if isinstance(a, str) else a
        to = W.starts[b] if isinstance(b, str) else b
        dd = G.near(G.walk(G.solid | G.mask(geoms), frm), to, 8)
        out.append("  %s: %s" % (name, "holds" if dd < 0 else "LEAK: crossed elsewhere (%d m)" % dd))
    inside = (np.abs(G.Xc) < W.B - 500) & (np.abs(G.Yc) < W.B - 500)
    out.append("walkable cells cut off from the player's start (inside the edge strip): %d of %d walkable" % (int(((d_all < 0) & ~G.solid & inside).sum()), int((~G.solid).sum())))
    # fairness: the walkable mask against its own turns
    walk, reach0 = ~G.blocked, d_all >= 0
    diffs = []
    for k in range(1, W.sym):
        q = k * (4 // W.sym)
        diffs.append(int(((walk != np.rot90(walk, q)) & (reach0 | np.rot90(reach0, q))).sum()))
    out.append("symmetry: cells troops can reach whose walkability differs under each turn of the map: %s of %d" % (", ".join(str(v) for v in diffs), int(reach0.sum())))

    def foot_ok(kind, x, y, own=None, free=False):
        sl = G.foot_slice(kind, x, y)
        h = G.H[sl]
        if h.size == 0 or (G.blocked[sl] & ~(own[sl] if own is not None else False)).any() or float(h.max() - h.min()) > FLAT_TOL:
            return False
        if free and G.built[sl].any():
            return False
        x0, y0, x1, y1 = building_meta(kind)["footprint"]
        return x + x0 > -W.B + 100 and x + x1 < W.B - 100 and y + y0 > -W.B + 100 and y + y1 < W.B - 100

    home = [(b[1], b[2]) for b in W.buildings if b[0] == "mine"]
    for i, (x, y) in enumerate(W.veins):
        ok = foot_ok("mine", x, y)
        dv = G.near(d_all, (x - 650.0, y), 4)
        wide = G.near(d_wide, (x - 650.0, y), 5) >= 0
        note = " (a mine stands on it)" if any(abs(x - hx) < 1 and abs(y - hy) < 1 for hx, hy in home) else ""
        out.append("vein %2d at (%6.0f, %6.0f) z %4.0f: mine %s, %s, %s%s" % (i, x, y, W.z(x, y), "fits" if ok else "DOES NOT FIT",
                                                                           ("%d m from the player's start" % dv) if dv >= 0 else "UNREACHABLE",
                                                                           "wide way to it" if wide else "NARROW: no wide way to it", note))
    for kind, lst in (("relic", W.relics), ("old tower", W.towers)):
        for i, (x, y, name) in enumerate(lst):
            dv = G.near(d_all, (x, y), 6)
            own = (np.abs(G.Xc - x) < 400.0) & (np.abs(G.Yc - y) < 400.0)
            ok = foot_ok("relictower" if kind == "relic" else "tower", x, y, own)
            out.append("%-9s %2d at (%6.0f, %6.0f) z %4.0f%s: tower %s, %s" % (kind, i, x, y, W.z(x, y), " (%s)" % name if name else "", "fits" if ok else "DOES NOT FIT",
                                                                              ("%d m from the player's start" % dv) if dv >= 0 else "UNREACHABLE"))
    for name, x, y in W.reach:
        dv = G.near(d_all, (x, y), 6)
        out.append("%s at (%.0f, %.0f): %s" % (name, x, y, ("%d m from the player's start" % dv) if dv >= 0 else "UNREACHABLE"))
    for team, anchor, poly in W.tables:
        counts = {}
        for kind in ("farm", "castle"):                        # the castle's footprint stands in for the largest thing built
            c = 0
            for x in np.arange(anchor[0] - 3800, anchor[0] + 3801, 200.0):
                for y in np.arange(anchor[1] - 3800, anchor[1] + 3801, 200.0):
                    if math.hypot(x - anchor[0], y - anchor[1]) <= 3800 and foot_ok(kind, x, y, free=True):
                        c += 1
            counts[kind] = c
        who = {0: "the player's", 1: "the enemy's", None: "a fallen kingdom's"}[team]
        dv = G.near(d_all, (anchor[0] + (1500.0 if anchor[0] < 0 else -1500.0), anchor[1] + (1400.0 if anchor[1] < 0 else -1400.0)), 6)
        out.append("%s table (%.0f m2 level, z %.0f): %d farm-sized and %d castle-sized building spots within 38 m of the castle; %s" % (
            who, poly.area / 10000.0, W.z(anchor[0], anchor[1]), counts["farm"], counts["castle"], ("%d m from the player's start" % dv) if dv >= 0 else "UNREACHABLE"))
        if min(counts.values()) < 60:
            out.append("  DOES NOT FIT: too little building ground on that table")
    grades = {}
    for r in W.roads:
        g_ = float(np.max(np.abs(np.diff(r["profile"][1])) / np.maximum(np.diff(r["profile"][0]), 1e-6)))
        grades[r["name"]] = max(grades.get(r["name"], 0.0), g_)
    tight_g = ["(%.0f, %.0f)" % (x, y) for x, y, r in W.greens if not foot_ok("barracks", x, y, free=True)]
    out.append("greens (level building ground out in the country): %d%s" % (len(W.greens), "; no room for a barracks on: " + " ".join(tight_g) if tight_g else ", a barracks fits on each"))
    out.append("roads: %d; steepest along the middle line (a grid cell may rise 45 cm per 100): %s" % (len(W.roads), ", ".join("%s %.2f" % kv for kv in sorted(grades.items()))))
    reach = d_all >= 0
    W.focus_max = float(np.ceil((G.H[reach].max() + 150.0) / 50.0) * 50.0)
    out.append("water: %.1f%% of the field is deep, %.1f%% ford or marsh; slopes too steep to walk: %.1f%%; boxes: %d" % (
        100.0 * float(G.water.mean()), 100.0 * float(((~np.isnan(T.nearest(W.WS, G.Xc, G.Yc))) & ~G.water).mean()), 100.0 * float(G.edge.mean()), len(D.blockers)))
    out.append("relief inside the field: %.0f .. %.0f cm; ground troops can reach: %.0f .. %.0f cm (the camera rides it up to %.0f); %.0f%% of the field is above 10 m, %.0f%% above 20 m" % (
        float(G.H.min()), float(G.H.max()), float(G.H[reach].min()), float(G.H[reach].max()), W.focus_max, 100.0 * float((G.H > 1000).mean()), 100.0 * float((G.H > 2000).mean())))
    for arg in sys.argv:                                       # --probe=x,y : the grid round a spot (height in dm; # blocked, . unreachable)
        if arg.startswith("--probe="):
            px_, py_ = (float(v) for v in arg[8:].split(","))
            ci, cj = G.cell((px_, py_))
            print("grid round (%.0f, %.0f), +X up, +Y right:" % (px_, py_))
            for i in range(min(ci + 9, G.n - 1), max(ci - 10, 0), -1):
                print(" ".join(("  #" if G.solid[i, j] else ("%3d" % round(G.H[i, j] / 10.0) if d_all[i, j] >= 0 else "%2d." % round(G.H[i, j] / 10.0))) for j in range(max(cj - 12, 0), min(cj + 13, G.n))))
    bad = [l for l in out if any(k in l for k in ("NO ROUTE", "LEAK", "DOES NOT FIT", "UNREACHABLE"))]
    tight = [l for l in out if "NARROW" in l and l not in bad]
    out.append("MAP CHECK: %s%s" % ("passed" if not bad else "%d PROBLEM(S): troops will not get everywhere they should" % len(bad),
                                    "" if not tight else "; %d warning(s): narrow ways (see NARROW above)" % len(tight)))
    for line in out:
        print(line)
    return out, G, d_all


def write_layout_preview(W, S, splat, D, G, d_all, path):
    """The plan of the field as the game will read it (+X up, +Y right, like the camera): the land, the water and the
    fords, ground too steep to walk, the blocker boxes, ground nobody can reach, roads, veins, ruins, kingdoms."""
    B = W.B
    half = B + 1200.0
    scale = 1500.0 / (2 * half)
    img, d, P = render(W, S, splat, D, (-half, half, -half, half), scale, plain=True)
    col = np.asarray(img).astype(np.float32)
    w = col.shape[0]
    xs = half - (np.arange(w) + 0.5) / scale
    ys = -half + (np.arange(w) + 0.5) / scale
    Yg, Xg = np.meshgrid(ys, xs)
    gi = np.clip(((Xg + B) / 100.0).astype(int), 0, G.n - 1)
    gj = np.clip(((Yg + B) / 100.0).astype(int), 0, G.n - 1)
    ing = (np.abs(Xg) < B) & (np.abs(Yg) < B)
    col = np.where((G.edge[gi, gj] & ing)[..., None], col * 0.55 + np.array([120, 70, 50], np.float32) * 0.45, col)
    col = np.where((G.boxes[gi, gj] & ing)[..., None], np.array([200, 50, 40], np.float32), col)
    lost = (d_all[gi, gj] < 0) & ~G.solid[gi, gj] & ing
    col = np.where(lost[..., None], col * 0.6 + np.array([230, 40, 230], np.float32) * 0.4, col)
    col = np.where(ing[..., None], col, col * 0.6)
    img = Image.fromarray(np.clip(col, 0, 255).astype(np.uint8))
    d = ImageDraw.Draw(img)
    font, small = ImageFont.load_default(size=17), ImageFont.load_default(size=13)

    def label(x, y, text, fill=(255, 255, 255), f=None, anchor="mm"):
        px_, py_ = P(x, y)
        f = f or font
        for ox, oy in ((-1, 0), (1, 0), (0, -1), (0, 1), (1, 1), (-1, -1)):
            d.text((px_ + ox, py_ + oy), text, fill=(0, 0, 0), font=f, anchor=anchor)
        d.text((px_, py_), text, fill=fill, font=f, anchor=anchor)

    for r in W.roads:
        pts = [P(x, y) for x, y in r["pts"]]
        d.line(pts, fill=(232, 208, 150) if r["kind"] == "paved" else (214, 180, 120), width=3 if r["kind"] == "paved" else 2)
    d.rectangle([P(B, -B), P(-B, B)], outline=(255, 255, 255))
    for kind, bx, by, yaw, team, lab in W.buildings:
        c = (70, 130, 255) if team == 0 else (255, 70, 50)
        x0, y0, x1, y1 = building_meta(kind)["footprint"]
        d.polygon([P(bx + x0, by + y0), P(bx + x1, by + y0), P(bx + x1, by + y1), P(bx + x0, by + y1)], fill=c, outline=(255, 255, 255))
        if kind == "castle":
            cx, cy = P(bx, by)
            d.ellipse([cx - 3800 * scale, cy - 3800 * scale, cx + 3800 * scale, cy + 3800 * scale], outline=c)
    for (who, (x, y)), c in zip(sorted(W.starts.items(), key=lambda kv: kv[0] != "player"), ((70, 130, 255), (255, 70, 50))):
        cx, cy = P(x, y)
        d.ellipse([cx - 8, cy - 8, cx + 8, cy + 8], outline=c, width=3)
    for i, (x, y) in enumerate(W.veins):
        cx, cy = P(x, y)
        d.polygon([(cx, cy - 9), (cx + 9, cy), (cx, cy + 9), (cx - 9, cy)], fill=(255, 205, 40), outline=(60, 40, 0))
        label(x - 380, y, "%d" % i, fill=(255, 225, 120), f=small)
    for x, y, name in W.relics:
        cx, cy = P(x, y)
        d.ellipse([cx - 8, cy - 8, cx + 8, cy + 8], fill=(150, 215, 255), outline=(0, 0, 0))
    for x, y, name in W.towers:
        cx, cy = P(x, y)
        d.rectangle([cx - 6, cy - 6, cx + 6, cy + 6], fill=(205, 205, 205), outline=(0, 0, 0))
    for x, y, r in W.greens:
        cx, cy = P(x, y)
        d.ellipse([cx - r * scale, cy - r * scale, cx + r * scale, cy + r * scale], outline=(190, 230, 150))
    for kind, x, y in D.structures:
        if kind not in ("cairn", "watch post"):
            label(x - 420, y, kind, fill=(255, 235, 190), f=small)
    for x, y, text, sm in W.labels:
        label(x, y, text, f=small if sm else font)
    for team, anchor, poly in W.tables:
        label(anchor[0] + (1300 if anchor[0] > 0 else -1300), anchor[1], {0: "PLAYER", 1: "ENEMY", None: "FALLEN KINGDOM"}[team], fill={0: (150, 190, 255), 1: (255, 160, 150), None: (220, 220, 220)}[team])
    y0 = 8
    for text, c in (("deep water (a wall)", (40, 90, 100)), ("ford / marsh (walkable)", (118, 150, 138)), ("too steep to walk (mountainside, bank)", (150, 95, 70)),
                    ("blocker boxes (trunks, boulders, ruins)", (200, 50, 40)), ("magenta: open ground nobody can reach", (230, 40, 230)),
                    ("gold vein / relic (round) / old tower (square); circle: 38 m territory; +X is up, +Y right", (255, 205, 40))):
        d.rectangle([8, y0, 22, y0 + 14], fill=c, outline=(0, 0, 0))
        d.text((28, y0), text, fill=(255, 255, 255), font=small)
        y0 += 18
    os.makedirs(os.path.dirname(path), exist_ok=True)
    img.save(path)


# ============================================================================================ meshes
def deck_mesh(W, dk):
    """A bridge: a stone slab from bank to bank on piers; or the shrine's dais. (The terraces' cap and wall: M_Terrain
    gives the top its set stones by the splat map and the sides coursed masonry.)"""
    m = Mesh(dk["name"])
    g = dk["geom"]
    T.add_cap(m, g, dk["z"])
    if dk.get("kind") == "dais":
        T.add_wall(m, T.ring_ccw(list(g.exterior.coords)), dk["z"], dk["z"] - 60.0)
        return m
    T.add_wall(m, T.ring_ccw(list(g.exterior.coords)), dk["z"], dk["z"] - 86.0)
    mid, dv, span, half = np.array(dk["mid"]), dk["dir"], dk["span"], dk["width"] * 0.5
    n = max(int(round(span / 520.0)) - 1, 1)
    yaw = math.degrees(math.atan2(dv[1], dv[0]))
    for i in range(n):                                          # piers down to the bed
        c = mid + dv * (span * ((i + 1) / (n + 1) - 0.5))
        bed = W.z(c[0], c[1]) - 30.0
        if bed < dk["z"] - 120.0:
            b = Mesh("pier")
            b.box((-55.0, -half + 30.0, bed - dk["z"]), (55.0, half - 30.0, -86.0), uv_offset=(float(i * 37), 0.0))
            m.append(b.transformed("pier", yaw, (c[0], c[1], dk["z"])))
    return m


def fall_mesh(W, name, f):
    """A waterfall: a ribbon from the tarn's lip down the rock face to the pool, lying a hand above the rock (so it is
    a sheer fall where the face is sheer and a cascade where it is not). UV0 = (0..1 across, distance fallen in cm),
    UV1.x = 0 at the lip .. 1 at the pool (M_Waterfall scrolls streaks down it and foams the foot)."""
    lip, o = np.array(f["lip"], float), np.array(f["out"], float)
    side = np.array([-o[1], o[0]])
    top, bottom = f["top"] + 4.0, f["bottom"] + 2.0
    path, d = [], -80.0
    zc = top
    while d < 6000.0:
        p = lip + o * d
        ws = float(T.nearest(W.WS, p[0], p[1]))
        zc = min(zc, max(W.z(p[0], p[1]) + 55.0, bottom)) if d > 0.0 else top
        path.append((d, zc))
        if d > 60.0 and not math.isnan(ws) and abs(ws - f["bottom"]) < 1.0 and W.z(p[0], p[1]) < f["bottom"] + 60.0:     # over the pool, clear of the rock
            path += [(d + 60.0, bottom), (d + 140.0, bottom)]
            break
        d += 20.0
    if len(path) > 120:                                        # keep the ribbon light: every row matters only where it bends
        keep = [0] + [i for i in range(1, len(path) - 1) if i % max(len(path) // 100, 1) == 0] + [len(path) - 1]
        path = [path[i] for i in sorted(set(keep))]
    foot = lip + o * (path[-1][0] - 40.0)
    f["foot"] = [round(float(foot[0]), 1), round(float(foot[1]), 1), round(float(f["bottom"]), 1)]      # where it meets the pool (spray, churned water)
    cols = 6
    m = Mesh(name)
    ids = []
    for i, (dist, z) in enumerate(path):
        t = float(np.clip((top - z) / max(top - bottom, 1.0), 0.0, 1.0))
        half = f["width"] * 0.5 * (1.0 + 0.3 * t)
        row = []
        for j in range(cols + 1):
            u = j / cols
            bow = 26.0 * (1.0 - (2.0 * u - 1.0) ** 2) * min(t * 6.0, 1.0)                  # the sheet bellies out in the middle
            p = lip + o * (dist + bow + 45.0 * min(t * 8.0, 1.0)) + side * (2.0 * u - 1.0) * half    # thrown clear of the rock
            row.append(m.vert((p[0], p[1], z + bow * 0.2), (o[0], o[1], 0.5), (u, top - z), (t, 0.0)))
        ids.append(row)
    for i in range(len(ids) - 1):
        for j in range(cols):
            m.quad(ids[i][j], ids[i + 1][j], ids[i + 1][j + 1], ids[i][j + 1])
            m.quad(ids[i][j], ids[i][j + 1], ids[i + 1][j + 1], ids[i + 1][j])  # both faces
    return m


def placements(W):
    """The kingdoms' buildings for the level builder, each on the ground it stands on."""
    placed = []
    for kind, x, y, yaw, team, label in W.buildings:
        meta = building_meta(kind)
        placed.append({"type": kind, "mesh": meta["mesh"], "label": label, "team": team, "pos": [x, y, round(W.z(x, y), 1)], "yaw": yaw,
                       "footprint": meta["footprint"], "ring_radius": meta["ring_radius"], "colliders": meta["colliders"], "sockets": meta["sockets"]})
    return placed


# ============================================================================================ one map
def generate(map_id):
    t0 = time.time()
    sfx = "" if map_id == "two" else "4"
    W = maps.PLANS[map_id]()
    W.finish()
    W.DECKD = np.full((N, N), 1e9, np.float32)
    for dk in W.decks:
        W.DECKD = np.minimum(W.DECKD, np.maximum(T.sdist(dk["geom"]), 0.0))
    S = Splat(W)
    splat = build_splat(W, S)
    D = Dressing(W, FAST)
    D.gameplay()
    D.scatter()
    if not os.environ.get("SR_NO_GROVES"): D.groves()
    D.rubble()
    report, G, d_all = validate(W, D)
    prev = os.path.join(ROOT, "Saved", "MapPreview")
    os.makedirs(prev, exist_ok=True)
    write_layout_preview(W, S, splat, D, G, d_all, os.path.join(prev, "layout%s.png" % sfx))
    with open(os.path.join(prev, "report%s.txt" % sfx), "w") as f:
        f.write("\n".join(report) + "\n")
    os.makedirs(os.path.join(ROOT, "Saved", "WorldPreview"), exist_ok=True)
    if "PROBLEM" in report[-1] and not FAST and "--force" not in sys.argv:
        # a map troops cannot walk is not written: fix the plan (the report says where), or pass --force
        print("map not written: it fails its checks (Saved/MapPreview/report%s.txt); --force writes it anyway" % sfx)
        return False
    if FAST:
        write_preview(W, S, splat, D, os.path.join(ROOT, "Saved", "WorldPreview", "map%s.png" % sfx))
        print("plan only (%.0f s): nothing written to SourceArt" % (time.time() - t0))
        return "PROBLEM" not in report[-1]

    # ---- meshes
    meshes, layout_terrain = [], []
    # the land: within 6 cm of the raster where troops walk (level ground comes out exactly level), looser on the
    # mountainsides, under water and beyond the field
    tol = 6.0 + 14.0 * T.smoothstep((W.SL - 0.5) / 0.4) + np.clip(W.OUT / 30.0, 0.0, 120.0)
    tol = np.where(~np.isnan(W.WS) & (W.WS - W.H > 40.0), np.maximum(tol, 30.0), tol)
    land, tris_land = T.terrain_meshes(W.H, tol, W.box)
    pool = mist_pool(W)
    for m in land:
        meshes.append(m)
        pts = np.array(m.p)                                     # (before it is recentred: world coordinates)
        mist = bool(T.nearest(pool, pts[:, 0], pts[:, 1]).max() > 0.2)
        # "mist": some of this chunk lies where ground mist pools (the level builder lays its mist sheet only on those)
        layout_terrain.append({"mesh": m.name, "pos": list(m.recenter()), "folder": "Terrain/Land", "mist": mist})
    for dk in W.decks:
        m = deck_mesh(W, dk)
        meshes.append(m)
        layout_terrain.append({"mesh": m.name, "pos": list(m.recenter()), "folder": "Terrain/Bridges" if dk.get("kind") != "dais" else "Terrain/Shrine"})
    waters, falls = [], []
    for i, wt in enumerate(W.waters):                           # one sheet per body of water, at its own height
        name = "SM_Water" if i == 0 else "SM_Water_%s_%d" % (wt["name"].title(), i)
        m = Mesh(name)
        g = wt["geom"].buffer(30.0)
        for part in (g.geoms if hasattr(g, "geoms") else [g]):
            T.add_cap(m, part, wt["surface"])
        waters.append({"mesh": name, "pos": list(m.recenter()), "surface": wt["surface"], "name": wt["name"]})
        meshes.append(m)
    for i, f in enumerate(W.falls):
        m = fall_mesh(W, "SM_Waterfall_%d" % i, f)
        falls.append({"mesh": m.name, "pos": list(m.recenter()), "lip": [round(f["lip"][0], 1), round(f["lip"][1], 1), f["top"]], "out": list(f["out"]),
                      "foot": f["foot"], "width": f["width"]})
        meshes.append(m)
    meshes += D.rock_meshes()
    for m in D.unique:
        meshes.append(m)
    meshes += props.build_prop_meshes()

    out_mesh = os.path.join(ROOT, "SourceArt", "Meshes")
    os.makedirs(out_mesh, exist_ok=True)
    count = write_gltf(os.path.join(out_mesh, "battlefield%s.gltf" % sfx), meshes)
    tris = sum(len(m.idx) for m in meshes)

    # ---- textures
    tex = os.path.join(ROOT, "SourceArt", "Textures")
    Image.fromarray(splat).save(os.path.join(tex, "T_Splat%s.png" % sfx))
    Image.fromarray(build_water_map(W, S)).save(os.path.join(tex, "T_WaterMap%s.png" % sfx))
    Image.fromarray(build_flow_map(W, S)).save(os.path.join(tex, "T_WaterFlow%s.png" % sfx))
    Image.fromarray(build_forest_map(W, S, D)).save(os.path.join(tex, "T_Forest%s.png" % sfx))
    write_preview(W, S, splat, D, os.path.join(tex, "T_MinimapBase%s.png" % sfx), minimap=512)

    # ---- layout
    top = float(np.ceil((float(W.H[W.OUT < 0].max()) + 2500.0) / 1000.0) * 1000.0)
    layout = {
        # the map's own numbers: the level builder puts them on the level's ASRMapInfo, which the game reads
        "map": {"id": W.id, "name": W.name, "note": W.note, "half_extent": W.B, "focus_height_max": W.focus_max, "trace_top": top, "trace_bottom": -3000.0,
                "starts": {k: list(v) for k, v in W.starts.items()}, "minimap": "T_MinimapBase%s" % sfx, "splat": "T_Splat%s" % sfx, "water_map": "T_WaterMap%s" % sfx,
                "sym": W.sym, "kingdoms": [{"team": team, "anchor": list(anchor)} for team, anchor, _ in W.tables]},
        "texel_cm": TEXEL, "bound": W.B,
        "splat": {"origin": list(S.origin), "size": S.size},
        "terrain": layout_terrain,
        # water: "mesh" is the rivers' sheet (with the lakes they run into), "extra" the tarns and meres at their own
        # heights; all carry the tag SRWater in the level. "map" is the world square T_WaterMap covers (the splat
        # map's); "flow" the direction the material slides its ripples along.
        "water": {"mesh": waters[0]["mesh"], "pos": waters[0]["pos"], "surface": waters[0]["surface"], "extra": waters[1:], "falls": falls,
                  "map": {"origin": list(S.origin), "size": S.size}, "flow": [W.flow[0], W.flow[1]], "wade": WADE},
        "landmark": W.landmark,
        "instances": D.instances, "actors": D.actors, "blockers": D.blockers, "buildings": placements(W),
        "veins": [[x, y, round(W.z(x, y), 1)] for x, y in W.veins],
        "greens": [[x, y, round(W.z(x, y), 1), r] for x, y, r in W.greens],
        "relics": [[x, y, round(W.z(x, y), 1), name] for x, y, name in W.relics], "old_towers": [[x, y, round(W.z(x, y), 1)] for x, y, name in W.towers],
        "roads": [{"name": r["name"], "kind": r["kind"], "keys": [[round(x, 1), round(y, 1)] for x, y in r["keys"]]} for r in W.roads],
        "crossings": {"fords": [[round(f["geom"].centroid.x, 1), round(f["geom"].centroid.y, 1)] for f in W.fords],
                      "bridges": [{"name": dk["name"], "pos": [round(dk["mid"][0], 1), round(dk["mid"][1], 1)], "z": dk["z"]} for dk in W.decks if dk.get("kind") != "dais"]},
        "relief": W.relief,
        "atmosphere": {"mist": W.mist},
        "starts": {k: list(v) for k, v in W.starts.items()},
    }
    os.makedirs(os.path.join(ROOT, "SourceArt", "World"), exist_ok=True)
    with open(os.path.join(ROOT, "SourceArt", "World", "layout%s.json" % sfx), "w") as f:
        json.dump(layout, f, separators=(",", ":"))
    write_preview(W, S, splat, D, os.path.join(ROOT, "Saved", "WorldPreview", "map%s.png" % sfx))
    print("%s written in %.0f s: meshes %d (%d tris, %d of them the land in %d chunks), instances %d, actors %d, blockers %d" % (
        W.name, time.time() - t0, count, tris, tris_land, len(land), sum(len(v) for v in D.instances.values()), len(D.actors), len(D.blockers)))
    return True


def main():
    which = "two"
    for i, a in enumerate(sys.argv):
        if a == "--map" and i + 1 < len(sys.argv):
            which = sys.argv[i + 1]
        elif a.startswith("--map="):
            which = a[6:]
    ids = list(maps.PLANS) if which == "all" else [which]
    if any(i not in maps.PLANS for i in ids):
        print("--map two | four | all")
        sys.exit(2)
    ok = [generate(i) for i in ids]
    sys.exit(0 if all(ok) else 1)


if __name__ == "__main__":
    main()
