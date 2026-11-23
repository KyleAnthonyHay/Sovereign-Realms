#!/usr/bin/env python3
"""Summarise the last ProfileGPU capture in the editor log: the passes over 0.6 ms, indented by depth.
   python3 Tools/pie.py run "r.ProfileGPU.ShowUI 0" "ProfileGPU"; python3 Tools/gpuprof.py"""
import os, re
L = os.path.expanduser("~/Library/Logs/Unreal Engine/SovereignRealmsEditor/SovereignRealms.log")
lines = open(L, errors="replace").read().split("\n")
idx = [i for i, l in enumerate(lines) if "LogRHI: Display:" in l and "┃" in l]
end = idx[-1]; s = set(idx[-4000:]); start = end
while start - 1 in s:
    start -= 1
rows = []
for l in lines[start:end + 1]:
    parts = l.split("┃")
    if len(parts) < 4:
        continue
    m = re.findall(r"([\d.]+) ms", parts[2]); name = parts[3]; ind = len(name) - len(name.lstrip())
    if m:
        rows.append((float(m[-1]), ind, name.strip()))
inds = sorted(set(r[1] for r in rows))
for inc, ind, name in rows:
    lvl = inds.index(ind)
    if inc >= 0.6 and lvl <= 7:
        print("%6.2f %s%s" % (inc, "  " * lvl, name[:64]))
