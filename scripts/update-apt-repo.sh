#!/bin/bash
# Generate APT repository metadata in docs/apt/
# Called by GitHub Actions after building .deb
set -e

DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$DIR"

VERSION=$(cat VERSION | head -1 | tr -d '[:space:]')
APT_DIR="docs/apt"

mkdir -p "$APT_DIR/binary-amd64"

# Copy .deb into apt repo
cp "dist/dck_${VERSION}_amd64.deb" "$APT_DIR/binary-amd64/"

# Generate Packages.gz
cd "$APT_DIR/binary-amd64"
dpkg-scanpackages -m . /dev/null > Packages 2>/dev/null || {
    # Fallback: manual Packages generation
    echo "dpkg-scanpackages not found, generating manually..."
    > Packages
    for deb in *.deb; do
        SIZE=$(stat -c%s "$deb" 2>/dev/null || stat -f%z "$deb" 2>/dev/null)
        SHA256=$(sha256sum "$deb" | cut -d' ' -f1)
        echo "Package: dck
Version: ${VERSION}
Architecture: amd64
Maintainer: animesao <animesao@users.noreply.github.com>
Filename: binary-amd64/$deb
Size: $SIZE
SHA256: $SHA256
Description: dck - lightweight container runtime
 No daemon. No Docker. Just containers.

" >> Packages
    done
}
gzip -9fk Packages

cd "$DIR/$APT_DIR"

# Generate Release file
NOW=$(date -u +"%a, %d %b %Y %H:%M:%S UTC")
SIZE_PKG=$(stat -c%s "binary-amd64/Packages.gz" 2>/dev/null || stat -f%z "binary-amd64/Packages.gz" 2>/dev/null)
SHA256_PKG=$(sha256sum "binary-amd64/Packages.gz" | cut -d' ' -f1)
SHA256_PKG_RAW=$(sha256sum "binary-amd64/Packages" | cut -d' ' -f1)

cat > Release <<EOF
Origin: dck
Label: dck APT Repository
Suite: stable
Codename: dck
Date: $NOW
Architectures: amd64
Components: binary
Description: dck lightweight container runtime
SHA256:
 $(sha256sum binary-amd64/Packages | cut -d' ' -f1) $(stat -c%s "binary-amd64/Packages" 2>/dev/null || stat -f%z "binary-amd64/Packages" 2>/dev/null) binary-amd64/Packages
 $(sha256sum binary-amd64/Packages.gz | cut -d' ' -f1) $(stat -c%s "binary-amd64/Packages.gz" 2>/dev/null || stat -f%z "binary-amd64/Packages.gz" 2>/dev/null) binary-amd64/Packages.gz
EOF

# Generate InRelease (unsigned - apt will show a warning but work with trusted=yes)
cp Release InRelease

echo "APT repo updated at $APT_DIR"
