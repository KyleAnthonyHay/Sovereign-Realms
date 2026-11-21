"""Calibration mesh for the importer: 3 m along +X (stone), 2 m along +Y (plank), 1 m up (roof); grey steps 0.25 0.5 0.75."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import voxlib as V
from voxlib import Vox
V.reset_scene()
v = Vox(24, 16, 8, 0.125, origin=(0, 0, 0))
v.box(0, 0, 0, 24, 2, 2, "stone")
v.box(0, 0, 0, 2, 16, 2, "plank")
v.box(0, 0, 0, 2, 2, 8, "roof")
for i, g in enumerate((64, 128, 191)):
    v.box(8 + i * 4, 8, 0, 11 + i * 4, 11, 3, "paint", (g, g, g))
v.box(20, 12, 0, 22, 14, 4, "glow", "lantern")
ob = v.to_object("SM_AxisTest")
V.export_gltf(ob)
