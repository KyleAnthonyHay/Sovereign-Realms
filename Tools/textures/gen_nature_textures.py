#!/usr/bin/env python3
"""Tileable procedural textures for the water (no outside source: made here).

  Tools/.venv/bin/python Tools/textures/gen_nature_textures.py
  -> SourceArt/Textures/Nature/T_N_WaterWaves_N.png   512: ripple normals (tangent space, +Y down like Unreal's)
     SourceArt/Textures/Nature/T_N_WaterNoise.png     512: R = foam breakup (cellular), G = soft cloud noise,
                                                           B = fine grain, A = streaks (drawn out along +X: white water)
Imported by Tools/import_world_assets.py (import_nature) to /Game/SR/Textures/Nature.
"""
import os
import numpy as np
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(ROOT, "SourceArt", "Textures", "Nature")
N = 512


def spectral(seed, lo, hi, power=1.0, stretch=(1.0, 1.0)):
    """Tileable noise: random phases, energy between `lo` and `hi` cycles across the tile."""
    r = np.random.default_rng(seed)
    fx, fy = np.meshgrid(np.fft.fftfreq(N) * N, np.fft.fftfreq(N) * N)
    f = np.hypot(fx * stretch[0], fy * stretch[1])
    amp = np.where((f >= lo) & (f <= hi), 1.0 / np.maximum(f, 1.0) ** power, 0.0)
    spec = amp * np.exp(2j * np.pi * r.random((N, N)))
    a = np.real(np.fft.ifft2(spec))
    return (a - a.min()) / (a.max() - a.min())


def worley(seed, cells):
    r = np.random.default_rng(seed)
    pts = (np.stack(np.meshgrid(np.arange(cells), np.arange(cells)), -1).reshape(-1, 2) + r.random((cells * cells, 2))) / cells
    y, x = np.meshgrid(np.arange(N) / N, np.arange(N) / N, indexing="ij")
    d = np.full((N, N), 9.0)
    for px, py in pts:
        dx, dy = np.abs(x - px), np.abs(y - py)
        d = np.minimum(d, np.hypot(np.minimum(dx, 1 - dx), np.minimum(dy, 1 - dy)))
    return np.clip(d * cells, 0, 1)


def main():
    os.makedirs(OUT, exist_ok=True)
    # ripples: mostly short crests, a little long swell; sharpened so crests are narrower than troughs
    h = spectral(1, 5, 60, 1.25) * 0.75 + spectral(2, 2, 9, 1.0) * 0.25
    h = 1.0 - np.abs(h * 2.0 - 1.0) ** 0.8 * 0.6 - (1.0 - h) * 0.4
    gy, gx = np.gradient(np.pad(h, 1, mode="wrap"))
    gx, gy = gx[1:-1, 1:-1] * 26.0, gy[1:-1, 1:-1] * 26.0
    n = np.dstack([-gx, -gy, np.ones_like(gx)])
    n /= np.linalg.norm(n, axis=2, keepdims=True)
    Image.fromarray(((n * 0.5 + 0.5) * 255 + 0.5).astype(np.uint8)).save(os.path.join(OUT, "T_N_WaterWaves_N.png"))
    foam = 1.0 - worley(3, 9) * 0.7 - worley(4, 23) * 0.3
    cloud = spectral(5, 1, 12, 1.6)
    grain = spectral(6, 30, 200, 0.3)
    streak = spectral(7, 2, 120, 0.9, stretch=(6.0, 1.0))
    img = np.dstack([foam, cloud, grain, streak])
    Image.fromarray((np.clip(img, 0, 1) * 255 + 0.5).astype(np.uint8)).save(os.path.join(OUT, "T_N_WaterNoise.png"))
    print("wrote", OUT)


if __name__ == "__main__":
    main()
