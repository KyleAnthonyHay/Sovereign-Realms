<#
The editor on Windows:  powershell -ExecutionPolicy Bypass -File Tools\windows\editor.ps1 [open|quit|build|start|rebuild]
(or double-click Tools\windows\Editor.bat).
  open (the default)   build SovereignRealmsEditor if the editor is not running, then open the project in it
  quit                 save dirty packages, close the editor, wait until the process and the MCP port are gone
  build                build SovereignRealmsEditor (the editor must be closed); the log in Saved\build_editor.log
  start                open the project and wait for the editor's MCP server (port 8000) and the Python bridge
  rebuild              quit + build + start
The counterpart of Tools/mac/editor.sh. The engine: $env:UE_ROOT, else the installed 5.8, else the newest UE_5.*
(Tools\windows\_env.ps1). An editor of another version than the project's is not opened unless -AllowEngineMismatch
is given: saving an asset from a newer editor makes it unreadable to the project's own version (the Mac's).
#>
param(
    [Parameter(Position = 0)][ValidateSet('open', 'quit', 'build', 'start', 'rebuild')][string]$Command = 'open',
    [switch]$AllowEngineMismatch
)
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\_env.ps1"

$UE = Get-VLEngineRoot
$Port = 8000

function Get-Editor { @(Get-Process -Name 'UnrealEditor' -ErrorAction SilentlyContinue) }
function Test-Running { (Get-Editor).Count -gt 0 }
function Test-Listening {
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $wait = $client.BeginConnect('127.0.0.1', $Port, $null, $null)
        if (-not $wait.AsyncWaitHandle.WaitOne(300)) { return $false }
        $client.EndConnect($wait)
        return $true
    } catch { return $false } finally { $client.Close() }
}
function Invoke-Bridge([string]$Code, [int]$Seconds) {
    # run a line of Python in the open editor (Tools/ue_py.py); $true if it answered
    $py = Get-VLPython $UE
    New-Item -ItemType Directory -Force -Path $VLSaved | Out-Null
    $p = Start-Process -FilePath $py -ArgumentList @("`"$(Join-Path $VLRoot 'Tools\ue_py.py')`"", '-c', "`"$Code`"", "$Seconds") -NoNewWindow -Wait -PassThru -RedirectStandardOutput (Join-Path $VLSaved 'bridge.out')
    Remove-Item -LiteralPath (Join-Path $VLSaved 'bridge.out') -ErrorAction SilentlyContinue
    return ($p.ExitCode -eq 0)
}

function Stop-Editor {
    if (Test-Running) {
        # unsaved packages put up a save dialog that blocks the quit: save them through the Python bridge first
        [void](Invoke-Bridge 'import unreal; unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True, True)' 20)
        foreach ($p in Get-Editor) { [void]$p.CloseMainWindow() }
    }
    $i = 0
    while ((Test-Running) -or (Test-Listening)) {
        $i++
        if ($i -eq 40) { Get-Editor | Stop-Process -Force -ErrorAction SilentlyContinue }
        if ($i -gt 45) { Get-Process -Name 'CrashReportClient*' -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue }
        if ($i -gt 90) { Write-Host 'editor did not quit'; return $false }
        Start-Sleep -Seconds 1
    }
    Write-Host 'editor closed'
    return $true
}

function Build-Editor {
    if (Test-Running) { Write-Host 'the editor is open: close it first (editor.ps1 quit), or use rebuild'; return $false }
    [void](Test-VLEngineMatches $UE)
    New-Item -ItemType Directory -Force -Path $VLSaved | Out-Null
    $log = Join-Path $VLSaved 'build_editor.log'
    Write-Host "building SovereignRealmsEditor with $UE (the log: Saved\build_editor.log) ..."
    $code = Invoke-VLLogged (Join-Path $UE 'Engine\Build\BatchFiles\Build.bat') @('SovereignRealmsEditor', 'Win64', 'Development', "-Project=`"$VLProject`"", '-WaitMutex') $log
    Get-Content -LiteralPath $log | Select-String -Pattern 'error|warning C|Result:|Total execution|unresolved external' | Select-Object -Last 40 | ForEach-Object { Write-Host $_.Line }
    return ($code -eq 0)
}

function Start-Editor {
    if (-not (Test-VLEngineMatches $UE) -and -not $AllowEngineMismatch) {
        Write-Host 'not opening the editor with another engine version (install the project''s, set UE_ROOT, or pass -AllowEngineMismatch and save nothing)'
        return $false
    }
    if (Test-Running) { Write-Host 'the editor is already open'; return $true }
    # a leftover crash reporter can hold the MCP port
    Get-Process -Name 'CrashReportClient*' -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    New-Item -ItemType Directory -Force -Path $VLSaved | Out-Null
    Start-Process -FilePath (Join-Path $UE 'Engine\Binaries\Win64\UnrealEditor.exe') -ArgumentList "`"$VLProject`""
    Write-Host 'the editor is starting (the first start compiles shaders: several minutes) ...'
    $i = 0
    while (-not (Test-Listening)) {
        $i++
        if ($i -gt 900) { Write-Host "the editor's MCP server is not on port $Port yet (the editor may still be loading; the scripted tools need it)"; return $false }
        if ($i -gt 20 -and -not (Test-Running)) { Write-Host 'the editor closed while starting (see Saved\Logs\SovereignRealms.log)'; return $false }
        Start-Sleep -Seconds 1
    }
    # the port opens before the editor ticks: wait until the Python bridge (Content/Python/init_unreal.py) answers
    $j = 0
    while (-not (Invoke-Bridge "print('ok')" 15)) {
        Remove-Item -Path (Join-Path $VLSaved 'PyInbox\*.py') -ErrorAction SilentlyContinue
        $j++
        if ($j -gt 30) { Write-Host 'bridge did not answer'; return $false }
    }
    Write-Host ("editor up (port after {0}s, bridge after {1}s more)" -f $i, ($j * 15))
    return $true
}

$ok = $true
switch ($Command) {
    'quit' { $ok = Stop-Editor }
    'build' { $ok = Build-Editor }
    'start' { $ok = Start-Editor }
    'rebuild' { $ok = (Stop-Editor) -and (Build-Editor) -and (Start-Editor) }
    'open' {
        if (Test-Running) { Write-Host 'the editor is already open' }
        else { $ok = (Build-Editor) -and (Start-Editor) }
    }
}
if (-not $ok) { exit 1 }
exit 0
