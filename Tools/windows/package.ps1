<#
Package a standalone Windows build:  powershell -ExecutionPolicy Bypass -File Tools\windows\package.ps1 [Shipping|Development]
(or double-click Tools\windows\Package.bat). Result: Builds\Windows\SovereignRealms\SovereignRealms.exe
(Development: Builds\Windows\SovereignRealms-Development\, so that the two builds stay side by side).
  Shipping (the default)   the build to play: no console, no log, no test hooks (the command inbox Saved\VLCommands.txt
                           and vl.Record are compiled out), no debug files
  Development              for tests: the ~ console, the log, the command inbox; bigger
The same steps as Tools/mac/package.sh: build + cook + stage + pak, the log in Saved\package.log, then the staged
folder copied to Builds\Windows. Nothing for debugging stays in that folder: the .pdb files are moved
beside it, to Builds\Windows\Symbols\<config> (keep them: a crash dump of this build is read with them), and the staging
manifests are dropped. Only Direct3D 12 / SM6 shaders are cooked (Config\Windows\WindowsEngine.ini).
-NoPrereqs leaves out the installer of the Visual C++ runtime that the folder otherwise carries
(Engine\Extras\Redist: about 40 MB; without it the game needs that runtime on the machine already).
The engine: $env:UE_ROOT, else the installed 5.8, else the newest UE_5.* (Tools\windows\_env.ps1).
Close the editor first (the game and the editor fight over the audio device otherwise).
#>
param(
    [Parameter(Position = 0)][ValidateSet('Shipping', 'Development')][string]$Config = 'Shipping',
    [switch]$NoPrereqs
)
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\_env.ps1"

$UE = Get-VLEngineRoot
[void](Test-VLEngineMatches $UE)
$Log = Join-Path $VLSaved 'package.log'
New-Item -ItemType Directory -Force -Path $VLSaved | Out-Null

$uatArgs = @('BuildCookRun', "-project=`"$VLProject`"", '-platform=Win64', "-clientconfig=$Config",
    '-build', '-cook', '-stage', '-pak', '-noP4', '-utf8output', '-unattended')
if ($Config -eq 'Shipping') { $uatArgs += '-nodebuginfo' }
if (-not $NoPrereqs) { $uatArgs += '-prereqs' }

Write-Host "packaging $Config with $UE (the log: Saved\package.log) ..."
$started = Get-Date
$code = Invoke-VLLogged (Join-Path $UE 'Engine\Build\BatchFiles\RunUAT.bat') $uatArgs $Log
if ($code -ne 0) { Write-Host "packaging failed (exit code $code): see Saved\package.log"; exit 1 }

$Staged = Join-Path $VLSaved 'StagedBuilds\Windows'
if (-not (Test-Path -LiteralPath (Join-Path $Staged 'SovereignRealms.exe'))) {
    Write-Host "packaging failed: no staged game at $Staged (see Saved\package.log)"; exit 1
}
$Out = Join-Path $VLRoot 'Builds\Windows'
$AppName = 'SovereignRealms'
if ($Config -ne 'Shipping') { $AppName = "SovereignRealms-$Config" }
$App = Join-Path $Out $AppName
New-Item -ItemType Directory -Force -Path $Out | Out-Null
# a mirror of the staged folder (robocopy: exit codes below 8 are success); a Development build's own Saved folder
# (its log, settings, captures) is left alone
& robocopy $Staged $App /MIR /XD (Join-Path $App 'SovereignRealms\Saved') /NFL /NDL /NJH /NJS /NP /R:2 /W:2 | Out-Null
if ($LASTEXITCODE -ge 8) { Write-Host "packaging failed: could not copy $Staged to $App (robocopy $LASTEXITCODE)"; exit 1 }

# no debug files in the game's folder: the symbols beside it, the staging manifests gone
$Symbols = Join-Path $Out "Symbols\$Config"
$pdbs = @(Get-ChildItem -LiteralPath $App -Recurse -File -Filter '*.pdb')
if ($pdbs.Count -gt 0) {
    New-Item -ItemType Directory -Force -Path $Symbols | Out-Null
    foreach ($f in $pdbs) { Move-Item -LiteralPath $f.FullName -Destination (Join-Path $Symbols $f.Name) -Force }
}
Get-ChildItem -LiteralPath $App -File -Filter 'Manifest_*.txt' | Remove-Item -Force
# (-nodebuginfo stages no .pdb at all: the one the build left in Binaries\Win64 is this executable's)
$builtName = 'SovereignRealms.pdb'
if ($Config -eq 'Shipping') { $builtName = 'SovereignRealms-Win64-Shipping.pdb' }
$built = Join-Path $VLRoot "Binaries\Win64\$builtName"
if ($pdbs.Count -eq 0 -and (Test-Path -LiteralPath $built)) {
    New-Item -ItemType Directory -Force -Path $Symbols | Out-Null
    Copy-Item -LiteralPath $built -Destination (Join-Path $Symbols $builtName) -Force
    $pdbs = @(Get-Item -LiteralPath $built)
}

$size = (Get-ChildItem -LiteralPath $App -Recurse -File | Measure-Object -Property Length -Sum).Sum
$minutes = [int]((Get-Date) - $started).TotalMinutes
Write-Host ("built: {0} ({1}, {2}, engine {3}, {4} min)" -f (Join-Path $App 'SovereignRealms.exe'), $Config, (Format-VLSize $size), (Get-VLEngineVersion $UE), $minutes)
if ($pdbs.Count -gt 0) { Write-Host ("symbols: {0} ({1} files)" -f $Symbols, $pdbs.Count) }
exit 0
