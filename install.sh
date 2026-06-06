#!/usr/bin/env bash
set -euo pipefail

APP="dck"
REPO_URL="https://gitlab.com/animesao/dck.git"
INSTALL_DIR="${INSTALL_DIR:-$HOME/.local/bin}"

# Root? use /usr/local/bin
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

cleanup() {
    header "Cleaning up"
    rm -rf build/ dist/ *.egg-info __pycache__/ 2>/dev/null || true
    find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
    find . -type f -name "*.pyc" -delete 2>/dev/null || true
    ok "Temporary build files removed"
}
trap cleanup EXIT

OS="$(uname -s)"
ARCH="$(uname -m)"
info "OS: ${OS} | Arch: ${ARCH}"

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
        apt)    $SUDO apt-get update && $SUDO apt-get install -y python3 python3-pip python3-venv ;;
        dnf)    $SUDO dnf install -y python3 python3-pip ;;
        pacman) $SUDO pacman -S --noconfirm python python-pip ;;
        zypper) $SUDO zypper install -y python3 python3-pip ;;
        brew)   brew install python@3.12 ;;
        *)      err "Install Python 3.10+ manually: https://python.org/downloads" ;;
    esac
    PYTHON="python3"
fi
ok "$($PYTHON --version)"

# Ensure python3-venv on Debian/Ubuntu
if [ "$PKG_MGR" = "apt" ]; then
    if ! dpkg -s python3-venv &>/dev/null 2>&1; then
        info "Installing python3-venv..."
        $SUDO apt-get install -y python3-venv
    fi
fi

# ── Git ─────────────────────────────────────────────────────────
header "Git"
if ! command -v git &>/dev/null; then
    warn "Git not found. Installing..."
    case "$PKG_MGR" in
        apt)    $SUDO apt-get install -y git ;;
        dnf)    $SUDO dnf install -y git ;;
        pacman) $SUDO pacman -S --noconfirm git ;;
        zypper) $SUDO zypper install -y git ;;
        brew)   brew install git ;;
    esac
fi
ok "Git $(git --version 2>&1 | grep -oP '\d+\.\d+\.\d+')"

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

USE_VENV=true
# Try venv first; fall back to global pip if it fails
if [ -d "venv" ] && [ ! -f "venv/bin/activate" ]; then
    warn "Corrupted venv found — removing and recreating"
    rm -rf venv
fi

if [ ! -d "venv" ] && [ "$USE_VENV" = true ]; then
    if $PYTHON -m venv venv 2>/dev/null; then
        source venv/bin/activate
        PYTHON="python"
        ok "Virtual environment created"
    else
        warn "venv creation failed — installing globally"
        USE_VENV=false
    fi
elif [ -d "venv" ]; then
    source venv/bin/activate
    PYTHON="python"
    ok "Using existing virtual environment"
fi

$PYTHON -m pip install --upgrade pip 2>&1 | tail -2 || true

info "Installing dependencies (docker-py, click, rich... this may take a minute)..."
$PYTHON -m pip install -e .
ok "${APP} installed"

# ── Add to PATH ─────────────────────────────────────────────────
header "Adding to PATH"
mkdir -p "$INSTALL_DIR"

if [ "$USE_VENV" = true ]; then
    ln -sf "$(pwd)/venv/bin/${APP}" "${INSTALL_DIR}/${APP}" 2>/dev/null || true
else
    # Find where pip installed the binary
    CLI_PATH="$($PYTHON -c "import sys; print(sys.argv[0])" 2>/dev/null)" || true
    BIN_PATH=$(command -v "$APP" 2>/dev/null) || true
    if [ -n "$BIN_PATH" ]; then
        ln -sf "$BIN_PATH" "${INSTALL_DIR}/${APP}" 2>/dev/null || true
    fi
fi
ok "Linked to ${INSTALL_DIR}/${APP}"

if [[ ":$PATH:" != *":${INSTALL_DIR}:"* ]]; then
    warn "Add ${INSTALL_DIR} to your PATH, then reload:"
    echo "  echo 'export PATH=\"\$PATH:${INSTALL_DIR}\"' >> ~/.bashrc"
    echo "  source ~/.bashrc"
fi

# ── Done ────────────────────────────────────────────────────────
header "Done"
ok "${APP} installed successfully!"
info "Run this (or open new terminal):"
info "  export PATH=\"\$PATH:${INSTALL_DIR}\""
info ""
info "Then use:"
info "  ${APP} doctor"
info "  ${APP} --help"
