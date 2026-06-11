#!/bin/sh
# Add dck APT repository and install
# Usage: curl -sSL https://raw.githubusercontent.com/animesao/dck/main/scripts/add-apt-repo.sh | sudo bash
set -e

if [ "$(id -u)" != "0" ]; then
    echo "This script must be run as root (or with sudo)."
    exit 1
fi

# Check if GitHub Pages is reachable
REPO_URL="https://animesao.github.io/dck"
echo "Checking APT repository availability..."
if curl -sSL -o /dev/null -w "%{http_code}" "$REPO_URL/Release" 2>/dev/null | grep -q "200"; then
    echo "Adding dck APT repository..."
    echo "deb [trusted=yes] $REPO_URL ./" > /etc/apt/sources.list.d/dck.list
    apt update -qq
    apt install -y dck
    echo "dck installed successfully!"
else
    echo "APT repository not yet available."
    echo "GitHub Pages may not be enabled for this repository."
    echo ""
    echo "Falling back to direct .deb download..."
    curl -sSL https://raw.githubusercontent.com/animesao/dck/main/scripts/install-apt.sh | sudo bash
fi
