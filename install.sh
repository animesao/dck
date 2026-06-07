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
        apt|dnf|zypper) pkg python3 python3-pip ;;
        pacman) pkg python python-pip ;;
        brew)   pkg python@3.12 ;;
        *)      err "Install Python 3.10+ manually: https://python.org/downloads" ;;
    esac
    PYTHON="python3"
fi
ok "$($PYTHON --version)"

# Install python3-venv (needed for ensurepip on Debian/Ubuntu)
# This ensures venv creation won't fail due to missing ensurepip
PY_VER="$($PYTHON -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
case "$PKG_MGR" in
    apt|dnf) pkg "python${PY_VER}-venv" 2>/dev/null || pkg python3-venv 2>/dev/null || true ;;
    *) true ;;
esac

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

# ── Native runtime dependencies ────────────────────────────────
header "Container runtime dependencies"
NEEDS_INSTALL=""
for cmd in ip iptables nsenter mount umount; do
    if ! command -v "$cmd" &>/dev/null; then
        NEEDS_INSTALL="$NEEDS_INSTALL $cmd"
    fi
done

if [ -n "$NEEDS_INSTALL" ]; then
    warn "Missing binaries:$NEEDS_INSTALL"
    case "$PKG_MGR" in
        apt)    pkg iproute2 iptables util-linux mount 2>/dev/null || true ;;
        dnf)    pkg iproute iptables util-linux 2>/dev/null || true ;;
        pacman) pkg iproute2 iptables util-linux 2>/dev/null || true ;;
        zypper) pkg iproute2 iptables util-linux 2>/dev/null || true ;;
        brew)   warn "Install missing tools manually: brew install iproute2mac iptables util-linux" ;;
    esac
fi

for cmd in ip iptables nsenter; do
    if command -v "$cmd" &>/dev/null; then
        ok "$cmd"
    fi
done

# ── Kernel tweaks ───────────────────────────────────────────────────
if [ "$OS" = "Linux" ] && [ "$(id -u)" -eq 0 ]; then
    # OverlayFS module
    if ! grep -q overlay /proc/filesystems 2>/dev/null; then
        modprobe overlay 2>/dev/null && ok "OverlayFS module loaded" || warn "Could not load overlay module"
    fi

    # cgroups v2
    if [ ! -f /sys/fs/cgroup/cgroup.controllers ]; then
        if grep -q systemd /proc/cmdline 2>/dev/null && grep -q cgroup_no_v1 /proc/cmdline 2>/dev/null; then
            :  # already set
        elif grep -q systemd /proc/cmdline 2>/dev/null; then
            warn "cgroups v2 not active — add 'systemd.unified_cgroup_hierarchy=1' to GRUB_CMDLINE_LINUX and reboot"
        else
            warn "cgroups v2 not found — resource limits will not work"
        fi
    else
        ok "cgroups v2"
    fi

    # Kernel keyring limits (ENOMEM fix for pivot_root)
    KEY_OK=true
    if [ -f /proc/sys/kernel/keys/root_maxkeys ]; then
        cur_keys=$(cat /proc/sys/kernel/keys/root_maxkeys)
        if [ "$cur_keys" -lt 1000000 ]; then
            sysctl -w kernel.keys.root_maxkeys=1000000 >/dev/null 2>&1 || true
            KEY_OK=false
        fi
    fi
    if [ -f /proc/sys/kernel/keys/root_maxbytes ]; then
        cur_bytes=$(cat /proc/sys/kernel/keys/root_maxbytes)
        if [ "$cur_bytes" -lt 25000000 ]; then
            sysctl -w kernel.keys.root_maxbytes=25000000 >/dev/null 2>&1 || true
            KEY_OK=false
        fi
    fi
    if [ "$KEY_OK" = false ]; then
        SYSCTL_CONF="/etc/sysctl.d/99-dck.conf"
        if [ ! -f "$SYSCTL_CONF" ] || ! grep -q "root_maxkeys" "$SYSCTL_CONF" 2>/dev/null; then
            echo "kernel.keys.root_maxkeys=1000000" >> "$SYSCTL_CONF" 2>/dev/null || true
        fi
        if [ ! -f "$SYSCTL_CONF" ] || ! grep -q "root_maxbytes" "$SYSCTL_CONF" 2>/dev/null; then
            echo "kernel.keys.root_maxbytes=25000000" >> "$SYSCTL_CONF" 2>/dev/null || true
        fi
        ok "kernel keyring limits increased (persistent)"
    fi

    # UFW: install if missing
    if ! command -v ufw &>/dev/null; then
        case "$PKG_MGR" in
            apt|dnf|pacman|zypper) pkg ufw 2>/dev/null || true ;;
        esac
    fi
    if command -v ufw &>/dev/null && ! ufw status 2>/dev/null | grep -q "active"; then
        ufw allow 22/tcp 2>/dev/null || true
        ufw --force enable 2>/dev/null || true
        ok "UFW enabled (SSH port 22 allowed)"
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

USE_VENV=true
if [ -d "venv" ] && [ ! -f "venv/bin/activate" ]; then
    warn "Corrupted venv found — removing and recreating"
    rm -rf venv
fi

ORIG_PYTHON="$PYTHON"

if [ ! -d "venv" ]; then
    ok "Creating virtual environment..."

    # Try to create venv. If it fails, install python3-venv and retry once.
    if ! $PYTHON -m venv venv >/dev/null 2>&1; then
        warn "venv failed — installing python3-venv and retrying"
        PY_VER="$($ORIG_PYTHON -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
        pkg "python${PY_VER}-venv" 2>/dev/null || pkg python3-venv 2>/dev/null || true
        $PYTHON -m venv venv >/dev/null 2>&1 || true
    fi

    VENV_OK=false
    if [ -f "venv/bin/activate" ]; then
        source venv/bin/activate
        PYTHON="python"
        if $PYTHON -m pip --version &>/dev/null; then
            VENV_OK=true
            ok "Virtual environment created"
        fi
    fi

    if [ "$VENV_OK" != true ]; then
        warn 'venv creation failed — installing globally'
        rm -rf venv 2>/dev/null || true
        PYTHON="$ORIG_PYTHON"
        USE_VENV=false
    fi
else
    source venv/bin/activate 2>/dev/null || true
    PYTHON="python"
    if ! $PYTHON -m pip --version &>/dev/null; then
        warn 'existing venv has no pip — installing globally'
        PYTHON="$ORIG_PYTHON"
        USE_VENV=false
    fi
fi

# Ensure pip is available
if ! $PYTHON -m pip --version &>/dev/null; then
    warn "pip not available — installing python3-pip"
    case "$PKG_MGR" in
        apt|dnf|pacman|zypper) pkg python3-pip 2>/dev/null || pkg python-pip 2>/dev/null || true ;;
    esac
    USE_VENV=false
    PYTHON="$ORIG_PYTHON"
fi

# Upgrade pip to avoid PEP 660 issues with old pip
info "Upgrading pip..."
$PYTHON -m pip install --upgrade pip --quiet 2>/dev/null || true

# Install dck (try editable, then non-editable, then with --no-build-isolation)
info "Installing dck package..."
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
[ "$LANG_CHOICE" = "ru" ] && info "Запусти: ${APP} doctor" || info "Run: ${APP} doctor"
info "${APP} --help"
