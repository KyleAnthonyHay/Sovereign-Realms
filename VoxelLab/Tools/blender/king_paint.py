"""Paints the owner's King David mesh (References/king.glb: geometry only) from his picture (References/king.png).

    ../Tools/.venv/bin/python Tools/blender/king_paint.py          (numpy + Pillow; not Blender)

1. finds the camera of the picture: the view of the mesh whose outline best covers the figure's outline;
2. gives every face the colour the picture shows on it, flattened to the figure's own handful of colours so the
   picture's light and shadow are not painted in (the engine lights him);
3. faces the picture cannot see (his back, his far side) take the colour of the mirrored face, or of the nearest seen
   face that points a similar way.
Writes Saved/king/colors.npz (per-triangle sRGB) and Saved/king/fit.png (the outline over the picture).
"""
import math
import os

import numpy as np
from PIL import Image, ImageDraw

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
OUT = os.path.join(ROOT, "Saved", "king")
m = np.load(os.path.join(OUT, "mesh.npz"))
V, I = m["V"], m["I"]
ref = Image.open(os.path.join(ROOT, "References", "king.png")).convert("RGB")
W, H = ref.size
R = np.asarray(ref).astype(np.float32)
bg = np.median(np.concatenate([R[:40, :40].reshape(-1, 3), R[:40, -40:].reshape(-1, 3)]), axis=0)
mask_full = (np.abs(R - bg).sum(axis=2) > 60)
mask_full[int(H * 0.93):] = False                      # the floor shadow is not him
ys, xs = np.where(mask_full)
BOX = (xs.min(), ys.min(), xs.max(), ys.max())
S = 4                                                  # the fit works on a quarter-size picture
small = np.asarray(Image.fromarray((mask_full * 255).astype(np.uint8)).resize((W // S, H // S), Image.BILINEAR)) > 127


def basis(az, el):
    a, e = math.radians(az), math.radians(el)
    f = np.array([-math.sin(a) * math.cos(e), math.cos(a) * math.cos(e), -math.sin(e)])
    r = np.array([math.cos(a), math.sin(a), 0.0])
    u = np.cross(r, f)
    return r, u, f


def project(az, el, persp=0.0):
    """Mesh -> picture pixels: the view is scaled and moved so that its box is the figure's box in the picture."""
    r, u, f = basis(az, el)
    c = V - V.mean(axis=0)
    x, y, d = c @ r, c @ u, c @ f
    if persp > 0:                                       # a little perspective: nearer parts larger
        k = 1.0 / (1.0 + d * persp)
        x, y = x * k, y * k
    sx = (BOX[2] - BOX[0]) / (x.max() - x.min())
    sy = (BOX[3] - BOX[1]) / (y.max() - y.min())
    s = (sx + sy) / 2.0
    px = (x - (x.max() + x.min()) / 2.0) * s + (BOX[0] + BOX[2]) / 2.0
    py = -(y - (y.max() + y.min()) / 2.0) * s + (BOX[1] + BOX[3]) / 2.0
    return px, py, d


def outline(px, py, scale=S):
    im = Image.new("L", (W // scale, H // scale), 0)
    dr = ImageDraw.Draw(im)
    P = np.stack([px, py], axis=1) / scale
    for t in I:
        dr.polygon([tuple(P[t[0]]), tuple(P[t[1]]), tuple(P[t[2]])], fill=255)
    return np.asarray(im) > 0


def score(az, el, persp=0.0):
    px, py, _ = project(az, el, persp)
    o = outline(px, py)
    return (o & small).sum() / float((o | small).sum())


best = (0, 0, 0, 0)
for az in range(-60, 31, 10):
    for el in range(-30, 21, 10):
        sc = score(az, el)
        if sc > best[0]:
            best = (sc, az, el, 0.0)
for _ in range(2):
    _, a0, e0, p0 = best
    for az in np.arange(a0 - 8, a0 + 8.1, 4 if _ == 0 else 2):
        for el in np.arange(e0 - 8, e0 + 8.1, 4 if _ == 0 else 2):
            for persp in (0.0, 0.15, 0.3):
                sc = score(az, el, persp)
                if sc > best[0]:
                    best = (sc, float(az), float(el), persp)
print("picture camera: az %.0f, el %.0f, perspective %.2f, outline overlap %.3f" % (best[1], best[2], best[3], best[0]))
px, py, depth = project(best[1], best[2], best[3])

# which face shows at each pixel: draw far faces first
P2 = np.stack([px, py], axis=1)
fd = depth[I].mean(axis=1)
order = np.argsort(-fd)
idim = Image.new("RGB", (W, H), (0, 0, 0))
dr = ImageDraw.Draw(idim)
for k in order:
    t = I[k]
    c = int(k) + 1
    dr.polygon([tuple(P2[t[0]]), tuple(P2[t[1]]), tuple(P2[t[2]])], fill=(c & 255, (c >> 8) & 255, (c >> 16) & 255))
ID = np.asarray(idim).astype(np.int64)
ID = ID[..., 0] + (ID[..., 1] << 8) + (ID[..., 2] << 16)
fit = Image.blend(ref, Image.fromarray(((ID > 0)[..., None] * np.array([255, 60, 200])).astype(np.uint8)), 0.35)
fit.save(os.path.join(OUT, "fit.png"))

# face normals: only faces turned towards the camera count as seen
r, u, f = basis(best[1], best[2])
n = np.cross(V[I[:, 1]] - V[I[:, 0]], V[I[:, 2]] - V[I[:, 0]])
n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
centre = V[I].mean(axis=1)
facing = -(n @ f)
F = len(I)
col = np.zeros((F, 3), np.float32)
seen = np.zeros(F, bool)
flat_id = ID.reshape(-1)
flat_rgb = R.reshape(-1, 3)
flat_ok = mask_full.reshape(-1)
orderpix = np.argsort(flat_id, kind="stable")
ids_sorted = flat_id[orderpix]
starts = np.searchsorted(ids_sorted, np.arange(1, F + 2))
for k in range(F):
    pix = orderpix[starts[k]:starts[k + 1]]
    pix = pix[flat_ok[pix]]
    if len(pix) >= 6 and facing[k] > 0.12:
        col[k] = np.median(flat_rgb[pix], axis=0)
        seen[k] = True
print("faces seen in the picture: %d of %d" % (seen.sum(), F))


def lab(c):
    c = np.asarray(c, np.float32) / 255.0
    L = 0.299 * c[:, 0] + 0.587 * c[:, 1] + 0.114 * c[:, 2]
    return np.stack([L * 0.6, (c[:, 0] - L) * 1.3, (c[:, 2] - L) * 1.3], axis=1)


def hexrgb(h):
    h = h.lstrip("#")
    return [int(h[i:i + 2], 16) for i in (0, 2, 4)]


# ---- the mesh's own pieces -> the parts of the figure (x: his left is +, y: back is +, z up; all as fractions of height)
def components():
    parent = np.arange(len(V))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a
    for t in I:
        a, b, c = find(t[0]), find(t[1]), find(t[2])
        parent[b] = a
        parent[c] = a
    roots = np.array([find(i) for i in range(len(V))])
    return roots[I[:, 0]]


comp = components()
part = np.empty(F, dtype=object)
for rt in np.unique(comp):
    fm = comp == rt
    vv = V[np.unique(I[fm])]
    lo, hi, cnt = vv.min(axis=0), vv.max(axis=0), int(fm.sum())
    cx, cz = (lo[0] + hi[0]) / 2.0, (lo[2] + hi[2]) / 2.0
    if lo[2] > 0.72:
        nm = "Head"
    elif cnt > 2000 and lo[2] < 0.05 and hi[0] - lo[0] > 0.6:
        nm = "Cape"
    elif hi[2] < 0.30 and cnt > 200:
        nm = "LegR" if cx < 0 else "LegL"
    elif cnt > 500 and hi[0] < -0.05 and lo[1] < -0.2:
        nm = "Sword"
    elif 0.30 < cz < 0.56 and abs(cx) > 0.14 and hi[2] < 0.70 and lo[2] > 0.28:
        nm = "ArmR" if cx < 0 else "ArmL"
    else:
        nm = "Body"
    part[fm] = nm

# ---- his colours, read off the picture (lit values), and which of them each part can have
PAL = {"gold": "#f0b020", "gold_dark": "#c8841a", "fur": "#f1dcb0", "fur_shade": "#d6b684", "green": "#5d7a24", "green_dark": "#40591c",
       "armour": "#9c9ca2", "armour_dark": "#5e5e66", "steel": "#e6e6ec", "skin": "#a8602c", "skin_dark": "#7c4622", "hair": "#1f1913",
       "leather": "#6a3c18", "tabard": "#ecd9a8", "white": "#f4f4ee"}
NAMES = list(PAL)
PRGB = np.array([hexrgb(PAL[k]) for k in NAMES], np.float32)
PLAB = lab(PRGB)
ALLOW = {
    "Cape": ["green", "green_dark", "gold", "gold_dark", "tabard"],
    "LegL": ["armour", "armour_dark", "steel", "gold", "gold_dark", "leather"],
    "LegR": ["armour", "armour_dark", "steel", "gold", "gold_dark", "leather"],
    "Sword": ["steel", "armour", "gold", "gold_dark"],
    "ArmL": ["armour", "armour_dark", "skin", "skin_dark", "gold", "gold_dark", "leather"],
    "ArmR": ["armour", "armour_dark", "skin", "skin_dark", "gold", "gold_dark", "leather"],
    "Head": ["skin", "skin_dark", "hair", "gold", "gold_dark", "white"],
    "Body": NAMES,
}
label = -np.ones(F, np.int64)
X = lab(col)
for nm, allowed in ALLOW.items():
    idx = np.where(seen & (part == nm))[0]
    if len(idx) == 0:
        continue
    al = np.array([NAMES.index(a) for a in allowed])
    d = ((X[idx][:, None, :] - PLAB[al][None]) ** 2).sum(axis=2)
    label[idx] = al[d.argmin(axis=1)]

# ---- neighbours (faces sharing an edge)
edge = {}
for fi, t in enumerate(I):
    for a, b in ((t[0], t[1]), (t[1], t[2]), (t[2], t[0])):
        edge.setdefault((min(a, b), max(a, b)), []).append(fi)
nbr = [[] for _ in range(F)]
for fs in edge.values():
    for a in fs:
        for b in fs:
            if a != b:
                nbr[a].append(b)

# smooth the seen labels (a lone wrong face takes its neighbours' colour), then let them spread a few faces into the unseen
for _ in range(2):
    new = label.copy()
    for fi in range(F):
        if label[fi] < 0:
            continue
        votes = [label[fi], label[fi]] + [label[j] for j in nbr[fi] if label[j] >= 0]
        vals, cnts = np.unique(votes, return_counts=True)
        new[fi] = vals[cnts.argmax()]
    label = new
for _ in range(3):
    new = label.copy()
    for fi in range(F):
        if label[fi] >= 0:
            continue
        votes = [label[j] for j in nbr[fi] if label[j] >= 0]
        if votes:
            vals, cnts = np.unique(votes, return_counts=True)
            new[fi] = vals[cnts.argmax()]
    label = new


def rule(fi):
    """The colour of a face the picture cannot see, from where it is on him."""
    x, y, z = centre[fi]
    nm = part[fi]
    if nm == "Cape":
        return "gold" if z < 0.045 else ("green_dark" if n[fi][2] < -0.3 else "green")
    if nm in ("LegL", "LegR"):
        return "leather" if z < 0.02 else "armour"
    if nm == "Sword":
        return "gold" if 0.40 < z < 0.52 else "steel"
    if nm in ("ArmL", "ArmR"):
        return "skin" if z < 0.42 else "armour"
    if nm == "Head":
        if z > 0.93:
            return "gold"
        return "hair" if (y > 0.05 or z < 0.84 or abs(x) > 0.085) else "skin"
    # the torso: fur over the shoulders, armour on the chest, belt, tabard and skirts, cape colour behind
    if z > 0.60 and (abs(x) > 0.10 or y > 0.04):
        return "fur" if n[fi][2] > -0.2 else "fur_shade"
    if y > 0.10:
        return "green_dark"
    if z > 0.47:
        return "armour"
    if z > 0.42:
        return "leather"
    return "tabard" if (abs(x) < 0.07 and y < 0.0) else "green"


for fi in np.where(label < 0)[0]:
    label[fi] = NAMES.index(rule(int(fi)))
# every facet a touch lighter or darker, as the cubes of the picture are
tone = 1.0 + (rng_tone := np.random.default_rng(5)).uniform(-0.055, 0.055, F)
flatcol = PRGB[label] * tone[:, None]
counts = {NAMES[k]: int((label == k).sum()) for k in range(len(NAMES))}
print("faces per colour:", counts)
np.savez(os.path.join(OUT, "colors.npz"), colors=np.clip(flatcol, 0, 255).astype(np.uint8), seen=seen, az=best[1], el=best[2],
         part=np.array([("ArmR" if p_ == "Sword" else p_) for p_ in part]))
print("wrote", os.path.join(OUT, "colors.npz"))
