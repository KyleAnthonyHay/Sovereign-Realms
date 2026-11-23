<#
Record a motion preview in a running PIE session (see README, "Motion previews"):
  powershell -ExecutionPolicy Bypass -File Tools\windows\rec.ps1 <name> <frames> "<frame> <console command>" ...
The frames (30 a second of game time, whatever the real frame rate) land in Saved\Screenshots\VL\<name>_NNN.png;
each "<frame> <command>" runs when the recording reaches that frame. Waits until the last frame is written.
The counterpart of Tools/mac/rec.sh.
#>
param(
    [Parameter(Mandatory = $true, Position = 0)][string]$Name,
    [Parameter(Mandatory = $true, Position = 1)][int]$Frames,
    [Parameter(Position = 2, ValueFromRemainingArguments = $true)][string[]]$At = @()
)
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\_env.ps1"

$shots = Join-Path $VLSaved 'Screenshots\VL'
Remove-Item -Path (Join-Path $shots ($Name + '_[0-9][0-9][0-9].png')) -ErrorAction SilentlyContinue
$lines = @()
foreach ($c in $At) { $lines += "vl.At $c" }
$lines += "vl.Record $Name $Frames"
# the game polls Saved\VLCommands.txt: write beside it, then move it into place in one step (no byte-order mark)
$tmp = Join-Path $VLSaved 'VLCommands.txt.tmp'
[System.IO.File]::WriteAllText($tmp, (($lines -join "`n") + "`n"), (New-Object System.Text.UTF8Encoding($false)))
Move-Item -LiteralPath $tmp -Destination (Join-Path $VLSaved 'VLCommands.txt') -Force
$last = Join-Path $shots ('{0}_{1:000}.png' -f $Name, ($Frames - 1))
$i = 0
while (-not (Test-Path -LiteralPath $last) -and $i -lt 600) { $i++; Start-Sleep -Milliseconds 200 }
Start-Sleep -Milliseconds 400
if (Test-Path -LiteralPath $last) { Write-Host "recorded $Name ($Frames frames)" } else { Write-Host "recording $Name did not finish" }
