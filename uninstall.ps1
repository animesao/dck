param(
    [switch]$Force
)

$Host.UI.RawUI.ForegroundColor = "Green"
Write-Host "[dck] Uninstalling dck..."
$Host.UI.RawUI.ForegroundColor = "White"

$InstallDir = "$env:USERPROFILE\.dck\bin"
$BinPath = "$InstallDir\dck.exe"

if (Test-Path $BinPath) {
    Remove-Item -Force $BinPath
    Write-Host "[dck] Removed $BinPath" -ForegroundColor Green
} else {
    Write-Host "[dck] dck.exe not found at $BinPath" -ForegroundColor Yellow
}

$DckDir = "$env:USERPROFILE\.dck"
if (Test-Path $DckDir) {
    if ($Force) {
        $confirm = "y"
    } else {
        Write-Host "WARNING: This will DELETE all images, containers, and data." -ForegroundColor Red
        $confirm = Read-Host "Remove $DckDir? [y/N]"
    }
    if ($confirm -eq "y" -or $confirm -eq "Y") {
        Remove-Item -Recurse -Force $DckDir
        Write-Host "[dck] Removed $DckDir" -ForegroundColor Green
    } else {
        Write-Host "[dck] Skipped $DckDir" -ForegroundColor Yellow
    }
}

$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($userPath -like "*$InstallDir*") {
    $newPath = ($userPath -split ";" | Where-Object { $_ -ne $InstallDir }) -join ";"
    [Environment]::SetEnvironmentVariable("Path", $newPath, "User")
    Write-Host "[dck] Removed $InstallDir from PATH" -ForegroundColor Green
}

Write-Host "[dck] dck uninstalled." -ForegroundColor Green
