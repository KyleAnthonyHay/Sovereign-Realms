<#
Frame times of L_RealmV2 in PIE at three fixed views (the editor open on L_RealmV2, no play session):
  powershell -ExecutionPolicy Bypass -File Tools\windows\realmv2_perf.ps1 [profile]
  base      the hero's camera at the player's castle
  mountain  a free camera south-west of the massif, the whole mountain in view
  overview  the postcard camera: the whole map
profile: also a ProfileGPU capture of the mountain view (Tools/gpuprof.py)
The editor idles at 3 fps while its window is not the one in front; an editor started by editor.ps1 has that
switched off (see there), one opened by hand must be in front, or the figures are 3 fps.
The counterpart of Tools/mac/realmv2_perf.sh (the same views and waits, so the numbers compare).
#>
param([Parameter(Position = 0)][string]$Mode = '')
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\_env.ps1"

$py = Get-VLPython (Get-VLEngineRoot)
$piePy = Join-Path $VLRoot 'Tools\pie.py'
function Invoke-Pie { & $py $piePy @args }

Invoke-Pie start 8 | Out-Null
Invoke-Pie run 'vl.StartMatch 0'
Start-Sleep -Seconds 5
$views = @(
    @('base', 'vl.View follow'),
    @('mountain', 'vl.View free -15000 12000 6000 2 -52 70'),
    @('overview', 'vl.View postcard')
)
foreach ($v in $views) {
    Invoke-Pie run $v[1]
    Start-Sleep -Seconds 9
    Invoke-Pie run 'vl.Perf'
    Start-Sleep -Seconds 1
    $line = (Invoke-Pie log 'perf:' 1 | Select-Object -Last 1)
    Write-Host ('{0}: {1}' -f $v[0], ($line -replace '.*perf: ', ''))
}
if ($Mode -eq 'profile') {
    Invoke-Pie run 'vl.View free -15000 12000 6000 2 -52 70' 'r.ProfileGPU.ShowUI 0'
    Start-Sleep -Seconds 3
    Invoke-Pie run 'ProfileGPU'
    Start-Sleep -Seconds 3
    & $py (Join-Path $VLRoot 'Tools\gpuprof.py')
}
Invoke-Pie stop | Out-Null
