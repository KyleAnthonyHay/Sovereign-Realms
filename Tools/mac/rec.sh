#!/bin/sh
# Record a motion preview in a running PIE session (see README, "Motion previews"):
#   Tools/mac/rec.sh <name> <frames> "<frame> <console command>" ...
# The frames (30 a second of game time, whatever the real frame rate) land in Saved/Screenshots/VL/<name>_NNN.png;
# each "<frame> <command>" runs when the recording reaches that frame. Waits until the last frame is written.
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
NAME="$1"; FRAMES="$2"; shift 2
rm -f "$ROOT/Saved/Screenshots/VL/${NAME}"_[0-9][0-9][0-9].png
set -- "$@"
ARGS=""
TMP="$ROOT/Saved/VLCommands.txt.tmp"
: > "$TMP"
for C in "$@"; do echo "vl.At $C" >> "$TMP"; done
echo "vl.Record $NAME $FRAMES" >> "$TMP"
mv "$TMP" "$ROOT/Saved/VLCommands.txt"
LAST=$(printf "%s/Saved/Screenshots/VL/%s_%03d.png" "$ROOT" "$NAME" $((FRAMES - 1)))
i=0
while [ ! -f "$LAST" ] && [ $i -lt 600 ]; do i=$((i + 1)); sleep 0.2; done
sleep 0.4
[ -f "$LAST" ] && echo "recorded $NAME ($FRAMES frames)" || echo "recording $NAME did not finish"
