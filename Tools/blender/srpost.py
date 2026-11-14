"""Sprite-cell stylisation: lighting value -> curated ramps, cleanup, outline, team mask, normal map.

Plain Python (numpy + pillow). Input cells come from render_sprites.py / srrender.reduce_cell.
"""

import numpy as np

import srmats

EMPTY = 255
NMAT = len(srmats.MATERIALS)
RAMPS = [np.array([srmats.hex_to_rgb(h) for h in m["ramp"]], dtype=np.uint8) for m in srmats.MATERIALS]
NB = np.array([len(r) for r in RAMPS])
IS_TEAM = np.array([m["team"] for m in srmats.MATERIALS])
IS_ACCENT = np.array([m["accent"] for m in srmats.MATERIALS])
IS_THIN = np.array([m["thin"] or m["fx"] for m in srmats.MATERIALS])    # no outline / interior lines
GAIN = np.array([m["gain"] for m in srmats.MATERIALS], dtype=np.float32)
BIAS = np.array([m["bias"] for m in srmats.MATERIALS], dtype=np.float32)
SPEC_K = np.array([m["spec"][0] for m in srmats.MATERIALS], dtype=np.float32)
SPEC_N = np.array([m["spec"][1] for m in srmats.MATERIALS], dtype=np.float32)
OUTLINE = np.array(srmats.hex_to_rgb(srmats.OUTLINE), dtype=np.uint8)
OUTLINE_TEAM = np.array(srmats.hex_to_rgb(srmats.OUTLINE_TEAM_GREY), dtype=np.uint8)

OPTS = dict(
    lo=0.34, hi=1.10,        # lighting value (gamma space) mapped to 0..1 across the ramp
    ao=0.75,                 # how much the AO pass darkens
    curve=1.2,               # >1 pushes more pixels into the dark bands
    depth_edge_cm=5.0,       # interior line where the surface behind is at least this much further away
    outline=True,
)


def _nb4(a, fill):
    """The four neighbours of every pixel (up, down, left, right), padded with fill."""
    p = np.pad(a, [(1, 1), (1, 1)] + [(0, 0)] * (a.ndim - 2), constant_values=fill)
    return p[:-2, 1:-1], p[2:, 1:-1], p[1:-1, :-2], p[1:-1, 2:]


def _nb8(a, fill):
    p = np.pad(a, [(1, 1), (1, 1)] + [(0, 0)] * (a.ndim - 2), constant_values=fill)
    h, w = a.shape[:2]
    return [p[1 + dy:1 + dy + h, 1 + dx:1 + dx + w] for dy in (-1, 0, 1) for dx in (-1, 0, 1) if (dy, dx) != (0, 0)]


def shade_value(cell, key_dir, o=OPTS):
    ident = cell["id"]
    safe = np.where(ident == EMPTY, 0, ident)
    L = cell["L"].astype(np.float32)
    ao = np.clip(cell["ao"].astype(np.float32), 0, 1)
    n = cell["n"].astype(np.float32)
    v = np.power(np.clip(L, 0, 4), 1 / 2.2) * (1 - o["ao"] * (1 - ao))
    v = (v - o["lo"]) / (o["hi"] - o["lo"])
    h = np.array(key_dir, dtype=np.float32) + np.array([0, 0, 1], dtype=np.float32)
    h /= np.linalg.norm(h)
    lit = np.clip((v - 0.35) / 0.3, 0, 1)
    spec = SPEC_K[safe] * np.power(np.clip(n @ h, 0, 1), SPEC_N[safe]) * lit
    v = (v - 0.5) * GAIN[safe] + 0.5 + BIAS[safe] + spec
    v = np.clip(v, 0, 0.9999)
    if o["curve"] != 1.0:
        v = np.power(v, o["curve"])
    return v


def stylise(cell, key_dir, cm_per_px, o=OPTS):
    """Returns rgba (h, w, 4) uint8, team mask (h, w) uint8, normal map (h, w, 3) uint8."""
    ident = cell["id"].copy()
    h, w = ident.shape
    v = shade_value(cell, key_dir, o)
    z = cell["z"].astype(np.float32)

    # --- orphan material pixels: a pixel with no 8-neighbour of its own material takes its commonest neighbour
    nb = _nb8(ident, EMPTY)
    same = np.zeros(ident.shape, bool)
    for q in nb:
        same |= q == ident
    lone = (ident != EMPTY) & ~same & ~IS_ACCENT[np.where(ident == EMPTY, 0, ident)]
    if lone.any():
        stack = np.stack(nb, -1)
        for y, x in zip(*np.nonzero(lone)):
            vals = stack[y, x]
            vals = vals[vals != EMPTY]
            if len(vals):
                ident[y, x] = np.bincount(vals).argmax()
            else:
                ident[y, x] = EMPTY
    solid = ident != EMPTY
    safe = np.where(solid, ident, 0)

    band = np.minimum((v * NB[safe]).astype(np.int32), NB[safe] - 1)

    # --- orphan shade pixels: a band value none of the same-material 4-neighbours share -> nearest of theirs
    for _ in range(2):
        nbi = _nb4(ident, EMPTY)
        nbb = _nb4(band, -1)
        has_same = np.zeros(ident.shape, bool)
        support = np.zeros(ident.shape, bool)
        for qi, qb in zip(nbi, nbb):
            m = qi == ident
            has_same |= m
            support |= m & (qb == band)
        fix = solid & has_same & ~support
        if not fix.any():
            break
        best = band.copy()
        bestd = np.full(ident.shape, 99)
        for qi, qb in zip(nbi, nbb):
            d = np.where(qi == ident, np.abs(qb - band), 99)
            take = d < bestd
            best = np.where(take, qb, best)
            bestd = np.where(take, d, bestd)
        band = np.where(fix, best, band)

    # --- interior lines: where the neighbour to the right / below / left / above is much nearer, darken
    zc = np.where(solid, z, 1e4)
    edge = np.zeros(ident.shape, bool)
    thr = o["depth_edge_cm"] / 100.0
    for q in _nb4(zc, 1e4):
        edge |= (zc - q) > thr
    edge &= solid & ~IS_THIN[safe]
    band = np.where(edge, np.maximum(band - 2, 0), band)

    rgb = np.zeros((h, w, 3), np.uint8)
    for k in range(NMAT):
        m = solid & (ident == k)
        if m.any():
            rgb[m] = RAMPS[k][band[m]]
    alpha = solid.copy()
    mask = (solid & IS_TEAM[safe])

    # --- silhouette outline, one pixel outside the shape, coloured from the pixel it hugs
    if o["outline"]:
        grow = np.zeros(ident.shape, bool)
        team_n = np.zeros(ident.shape, bool)
        nbs = _nb4(solid, False)
        nbt = _nb4(mask, False)
        nbthin = _nb4(solid & IS_THIN[safe], False)
        only_thin = np.ones(ident.shape, bool)
        for q, t, th in zip(nbs, nbt, nbthin):
            grow |= q
            team_n |= t
            only_thin &= (~q) | th
        ring = grow & ~solid & ~only_thin
        rgb[ring] = OUTLINE
        ring_team = ring & team_n
        rgb[ring_team] = OUTLINE_TEAM
        alpha |= ring
        mask |= ring_team

    rgba = np.dstack([rgb, np.where(alpha, 255, 0).astype(np.uint8)])

    # --- normal map (R = +x right, G = +y DOWN for Unreal / DirectX, B = toward camera); outline takes its neighbour's
    n = cell["n"].astype(np.float32).copy()
    n[~solid] = 0
    if o["outline"]:
        acc = np.zeros_like(n)
        for q in _nb4(n, 0.0):
            acc += q
        ln = np.linalg.norm(acc, axis=-1, keepdims=True)
        fill = np.where(ln > 1e-4, acc / np.maximum(ln, 1e-4), np.array([0, 0, 1], np.float32))
        n = np.where((alpha & ~solid)[..., None], fill, n)
    n[~alpha] = (0, 0, 1)
    nm = np.stack([n[..., 0], -n[..., 1], n[..., 2]], -1)
    nm = np.clip(np.rint((nm * 0.5 + 0.5) * 255), 0, 255).astype(np.uint8)
    return rgba, np.where(mask, 255, 0).astype(np.uint8), nm


TEAMS = {"blue": (0.05, 0.22, 0.80), "red": (0.72, 0.07, 0.05)}


def _lin(c):
    c = c.astype(np.float32) / 255.0
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def _srgb(c):
    c = np.clip(c, 0, 1)
    return np.rint(np.where(c <= 0.0031308, c * 12.92, 1.055 * c ** (1 / 2.4) - 0.055) * 255).astype(np.uint8)


def tint(rgba, mask, team):
    """The in-game team formula: rgb = lerp(color, color * TeamColor * 2, mask) in linear space."""
    tc = np.array(TEAMS[team] if isinstance(team, str) else team, dtype=np.float32)
    lin = _lin(rgba[..., :3])
    m = (mask.astype(np.float32) / 255.0)[..., None]
    out = lin * (1 - m) + lin * tc * 2.0 * m
    return np.dstack([_srgb(out), rgba[..., 3]])
