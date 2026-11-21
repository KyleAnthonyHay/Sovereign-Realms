#!/usr/bin/env python3
"""Contact sheet of screenshots, for looking at several at once:
    Tools/.venv/bin/python Tools/sheet.py <out name> <shot name> [<shot name> ...]     (names under Saved/Screenshots/SR, no .png)"""
import os, sys
from PIL import Image
D = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "Saved", "Screenshots", "SR")
names = sys.argv[2:]
cols = 2 if len(names) > 1 else 1
rows = (len(names) + cols - 1) // cols
w, h = 960, 574
s = Image.new("RGB", (cols * w, rows * h))
for i, n in enumerate(names):
    s.paste(Image.open(os.path.join(D, n + ".png")).convert("RGB").resize((w, h)), ((i % cols) * w, (i // cols) * h))
s.save(os.path.join(D, sys.argv[1] + ".png"))
