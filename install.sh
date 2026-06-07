#!/bin/sh
set -e

BOLD=$(tput bold 2>/dev/null || echo "")
RESET=$(tput sgr0 2>/dev/null || echo "")
GREEN=$(tput setaf 2 2>/dev/null || echo "")
YELLOW=$(tput setaf 3 2>/dev/null || echo "")
RED=$(tput setaf 1 2>/dev/null || echo "")

info()  { echo "${BOLD}${GREEN}[dck]${RESET} $*"; }
warn()  { echo "${BOLD}${YELLOW}[dck]${RESET} $*"; }
err()   { echo "${BOLD}${RED}[dck]${RESET} $*" >&2; }

DCK_BIN="/usr/local/bin/dck"
DIR="$(cd "$(dirname "$0")" && pwd)"

detect_os() {
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        OS=$ID
        OS_LIKE=$ID_LIKE
    elif command -v lsb_release >/dev/null 2>&1; then
        OS=$(lsb_release -si | tr '[:upper:]' '[:lower:]')
    else
        OS=$(uname -s | tr '[:upper:]' '[:lower:]')
    fi
    echo "$OS"
}

install_pkg() {
    case "$1" in
        debian|ubuntu|linuxmint|pop)
            apt-get update -qq
            apt-get install -y -qq "$2"
            ;;
        rhel|centos|fedora|rocky|almalinux)
            if command -v dnf >/dev/null 2>&1; then
                dnf install -y -q "$2"
            else
                yum install -y -q "$2"
            fi
            ;;
        arch|manjaro|endeavouros)
            pacman -S --noconfirm "$2"
            ;;
        alpine)
            apk add "$2"
            ;;
        suse|opensuse*)
            zypper install -y "$2"
            ;;
        *)
            warn "Unknown OS: $1. Please install $2 manually."
            return 1
            ;;
    esac
}

ensure_go() {
    if command -v go >/dev/null 2>&1; then
        info "Go found: $(go version)"
        return 0
    fi
    warn "Go not found. Installing..."
    case "$1" in
        debian|ubuntu|linuxmint|pop)
            install_pkg "$1" "golang-go"
            ;;
        fedora|rhel|centos)
            install_pkg "$1" "golang"
            ;;
        arch|manjaro)
            install_pkg "$1" "go"
            ;;
        alpine)
            install_pkg "$1" "go"
            ;;
        *)
            err "Please install Go manually from https://go.dev/dl/"
            exit 1
            ;;
    esac
}

ensure_packages() {
    info "Checking required packages..."
    case "$1" in
        debian|ubuntu|linuxmint|pop)
            install_pkg "$1" "util-linux iproute2 iptables procps curl ufw"
            ;;
        fedora|rhel|centos|rocky|almalinux)
            install_pkg "$1" "util-linux iproute iptables procps-ng curl ufw"
            ;;
        arch|manjaro|endeavouros)
            install_pkg "$1" "util-linux iproute2 iptables procps-ng curl ufw"
            ;;
        alpine)
            install_pkg "$1" "util-linux iproute2 iptables procps curl"
            warn "UFW not available on Alpine (use iptables directly)"
            ;;
        suse|opensuse*)
            install_pkg "$1" "util-linux iproute2 iptables procps curl ufw"
            ;;
        *)
            warn "Unknown OS. Ensure these are installed:"
            warn "  util-linux, iproute2, iptables, procps, curl"
            ;;
    esac
}

setup_ufw() {
    if command -v ufw >/dev/null 2>&1; then
        info "Configuring UFW..."
        ufw_was_enabled=false
        if ufw status | grep -q "Status: active"; then
            ufw_was_enabled=true
        fi

        ufw allow 22/tcp >/dev/null 2>&1 && info "  Port 22/tcp opened (SSH)"

        if ! $ufw_was_enabled; then
            ufw --force enable >/dev/null 2>&1 || true
            info "  UFW enabled"
        fi
    else
        warn "UFW not found. Install it for firewall management."
    fi
}

setup_system() {
    info "Configuring system..."

    if [ -f /proc/sys/net/ipv4/ip_forward ]; then
        echo 1 > /proc/sys/net/ipv4/ip_forward
        if [ -f /etc/sysctl.conf ]; then
            grep -q "net.ipv4.ip_forward=1" /etc/sysctl.conf 2>/dev/null || \
                echo "net.ipv4.ip_forward=1" >> /etc/sysctl.conf
        fi
        info "  IP forwarding enabled"
    fi

    if [ -d /sys/fs/cgroup ] && [ -f /sys/fs/cgroup/cgroup.controllers ]; then
        info "  cgroups v2 detected"
    fi
}

install_dck() {
    info "Building dck..."
    cd "$DIR"
    go build -ldflags="-s -w" -o dck .
    install -d "$(dirname "$DCK_BIN")"
    install -m 755 dck "$DCK_BIN"
    rm -f dck
    info "Installed to $DCK_BIN"
}

verify() {
    info "Verifying installation..."
    if command -v dck >/dev/null 2>&1; then
        info "  dck: $(dck --version)"
    fi
    for cmd in unshare nsenter ip iptables pgrep mount umount; do
        if command -v "$cmd" >/dev/null 2>&1; then
            info "  $cmd: available"
        else
            warn "  $cmd: NOT FOUND"
        fi
    done
}

main() {
    echo ""
    info "${BOLD}dck - Simple Container Runtime Installer${RESET}"
    echo ""

    if [ "$(id -u)" != "0" ]; then
        err "This installer must be run as root (or with sudo)."
        exit 1
    fi

    OS=$(detect_os)
    info "Detected OS: $OS"

    case "$OS" in
        debian|ubuntu|linuxmint|pop|rhel|centos|fedora|rocky|almalinux|arch|manjaro|endeavouros|alpine|suse|opensuse*)
            ;;
        *)
            warn "Untested OS: $OS. Proceeding anyway..."
            ;;
    esac

    ensure_go "$OS"
    ensure_packages "$OS"
    setup_ufw
    setup_system
    install_dck
    verify

    echo ""
    info "${BOLD}Installation complete!${RESET}"
    echo ""
    info "Quick start:"
    info "  dck pull alpine"
    info "  dck run --rm alpine echo hello"
    info "  dck --help"
    echo ""
}

main
