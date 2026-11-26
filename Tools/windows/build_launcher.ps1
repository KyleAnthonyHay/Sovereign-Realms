<#
Build the launcher (Tools\windows\launcher): the packaged game's SovereignRealms.exe, the runner up at once while the
game starts behind it (see VLLauncher.cpp). One C++ file and its resources, built with the Visual Studio C++ tools
(vswhere finds them), no engine. Called by package.ps1; by hand:
    powershell -ExecutionPolicy Bypass -File Tools\windows\build_launcher.ps1 [-Out <exe>]
Result: Intermediate\Launcher\SovereignRealms.exe (or -Out). Plain ASCII on purpose (PowerShell 5.1 reads it as ANSI).
#>
param([string]$Out = '')
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\_env.ps1"

$Src = Join-Path $PSScriptRoot 'launcher'
$Work = Join-Path $VLRoot 'Intermediate\Launcher'
if (-not $Out) { $Out = Join-Path $Work 'SovereignRealms.exe' }
New-Item -ItemType Directory -Force -Path $Work | Out-Null

# the resources, gathered beside a copy of the .rc
$UE = Get-VLEngineRoot
Copy-Item -Force (Join-Path $Src 'VLLauncher.rc'), (Join-Path $Src 'resource.h') $Work
foreach ($n in 'T_UI_KingRun', 'T_UI_KingCrouchRun', 'T_UI_RunnerProps', 'T_UI_Emblem') {
    Copy-Item -Force (Join-Path $VLRoot "SourceArt\UI\$n.png") $Work
}
foreach ($n in 'Roboto-Bold', 'Roboto-Regular') {
    Copy-Item -Force (Join-Path $UE "Engine\Content\Slate\Fonts\$n.ttf") $Work
}
# the icon: the emblem's 256 px PNG in an .ico (one PNG entry; 0 in the size bytes means 256)
$png = [IO.File]::ReadAllBytes((Join-Path $VLRoot 'SourceArt\UI\T_UI_Emblem.png'))
$ms = New-Object IO.MemoryStream
$bw = New-Object IO.BinaryWriter $ms
$bw.Write([uint16]0); $bw.Write([uint16]1); $bw.Write([uint16]1)
$bw.Write([byte]0); $bw.Write([byte]0); $bw.Write([byte]0); $bw.Write([byte]0)
$bw.Write([uint16]1); $bw.Write([uint16]32); $bw.Write([uint32]$png.Length); $bw.Write([uint32]22)
$bw.Write($png); $bw.Flush()
[IO.File]::WriteAllBytes((Join-Path $Work 'app.ico'), $ms.ToArray())

$vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe'
$vs = & $vswhere -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if (-not $vs) { Write-Host 'build_launcher: no Visual Studio C++ tools found'; exit 1 }
$vcvars = Join-Path $vs 'VC\Auxiliary\Build\vcvars64.bat'
$cpp = Join-Path $Src 'VLLauncher.cpp'
$cmd = "set `"PATH=$(Split-Path $vswhere);%PATH%`" && `"$vcvars`" >nul && cd /d `"$Work`" && rc /nologo /fo VLLauncher.res VLLauncher.rc && " +
    "cl /nologo /O2 /MT /EHsc /std:c++17 /W3 /DUNICODE /D_UNICODE /D_CRT_SECURE_NO_WARNINGS /I`"$Src`" /Fo`"$Work\\`" `"$cpp`" VLLauncher.res " +
    "/link /SUBSYSTEM:WINDOWS /OUT:`"$Out`" user32.lib gdi32.lib ole32.lib windowscodecs.lib dwmapi.lib"
& cmd.exe /c $cmd
if ($LASTEXITCODE -ne 0) { Write-Host "build_launcher: failed ($LASTEXITCODE)"; exit 1 }
Write-Host "build_launcher: $Out"
exit 0
