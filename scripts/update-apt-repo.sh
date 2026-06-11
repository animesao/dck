#!/bin/bash
# Generate APT repository metadata in docs/apt/
# Called by GitHub Actions after building .deb
set -e

DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$DIR"

VERSION=$(cat VERSION | head -1 | tr -d '[:space:]')
APT_DIR="docs/apt"

mkdir -p "$APT_DIR"

# Copy .deb into apt repo
cp "dist/dck_${VERSION}_amd64.deb" "$APT_DIR/"

# Generate Packages
cd "$APT_DIR"
> Packages
for deb in *.deb; do
    SIZE=$(stat -c%s "$deb" 2>/dev/null || stat -f%z "$deb" 2>/dev/null)
    SHA256=$(sha256sum "$deb" | cut -d' ' -f1)
    {
        echo "Package: dck"
        echo "Version: ${VERSION}"
        echo "Architecture: amd64"
        echo "Maintainer: animesao <animesao@users.noreply.github.com>"
        echo "Filename: $deb"
        echo "Size: $SIZE"
        echo "SHA256: $SHA256"
        echo "Description: dck - lightweight container runtime"
        echo " No daemon. No Docker. Just containers."
        echo ""
    } >> Packages
done
gzip -9fk Packages

# Generate Release file
NOW=$(date -u +"%a, %d %b %Y %H:%M:%S UTC")
cat > Release <<EOF
Origin: dck
Label: dck APT Repository
Suite: stable
Codename: dck
Date: $NOW
Architectures: amd64
Description: dck lightweight container runtime
SHA256:
 $(sha256sum Packages | cut -d' ' -f1) $(stat -c%s "Packages" 2>/dev/null || stat -f%z "Packages" 2>/dev/null) Packages
 $(sha256sum Packages.gz | cut -d' ' -f1) $(stat -c%s "Packages.gz" 2>/dev/null || stat -f%z "Packages.gz" 2>/dev/null) Packages.gz
EOF

# Generate InRelease (unsigned - apt will show a warning but work with trusted=yes)
cp Release InRelease

echo "APT repo updated at $APT_DIR"
