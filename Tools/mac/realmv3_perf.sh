#!/bin/sh
# Frame times of L_RealmV3 in PIE at three fixed views (the editor open on L_RealmV3, no play session):  sh Tools/mac/realmv3_perf.sh [profile]
#   base      the hero's camera at the player's castle
#   pass      a free camera over plateau A's rim: the ramp, the pass, the north-west crest and the basin behind it
#   overview  the postcard camera: the whole map
# profile: also a ProfileGPU capture of the pass view (Tools/gpuprof.py)
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
pie() { python3 "$ROOT/Tools/pie.py" "$@"; }
pie start 8 >/dev/null; pie run "vl.StartMatch 0"; sleep 5
for v in "base|vl.View follow" "pass|vl.View free -12600 -6600 4600 -16 28 70" "overview|vl.View postcard"; do
    pie run "${v#*|}"; sleep 9; pie run "vl.Perf"; sleep 1
    echo "${v%%|*}: $(pie log 'perf:' 1 | sed 's/.*perf: //')"
done
if [ "$1" = "profile" ]; then
    pie run "vl.View free -12600 -6600 4600 -16 28 70" "r.ProfileGPU.ShowUI 0"; sleep 3; pie run "ProfileGPU"; sleep 3; python3 "$ROOT/Tools/gpuprof.py"
fi
pie stop >/dev/null
