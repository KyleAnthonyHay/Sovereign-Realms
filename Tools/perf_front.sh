#!/bin/sh
# Frame-time samples with the editor frontmost (PIE is paced down to 30-40 fps whenever another application is in front,
# and the GPU time it then reports does not follow the scene). Needs PIE running. Brings the editor to the front,
# samples each view, and gives the front back to whatever had it.
#   Tools/perf_front.sh "X Y Zoom" ["X Y Zoom" ...]
P="$(cd "$(dirname "$0")" && pwd)/pie.py"
prev="$(osascript -e 'tell application "System Events" to get name of first application process whose frontmost is true' 2>/dev/null)"
osascript -e 'tell application "UnrealEditor" to activate' >/dev/null 2>&1
sleep 3
for v in "$@"; do
  python3 "$P" run "sr.Camera $v" >/dev/null; sleep 3
  python3 "$P" run "sr.Perf 5" >/dev/null; sleep 7
  echo "$v: $(python3 "$P" log PERF 1 | sed 's/^LogSovereign: //')"
done
[ -n "$prev" ] && osascript -e "tell application \"$prev\" to activate" >/dev/null 2>&1
