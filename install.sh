#!/usr/bin/env bash
set -euo pipefail

# dck Container Runtime Installer
# Usage: curl -sSL https://raw.githubusercontent.com/animesao/dck/main/install.sh | sudo bash

REPO="animesao/dck"
DCK_BIN="/usr/local/bin/dck"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
log()  { echo -e "${GREEN}[+]${NC} $1"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }
err()  { echo -e "${RED}[x]${NC} $1"; exit 1; }

if [[ $EUID -ne 0 ]]; then err "Must run as root: sudo bash install.sh"; fi
if [[ ! -f /etc/os-release ]]; then err "Unsupported OS"; fi
source /etc/os-release
if [[ "$ID" != "ubuntu" && "$ID" != "debian" ]]; then err "Unsupported OS: $ID"; fi
log "OS: $PRETTY_NAME"

ARCH="amd64"
if [[ "$(uname -m)" == "aarch64" ]]; then ARCH="arm64"; fi

# ---- Detect latest version ----
log "Fetching latest release..."
LATEST_TAG=$(curl -sfL "https://api.github.com/repos/$REPO/releases/latest" \
  | grep '"tag_name"' | cut -d'"' -f4)

if [[ -z "$LATEST_TAG" ]]; then
  err "Could not detect latest release. Check https://github.com/$REPO/releases"
fi
log "Latest version: $LATEST_TAG"

# ---- Dependencies ----
log "Installing dependencies..."
apt-get update -qq
apt-get install -y -qq curl tar gzip sudo ufw

# ---- Download binary ----
log "Downloading dck ${LATEST_TAG} (${ARCH})..."
curl -fsSL "https://github.com/$REPO/releases/download/${LATEST_TAG}/dck-linux-${ARCH}" \
  -o "$DCK_BIN"
chmod +x "$DCK_BIN"
log "Binary installed: $DCK_BIN"

# ---- Verify binary works (check for glibc error) ----
if ! "$DCK_BIN" --version &>/dev/null; then
  warn "Binary failed to run (likely glibc mismatch). Building from source..."
  if command -v go &>/dev/null; then
    log "Building dck from source..."
    TMPDIR=$(mktemp -d)
    git clone --depth 1 "https://github.com/$REPO.git" "$TMPDIR" 2>/dev/null || {
      err "Git clone failed. Install Go manually and run: CGO_ENABLED=0 go build"
    }
    cd "$TMPDIR"
    CGO_ENABLED=0 go build -tags netgo -installsuffix netgo -ldflags="-s -w" -o dck .
    cp dck "$DCK_BIN"
    chmod +x "$DCK_BIN"
    cd /
    rm -rf "$TMPDIR"
    log "Built from source: $DCK_BIN"
  else
    warn "Go not installed. Installing Go 1.21 to build from source..."
    curl -fsSL "https://go.dev/dl/go1.21.13.linux-amd64.tar.gz" -o /tmp/go.tar.gz
    tar -C /usr/local -xzf /tmp/go.tar.gz
    export PATH=$PATH:/usr/local/go/bin
    TMPDIR=$(mktemp -d)
    git clone --depth 1 "https://github.com/$REPO.git" "$TMPDIR"
    cd "$TMPDIR"
    CGO_ENABLED=0 /usr/local/go/bin/go build -tags netgo -installsuffix netgo -ldflags="-s -w" -o dck .
    cp dck "$DCK_BIN"
    chmod +x "$DCK_BIN"
    cd /
    rm -rf "$TMPDIR" /tmp/go.tar.gz
    log "Built from source: $DCK_BIN"
  fi
fi

# ---- System deps for dck ----
log "Installing dck system dependencies..."
apt-get install -y -qq util-linux iproute2 iptables procps curl 2>/dev/null || true

# ---- UFW ----
if command -v ufw &>/dev/null; then
  ufw allow 22/tcp 2>/dev/null || true
  ufw --force enable 2>/dev/null || true
  log "UFW configured (allow SSH)"
fi

# ---- IP forwarding ----
if [[ -f /proc/sys/net/ipv4/ip_forward ]]; then
  echo 1 > /proc/sys/net/ipv4/ip_forward
  grep -q "net.ipv4.ip_forward=1" /etc/sysctl.conf 2>/dev/null || \
    echo "net.ipv4.ip_forward=1" >> /etc/sysctl.conf
  log "IP forwarding enabled"
fi

# ---- Verify ----
log "Verifying installation..."
if command -v dck &>/dev/null; then
  log "dck installed: $(dck --version 2>/dev/null || echo 'ok')"
else
  warn "dck not found in PATH — ensure $DCK_BIN is accessible"
fi

# ---- Done ----
echo ""
log "════════════════════════════════════════"
log "  dck installed successfully!"
log "════════════════════════════════════════"
log ""
log "  Quick start:"
log "    dck pull alpine"
log "    dck run --rm alpine echo hello"
log "    dck --help"
log ""
log "  Docs:  https://github.com/$REPO"
echo ""
