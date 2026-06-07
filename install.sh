#!/usr/bin/env bash
set -euo pipefail

APP="dck"
REPO="https://gitlab.com/animesao/dck.git"
INSTALL_DIR="${INSTALL_DIR:-$HOME/.local/bin}"
[ "$(id -u)" -eq 0 ] && INSTALL_DIR="/usr/local/bin"

BOLD='\033[1m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
RED='\033[0;31m'; CYAN='\033[0;36m'; NC='\033[0m'
info()  { printf "${CYAN}%s${NC}\n" "$*"; }
ok()    { printf "${GREEN}✓ %s${NC}\n" "$*"; }
warn()  { printf "${YELLOW}⚠ %s${NC}\n" "$*"; }
err()   { printf "${RED}✗ %s${NC}\n" "$*"; exit 1; }

OS="$(uname -s)"
ARCH="$(uname -m)"
info "${OS} ${ARCH}"

# ── package manager ──────────────────────────────────────────────
PKG_MGR=""
SUDO=""
if [ "$OS" = "Linux" ]; then
    command -v apt-get  &>/dev/null && PKG_MGR="apt"  || true
    command -v dnf      &>/dev/null && PKG_MGR="dnf"  || true
    command -v pacman   &>/dev/null && PKG_MGR="pacman" || true
    command -v zypper   &>/dev/null && PKG_MGR="zypper" || true
fi
[ "$OS" = "Darwin" ] && PKG_MGR="brew"
[ "$(id -u)" -ne 0 ] && command -v sudo &>/dev/null && SUDO="sudo"

pkg() {
    case "$PKG_MGR" in
        apt)    $SUDO apt-get install --no-install-recommends -y "$@" ;;
        dnf)    $SUDO dnf install -y "$@" ;;
        pacman) $SUDO pacman -S --noconfirm "$@" ;;
        zypper) $SUDO zypper install -y "$@" ;;
        brew)   brew install "$@" ;;
    esac
}

# ── Python ────────────────────────────────────────────────────────
PYTHON=""
for cmd in python3 python; do
    if command -v "$cmd" &>/dev/null; then
        ver=$($cmd -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null)
        major="${ver%.*}"; minor="${ver#*.}"
        if [ "$major" -ge 3 ] && [ "$minor" -ge 10 ]; then
            PYTHON="$cmd"
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    warn "Python 3.10+ not found — installing"
    case "$PKG_MGR" in
        apt|dnf|zypper) pkg python3 python3-pip python3-venv ;;
        pacman) pkg python python-pip ;;
        brew)   pkg python@3.12 ;;
    esac
    PYTHON="python3"
fi
ok "$($PYTHON --version 2>&1)"

# ── runtime deps ──────────────────────────────────────────────────
MISSING=""
for cmd in ip iptables nsenter; do
    command -v "$cmd" &>/dev/null || MISSING="$MISSING $cmd"
done
if [ -n "$MISSING" ]; then
    case "$PKG_MGR" in
        apt)    pkg iproute2 iptables util-linux ;;
        dnf)    pkg iproute iptables util-linux ;;
        pacman) pkg iproute2 iptables util-linux ;;
        zypper) pkg iproute2 iptables util-linux ;;
        brew)   warn "Install manually: iproute2mac iptables util-linux" ;;
    esac
fi
for cmd in ip iptables nsenter; do
    command -v "$cmd" &>/dev/null && ok "$cmd" || warn "missing: $cmd"
done

# ── overlay + cgroups check ───────────────────────────────────────
if [ "$OS" = "Linux" ] && [ "$(id -u)" -eq 0 ]; then
    grep -q overlay /proc/filesystems 2>/dev/null || { modprobe overlay 2>/dev/null && ok "overlayfs"; }
    [ -f /sys/fs/cgroup/cgroup.controllers ] && ok "cgroups v2" || warn "cgroups v2 not active"
fi

# ── install via pip ───────────────────────────────────────────────
$PYTHON -m pip install --quiet --upgrade pip 2>/dev/null || true

if $PYTHON -m pip install --quiet "git+${REPO}" 2>/dev/null; then
    ok "installed from git"
elif $PYTHON -m pip install --quiet --no-build-isolation "git+${REPO}" 2>/dev/null; then
    ok "installed from git (no build isolation)"
else
    # fallback: clone and install
    TMP=$(mktemp -d)
    git clone --depth 1 "$REPO" "$TMP/$APP"
    $PYTHON -m pip install "$TMP/$APP" || $PYTHON -m pip install --no-build-isolation "$TMP/$APP"
    rm -rf "$TMP"
fi

# ── symlink ───────────────────────────────────────────────────────
CLI_PATH=$(command -v "$APP" 2>/dev/null) || true
if [ -n "$CLI_PATH" ]; then
    mkdir -p "$INSTALL_DIR"
    ln -sf "$CLI_PATH" "${INSTALL_DIR}/${APP}" 2>/dev/null || true
    ok "linked to ${INSTALL_DIR}/${APP}"
fi

if [[ ":$PATH:" != *":${INSTALL_DIR}:"* ]]; then
    warn "add to PATH: echo 'export PATH=\"\$PATH:${INSTALL_DIR}\"' >> ~/.bashrc"
fi

ok "${APP} installed!"
info "${APP} --help"
