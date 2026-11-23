<#
Rebuild Realm v3 (L_RealmV3) end to end (the editor open, not in PIE):
  powershell -ExecutionPolicy Bypass -File Tools\windows\realmv3_rebuild.ps1 [layout|blender|import|level]
  (no argument)  the plan + ground + sea + barriers in Blender, import them, the ground's levels of detail, the level
  layout         only the plan changed (things moved; no ground or hazard changed): realmv3.json + the level, no import
  blender        only the Blender part (no editor needed): the meshes and the plan
  import         only the import of what Blender wrote, the levels of detail and the level
  level          only /Game/Maps/L_RealmV3 from the realmv3.json that is there
The balance report (walking distances from each castle, the proof that the passes are the only way) needs scipy: it is
measured with the tools' python first (Tools\.venv\Scripts\python.exe: numpy, scipy, pillow) and kept in realmv3.json by
the Blender run. The counterpart of Tools/mac/realmv3_rebuild.sh.
#>
param([Parameter(Position = 0)][ValidateSet('', 'layout', 'blender', 'import', 'level')][string]$Mode = '')
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\_env.ps1"

$blender = Get-VLBlender
$py = Get-VLPython (Get-VLEngineRoot)
$venv = Join-Path $VLRoot 'Tools\.venv\Scripts\python.exe'
$uePy = Join-Path $VLRoot 'Tools\ue_py.py'
$root = $VLRoot -replace '\\', '/'

function Invoke-Editor([string]$Script, [int]$Seconds) {
    # run a Python file in the open editor; its last line is the report
    & $py $uePy $Script $Seconds | Select-Object -Last 1
}

if ($Mode -in '', 'layout', 'blender') {
    if (Test-Path -LiteralPath $venv) {
        & $venv (Join-Path $VLRoot 'Tools\blender\realmv3_layout.py') --balance | Where-Object { $_ -notmatch '^realmv3:' }
    }
}
if ($Mode -eq 'layout') {
    $log = Join-Path $VLSaved 'build_realmv3_layout.log'
    [void](Invoke-VLLogged $blender @('-b', '--factory-startup', '--python', "`"$(Join-Path $VLRoot 'Tools\blender\realmv3_layout.py')`"") $log)
    Get-Content -LiteralPath $log | Select-String -Pattern '^realmv3|Traceback|Error' | ForEach-Object { Write-Host $_.Line }
}
if ($Mode -in '', 'blender') {
    $log = Join-Path $VLSaved 'build_realmv3_terrain.log'
    [void](Invoke-VLLogged $blender @('-b', '--factory-startup', '--python', "`"$(Join-Path $VLRoot 'Tools\blender\assets\realmv3_terrain.py')`"", '--', '--no-render') $log)
    Get-Content -LiteralPath $log | Select-String -Pattern '^realmv3|^barrier|Traceback|Error' | ForEach-Object { Write-Host $_.Line }
    if ($Mode -eq 'blender') { exit 0 }
}
if ($Mode -in '', 'import') {
    $snippet = Join-Path $VLSaved 'realmv3_import.py'
    @"
import json
ROOT = r'$root'
TILES = json.load(open(ROOT + '/SourceArt/Meshes/realmv3_tiles.json'))
PARTS = ['meshes']; ONLY = TILES + [t + s for t in TILES for s in ('_L1', '_L2')] + ['SM_RealmV3Ramps', 'SM_RealmV3Sea', 'SM_RealmV3Barrier']
exec(open(ROOT + '/Tools/ue/import_assets.py').read())
"@ | Set-Content -LiteralPath $snippet -Encoding ascii
    Invoke-Editor $snippet 5400
    Remove-Item -LiteralPath $snippet -ErrorAction SilentlyContinue
    Invoke-Editor (Join-Path $VLRoot 'Tools\ue\realmv3_lods.py') 3600      # the ground's further levels of detail
}
Invoke-Editor (Join-Path $VLRoot 'Tools\ue\build_realmv3.py') 3600
