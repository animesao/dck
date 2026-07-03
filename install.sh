#!/usr/bin/env bash
set -euo pipefail

# dck Container Runtime Installer
# Usage: curl -sSL https://raw.githubusercontent.com/animesao/dck/main/install.sh | sudo bash

REPO="animesao/dck"
BRANCH=""
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

# ---- Branch selection ----
echo ""
echo -e "${YELLOW}════════════════════════════════════════${NC}"
echo -e "${YELLOW}     Choose Installation Channel${NC}"
echo -e "${YELLOW}════════════════════════════════════════${NC}"
echo -e "  ${GREEN}1)${NC} stable  — latest stable release (recommended)"
echo -e "  ${GREEN}2)${NC} dev     — development build (unstable)"
echo ""
while [[ -z "$BRANCH" ]]; do
  read -p "Select [1/2]: " -r CH </dev/tty || true
  case "$CH" in
    1) BRANCH="stalbal" ;;
    2) BRANCH="dev" ;;
    *) echo -e "${RED}Invalid choice. Enter 1 or 2.${NC}" ;;
  esac
done
log "Selected channel: $BRANCH"

# ---- Version selection ----
echo ""
echo -e "${YELLOW}════════════════════════════════════════${NC}"
echo -e "${YELLOW}     Select Version${NC}"
echo -e "${YELLOW}════════════════════════════════════════${NC}"

LATEST_TAG=$(curl -sfL "https://api.github.com/repos/$REPO/releases?per_page=30" \
  | grep '"tag_name"' \
  | cut -d'"' -f4 \
  | grep -E "v[0-9]+\.[0-9]+\.[0-9]+-${BRANCH}\.[a-f0-9]+$" \
  | head -1 \
  2>/dev/null || true)

if [[ -z "$LATEST_TAG" ]]; then
  err "Could not detect latest release. Check https://github.com/$REPO/releases"
fi

log "Latest $BRANCH version: $LATEST_TAG"
echo ""
echo -e "  ${GREEN}1${NC}) $LATEST_TAG (latest)"
echo -e "  ${GREEN}2${NC}) Enter custom tag"
echo ""
while true; do
  read -p "Select [1/2] (default=1): " -r VC </dev/tty || true
  if [[ -z "$VC" || "$VC" == "1" ]]; then
    SELECTED_TAG="$LATEST_TAG"
    log "Selected: $SELECTED_TAG"
    break
  elif [[ "$VC" == "2" ]]; then
    read -p "Enter tag (e.g. v1.19.0-stalbal.abc1234): " -r SELECTED_TAG </dev/tty || true
    if [[ -n "$SELECTED_TAG" ]]; then
      log "Selected: $SELECTED_TAG"
      break
    fi
    echo -e "${RED}Tag cannot be empty${NC}"
  else
    echo -e "${RED}Invalid choice${NC}"
  fi
done

# ---- Dependencies ----
log "Installing dependencies..."
apt-get update -qq
apt-get install -y -qq curl tar gzip sudo ufw

# ---- Download binary ----
log "Downloading dck ${SELECTED_TAG} (${ARCH})..."
curl -fsSL "https://github.com/$REPO/releases/download/${SELECTED_TAG}/dck-linux-${ARCH}" \
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

# ---- Download .deb ----
# .deb uses base semver (no -dev.<sha> suffix) as filename
DEB_BASE="${SELECTED_TAG#v}"
DEB_BASE="${DEB_BASE%%-*}"
DEB_NAME="dck_${DEB_BASE}_${ARCH}.deb"
log "Downloading .deb package..."
curl -fsSL "https://github.com/$REPO/releases/download/${SELECTED_TAG}/${DEB_NAME}" \
  -o "/tmp/$DEB_NAME" 2>/dev/null && {
  log "Installing .deb package..."
  dpkg -i "/tmp/$DEB_NAME" 2>/dev/null || apt-get install -f -y -qq
  rm -f "/tmp/$DEB_NAME"
} || warn "No .deb package for this version, binary only"

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
