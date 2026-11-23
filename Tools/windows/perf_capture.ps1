<#
Frame times of the packaged Development build in a battle, at a fixed window size:
  powershell -ExecutionPolicy Bypass -File Tools\windows\perf_capture.ps1 [-Width 1920] [-Height 1080] [-Seconds 30]
      [-Warmup 75] [-Map L_RealmV2] [-Tag 1080p] [-NoTestWorld] [-ProfileGpu]
Needs Builds\Windows\SovereignRealms-Development from `package.ps1 Development` (the Shipping build has no command inbox, no log
and no CSV profiler). What it does:
  1. starts the game on the map with ?Match=1?Difficulty=2?AIvsAI=2 (and ?TestWorld=1: both sides at their most), in a
     window of Width x Height: both sides are played by the computer, so the battle needs no hands
  2. takes off the frame cap and the background throttle for the measurement (t.MaxFPS 0, vl.Opt.IdleThrottle 0;
     the game's own default is 60 fps), waits Warmup seconds for the armies to meet
  3. at each of three views (the same as Tools/mac/realmv2_perf.sh: base = the hero's camera, mountain = a free camera
     with the massif in view, overview = the postcard camera, the whole map) records Seconds of Unreal's CSV profiler
     (the numbers of `stat unit`: Frame, Game, Draw, GPU, RHIT) and logs vl.Perf and vl.Battle
  4. -ProfileGpu: a ProfileGPU capture of the overview into the log (the `stat gpu` breakdown)
  5. quits the game and prints one line a view (Tools/perf_csv.py)
The captures are copied to Saved\Perf\<Tag>\ (<view>.csv, the game's log as game.log, summary.txt).
The settings are whatever the build's own Saved\Config says; a freshly packaged build has none, so the game's
defaults apply (High, render scale 100 %). The window size the game remembers is overridden with r.SetRes.
#>
param(
    [int]$Width = 1920,
    [int]$Height = 1080,
    [int]$Seconds = 30,
    [int]$Warmup = 75,
    [string]$Map = 'L_RealmV2',
    [string]$Tag = '',
    [switch]$NoTestWorld,
    [switch]$ProfileGpu,
    [string]$AB = '',
    [string]$Pre = '',
    [string]$ExtraArgs = '',
    [switch]$Fullscreen,
    [string]$Post = ''
)
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\_env.ps1"

if (-not $Tag) { $Tag = "${Width}x${Height}" }
$App = Join-Path $VLRoot 'Builds\Windows\SovereignRealms-Development'
$Exe = Join-Path $App 'SovereignRealms\Binaries\Win64\SovereignRealms.exe'
if (-not (Test-Path -LiteralPath $Exe)) { Write-Host "no Development build at $Exe : run Tools\windows\package.ps1 Development first"; exit 1 }
$GameSaved = Join-Path $App 'SovereignRealms\Saved'
$Log = Join-Path $GameSaved 'Logs\SovereignRealms.log'
$CsvDir = Join-Path $GameSaved 'Profiling\CSV'
$Inbox = Join-Path $GameSaved 'VLCommands.txt'
$Out = Join-Path $VLSaved "Perf\$Tag"
New-Item -ItemType Directory -Force -Path $Out, $GameSaved | Out-Null
Remove-Item -Path (Join-Path $Out '*') -Force -ErrorAction SilentlyContinue

function Send-Commands([string[]]$Lines) {
    # the game polls Saved\VLCommands.txt and deletes it once read
    $tmp = "$Inbox.tmp"
    [System.IO.File]::WriteAllText($tmp, (($Lines -join "`n") + "`n"), (New-Object System.Text.UTF8Encoding($false)))
    Move-Item -LiteralPath $tmp -Destination $Inbox -Force
    $i = 0
    # (the game may be deleting the file at this very moment: 'access denied' then means it is still there)
    function Test-Inbox { try { return (Test-Path -LiteralPath $Inbox -ErrorAction Stop) } catch { return $true } }
    while ((Test-Inbox) -and $i -lt 200) { $i++; Start-Sleep -Milliseconds 100 }
    if (Test-Inbox) { throw 'the game did not take the commands (is it running, and a Development build?)' }
}
function Read-Log {
    # (the game holds the log open for writing)
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

$url = "/Game/Maps/$Map" + '?Match=1?Difficulty=2?AIvsAI=2'
if (-not $NoTestWorld) { $url += '?TestWorld=1' }
# -Fullscreen: the size asked for as a full-screen mode. A window cannot be larger than the desktop as Windows
# reports it to a game that is not DPI-aware (2194 x 1234 on a 4K display at 175 %): "2560 x 1440" in a window was
# drawn at that size there. The script warns when a ProfileGPU shows another output size than the one asked for.
$gameArgs = @($url, '-windowed', "-ResX=$Width", "-ResY=$Height", '-nosplash', '-unattended', '-NoVSync', '-FIXEDSEED')
if ($ExtraArgs) { $gameArgs += $ExtraArgs.Split(' ') }
Remove-Item -LiteralPath $Inbox -ErrorAction SilentlyContinue
$before = @(Get-ChildItem -LiteralPath $CsvDir -Filter '*.csv' -ErrorAction SilentlyContinue | ForEach-Object { $_.FullName })

Write-Host "starting $Map at ${Width}x${Height} ..."
$started = Get-Date
$script:Game = Start-Process -FilePath $Exe -ArgumentList $gameArgs -PassThru
$results = @()
try {
    Start-Sleep -Seconds 3
    Wait-Log 'LogLoad: \(Engine Initialization\) Total time' 300
    $engineUp = ((Get-Date) - $started).TotalSeconds
    Wait-Log 'LogSovereignRealms' 300
    Start-Sleep -Seconds 5
    Send-Commands (@('t.MaxFPS 0', 'vl.Opt.IdleThrottle 0', 'r.VSync 0', "r.SetRes ${Width}x${Height}$(if ($Fullscreen) { 'f' } else { 'w' })", 'vl.Battle') + @($Pre.Split(';') | Where-Object { $_.Trim() }))
    $ready = ((Get-Date) - $started).TotalSeconds
    Write-Host ("engine up after {0:N1} s, in the match after {1:N1} s; warming up {2} s ..." -f $engineUp, $ready, $Warmup)
    Start-Sleep -Seconds $Warmup

    $views = @(
        # (the player's castle from a hero-like camera: with both sides played by the computer the king is benched off
        # the map, and 'vl.View follow' showed the empty sea)
        @('base', 'vl.View free -19600 13400 1500 -24 -40 40'),
        @('mountain', 'vl.View free -15000 12000 6000 2 -52 70'),
        @('overview', 'vl.View postcard')
    )
    foreach ($v in $views) {
        Send-Commands @($v[1])
        Start-Sleep -Seconds 8
        Send-Commands @('vl.Battle', 'csvprofile start')
        Start-Sleep -Seconds $Seconds
        Send-Commands @('csvprofile stop', 'vl.Perf')
        Start-Sleep -Seconds 4
        $new = @(Get-ChildItem -LiteralPath $CsvDir -Filter '*.csv' -ErrorAction SilentlyContinue | Where-Object { $before -notcontains $_.FullName } | Sort-Object LastWriteTime)
        if ($new.Count -eq 0) { throw "no CSV capture was written for the view '$($v[0])'" }
        $dst = Join-Path $Out ($v[0] + '.csv')
        Copy-Item -LiteralPath $new[-1].FullName -Destination $dst -Force
        $before += $new | ForEach-Object { $_.FullName }
        $results += ,@($v[0], $dst)
        Write-Host "  $($v[0]) captured"
    }
    if ($ProfileGpu) {
        Send-Commands @('r.ProfileGPU.ShowUI 0', 'ProfileGPU')
        Start-Sleep -Seconds 6
    }
    # -AB "r.Nanite 0;r.HZBOcclusion 1": each set at the overview for 15 s of CSV and a ProfileGPU, then put back
    foreach ($ab in @($AB.Split(';') | Where-Object { $_.Trim() })) {
        $ab = $ab.Trim()
        # ("set|restore" for a command that is not a console variable: nothing to read its present value from)
        $restore = ''
        if ($ab.Contains('|')) { $restore = $ab.Split('|')[1].Trim(); $ab = $ab.Split('|')[0].Trim() }
        $parts = $ab.Split(' ')
        if (-not $restore) {
            Send-Commands @($parts[0])              # (logs its present value)
            Start-Sleep -Seconds 1
            $was = '1'
            if ((Read-Log) -match ('(?s).*' + [regex]::Escape($parts[0]) + ' = "([^"]*)"')) { $was = $Matches[1] }
            $restore = "$($parts[0]) $was"
        }
        Send-Commands @($ab)
        Start-Sleep -Seconds 6
        Send-Commands @('csvprofile start')
        Start-Sleep -Seconds 15
        Send-Commands @('csvprofile stop')
        Start-Sleep -Seconds 3
        $new = @(Get-ChildItem -LiteralPath $CsvDir -Filter '*.csv' -ErrorAction SilentlyContinue | Where-Object { $before -notcontains $_.FullName } | Sort-Object LastWriteTime)
        if ($new.Count -gt 0) {
            $name = 'ab_' + ($ab -replace '[^A-Za-z0-9]+', '_')
            $dst = Join-Path $Out ($name + '.csv')
            Copy-Item -LiteralPath $new[-1].FullName -Destination $dst -Force
            $before += $new | ForEach-Object { $_.FullName }
            $results += ,@($name, $dst)
        }
        Send-Commands @($restore)
        Start-Sleep -Seconds 3
    }
    # -Post "stat dumpave -num=120 -ms=0.02": console commands at the overview once the captures are done
    if ($Post.Trim()) {
        Send-Commands @($Post.Split(';') | Where-Object { $_.Trim() })
        Start-Sleep -Seconds 12
    }
    Send-Commands @('vl.Battle')
    Start-Sleep -Seconds 1
    # the size really drawn at (the last "TemporalSuperResolution ... -> W x H" of a ProfileGPU, if one was taken)
    if ((Read-Log) -match '(?s).*TemporalSuperResolution[^
]*-> (\d+)x(\d+)') {
        if ([int]$Matches[1] -ne $Width -or [int]$Matches[2] -ne $Height) { Write-Host "WARNING: the game drew at $($Matches[1]) x $($Matches[2]), not ${Width} x ${Height}" }
    }
}
finally {
    if (-not $script:Game.HasExited) {
        try { Send-Commands @('quit') } catch {}
        if (-not $script:Game.WaitForExit(15000)) { Stop-Process -Id $script:Game.Id -Force -ErrorAction SilentlyContinue }
    }
    if (Test-Path -LiteralPath $Log) { Copy-Item -LiteralPath $Log -Destination (Join-Path $Out 'game.log') -Force }
}

$py = Get-VLPython (Get-VLEngineRoot)
$summary = Join-Path $Out 'summary.txt'
$lines = @("${Map} ${Width}x${Height}, $Seconds s a view, engine up after $([int]$engineUp) s, in the match after $([int]$ready) s")
foreach ($r in $results) {
    $text = (& $py (Join-Path $VLRoot 'Tools\perf_csv.py') $r[1]) -replace [regex]::Escape($r[1]), $r[0]
    $lines += $text
}
$lines | Set-Content -LiteralPath $summary -Encoding UTF8
$lines | ForEach-Object { Write-Host $_ }
Write-Host "captures: $Out"
exit 0
