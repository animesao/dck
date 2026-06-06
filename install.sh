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
    header "Cleaning up"
    rm -rf build/ dist/ *.egg-info __pycache__/ 2>/dev/null || true
    find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
    find . -type f -name "*.pyc" -delete 2>/dev/null || true
    ok "Temporary build files removed"
}
trap cleanup EXIT

OS="$(uname -s)"
ARCH="$(uname -m)"
DISTRO=""
if [ "$OS" = "Linux" ]; then
    if [ -f /etc/os-release ]; then
        DISTRO="$(grep -oP 'PRETTY_NAME="\K[^"]+' /etc/os-release)"
    elif command -v lsb_release &>/dev/null; then
        DISTRO="$(lsb_release -d 2>/dev/null | cut -f2)"
    fi
fi
[ -z "$DISTRO" ] && DISTRO="$OS"
info "System: ${DISTRO} | Arch: ${ARCH}"

# ── Language ────────────────────────────────────────────────────
LANG_CHOICE="en"
if [ -t 0 ]; then
    printf "\n%s" "Select language / Выберите язык [en/ru] (en): "
    read -r lang_choice
    [ "$lang_choice" = "ru" ] && LANG_CHOICE="ru"
fi
[ "$LANG_CHOICE" = "ru" ] && info "Язык: Русский" || info "Language: English"

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

# ── Update system packages ─────────────────────────────────────
header "System update"
case "$PKG_MGR" in
    apt)    $SUDO apt-get update -qq && $SUDO apt-get upgrade -y --no-install-recommends 2>/dev/null || warn "apt update/upgrade failed" ;;
    dnf)    $SUDO dnf upgrade -y 2>/dev/null || warn "dnf upgrade failed" ;;
    pacman) $SUDO pacman -Syu --noconfirm 2>/dev/null || warn "pacman update failed" ;;
    zypper) $SUDO zypper update -y 2>/dev/null || warn "zypper update failed" ;;
    brew)   brew update 2>/dev/null || warn "brew update failed" ;;
esac
ok "System packages updated"

# ── Base dependencies (ca-certificates for HTTPS) ──────────────
header "Base dependencies"
case "$PKG_MGR" in
    apt|dnf|zypper) pkg ca-certificates 2>/dev/null || true ;;
    pacman) pkg ca-certificates ca-certificates-utils 2>/dev/null || true ;;
    brew) true ;;
esac
ok "SSL certificates ready"

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
        apt|dnf|pacman|zypper) pkg python3 python3-pip ;;
        brew)   pkg python@3.12 ;;
        *)      err "Install Python 3.10+ manually: https://python.org/downloads" ;;
    esac
    PYTHON="python3"
fi
ok "$($PYTHON --version)"

# Ensure python3-venv on Debian/Ubuntu (best-effort, fallback if unavailable)
VENV_MODULE_AVAIL=true
$PYTHON -m venv -h &>/dev/null || VENV_MODULE_AVAIL=false

# ── curl ────────────────────────────────────────────────────────
header "curl"
if ! command -v curl &>/dev/null; then
    warn "curl not found. Installing..."
    pkg curl
fi
ok "curl"

# ── Git ─────────────────────────────────────────────────────────
header "Git"
if ! command -v git &>/dev/null; then
    warn "Git not found. Installing..."
    pkg git
fi
ok "Git $(git --version 2>&1 | grep -oP '\d+\.\d+\.\d+')"

# ── Docker ──────────────────────────────────────────────────────
header "Docker"
DOCKER_OK=true
if ! command -v docker &>/dev/null; then
    warn "Docker not found."
    if [ -t 0 ]; then
        if [ "$LANG_CHOICE" = "ru" ]; then
            printf "%s" "  Установить Docker сейчас? [Y/n]: "
        else
            printf "%s" "  Install Docker now? [Y/n]: "
        fi
        read -r docker_choice
        case "$docker_choice" in
            n|N|no|NO) DOCKER_OK=false ;;
            *)         DOCKER_OK=true  ;;
        esac
    else
        DOCKER_OK=true
    fi

    if [ "$DOCKER_OK" = true ]; then
        info "Installing Docker..."
        if command -v curl &>/dev/null; then
            curl -fsSL https://get.docker.com | sh || {
                warn "get.docker.com failed — trying package manager..."
                pkg docker 2>/dev/null || brew install --cask docker 2>/dev/null || true
            }
        else
            pkg docker 2>/dev/null || brew install --cask docker 2>/dev/null || true
        fi
    fi
fi

if command -v docker &>/dev/null; then
    ok "$(docker --version 2>&1 | head -1)"

    # Start and enable Docker daemon (Linux)
    if [ "$OS" = "Linux" ] && ! docker info &>/dev/null; then
        info "Starting Docker daemon..."
        if command -v systemctl &>/dev/null; then
            $SUDO systemctl enable --now docker 2>/dev/null || true
        elif command -v service &>/dev/null; then
            $SUDO service docker start 2>/dev/null || true
        fi
        sleep 2
    fi

    # Add user to docker group if not root
    if [ "$(id -u)" -ne 0 ] && command -v groups &>/dev/null; then
        if ! groups "$USER" 2>/dev/null | grep -q docker; then
            warn "Adding user to 'docker' group (you may need to re-login)"
            $SUDO usermod -aG docker "$USER" 2>/dev/null || true
        fi
    fi

    if docker info &>/dev/null; then
        ok "Docker daemon is running"
    else
        warn "Docker daemon is not running — start it manually"
    fi
else
    warn "Docker not installed. Some dck commands will not work."
    warn "Install Docker manually: https://docs.docker.com/engine/install/"
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

USE_VENV=true
if [ -d "venv" ] && [ ! -f "venv/bin/activate" ]; then
    warn "Corrupted venv found — removing and recreating"
    rm -rf venv
fi

if [ ! -d "venv" ]; then
    ok "Creating virtual environment..."

    # Ensure the venv module is available
    if [ "$VENV_MODULE_AVAIL" = false ]; then
        warn "venv module not available — trying to install"
        pkg python3-venv 2>/dev/null || pkg "$($PYTHON -c 'import sys; print(f"python{sys.version_info.major}.{sys.version_info.minor}-venv")')" 2>/dev/null || true
    fi

    # Try normal venv, fallback to --without-pip, then global
    VENV_OK=false
    if $PYTHON -m venv venv 2>/dev/null; then
        VENV_OK=true
    elif $PYTHON -m venv --without-pip venv 2>/dev/null; then
        VENV_OK=true
    else
        # Last attempt: try installing python3-venv explicitly by version
        warn "venv still failing — trying version-specific package"
        PY_VER="$($PYTHON -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
        pkg "python${PY_VER}-venv" 2>/dev/null || true
        if $PYTHON -m venv --without-pip venv 2>/dev/null; then
            VENV_OK=true
        fi
    fi

    if [ "$VENV_OK" = true ]; then
        source venv/bin/activate
        PYTHON="python"
        # If created without pip, install pip manually
        if ! $PYTHON -m pip --version &>/dev/null; then
            $PYTHON -m ensurepip --upgrade 2>/dev/null || python3 -m ensurepip --upgrade 2>/dev/null || true
            if ! $PYTHON -m pip --version &>/dev/null; then
                warn 'ensurepip failed — installing pip manually'
                curl -sSL https://bootstrap.pypa.io/get-pip.py | $PYTHON 2>/dev/null || true
            fi
        fi
        ok "Virtual environment created"
    else
        warn 'venv creation failed — installing globally'
        USE_VENV=false
    fi
else
    source venv/bin/activate
    PYTHON="python"
    ok "Using existing virtual environment"
fi

# Ensure pip is available (upgrade it first to avoid PEP 660 issues)
$PYTHON -m pip install --upgrade pip --quiet 2>/dev/null || true

if ! $PYTHON -m pip --version &>/dev/null; then
    warn "pip not available — installing python3-pip system-wide"
    case "$PKG_MGR" in
        apt|dnf|pacman|zypper) pkg python3-pip 2>/dev/null || pkg python-pip 2>/dev/null || true ;;
    esac
    USE_VENV=false
fi

# Upgrade pip again if newly installed
$PYTHON -m pip install --upgrade pip --quiet 2>/dev/null || true

$PYTHON -m pip install --quiet --no-cache-dir -e . 2>/dev/null || $PYTHON -m pip install --quiet --no-cache-dir . 2>/dev/null || {
    warn "pip install failed — trying with --no-build-isolation"
    $PYTHON -m pip install --quiet --no-cache-dir --no-build-isolation -e .
}
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

# ── Set language ────────────────────────────────────────────────
if [ "$LANG_CHOICE" = "ru" ]; then
    "${INSTALL_DIR}/${APP}" lang ru 2>/dev/null || true
fi

# ── Done ────────────────────────────────────────────────────────
header "Done"
ok "${APP} installed successfully!"
[ "$LANG_CHOICE" = "ru" ] && info "Запусти: ${APP} doctor" || info "Run: ${APP} doctor"
info "${APP} --help"
