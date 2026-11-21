#!/bin/sh
# Visual check views for both maps (needs PIE running on that map): Tools/visual_shots.sh <prefix> <two|four>
# Saves Saved/Screenshots/SR/<prefix>_<map>_<view>.png. Same views every time, so before / after can be compared.
P="$(cd "$(dirname "$0")" && pwd)/pie.py"
pre="$1"; map="$2"
python3 "$P" run "sr.Fog 0" >/dev/null
shot() { python3 "$P" shot "${pre}_${map}_$1" $2 $3 $4 | sed 's/.*\///'; }
if [ "$map" = "two" ]; then
  shot kingdom -9900 -9100 0.45
  shot ford -9262 6474 0.4
  shot ford_close -9262 6474 0.08
  shot marsh -5378 5037 0.3
  shot falls 8900 -17900 0.5
  shot mountain 6500 -17000 0.7
  shot crag 10500 -15500 0.35
  shot mere -14639 -562 0.5
  shot shrine 0 0 0.45
  shot out 0 0 1.0
else
  shot kingdom -22300 -22400 0.45
  shot ford -12202 -534 0.4
  shot ford_close -12202 -534 0.05
  shot falls -6700 0 0.5
  shot moor 0 0 0.6
  shot mere -27593 -3894 0.5
  shot bridge -21536 -2625 0.4
  shot out 0 0 1.0
fi
