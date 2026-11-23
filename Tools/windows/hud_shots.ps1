<#
Screenshots of the interface of the packaged Development build at a list of window sizes and display modes, and a
stress run of the display settings:
  powershell -ExecutionPolicy Bypass -File Tools\windows\hud_shots.ps1 [-Sizes 1920x1080,1440x1080,...] [-Title] [-Stress 12]
      [-Default] [-Out Saved\HUDShots]
Needs Builds\Windows\SovereignRealms-Development from `package.ps1 Development` (the command inbox Saved\VLCommands.txt
is a Development build's). What it does:
  -Sizes   for each "WxH" (a window) or "WxHwf" (borderless full screen) or "WxHf" (exclusive full screen): the Test
           World on L_RealmV2 with the player's castle selected, a barracks, a platoon, then the pause menu, Settings,
           Controls and New Game; each saved WITH the interface (vl.Shot <name> ui) as <Out>\<size>_<what>.png
  -Title   the same sizes on the title screen: the main menu, Settings, New Game, Controls
  -Stress  N rounds, in a match and then on the title screen, of real clicks on Settings' rows (the buttons' places are
           read from vl.HUD): Display mode (Windowed -> Borderless -> Full screen, kept or let go back), Resolution up and
           down, VSync, Quality, Render scale. The game must still be running at the end.
  -Default starts the game with no arguments at all, as a double click does, and reports the mode it came up in.
The player's own settings (the build's Saved\Config\Windows\GameUserSettings.ini) are put back when the script ends.
Plain ASCII on purpose (Windows PowerShell 5.1 reads a script without a byte-order mark as ANSI).
#>
param(
    [string[]]$Sizes = @(),
    [switch]$Title,
    [int]$Stress = 0,
    [switch]$Default,
    [string]$Map = 'L_RealmV2',
    [string]$Out = ''
)
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\_env.ps1"

$App = Join-Path $VLRoot 'Builds\Windows\SovereignRealms-Development'
$Exe = Join-Path $App 'SovereignRealms\Binaries\Win64\SovereignRealms.exe'
if (-not (Test-Path -LiteralPath $Exe)) { Write-Host "no Development build at $Exe : run Tools\windows\package.ps1 Development first"; exit 1 }
if (@(Get-Process -Name 'SovereignRealms' -ErrorAction SilentlyContinue).Count -gt 0) { Write-Host 'the game is running: close it first'; exit 1 }
$GameSaved = Join-Path $App 'SovereignRealms\Saved'
$Log = Join-Path $GameSaved 'Logs\SovereignRealms.log'
$Inbox = Join-Path $GameSaved 'VLCommands.txt'
$Shots = Join-Path $GameSaved 'Screenshots\VL'
$Settings = Join-Path $GameSaved 'Config\Windows\GameUserSettings.ini'
if (-not $Out) { $Out = Join-Path $VLSaved 'HUDShots' }
New-Item -ItemType Directory -Force -Path $Out, $GameSaved | Out-Null
$Sizes = @($Sizes | ForEach-Object { $_.Split(',') } | Where-Object { $_.Trim() } | ForEach-Object { $_.Trim() })

function Send-Commands([string[]]$Lines) {
    $tmp = "$Inbox.tmp"
    [System.IO.File]::WriteAllText($tmp, (($Lines -join "`n") + "`n"), (New-Object System.Text.UTF8Encoding($false)))
    Move-Item -LiteralPath $tmp -Destination $Inbox -Force
    $i = 0
    function Test-Inbox { try { return (Test-Path -LiteralPath $Inbox -ErrorAction Stop) } catch { return $true } }
    while ((Test-Inbox) -and $i -lt 300) {
        if ($script:Game.HasExited) { throw "the game exited (code $($script:Game.ExitCode)): see $Log" }
        $i++; Start-Sleep -Milliseconds 100
    }
    if (Test-Inbox) { throw 'the game did not take the commands (is it a Development build?)' }
}
function Read-Log {
    $fs = New-Object System.IO.FileStream($Log, [System.IO.FileMode]::Open, [System.IO.FileAccess]::Read, [System.IO.FileShare]::ReadWrite)
    try { return (New-Object System.IO.StreamReader($fs, [System.Text.Encoding]::UTF8)).ReadToEnd() } finally { $fs.Close() }
}
function Wait-Log([string]$Pattern, [int]$TimeoutSeconds) {
    $end = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $end) {
        if ($script:Game.HasExited) { throw "the game exited (code $($script:Game.ExitCode)) while waiting for '$Pattern': see $Log" }
        if ((Test-Path -LiteralPath $Log) -and ((Read-Log) -match $Pattern)) { return }
        Start-Sleep -Milliseconds 500
    }
    throw "'$Pattern' did not appear in the log within $TimeoutSeconds s"
}
function Start-Game([string[]]$GameArgs) {
    Remove-Item -LiteralPath $Inbox -ErrorAction SilentlyContinue
    if ($GameArgs.Count -gt 0) { $script:Game = Start-Process -FilePath $Exe -ArgumentList $GameArgs -PassThru }
    else { $script:Game = Start-Process -FilePath $Exe -PassThru }
    Start-Sleep -Seconds 3
    Wait-Log 'LogLoad: \(Engine Initialization\) Total time' 300
    Wait-Log 'LogSovereignRealms: graphics: quality' 300
    Start-Sleep -Seconds 6
}
function Stop-Game {
    if ($script:Game -and -not $script:Game.HasExited) {
        try { Send-Commands @('quit') } catch {}
        if (-not $script:Game.WaitForExit(20000)) { Stop-Process -Id $script:Game.Id -Force -ErrorAction SilentlyContinue }
    }
    # (no crash reporter window may stay on the screen)
    Get-Process -Name 'CrashReportClient*' -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
}
function Save-Shot([string]$Name) {
    $png = Join-Path $Shots "$Name.png"
    Remove-Item -LiteralPath $png -ErrorAction SilentlyContinue
    Send-Commands @("vl.Shot $Name ui")
    $i = 0
    while (-not (Test-Path -LiteralPath $png) -and $i -lt 60) { $i++; Start-Sleep -Milliseconds 100 }
    Start-Sleep -Milliseconds 300
    if (Test-Path -LiteralPath $png) { Move-Item -LiteralPath $png -Destination (Join-Path $Out "$Name.png") -Force } else { Write-Host "  no screenshot for $Name" }
}
function Set-Size([string]$Size) {
    # "1920x1080" a window, "...wf" borderless, "...f" exclusive; returns a name for the files
    $spec = $Size
    if ($Size -notmatch '(w|f|wf)$') { $spec = $Size + 'w' }
    Send-Commands @("r.SetRes $spec")
    Start-Sleep -Milliseconds 2500
    return ($Size -replace 'wf$', '_borderless' -replace 'f$', '_exclusive' -replace 'w$', '')
}
function Get-Buttons {
    # the buttons of the last frame: id -> @(U, V), from vl.HUD's lines after a marker of this call
    Send-Commands @('vl.HUD')
    Start-Sleep -Milliseconds 400
    $text = Read-Log
    $at = $text.LastIndexOf('command: vl.HUD')
    $map = @{}
    if ($at -ge 0) {
        foreach ($m in [regex]::Matches($text.Substring($at), 'hud button (\d+) at ([\d.]+) ([\d.]+)')) { $map[[int]$m.Groups[1].Value] = @($m.Groups[2].Value, $m.Groups[3].Value) }
    }
    return $map
}
function Click-Button([int]$Id) {
    $b = Get-Buttons
    if (-not $b.ContainsKey($Id)) { return $false }
    Send-Commands @("vl.UIClick $($b[$Id][0]) $($b[$Id][1])")
    return $true
}
function Invoke-Stress([int]$Rounds, [string]$Where) {
    # Settings is open. 411 Display mode, 412 / 413 Resolution down / up, 414 VSync, 408 Quality, 409 Render scale;
    # "Keep this display mode?": 370 GO BACK, 371 KEEP
    $clicks = 0
    for ($r = 0; $r -lt $Rounds; $r++) {
        foreach ($id in 411, 413, 409, 413, 412, 408, 414, 411, 412, 409) {
            if (Click-Button $id) { $clicks++ }
            Start-Sleep -Milliseconds 900
            $b = Get-Buttons
            if ($b.ContainsKey(371)) {
                # an exclusive mode asks to be kept: keep it on even rounds, send it back on odd ones
                if ($r % 2 -eq 0) { [void](Click-Button 371) } else { [void](Click-Button 370) }
                $clicks++
                Start-Sleep -Milliseconds 1500
            }
        }
        if ($script:Game.HasExited) { throw "the game exited in round $r of the stress run ($Where)" }
        Write-Host "  stress ($Where): round $($r + 1) of $Rounds, $clicks clicks so far"
    }
    $text = Read-Log
    $changes = [regex]::Matches($text, 'LogSovereignRealms: window: (a window|full screen|exclusive full screen) \d+ x \d+').Count
    Write-Host "  stress ($Where): $clicks clicks, $changes display changes logged, the game is running"
}

$backup = "$Settings.hudshots-backup"
$hadSettings = Test-Path -LiteralPath $Settings
if ($hadSettings) { Copy-Item -LiteralPath $Settings -Destination $backup -Force }
$first = '1920x1080'
if ($Sizes.Count -gt 0 -and $Sizes[0] -match '^(\d+)x(\d+)') { $first = $Matches[0] }
$w, $h = $first.Split('x')
$common = @('-windowed', "-ResX=$w", "-ResY=$h", '-nosplash', '-unattended', '-FIXEDSEED')
try {
    if ($Default) {
        Write-Host 'starting the game as a double click does (no arguments) ...'
        Start-Game @()
        Start-Sleep -Seconds 4
        Save-Shot 'default_launch'
        $text = Read-Log
        foreach ($m in [regex]::Matches($text, 'LogSovereignRealms: window: [^\r\n]*|LogInit: Setting process to per monitor DPI aware|LogViewport: Display: Viewport MouseLockMode[^\r\n]*|LogWindows:\s+resolution: [^\r\n]*')) { Write-Host "  $($m.Value)" }
        Stop-Game
    }
    if ($Sizes.Count -gt 0) {
        Write-Host "starting $Map (Test World) ..."
        Start-Game (@("/Game/Maps/$Map" + '?Match=1?Difficulty=0?TestWorld=1') + $common)
        Send-Commands @('vl.Mode overview', 'vl.SelectUnits troops', 'vl.Platoon assign 1')      # (a match starts in the hero view: the selection panel is the overview's)
        foreach ($size in $Sizes) {
            $tag = Set-Size $size
            Write-Host "  $tag"
            Send-Commands @('vl.Menu 0', 'vl.Select Castle'); Start-Sleep -Milliseconds 700; Save-Shot "${tag}_castle"
            Send-Commands @('vl.Select Barracks'); Start-Sleep -Milliseconds 700; Save-Shot "${tag}_barracks"
            Send-Commands @('vl.Select none', 'vl.Platoon select 1'); Start-Sleep -Milliseconds 700; Save-Shot "${tag}_platoon"
            Send-Commands @('vl.Menu pause'); Start-Sleep -Milliseconds 700; Save-Shot "${tag}_pause"
            Send-Commands @('vl.Menu settings'); Start-Sleep -Milliseconds 700; Save-Shot "${tag}_settings"
            Send-Commands @('vl.Menu controls'); Start-Sleep -Milliseconds 700; Save-Shot "${tag}_controls"
            Send-Commands @('vl.Menu new'); Start-Sleep -Milliseconds 700; Save-Shot "${tag}_newgame"
            Send-Commands @('vl.Menu 0')
        }
        if ($Stress -gt 0) {
            Send-Commands @('vl.Menu settings'); Start-Sleep -Milliseconds 700
            Invoke-Stress $Stress 'in a match'
            Save-Shot 'stress_match_end'
            Send-Commands @('vl.Menu 0', 'vl.Perf')
        }
        Stop-Game
    }
    if ($Title) {
        Write-Host 'starting the title screen ...'
        Start-Game (@("/Game/Maps/$Map") + $common)
        foreach ($size in $Sizes) {
            $tag = Set-Size $size
            Write-Host "  $tag (title)"
            Send-Commands @('vl.Menu main'); Start-Sleep -Milliseconds 700; Save-Shot "${tag}_title"
            Send-Commands @('vl.Menu settings'); Start-Sleep -Milliseconds 700; Save-Shot "${tag}_title_settings"
            Send-Commands @('vl.Menu new'); Start-Sleep -Milliseconds 700; Save-Shot "${tag}_title_newgame"
            Send-Commands @('vl.Menu controls'); Start-Sleep -Milliseconds 700; Save-Shot "${tag}_title_controls"
        }
        if ($Stress -gt 0) {
            Send-Commands @('vl.Menu settings'); Start-Sleep -Milliseconds 700
            Invoke-Stress $Stress 'on the title screen'
            Save-Shot 'stress_title_end'
        }
        Stop-Game
    }
}
finally {
    Stop-Game
    Start-Sleep -Seconds 1
    if (Test-Path -LiteralPath $Log) { Copy-Item -LiteralPath $Log -Destination (Join-Path $Out 'game.log') -Force }
    # the player's own settings back (the sizes and modes of this run are not theirs)
    if ($hadSettings) { Move-Item -LiteralPath $backup -Destination $Settings -Force } else { Remove-Item -LiteralPath $Settings -ErrorAction SilentlyContinue }
}
Write-Host "screenshots: $Out"
exit 0
