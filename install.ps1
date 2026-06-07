param(
    [string]$InstallDir = "$env:USERPROFILE\.dck\bin",
    [switch]$NoPath
)

$Host.UI.RawUI.ForegroundColor = "Green"
Write-Host "[dck] dck - Simple Container Runtime Installer"
$Host.UI.RawUI.ForegroundColor = "White"
Write-Host ""

$DckDir = "$env:USERPROFILE\.dck"
$BinPath = "$InstallDir\dck.exe"

$Host.UI.RawUI.ForegroundColor = "Green"
Write-Host "[dck] Installing to: $BinPath"
$Host.UI.RawUI.ForegroundColor = "White"

if (-not (Get-Command go -ErrorAction SilentlyContinue)) {
    $Host.UI.RawUI.ForegroundColor = "Yellow"
    Write-Host "[dck] Go not found. Downloading Go installer..."
    $Host.UI.RawUI.ForegroundColor = "White"

    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        $goUrl = "https://go.dev/dl/go1.22.5.windows-amd64.msi"
        $goInstaller = "$env:TEMP\go.msi"
        try {
            [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
            Invoke-WebRequest -Uri $goUrl -OutFile $goInstaller -UseBasicParsing
            Write-Host "[dck] Installing Go (requires admin)..."
            Start-Process msiexec -ArgumentList "/i `"$goInstaller`" /quiet /norestart" -Wait
            $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")
        } catch {
            Write-Host "[dck] Go installation failed. Install manually from https://go.dev/dl/" -ForegroundColor Red
            exit 1
        }
    } else {
        Write-Host "[dck] Installing Go via winget..."
        winget install GoLang.Go --silent --accept-package-agreements
        $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")
    }

    if (-not (Get-Command go -ErrorAction SilentlyContinue)) {
        Write-Host "[dck] Please restart the script after Go installation." -ForegroundColor Yellow
        exit 1
    }
    Write-Host "[dck] Go installed: $(go version)" -ForegroundColor Green
}

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

Write-Host "[dck] Building dck..."
$env:CGO_ENABLED = "0"
go build -ldflags="-s -w" -o dck.exe .

if (-not (Test-Path $InstallDir)) {
    New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
}

Move-Item -Force dck.exe "$BinPath"
Write-Host "[dck] Binary installed to $BinPath" -ForegroundColor Green

if (-not $NoPath) {
    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    if ($userPath -notlike "*$InstallDir*") {
        [Environment]::SetEnvironmentVariable("Path", "$userPath;$InstallDir", "User")
        Write-Host "[dck] Added to PATH (user)" -ForegroundColor Yellow
        Write-Host "[dck] Restart terminal or run: `$env:Path += ';$InstallDir'" -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "[dck] Installation complete!" -ForegroundColor Green
Write-Host ""
Write-Host "[dck] Quick start:"
Write-Host "[dck]   dck pull alpine"
Write-Host "[dck]   dck run --rm alpine echo hello"
Write-Host "[dck]   dck --help"
Write-Host ""
