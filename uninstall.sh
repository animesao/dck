#!/bin/sh
set -e

BOLD=$(tput bold 2>/dev/null || echo "")
RED=$(tput setaf 1 2>/dev/null || echo "")
GREEN=$(tput setaf 2 2>/dev/null || echo "")
RESET=$(tput sgr0 2>/dev/null || echo "")

info()  { echo "${BOLD}${GREEN}[dck]${RESET} $*"; }
warn()  { echo "${BOLD}${RED}[dck]${RESET} $*" >&2; }

FORCE=false
for arg do
    case "$arg" in
        -f|--force|-y|--yes) FORCE=true ;;
    esac
done

info "Uninstalling dck..."

PREFIX="${PREFIX:-/usr/local}"
BIN="$PREFIX/bin/dck"

if [ -f "$BIN" ]; then
    rm -f "$BIN"
    info "Removed $BIN"
else
    warn "dck binary not found at $BIN"
fi

DCK_DIR="${DCK_DIR:-$HOME/.dck}"
if [ -d "$DCK_DIR" ]; then
    echo ""
    if [ "$FORCE" = "true" ] || [ ! -t 0 ]; then
        rm -rf "$DCK_DIR"
        info "Removed $DCK_DIR"
    else
        warn "WARNING: This will DELETE all images, containers, and data"
        printf "Remove %s? [y/N] " "$DCK_DIR"
        read -r confirm
        if [ "$confirm" = "y" ] || [ "$confirm" = "Y" ]; then
            rm -rf "$DCK_DIR"
            info "Removed $DCK_DIR"
        else
            info "Skipped $DCK_DIR (remove manually: rm -rf $DCK_DIR)"
        fi
    fi
fi

info "dck uninstalled."
