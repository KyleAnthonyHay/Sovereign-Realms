#!/bin/sh
# Editor lifecycle for scripted work on macOS (Live Coding does not work there).
#   Tools/editor.sh quit      save nothing, quit, wait until the process and the MCP port are gone
#   Tools/editor.sh build     build SovereignRealmsEditor (editor must be closed)
#   Tools/editor.sh start     launch on the project and wait for the MCP server (port 8000)
#   Tools/editor.sh rebuild   quit + build + start
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
UE="${UE_ROOT:-/Users/Shared/Epic Games/UnrealInstall/UE_5.8}"
running() { pgrep -f "UnrealEditor.app/Contents/MacOS/UnrealEditor" >/dev/null; }
listening() { lsof -nP -iTCP:8000 -sTCP:LISTEN >/dev/null 2>&1; }
quit() {
    running && osascript -e 'quit app "UnrealEditor"' >/dev/null 2>&1
    i=0
    while running || listening; do
        i=$((i + 1))
        [ $i -eq 40 ] && pkill -f "UnrealEditor.app/Contents/MacOS/UnrealEditor"
        [ $i -gt 45 ] && pkill -f CrashReportClient
        [ $i -gt 90 ] && { echo "editor did not quit"; return 1; }
        sleep 1
    done
    echo "editor closed"
}
build() {
    "$UE/Engine/Build/BatchFiles/Mac/Build.sh" SovereignRealmsEditor Mac Development -Project="$ROOT/SovereignRealms.uproject" -WaitMutex 2>&1 \
        | grep -E "error|warning: |Result:|Total execution|Undefined symbols|ld:" | grep -v "^$" | tail -40
}
start() {
    open -a "$UE/Engine/Binaries/Mac/UnrealEditor.app" --args "$ROOT/SovereignRealms.uproject"
    i=0
    until listening; do
        i=$((i + 1)); [ $i -gt 240 ] && { echo "editor did not start"; return 1; }
        sleep 1
    done
    # the port opens before the editor ticks: wait until the Python bridge (Content/Python/init_unreal.py) answers
    j=0
    until python3 "$ROOT/Tools/ue_py.py" -c "print('ok')" 15 >/dev/null 2>&1; do
        rm -f "$ROOT"/Saved/PyInbox/*.py 2>/dev/null
        j=$((j + 1)); [ $j -gt 30 ] && { echo "bridge did not answer"; return 1; }
    done
    echo "editor up (port after ${i}s, bridge after $((j * 15))s more)"
}
case "$1" in
    quit) quit ;;
    build) build ;;
    start) start ;;
    rebuild) quit && build && start ;;
    *) sed -n 2,7p "$0" ;;
esac
