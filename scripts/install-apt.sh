#!/bin/sh
# Install dck via APT repository
# Usage: curl -sSL https://raw.githubusercontent.com/animesao/dck/main/scripts/install-apt.sh | sudo bash
set -e

BOLD=$(tput bold 2>/dev/null || echo "")
RESET=$(tput sgr2 2>/dev/null || echo "")
GREEN=$(tput setaf 2 2>/dev/null || echo "")

info() { echo "${BOLD}${GREEN}[dck]${RESET} $*"; }

if [ "$(id -u)" != "0" ]; then
    echo "This script must be run as root (or with sudo)."
    exit 1
fi

# Detect latest version from GitHub API
info "Detecting latest version..."
LATEST=$(curl -sSL https://api.github.com/repos/animesao/dck/releases/latest 2>/dev/null | \
    grep '"tag_name"' | head -1 | sed 's/.*"tag_name": "\(.*\)".*/\1/' | tr -d 'v')

if [ -z "$LATEST" ]; then
    LATEST="1.10.0"
    info "Using fallback version: $LATEST"
fi

info "Downloading dck v$LATEST..."
DEB_URL="https://github.com/animesao/dck/releases/download/${LATEST}/dck_${LATEST}_amd64.deb"

TMPDIR=$(mktemp -d)
cd "$TMPDIR"

curl -sSL -o dck.deb "$DEB_URL" || {
    # Try with v prefix
    DEB_URL="https://github.com/animesao/dck/releases/download/v${LATEST}/dck_${LATEST}_amd64.deb"
    curl -sSL -o dck.deb "$DEB_URL" || {
        echo "Failed to download: $DEB_URL"
        exit 1
    }
}

info "Installing..."
dpkg -i dck.deb 2>/dev/null || apt-get install -f -y -qq

rm -rf "$TMPDIR"

info "dck v$LATEST installed!"
