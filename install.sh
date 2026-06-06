#!/usr/bin/env bash
set -euo pipefail

APP="dck"
REPO_URL="https://gitlab.com/animesao/dck.git"
INSTALL_DIR="${INSTALL_DIR:-$HOME/.local/bin}"

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

header() {
    printf "\n${BOLD}=== %s ===${NC}\n\n" "$*"
}

cleanup() {
    header "Cleaning up"
    rm -rf build/ dist/ *.egg-info __pycache__/
    find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
    find . -type f -name "*.pyc" -delete 2>/dev/null || true
    ok "Temporary build files removed"
}

trap cleanup EXIT

# ── Detect OS ──────────────────────────────────────────────────
OS="$(uname -s)"
ARCH="$(uname -m)"
info "OS: ${OS} | Arch: ${ARCH}"

case "$OS" in
    Linux)  PKG_MGR=""
            if command -v apt-get &>/dev/null; then PKG_MGR="apt"
            elif command -v dnf &>/dev/null; then PKG_MGR="dnf"
            elif command -v pacman &>/dev/null; then PKG_MGR="pacman"
            elif command -v zypper &>/dev/null; then PKG_MGR="zypper"
            fi ;;
    Darwin) PKG_MGR="brew" ;;
    *)      err "Unsupported OS: $OS" ;;
esac

# ── Check / Install Python ─────────────────────────────────────
header "Python"

PYTHON=""
for cmd in python3 python; do
    if command -v "$cmd" &>/dev/null; then
        ver="$($cmd --version 2>&1 | grep -oP '\d+\.\d+')"
        major="${ver%.*}"
        minor="${ver#*.}"
        if [ "$major" -ge 3 ] && [ "$minor" -ge 10 ]; then
            PYTHON="$cmd"
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    warn "Python 3.10+ not found."
    if [ -n "$PKG_MGR" ]; then
        info "Installing Python via ${PKG_MGR}..."
        case "$PKG_MGR" in
            apt)    sudo apt-get update && sudo apt-get install -y python3 python3-pip python3-venv ;;
            dnf)    sudo dnf install -y python3 python3-pip ;;
            pacman) sudo pacman -S --noconfirm python python-pip ;;
            zypper) sudo zypper install -y python3 python3-pip ;;
            brew)   brew install python@3.12 ;;
        esac
        PYTHON="python3"
    else
        err "Install Python 3.10+ manually: https://python.org/downloads"
    fi
fi
ok "$($PYTHON --version)"

# ── Check / Install Git ────────────────────────────────────────
header "Git"
if ! command -v git &>/dev/null; then
    warn "Git not found. Installing..."
    case "$PKG_MGR" in
        apt)    sudo apt-get install -y git ;;
        dnf)    sudo dnf install -y git ;;
        pacman) sudo pacman -S --noconfirm git ;;
        zypper) sudo zypper install -y git ;;
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

# ── Create venv (optional) ─────────────────────────────────────
header "Virtual environment"
if [ ! -d "venv" ]; then
    $PYTHON -m venv venv
    ok "Created virtual environment"
else
    ok "Virtual environment already exists"
fi
source venv/bin/activate
PYTHON="python"
ok "Using: $(which $PYTHON)"

# ── Upgrade pip & install dependencies ─────────────────────────
header "Dependencies"
$PYTHON -m pip install --quiet --upgrade pip
$PYTHON -m pip install --quiet build
ok "pip updated, build installed"

# ── Install dck ────────────────────────────────────────────────
header "Installing ${APP}"
$PYTHON -m pip install --quiet -e .
ok "${APP} installed"

# ── Install to PATH (symlink) ──────────────────────────────────
header "Adding to PATH"
mkdir -p "$INSTALL_DIR"
ln -sf "$(pwd)/venv/bin/${APP}" "${INSTALL_DIR}/${APP}" 2>/dev/null || true
if [[ ":$PATH:" != *":${INSTALL_DIR}:"* ]]; then
    warn "Add ${INSTALL_DIR} to your PATH:"
    printf "  echo 'export PATH=\"\$PATH:%s\"' >> ~/.bashrc\n" "$INSTALL_DIR"
    printf "  source ~/.bashrc\n"
fi
ok "Symlinked to ${INSTALL_DIR}/${APP}"

# ── Done ────────────────────────────────────────────────────────
header "Done"
ok "${APP} installed successfully!"
info "Run: ${APP} doctor"
info "Or:  ${APP} --help"
