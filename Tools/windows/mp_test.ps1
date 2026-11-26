<#
A multiplayer match played by script on this one PC: a host and a joining game side by side, driven through their
command inboxes, with what each game holds compared as it goes (Docs\Multiplayer\TESTING.md):
  powershell -ExecutionPolicy Bypass -File Tools\windows\mp_test.ps1 [-Map realmv3] [-Editor] [-Keep]
Needs Builds\Windows\SovereignRealms-Development from `package.ps1 Development` (the command inbox and vl.* are a
Development build's). -Editor runs the two games from the editor's binaries instead (UnrealEditor.exe -game: no
packaging, slower to load). Both games run from the same folder: each has its own inbox (-VLInbox=) and log.
What it checks, in order:
  join      the joining game connects (the version is accepted), gets its King, and the match starts in both
  state     both games hold the same units, buildings and kingdoms (vl.NetDump in each, compared)
  move      the joining player orders its troops to a point: they walk there in the host's game
  fight     swordsmen and archers of both sides fight; the dead, the health and the places agree in both games
  build     the joining player lays a barracks: it is a site in both games, paid for on the host
  hero      the joining player walks its King by hand: the host has him where the joining game does
  end       the joining player's castle falls: victory on the host, defeat in the joining game
  leave     the joining game quits: the host is told; then the host quits; neither game crashed or logged an ensure
-Keep leaves the two games running at the end (to look at them). Exit code 0: every check passed.
Plain ASCII on purpose (Windows PowerShell 5.1 reads a script without a byte-order mark as ANSI).
#>
param(
    [string]$Map = 'realmv3',
    [switch]$Editor,
    [switch]$Keep
)
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\_env.ps1"

if ($Editor) {
    $Exe = Join-Path (Get-VLEngineRoot) 'Engine\Binaries\Win64\UnrealEditor.exe'
    $Saved = $VLSaved
    $First = @("`"$VLProject`"", '-game')
    $ProcessName = 'UnrealEditor'
} else {
    $App = Join-Path $VLRoot 'Builds\Windows\SovereignRealms-Development'
    $Exe = Join-Path $App 'SovereignRealms\Binaries\Win64\SovereignRealms.exe'
    $Saved = Join-Path $App 'SovereignRealms\Saved'
    $First = @()
    $ProcessName = 'SovereignRealms'
}
if (-not (Test-Path -LiteralPath $Exe)) { Write-Host "no game at $Exe : run Tools\windows\package.ps1 Development first (or pass -Editor)"; exit 1 }
if (@(Get-Process -Name $ProcessName -ErrorAction SilentlyContinue).Count -gt 0) { Write-Host "$ProcessName is running: close it first"; exit 1 }
$Logs = Join-Path $Saved 'Logs'
New-Item -ItemType Directory -Force -Path $Logs | Out-Null
$Log = @{ host = (Join-Path $Logs 'mp_host.log'); client = (Join-Path $Logs 'mp_client.log') }
$Inbox = @{ host = (Join-Path $Saved 'VLHost.txt'); client = (Join-Path $Saved 'VLClient.txt') }
$Game = @{}
$script:Failed = 0

function Read-Text([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) { return '' }
    $fs = New-Object System.IO.FileStream($Path, [System.IO.FileMode]::Open, [System.IO.FileAccess]::Read, [System.IO.FileShare]::ReadWrite)
    try { return (New-Object System.IO.StreamReader($fs, [System.Text.Encoding]::UTF8)).ReadToEnd() } finally { $fs.Close() }
}
function Send([string]$Who, [string[]]$Lines) {
    $file = $Inbox[$Who]
    $tmp = "$file.tmp"
    [System.IO.File]::WriteAllText($tmp, (($Lines -join "`n") + "`n"), (New-Object System.Text.UTF8Encoding($false)))
    Move-Item -LiteralPath $tmp -Destination $file -Force
    $i = 0
    while ((Test-Path -LiteralPath $file) -and $i -lt 200) {
        if ($Game[$Who].HasExited) { throw "the $Who game exited (code $($Game[$Who].ExitCode)): see $($Log[$Who])" }
        $i++; Start-Sleep -Milliseconds 50
    }
    if (Test-Path -LiteralPath $file) { throw "the $Who game did not take its commands" }
}
function Wait-Log([string]$Who, [string]$Pattern, [int]$Seconds) {
    $end = (Get-Date).AddSeconds($Seconds)
    while ((Get-Date) -lt $end) {
        if ($Game[$Who].HasExited) { throw "the $Who game exited (code $($Game[$Who].ExitCode)) while waiting for '$Pattern': see $($Log[$Who])" }
        if ((Read-Text $Log[$Who]) -match $Pattern) { return }
        Start-Sleep -Milliseconds 500
    }
    throw "'$Pattern' did not appear in the $Who game's log within $Seconds s ($($Log[$Who]))"
}
function Start-One([string]$Who, [int]$X, [string]$Last) {
    Remove-Item -LiteralPath $Inbox[$Who], $Log[$Who] -ErrorAction SilentlyContinue
    $a = $First + @('-windowed', '-ResX=960', '-ResY=540', "-WinX=$X", '-WinY=40', '-nosplash', '-unattended', '-nosound', '-FIXEDSEED',
        "-VLInbox=$(Split-Path -Leaf $Inbox[$Who])", "-abslog=`"$($Log[$Who])`"", $Last)
    $Game[$Who] = Start-Process -FilePath $Exe -ArgumentList $a -PassThru
}
function Get-Dump([string]$Who) {
    # this game's units, buildings and kingdoms (vl.NetDump), as a table of "kind key" -> its fields
    $path = Join-Path $Saved "mp_dump_$Who.txt"
    $table = @{}
    foreach ($line in (Get-Content -LiteralPath $path)) {
        $words = $line.Split(' ')
        $fields = @{}
        foreach ($w in $words[1..($words.Count - 1)]) { $kv = $w.Split('=', 2); if ($kv.Count -eq 2) { $fields[$kv[0]] = $kv[1] } }
        $key = switch ($words[0]) { 'unit' { "unit $($fields.team) $($fields.name)" } 'building' { "building $($fields.id)" } 'kingdom' { "kingdom $($fields.team)" } default { 'match' } }
        $table[$key] = $fields
    }
    return $table
}
function Get-Both {
    # both games asked at once (their inboxes are polled twenty times a second: within a tenth of a second of each other)
    foreach ($w in 'host', 'client') { Remove-Item -LiteralPath (Join-Path $Saved "mp_dump_$w.txt") -ErrorAction SilentlyContinue }
    foreach ($w in 'host', 'client') {
        [System.IO.File]::WriteAllText("$($Inbox[$w]).tmp", "vl.NetDump mp_dump_$w`n", (New-Object System.Text.UTF8Encoding($false)))
    }
    foreach ($w in 'host', 'client') { Move-Item -LiteralPath "$($Inbox[$w]).tmp" -Destination $Inbox[$w] -Force }
    $i = 0
    while ((-not (Test-Path -LiteralPath (Join-Path $Saved 'mp_dump_host.txt')) -or -not (Test-Path -LiteralPath (Join-Path $Saved 'mp_dump_client.txt'))) -and $i -lt 100) { $i++; Start-Sleep -Milliseconds 100 }
    Start-Sleep -Milliseconds 200
    return @{ host = (Get-Dump 'host'); client = (Get-Dump 'client') }
}
function Compare-Games($Both, [double]$Reach, [double]$HealthSlack) {
    # what differs between the two games: units and buildings one has and the other has not, the living and the dead,
    # health further apart than HealthSlack, places further apart than Reach cm, and the kingdoms' numbers
    $h = $Both.host; $c = $Both.client
    $diff = @()
    foreach ($k in $h.Keys) { if (-not $c.ContainsKey($k)) { $diff += "only the host has: $k" } }
    foreach ($k in $c.Keys) { if (-not $h.ContainsKey($k)) { $diff += "only the joining game has: $k" } }
    foreach ($k in $h.Keys) {
        if (-not $c.ContainsKey($k)) { continue }
        $a = $h[$k]; $b = $c[$k]
        if ($k -eq 'match') {
            if ($a.state -ne $b.state -or $a.winner -ne $b.winner) { $diff += "match: state $($a.state)/$($b.state) winner $($a.winner)/$($b.winner)" }
            continue
        }
        if ($k.StartsWith('kingdom')) {
            foreach ($f in 'gold', 'food', 'recruited', 'lost', 'killed', 'buildingslost') {
                if ([Math]::Abs([double]$a[$f] - [double]$b[$f]) -gt ($(if ($f -eq 'gold' -or $f -eq 'food') { 40 } else { 2 }))) { $diff += "${k}: $f $($a[$f]) / $($b[$f])" }
            }
            continue
        }
        if ($a.alive -ne $b.alive) { $diff += "${k}: alive $($a.alive) / $($b.alive)"; continue }
        if ([Math]::Abs([double]$a.health - [double]$b.health) -gt $HealthSlack) { $diff += "${k}: health $($a.health) / $($b.health)" }
        if ($k.StartsWith('unit') -and $a.alive -eq '1') {
            $far = [Math]::Sqrt([Math]::Pow([double]$a.x - [double]$b.x, 2) + [Math]::Pow([double]$a.y - [double]$b.y, 2))
            if ($far -gt $Reach) { $diff += ("{0}: {1:N0} cm apart" -f $k, $far) }
        }
        if ($k.StartsWith('building') -and ($a.team -ne $b.team -or $a.level -ne $b.level -or [Math]::Abs([double]$a.build - [double]$b.build) -gt 0.1)) {
            $diff += "${k}: team $($a.team)/$($b.team) level $($a.level)/$($b.level) build $($a.build)/$($b.build)"
        }
    }
    return $diff
}
function Report([string]$Name, [bool]$Ok, [string]$Note) {
    if (-not $Ok) { $script:Failed++ }
    Write-Host ("  {0,-6} {1}  {2}" -f $Name, $(if ($Ok) { 'PASS' } else { 'FAIL' }), $Note)
}
function Count($Table, [string]$Team, [string]$Alive) {
    return @($Table.Keys | Where-Object { $_.StartsWith("unit $Team ") -and $Table[$_].alive -eq $Alive }).Count
}

try {
    Write-Host "multiplayer test on ${Map}: $Exe"
    # ---- join
    Start-One 'host' 0 "-VLHost=$Map"
    Wait-Log 'host' 'IpNetDriver listening on port' 240
    Start-One 'client' 960 '-VLJoin=127.0.0.1'
    Wait-Log 'host' 'LogSovereignRealms: match started on' 240
    Wait-Log 'client' 'multiplayer: the match has started' 60
    Start-Sleep -Seconds 4
    $hostLog = Read-Text $Log.host
    Report 'join' ($hostLog -match 'asks to join \(version [^)]*\): let in' -and $hostLog -match 'the other player has joined') 'the joining game was let in and the match started in both'

    # ---- state: the two games hold the same match
    $both = Get-Both
    $diff = @(Compare-Games $both 60 2)
    $units = @($both.host.Keys | Where-Object { $_.StartsWith('unit') }).Count
    $buildings = @($both.host.Keys | Where-Object { $_.StartsWith('building') }).Count
    Report 'state' ($diff.Count -eq 0 -and $units -ge 10 -and $both.client.match.mine -eq '1') "$units units, $buildings buildings in both; $($diff.Count) difference(s) $(($diff | Select-Object -First 3) -join '; ')"

    # ---- move: the joining player's order is carried out by the host
    $king = $both.host['unit 1 King_David']
    $tx = [double]$king.x + 1500; $ty = [double]$king.y + 1500
    Send 'client' @('vl.Mode overview', 'vl.SelectUnits troops', "vl.Order selection $tx $ty")
    Start-Sleep -Seconds 9
    $both = Get-Both
    $near = @($both.host.Keys | Where-Object { $_.StartsWith('unit 1 ') -and $_ -notmatch 'King|Tower' -and
        [Math]::Sqrt([Math]::Pow([double]$both.host[$_].x - $tx, 2) + [Math]::Pow([double]$both.host[$_].y - $ty, 2)) -lt 700 }).Count
    $diff = @(Compare-Games $both 150 2)
    Report 'move' ($near -ge 4 -and $diff.Count -eq 0) "$near of the joining player's troops are at the point in the host's game; $($diff.Count) difference(s) $(($diff | Select-Object -First 3) -join '; ')"

    # ---- fight: swordsmen and archers of both sides
    $fx = $tx + 1300; $fy = $ty + 1300
    Send 'host' @("vl.SpawnTeam Swordsman 0 $fx $fy 12", "vl.SpawnTeam Archer 0 $($fx + 400) $($fy + 400) 8", "vl.SpawnTeam Swordsman 1 $($tx - 300) $($ty - 300) 12", "vl.SpawnTeam Archer 1 $($tx - 700) $($ty - 700) 8")
    Start-Sleep -Seconds 2
    Send 'client' @('vl.SelectUnits troops', "vl.AttackMove selection $fx $fy")
    $worst = 0
    for ($round = 0; $round -lt 4; $round++) {
        Start-Sleep -Seconds 5
        $both = Get-Both
        # (mid-fight: a blow lands in one game a moment before the other hears of it)
        $diff = @(Compare-Games $both 260 60 | Where-Object { $_ -notmatch 'alive' })
        $worst = [Math]::Max($worst, $diff.Count)
    }
    Start-Sleep -Seconds 12
    $both = Get-Both
    $diff = @(Compare-Games $both 260 45)
    $lost = [int]$both.host['kingdom 0'].lost + [int]$both.host['kingdom 1'].lost
    Report 'fight' ($lost -ge 8 -and $diff.Count -le 2 -and $worst -le 6) "$lost troops fell (host: $(Count $both.host '0' '1') of team 0 and $(Count $both.host '1' '1') of team 1 alive; joining game: $(Count $both.client '0' '1') and $(Count $both.client '1' '1')); differences mid-fight at most $worst, after it $($diff.Count) $(($diff | Select-Object -First 3) -join '; ')"

    # ---- build: the joining player lays a barracks
    $gold = [int]$both.host['kingdom 1'].gold
    Send 'client' @("vl.Build barracks $([double]$king.x + 900) $([double]$king.y + 900) 0 enemy near")
    Start-Sleep -Seconds 6
    $both = Get-Both
    $siteH = @($both.host.Keys | Where-Object { $_.StartsWith('building') -and $both.host[$_].kind -eq 'Barracks' -and $both.host[$_].team -eq '1' })
    $siteC = @($both.client.Keys | Where-Object { $_.StartsWith('building') -and $both.client[$_].kind -eq 'Barracks' -and $both.client[$_].team -eq '1' })
    Report 'build' ($siteH.Count -eq 1 -and $siteC.Count -eq 1 -and $siteH[0] -eq $siteC[0]) "a Barracks of team 1 in the host's game ($($siteH.Count)) and in the joining game ($($siteC.Count)); team 1's gold $gold -> $($both.host['kingdom 1'].gold)"

    # ---- hero: the joining player walks its King by hand
    $before = $both.host['unit 1 King_David']
    Send 'client' @('vl.Control king', 'vl.Mode hero', 'vl.Move 1 0 2 run')
    Start-Sleep -Seconds 4
    $both = Get-Both
    $kh = $both.host['unit 1 King_David']; $kc = $both.client['unit 1 King_David']
    $walked = [Math]::Sqrt([Math]::Pow([double]$kh.x - [double]$before.x, 2) + [Math]::Pow([double]$kh.y - [double]$before.y, 2))
    $apart = [Math]::Sqrt([Math]::Pow([double]$kh.x - [double]$kc.x, 2) + [Math]::Pow([double]$kh.y - [double]$kc.y, 2))
    Report 'hero' ($walked -gt 500 -and $apart -lt 60) ("the King walked {0:N0} cm by hand; the two games have him {1:N0} cm apart" -f $walked, $apart)

    # ---- end: the joining player's castle falls
    Send 'host' @('vl.Kill castle enemy')
    Start-Sleep -Seconds 5
    $both = Get-Both
    Report 'end' ($both.host.match.state -eq '2' -and $both.client.match.state -eq '2' -and $both.host.match.winner -eq '0' -and $both.client.match.winner -eq '0' -and
        (Read-Text $Log.host) -match 'VICTORY' -and (Read-Text $Log.client) -match 'DEFEAT') 'victory on the host, defeat in the joining game'

    if ($Keep) { Write-Host '  (-Keep: the two games are left running)'; exit $script:Failed }

    # ---- leave: the joining game quits, then the host
    Send 'client' @('quit')
    [void]$Game.client.WaitForExit(30000)
    Start-Sleep -Seconds 3
    $told = (Read-Text $Log.host) -match 'multiplayer: the other player has left'
    Send 'host' @('quit')
    [void]$Game.host.WaitForExit(30000)
    $bad = @()
    foreach ($w in 'host', 'client') {
        $text = Read-Text $Log[$w]
        if (-not $Game[$w].HasExited) { $bad += "the $w game did not exit" }
        elseif ($Game[$w].ExitCode -ne 0) { $bad += "the $w game exited with code $($Game[$w].ExitCode)" }
        if ($text -match 'Fatal error|Unhandled Exception|Ensure condition failed|Assertion failed') { $bad += "the $w game's log has a crash or an ensure" }
    }
    Report 'leave' ($told -and $bad.Count -eq 0) "the host was told the other player left; both games exited cleanly $($bad -join '; ')"
}
catch {
    Write-Host "  FAILED: $($_.Exception.Message)"
    $script:Failed++
}
finally {
    if (-not $Keep) {
        foreach ($w in 'host', 'client') { if ($Game[$w] -and -not $Game[$w].HasExited) { Stop-Process -Id $Game[$w].Id -Force -ErrorAction SilentlyContinue } }
        Get-Process -Name 'CrashReportClient*' -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    }
}
Write-Host $(if ($script:Failed -eq 0) { 'multiplayer test: all checks passed' } else { "multiplayer test: $script:Failed check(s) FAILED (logs: $($Log.host), $($Log.client))" })
exit $script:Failed
