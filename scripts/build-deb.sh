#!/bin/sh
# Build dck .deb package for Debian/Ubuntu
set -e

DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$DIR"

VERSION=$(cat VERSION 2>/dev/null | head -1 | tr -d '[:space:]')
: "${VERSION:=1.10.0}"

echo "==> Building dck v$VERSION for linux/amd64..."

# Ensure Go exists
if ! command -v go >/dev/null 2>&1; then
    echo "Error: Go not found. Install Go >= 1.18"
    exit 1
fi

# Clean any previous build
rm -f dck dist/*.deb

# Build the binary
echo "==> Compiling..."
CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -ldflags="-s -w -X dck/cmd.version=$VERSION" -o dck .

mkdir -p dist

# Prepare package directory
PKG_ROOT="packaging/deb"
PKG_DIR="$PKG_ROOT"
BIN_DEST="$PKG_DIR/usr/bin"

# Copy binary
install -d "$BIN_DEST"
install -m 755 dck "$BIN_DEST/dck"

# Set permissions
chmod 755 "$PKG_DIR/DEBIAN/postinst"
chmod 755 "$PKG_DIR/DEBIAN/prerm"

# Build .deb
echo "==> Building .deb package..."
fakeroot dpkg-deb --build "$PKG_DIR" "dist/dck_${VERSION}_amd64.deb" 2>/dev/null || \
dpkg-deb --build "$PKG_DIR" "dist/dck_${VERSION}_amd64.deb"

# Clean up binary from package dir
rm -f "$BIN_DEST/dck"
rm -f dck

echo ""
echo "   Package: dist/dck_${VERSION}_amd64.deb"
echo "   Size:    $(ls -lh "dist/dck_${VERSION}_amd64.deb" | awk '{print $5}')"
echo ""
echo "Install:"
echo "   sudo dpkg -i dist/dck_${VERSION}_amd64.deb"
echo "   sudo apt-get install -f   # install dependencies"
