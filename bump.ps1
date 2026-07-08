# Bump version: reads latest tag vX.Y.Z, increments Z, tags and pushes
$ErrorActionPreference = "Stop"

# Get latest tag matching v*.*.*
$tags = git tag --list 'v*.*.*' --sort=-version:refname
if (-not $tags) {
    $newVer = "v1.21.0"
} else {
    $latest = $tags[0]
    $parts = $latest.TrimStart("v").Split(".")
    $patch = [int]$parts[2] + 1
    $newVer = "v$($parts[0]).$($parts[1]).$patch"
}

Write-Host "New version: $newVer"

# Update VERSION file
$newVer.TrimStart("v") | Set-Content VERSION -NoNewline

git add VERSION
git commit -m "chore: bump version to $newVer"

git tag $newVer
git push origin main --tags

Write-Host "Done. CI will build and create release for $newVer"
