#!/bin/sh
# Add dck APT repository (GitHub Pages — main branch, /docs folder)
# Usage: curl -sSL https://raw.githubusercontent.com/animesao/dck/main/scripts/add-apt-repo.sh | sudo bash
set -e

if [ "$(id -u)" != "0" ]; then
    echo "This script must be run as root (or with sudo)."
    exit 1
fi

echo "Adding dck APT repository..."
echo "deb [trusted=yes] https://animesao.github.io/dck/apt ./" > /etc/apt/sources.list.d/dck.list

echo "Updating package lists..."
apt update -qq

echo "Installing dck..."
apt install -y dck
