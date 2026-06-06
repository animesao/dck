#!/usr/bin/env pwsh
#Requires -Version 5.1
param(
    [string]$InstallDir = "$HOME\.local\bin"
)

$ErrorActionPreference = "Stop"
$App = "dck"
$RepoUrl = "https://gitlab.com/animesao/dck.git"
$PythonMin = [version]"3.10.0"

function Write-Info  { Write-Host "  $args" -ForegroundColor Cyan }
function Write-Ok    { Write-Host "✓ $args" -ForegroundColor Green }
function Write-Warn  { Write-Host "⚠ $args" -ForegroundColor Yellow }
function Write-Err   { Write-Host "✗ $args" -ForegroundColor Red; exit 1 }

Write-Host "`n=== $App Installer ===`n" -ForegroundColor White -BackgroundColor DarkCyan

# ── Check Python ────────────────────────────────────────────────
Write-Host "`nPython" -ForegroundColor White -BackgroundColor DarkGray
$py = $null
foreach ($cmd in @("python3", "python", "py")) {
    try {
        $ver = & $cmd --version 2>&1
        if ($ver -match '(\d+\.\d+\.\d+)') {
            $v = [version]$Matches[1]
            if ($v -ge $PythonMin) { $py = $cmd; break }
        }
    } catch {}
}
if (-not $py) {
    Write-Warn "Python 3.10+ not found."
    $choice = Read-Host "Install Python via winget? (y/n)"
    if ($choice -eq 'y') {
        winget install Python.Python.3.12
        $py = "python"
    } else {
        Write-Err "Install Python manually from https://python.org/downloads"
    }
}
Write-Ok "$(& $py --version)"

# ── Check Git ───────────────────────────────────────────────────
Write-Host "`nGit" -ForegroundColor White -BackgroundColor DarkGray
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Write-Warn "Git not found."
    $choice = Read-Host "Install Git via winget? (y/n)"
    if ($choice -eq 'y') {
        winget install Git.Git
        $env:Path = [System.Environment]::GetEnvironmentVariable("Path","User") + ";$env:Path"
    } else {
        Write-Err "Install Git manually from https://git-scm.com"
    }
}
Write-Ok "Git $(& git --version 2>&1)"

# ── Clone / Update ──────────────────────────────────────────────
Write-Host "`nSource" -ForegroundColor White -BackgroundColor DarkGray
if (Test-Path $App) {
    Write-Warn "Directory '$App' exists. Pulling latest..."
    Push-Location $App; git pull; Pop-Location
} else {
    git clone $RepoUrl
}
Set-Location $App
Write-Ok "Source ready"

# ── Virtual environment ─────────────────────────────────────────
Write-Host "`nVirtual environment" -ForegroundColor White -BackgroundColor DarkGray
if (-not (Test-Path "venv")) {
    & $py -m venv venv
    Write-Ok "Created virtual environment"
} else {
    Write-Ok "Already exists"
}
. .\venv\Scripts\Activate.ps1
$py = "python"
Write-Ok "Using: $(Get-Command $py)"

# ── Install dependencies ────────────────────────────────────────
Write-Host "`nDependencies" -ForegroundColor White -BackgroundColor DarkGray
& $py -m pip install --quiet --upgrade pip
& $py -m pip install --quiet build
Write-Ok "pip updated, build installed"

# ── Install dck ─────────────────────────────────────────────────
Write-Host "`nInstalling $App" -ForegroundColor White -BackgroundColor DarkGray
& $py -m pip install --quiet -e .
Write-Ok "$App installed"

# ── Add to PATH ─────────────────────────────────────────────────
Write-Host "`nPATH" -ForegroundColor White -BackgroundColor DarkGray
$targetPath = Join-Path (Get-Location) "venv\Scripts\$App.exe"
$installPath = Join-Path $InstallDir "$App.exe"
New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
Copy-Item -Path $targetPath -Destination $installPath -Force
Write-Ok "Copied to $installPath"

$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($userPath -notlike "*$InstallDir*") {
    $newPath = "$userPath;$InstallDir"
    [Environment]::SetEnvironmentVariable("Path", $newPath, "User")
    $env:Path = $env:Path + ";$InstallDir"
    Write-Warn "Added $InstallDir to PATH. Restart terminal or run: `$env:Path += ';$InstallDir'"
} else {
    Write-Ok "$InstallDir already in PATH"
}

# ── Cleanup ─────────────────────────────────────────────────────
Write-Host "`nCleanup" -ForegroundColor White -BackgroundColor DarkGray
Remove-Item -Recurse -Force build, dist, *.egg-info -ErrorAction SilentlyContinue
Get-ChildItem -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
Get-ChildItem -Recurse -Filter "*.pyc" | Remove-Item -Force -ErrorAction SilentlyContinue
Write-Ok "Temporary files removed"

# ── Done ────────────────────────────────────────────────────────
Write-Host "`n=== Done ===" -ForegroundColor White -BackgroundColor DarkGreen
Write-Ok "$App installed successfully!"
Write-Info "Run: $App doctor"
Write-Info "Or:  $App --help"
