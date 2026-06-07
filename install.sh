#!/usr/bin/env bash
set -euo pipefail

APP="dck"
REPO_URL="https://github.com/animesao/dck.git"
INSTALL_DIR="${INSTALL_DIR:-$HOME/.local/bin}"

if [ "$(id -u)" -eq 0 ]; then
    INSTALL_DIR="/usr/local/bin"
fi

BOLD='\033[1m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m'

info()  { printf "${CYAN}%s${NC}\n" "$*"; }
ok()    { printf "${GREEN}✓ %s${NC}\n" "$*"; }
warn()  { printf "${YELLOW}⚠ %s${NC}\n" "$*"; }
err()   { printf "${RED}✗ %s${NC}\n" "$*"; exit 1; }
header(){ printf "\n${BOLD}=== %s ===${NC}\n\n" "$*"; }
pkg()   {
    case "$PKG_MGR" in
        apt)    $SUDO apt-get install --no-install-recommends -y "$@" ;;
        dnf)    $SUDO dnf install -y "$@" ;;
        pacman) $SUDO pacman -S --noconfirm "$@" ;;
        zypper) $SUDO zypper install -y "$@" ;;
        brew)   brew install "$@" ;;
    esac
}

cleanup() {
    rm -rf build/ dist/ *.egg-info __pycache__/ 2>/dev/null || true
    find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
    find . -type f -name "*.pyc" -delete 2>/dev/null || true
}
trap cleanup EXIT

OS="$(uname -s)"
ARCH="$(uname -m)"
info "System: ${OS} ${ARCH}"

# ── Detect package manager ────────────────────────────────────
PKG_MGR=""
case "$OS" in
    Linux)
        if   command -v apt-get &>/dev/null; then PKG_MGR="apt"
        elif command -v dnf    &>/dev/null; then PKG_MGR="dnf"
        elif command -v pacman &>/dev/null; then PKG_MGR="pacman"
        elif command -v zypper &>/dev/null; then PKG_MGR="zypper"
        fi ;;
    Darwin) PKG_MGR="brew" ;;
    *)      err "Unsupported OS: $OS" ;;
esac

SUDO=""
if [ "$(id -u)" -ne 0 ] && command -v sudo &>/dev/null; then
    SUDO="sudo"
fi

# ── Python ──────────────────────────────────────────────────────
header "Python"
PYTHON=""
for cmd in python3 python; do
    if command -v "$cmd" &>/dev/null; then
        ver="$($cmd --version 2>&1 | grep -oP '\d+\.\d+')"
        major="${ver%.*}"; minor="${ver#*.}"
        if [ "$major" -ge 3 ] && [ "$minor" -ge 10 ]; then
            PYTHON="$cmd"
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    warn "Python 3.10+ not found. Installing..."
    case "$PKG_MGR" in
        apt|dnf|zypper) pkg python3 python3-pip ;;
        pacman) pkg python python-pip ;;
        brew)   pkg python@3.12 ;;
        *)      err "Install Python 3.10+ manually: https://python.org/downloads" ;;
    esac
    PYTHON="python3"
fi
ok "$($PYTHON --version)"

# ── Runtime dependencies ─────────────────────────────────────────
header "Container runtime dependencies"
for cmd in ip iptables nsenter; do
    if ! command -v "$cmd" &>/dev/null; then
        case "$PKG_MGR" in
            apt)    pkg iproute2 iptables util-linux 2>/dev/null || true ;;
            dnf)    pkg iproute iptables util-linux 2>/dev/null || true ;;
            pacman) pkg iproute2 iptables util-linux 2>/dev/null || true ;;
            zypper) pkg iproute2 iptables util-linux 2>/dev/null || true ;;
            brew)   warn "Install manually: brew install iproute2mac iptables util-linux" ;;
        esac
    fi
done
for cmd in ip iptables nsenter; do
    command -v "$cmd" &>/dev/null && ok "$cmd" || warn "Missing: $cmd"
done

# ── Kernel checks ─────────────────────────────────────────────────
if [ "$OS" = "Linux" ] && [ "$(id -u)" -eq 0 ]; then
    if ! grep -q overlay /proc/filesystems 2>/dev/null; then
        modprobe overlay 2>/dev/null && ok "OverlayFS module loaded" || warn "Could not load overlay module"
    fi
    if [ ! -f /sys/fs/cgroup/cgroup.controllers ]; then
        warn "cgroups v2 not active — resource limits will not work"
    else
        ok "cgroups v2"
    fi
fi

# ── Clone / Update ──────────────────────────────────────────────
header "Getting source"
if [ -d "$APP" ]; then
    warn "Directory '$APP' exists. Pulling latest..."
    cd "$APP" && git pull
else
    git clone "$REPO_URL"
    cd "$APP"
fi
ok "Source ready"

# ── Install ─────────────────────────────────────────────────────
header "Installing ${APP}"

$PYTHON -m pip install --upgrade pip --quiet 2>/dev/null || true

if $PYTHON -m pip install --no-cache-dir -e . 2>&1 | tail -3; then
    :  # success
elif $PYTHON -m pip install --no-cache-dir . 2>&1 | tail -3; then
    :  # success
elif $PYTHON -m pip install --no-cache-dir --no-build-isolation -e . 2>&1 | tail -3; then
    :  # success
elif $PYTHON -m pip install --no-cache-dir --no-build-isolation . 2>&1 | tail -3; then
    :  # success
else
    err "pip install failed — run manually: cd $(pwd) && pip install ."
fi

CLI_PATH=$(command -v "$APP" 2>/dev/null) || true
if [ -n "$CLI_PATH" ]; then
    mkdir -p "$INSTALL_DIR"
    ln -sf "$CLI_PATH" "${INSTALL_DIR}/${APP}" 2>/dev/null || true
    ok "Linked to ${INSTALL_DIR}/${APP}"
fi

if [[ ":$PATH:" != *":${INSTALL_DIR}:"* ]]; then
    warn "Add ${INSTALL_DIR} to your PATH, then reload:"
    echo "  echo 'export PATH=\"\$PATH:${INSTALL_DIR}\"' >> ~/.bashrc"
    echo "  source ~/.bashrc"
fi

# ── Done ────────────────────────────────────────────────────────
header "Done"
ok "${APP} installed successfully!"
info "Run: ${APP} --help"
