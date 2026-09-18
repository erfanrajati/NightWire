[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

# NightWire installer / upgrader for Windows PowerShell 5.1+ and PowerShell 7+.
# Optional overrides:
#   NIGHTWIRE_INSTALL_DIR=C:\Apps\NightWire
#   NIGHTWIRE_BIN_DIR=C:\Users\me\bin
#   NIGHTWIRE_PYTHON=3.12

function Fail([string]$Message) {
    throw "NightWire installer: $Message"
}

function Get-FullPath([string]$Path) {
    return [System.IO.Path]::GetFullPath($ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($Path))
}

function Find-Uv {
    $Command = Get-Command uv.exe -ErrorAction SilentlyContinue
    if ($null -ne $Command) {
        return $Command.Source
    }

    foreach ($Candidate in @(
        (Join-Path $HOME ".local\bin\uv.exe"),
        (Join-Path $HOME ".cargo\bin\uv.exe")
    )) {
        if (Test-Path -LiteralPath $Candidate -PathType Leaf) {
            return $Candidate
        }
    }
    return $null
}

if ($env:OS -ne "Windows_NT") {
    Fail "install.ps1 is for Windows. On Linux or macOS, run ./install.sh."
}

$SourceDir = Get-FullPath $PSScriptRoot
$DefaultInstallDir = Join-Path $env:LOCALAPPDATA "NightWire"
$DefaultBinDir = Join-Path $env:LOCALAPPDATA "Programs\NightWire"
$InstallDir = Get-FullPath $(if ($env:NIGHTWIRE_INSTALL_DIR) { $env:NIGHTWIRE_INSTALL_DIR } else { $DefaultInstallDir })
$BinDir = Get-FullPath $(if ($env:NIGHTWIRE_BIN_DIR) { $env:NIGHTWIRE_BIN_DIR } else { $DefaultBinDir })
$PythonRequest = if ($env:NIGHTWIRE_PYTHON) { $env:NIGHTWIRE_PYTHON } else { "3.11" }
$CommandPath = Join-Path $BinDir "nightwire.cmd"
$PowerShellLauncherPath = Join-Path $BinDir "nightwire.ps1"
$TempRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("nightwire-install-" + [guid]::NewGuid().ToString("N"))
$StageDir = Join-Path $TempRoot "release"

try {
    Write-Host ""
    Write-Host "Installing NightWire"
    Write-Host "Source:  $SourceDir"
    Write-Host "Target:  $InstallDir"
    Write-Host "Command: $CommandPath"
    Write-Host ""

    foreach ($RequiredFile in @("app.py", "pyproject.toml", "uv.lock", "release-manifest.txt")) {
        if (-not (Test-Path -LiteralPath (Join-Path $SourceDir $RequiredFile) -PathType Leaf)) {
            Fail "$RequiredFile was not found."
        }
    }

    New-Item -ItemType Directory -Path $StageDir -Force | Out-Null
    $ManifestPath = Join-Path $SourceDir "release-manifest.txt"
    $Manifest = @(Get-Content -LiteralPath $ManifestPath | Where-Object { $_.Trim().Length -gt 0 })
    foreach ($RelativePath in $Manifest) {
        $Normalized = $RelativePath.Replace("/", "\")
        if ([System.IO.Path]::IsPathRooted($Normalized) -or $Normalized -match '(^|\\)\.\.(\\|$)') {
            Fail "unsafe path in release manifest: $RelativePath"
        }
        $SourcePath = Join-Path $SourceDir $Normalized
        if (-not (Test-Path -LiteralPath $SourcePath -PathType Leaf)) {
            Fail "release file is missing: $RelativePath"
        }
        $StagePath = Join-Path $StageDir $Normalized
        New-Item -ItemType Directory -Path (Split-Path -Parent $StagePath) -Force | Out-Null
        Copy-Item -LiteralPath $SourcePath -Destination $StagePath -Force
    }

    foreach ($RequiredFile in @("app.py", "static\app.js", "static\styles.css")) {
        if (-not (Test-Path -LiteralPath (Join-Path $StageDir $RequiredFile) -PathType Leaf)) {
            Fail "the staged release is incomplete ($RequiredFile)."
        }
    }

    $VersionPath = Join-Path $StageDir "VERSION"
    $Version = if (Test-Path -LiteralPath $VersionPath) { (Get-Content -LiteralPath $VersionPath -Raw).Trim() } else { "unknown" }
    Write-Host "Release: $Version"

    $UvPath = Find-Uv
    if (-not $UvPath) {
        Write-Host "uv was not found; installing it for $env:USERNAME..."
        $UvInstaller = Join-Path $TempRoot "uv-install.ps1"
        Invoke-WebRequest -UseBasicParsing -Uri "https://astral.sh/uv/install.ps1" -OutFile $UvInstaller
        $PreviousInstallDir = $env:UV_INSTALL_DIR
        $PreviousNoModifyPath = $env:UV_NO_MODIFY_PATH
        try {
            $env:UV_INSTALL_DIR = Join-Path $HOME ".local\bin"
            $env:UV_NO_MODIFY_PATH = "1"
            & $UvInstaller
        }
        finally {
            $env:UV_INSTALL_DIR = $PreviousInstallDir
            $env:UV_NO_MODIFY_PATH = $PreviousNoModifyPath
        }
        $UvPath = Find-Uv
        if (-not $UvPath) {
            Fail "uv was installed but could not be located."
        }
    }

    New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
    $PreservedNames = @("files", "data", ".venv")
    Get-ChildItem -LiteralPath $InstallDir -Force | ForEach-Object {
        $Preserve = $PreservedNames -contains $_.Name -or $_.Name -eq ".env" -or $_.Name -like ".env.*"
        if (-not $Preserve) {
            Remove-Item -LiteralPath $_.FullName -Recurse -Force
        }
    }

    foreach ($RelativePath in $Manifest) {
        $Normalized = $RelativePath.Replace("/", "\")
        $InstalledPath = Join-Path $InstallDir $Normalized
        New-Item -ItemType Directory -Path (Split-Path -Parent $InstalledPath) -Force | Out-Null
        Copy-Item -LiteralPath (Join-Path $StageDir $Normalized) -Destination $InstalledPath -Force
    }
    New-Item -ItemType Directory -Path (Join-Path $InstallDir "files") -Force | Out-Null
    New-Item -ItemType Directory -Path (Join-Path $InstallDir "data") -Force | Out-Null

    Write-Host "Verifying installed files..."
    foreach ($RelativePath in $Manifest) {
        $Normalized = $RelativePath.Replace("/", "\")
        $ExpectedHash = (Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $StageDir $Normalized)).Hash
        $ActualPath = Join-Path $InstallDir $Normalized
        if (-not (Test-Path -LiteralPath $ActualPath -PathType Leaf)) {
            Fail "verification failed; installed file is missing: $RelativePath"
        }
        $ActualHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $ActualPath).Hash
        if ($ExpectedHash -ne $ActualHash) {
            Fail "verification failed; installed file differs: $RelativePath"
        }
    }

    New-Item -ItemType Directory -Path $BinDir -Force | Out-Null
    $StableUvPath = Join-Path $BinDir "uv.exe"
    if ((Get-FullPath $UvPath) -ne (Get-FullPath $StableUvPath)) {
        Copy-Item -LiteralPath $UvPath -Destination $StableUvPath -Force
    }

    Write-Host "Syncing the locked uv environment..."
    $env:UV_PROJECT_ENVIRONMENT = Join-Path $InstallDir ".venv"
    & $StableUvPath sync --project $InstallDir --locked --no-dev --python $PythonRequest
    if ($LASTEXITCODE -ne 0) {
        Fail "uv sync failed with exit code $LASTEXITCODE."
    }

    $EscapedInstallDir = $InstallDir.Replace("'", "''")
    $EscapedUvPath = $StableUvPath.Replace("'", "''")
    $Launcher = @"
`$ErrorActionPreference = "Stop"
`$AppDir = '$EscapedInstallDir'
`$UvBin = '$EscapedUvPath'
`$PortValue = if (`$env:NIGHTWIRE_PORT) { `$env:NIGHTWIRE_PORT } elseif (`$env:PORT) { `$env:PORT } else { "8080" }

for (`$Index = 0; `$Index -lt `$args.Count; `$Index++) {
    switch (`$args[`$Index]) {
        { `$_ -in @("-p", "--port") } {
            if (`$Index + 1 -ge `$args.Count) { throw "Missing value after `$_." }
            `$Index++
            `$PortValue = `$args[`$Index]
        }
        { `$_ -in @("-h", "--help") } {
            Write-Host "Usage: nightwire [--port PORT]"
            Write-Host "Start the NightWire LAN file server (default port: 8080)."
            exit 0
        }
        default { throw "Unknown option: `$_" }
    }
}

`$ParsedPort = 0
if (-not [int]::TryParse(`$PortValue, [ref]`$ParsedPort) -or `$ParsedPort -lt 1 -or `$ParsedPort -gt 65535) {
    throw "Port must be a number between 1 and 65535."
}
if (-not (Test-Path -LiteralPath `$AppDir -PathType Container)) { throw "NightWire is not installed at `$AppDir." }
if (-not (Test-Path -LiteralPath `$UvBin -PathType Leaf)) { throw "uv is missing at `$UvBin." }

`$env:PORT = `$ParsedPort.ToString()
`$env:UV_PROJECT_ENVIRONMENT = Join-Path `$AppDir ".venv"
Set-Location -LiteralPath `$AppDir
& `$UvBin run --project `$AppDir --locked --no-sync python app.py
exit `$LASTEXITCODE
"@
    Set-Content -LiteralPath $PowerShellLauncherPath -Value $Launcher -Encoding UTF8

    $CmdLauncher = "@echo off`r`npowershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$PowerShellLauncherPath`" %*`r`n"
    Set-Content -LiteralPath $CommandPath -Value $CmdLauncher -Encoding ASCII

    $UserPath = [Environment]::GetEnvironmentVariable("Path", "User")
    $PathEntries = @($UserPath -split ";" | Where-Object { $_ })
    if (-not ($PathEntries | Where-Object { $_.TrimEnd("\") -ieq $BinDir.TrimEnd("\") })) {
        $NewUserPath = (@($PathEntries) + $BinDir) -join ";"
        [Environment]::SetEnvironmentVariable("Path", $NewUserPath, "User")
        Write-Host "Added $BinDir to your user PATH. Open a new terminal before using nightwire."
    }

    Write-Host ""
    Write-Host "NightWire $Version was installed successfully."
    Write-Host "Start:     nightwire"
    Write-Host "Port:      nightwire --port 9000"
    Write-Host "App:       $InstallDir"
    Write-Host "Uploads:   $(Join-Path $InstallDir 'files')"
    Write-Host "Command:   $CommandPath"
    Write-Host ""
}
finally {
    if (Test-Path -LiteralPath $TempRoot) {
        Remove-Item -LiteralPath $TempRoot -Recurse -Force
    }
}
