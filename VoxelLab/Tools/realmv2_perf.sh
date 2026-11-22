#!/bin/sh
# Frame times of L_RealmV2 in PIE at three fixed views (the editor open on L_RealmV2, no play session):  sh Tools/realmv2_perf.sh [profile]
#   base      the hero's camera at the player's castle
#   mountain  a free camera south-west of the massif, the whole mountain in view
#   overview  the postcard camera: the whole map
# profile: also a ProfileGPU capture of the mountain view (Tools/gpuprof.py)
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
pie() { python3 "$ROOT/Tools/pie.py" "$@"; }
pie start 8 >/dev/null; pie run "vl.StartMatch 0"; sleep 5
for v in "base|vl.View follow" "mountain|vl.View free -15000 12000 6000 2 -52 70" "overview|vl.View postcard"; do
    pie run "${v#*|}"; sleep 9; pie run "vl.Perf"; sleep 1
    echo "${v%%|*}: $(pie log 'perf:' 1 | sed 's/.*perf: //')"
done
if [ "$1" = "profile" ]; then
    pie run "vl.View free -15000 12000 6000 2 -52 70" "r.ProfileGPU.ShowUI 0"; sleep 3; pie run "ProfileGPU"; sleep 3; python3 "$ROOT/Tools/gpuprof.py"
fi
pie stop >/dev/null
