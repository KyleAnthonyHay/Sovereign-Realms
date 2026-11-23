# Shared by the scripts in Tools/windows (dot-source it:  . "$PSScriptRoot\_env.ps1").
# Where things are on this machine, said the same way as Tools/vl_env.py and Tools/mac/*.sh:
#   the engine    $env:UE_ROOT if set; else the launcher's install of the project's version (5.8), from the registry or
#                 C:\Program Files\Epic Games\UE_5.8; else the newest UE_5.* there
#   python        a real python on PATH (not the Microsoft Store stub); else the one the engine ships
#   blender       $env:BLENDER if set; else the newest under C:\Program Files\Blender Foundation
# Plain ASCII on purpose: Windows PowerShell 5.1 reads a script without a byte-order mark as ANSI.

$script:VLRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$script:VLProject = Join-Path $VLRoot 'SovereignRealms.uproject'
$script:VLSaved = Join-Path $VLRoot 'Saved'

function Get-VLProjectEngineVersion {
    # the project's EngineAssociation ("5.8")
    $text = Get-Content -Raw -LiteralPath $VLProject
    if ($text -match '"EngineAssociation"\s*:\s*"([^"]*)"') { return $Matches[1] }
    return ''
}

function Test-VLEngineDir([string]$Dir) {
    if ([string]::IsNullOrEmpty($Dir)) { return $false }
    return (Test-Path -LiteralPath (Join-Path $Dir 'Engine\Build\BatchFiles\RunUAT.bat'))
}

function Get-VLEngineRoot {
    if ($env:UE_ROOT) {
        if (-not (Test-VLEngineDir $env:UE_ROOT)) { throw "UE_ROOT is set to '$($env:UE_ROOT)' but there is no engine there" }
        return $env:UE_ROOT.TrimEnd('\', '/')
    }
    $want = Get-VLProjectEngineVersion
    $candidates = @()
    # the launcher records each install here
    try {
        $reg = Get-ItemProperty -Path "HKLM:\SOFTWARE\EpicGames\Unreal Engine\$want" -ErrorAction Stop
        if ($reg.InstalledDirectory) { $candidates += $reg.InstalledDirectory }
    } catch {}
    $base = Join-Path $env:ProgramFiles 'Epic Games'
    $candidates += (Join-Path $base "UE_$want")
    foreach ($c in $candidates) { if (Test-VLEngineDir $c) { return $c.TrimEnd('\', '/') } }
    # not installed: the newest UE_5.* (a newer engine builds and cooks the project; see the README, "Platforms")
    $found = @(Get-ChildItem -LiteralPath $base -Directory -Filter 'UE_5.*' -ErrorAction SilentlyContinue |
        Where-Object { Test-VLEngineDir $_.FullName } |
        Sort-Object { [version](($_.Name -replace '^UE_', '') -replace '[^0-9.]', '') } -Descending)
    if ($found.Count -gt 0) { return $found[0].FullName }
    throw "no Unreal Engine found: install $want with the Epic launcher, or set UE_ROOT to the engine's folder"
}

function Get-VLEngineVersion([string]$EngineRoot) {
    # "5.8" from Engine\Build\Build.version
    $file = Join-Path $EngineRoot 'Engine\Build\Build.version'
    if (-not (Test-Path -LiteralPath $file)) { return '' }
    $v = Get-Content -Raw -LiteralPath $file | ConvertFrom-Json
    return ('{0}.{1}' -f $v.MajorVersion, $v.MinorVersion)
}

function Test-VLEngineMatches([string]$EngineRoot) {
    # $true when the engine is the project's version; says so when it is not
    $have = Get-VLEngineVersion $EngineRoot
    $want = Get-VLProjectEngineVersion
    if ($have -eq $want) { return $true }
    Write-Warning "the engine at '$EngineRoot' is $have; the project is $want. Building and packaging with it is fine (nothing is saved); an editor of a newer version must not save assets (the $want editor could no longer open them)."
    return $false
}

function Get-VLPython([string]$EngineRoot) {
    foreach ($name in 'python', 'python3', 'py') {
        $cmd = Get-Command $name -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
        # (the Microsoft Store's stub in WindowsApps only opens the Store)
        if ($cmd -and $cmd.Source -notmatch '\\WindowsApps\\') { return $cmd.Source }
    }
    if ($EngineRoot) {
        $bundled = Join-Path $EngineRoot 'Engine\Binaries\ThirdParty\Python3\Win64\python.exe'
        if (Test-Path -LiteralPath $bundled) { return $bundled }
    }
    throw 'no python found: install Python 3 (python.org) or set UE_ROOT so that the engine''s own can be used'
}

function Get-VLBlender {
    if ($env:BLENDER) { return $env:BLENDER }
    $found = @(Get-ChildItem -Path (Join-Path $env:ProgramFiles 'Blender Foundation\Blender*\blender.exe') -ErrorAction SilentlyContinue | Sort-Object FullName -Descending)
    if ($found.Count -gt 0) { return $found[0].FullName }
    return 'blender'
}

function Invoke-VLLogged([string]$File, [string[]]$Arguments, [string]$Log) {
    # run a program to the end with everything it prints in $Log (as the program wrote it); returns its exit code
    $err = "$Log.err"
    $p = Start-Process -FilePath $File -ArgumentList $Arguments -NoNewWindow -Wait -PassThru -RedirectStandardOutput $Log -RedirectStandardError $err
    if ((Test-Path -LiteralPath $err) -and (Get-Item -LiteralPath $err).Length -gt 0) {
        Add-Content -LiteralPath $Log -Value (Get-Content -LiteralPath $err) -Encoding UTF8
    }
    Remove-Item -LiteralPath $err -ErrorAction SilentlyContinue
    return $p.ExitCode
}

function Format-VLSize([long]$Bytes) {
    if ($Bytes -ge 1GB) { return ('{0:N2} GB' -f ($Bytes / 1GB)) }
    return ('{0:N0} MB' -f ($Bytes / 1MB))
}
