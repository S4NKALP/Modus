#!/bin/bash

#  ███╗   ███╗ ██████╗ ██████╗ ██╗   ██╗███████╗
#  ████╗ ████║██╔═══██╗██╔══██╗██║   ██║██╔════╝
#  ██╔████╔██║██║   ██║██║  ██║██║   ██║███████╗
#  ██║╚██╔╝██║██║   ██║██║  ██║██║   ██║╚════██║
#  ██║ ╚═╝ ██║╚██████╔╝██████╔╝╚██████╔╝███████║
#  ╚═╝     ╚═╝ ╚═════╝ ╚═════╝  ╚═════╝ ╚══════╝
#
#  A hackable shell for Hyprland
#  Installation Script for Arch Linux
#
#  Repository: https://github.com/S4NKALP/Modus
#  License: GPLv3

set -e
set -u
set -o pipefail

# ── CLI flags ──────────────────────────────────────────────────────
AUTO_YES=false
DRY_RUN=false
for arg in "$@"; do
    case "$arg" in
        -y|--yes)      AUTO_YES=true ;;
        -n|--dry-run)  DRY_RUN=true ;;
        -h|--help)
            echo "Usage: install.sh [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  -y, --yes       Skip all prompts"
            echo "  -n, --dry-run   Show what would be installed without installing"
            echo "  -h, --help      Show this help"
            exit 0
            ;;
    esac
done

REPO_URL="https://github.com/S4NKALP/Modus.git"
INSTALL_DIR="$HOME/.config/Modus"

# ── Package definitions ────────────────────────────────────────────
PACKAGES=(
    uv
    fabric-cli-git
    uwsm
    cliphist
    slurp
    grim
    swappy
    wl-clipboard
    wtype
    libnotify
    playerctl
    matugen-bin
    hypridle
    hyprsunset
    hyprpicker
    hyprshot
    gtk-session-lock
    awww
    apple-fonts
    webp-pixbuf-loader
    cinnamon-desktop
    libmediaart
    acpi
    brightnessctl
    power-profiles-daemon
    ddcutil
    at-spi2-core
    networkmanager
    network-manager-applet
    blueman
    pipewire
    libpulse
    gcc
    make
    pkgconf
    meson
    ninja
    wayland-protocols
    gobject-introspection
    gtk-layer-shell
    librsvg
    libqalculate
    appmenu-gtk-module
    libdbusmenu-gtk3
    libdbusmenu-qt5
    pciutils
    wf-recorder
    ffmpeg
)

# ── Colors ─────────────────────────────────────────────────────────
if [ -t 1 ]; then
    GREEN=$(tput setaf 2)
    YELLOW=$(tput setaf 3)
    RED=$(tput setaf 1)
    CYAN=$(tput setaf 6)
    BLUE=$(tput setaf 4)
    MAGENTA=$(tput setaf 5)
    BOLD=$(tput bold)
    DIM=$(tput dim)
    RESET=$(tput sgr0)
else
    GREEN="" YELLOW="" RED="" CYAN="" BLUE="" MAGENTA="" BOLD="" DIM="" RESET=""
fi

ARROW="→"
CHECK="✔"
CROSS="✖"
INFO="ℹ"
WARN="⚠"
BULLET="•"

# ── Helpers ────────────────────────────────────────────────────────
header() {
    echo ""
    echo -e "  ${BOLD}${CYAN}╔══════════════════════════════════════════════╗${RESET}"
    echo -e "  ${BOLD}${CYAN}║${RESET}  ${BOLD}Modus Installer${RESET}  ${DIM}v2.0${RESET}                       ${BOLD}${CYAN}║${RESET}"
    echo -e "  ${BOLD}${CYAN}╚══════════════════════════════════════════════╝${RESET}"
    echo ""
}

section() {
    echo ""
    echo -e "  ${BOLD}${MAGENTA}── $1 ──${RESET}"
}

step() {
    echo -e "  ${CYAN}${ARROW}${RESET} $1"
}

success() {
    echo -e "  ${GREEN}${CHECK}${RESET} ${GREEN}$1${RESET}"
}

warn() {
    echo -e "  ${YELLOW}${WARN}${RESET} ${YELLOW}$1${RESET}"
}

error() {
    echo -e "  ${RED}${CROSS}${RESET} ${RED}$1${RESET}"
}

info() {
    echo -e "  ${BLUE}${INFO}${RESET} ${DIM}$1${RESET}"
}

divider() {
    echo -e "  ${DIM}──────────────────────────────────────────────${RESET}"
}

confirm() {
    local prompt="$1"
    local default="${2:-n}"
    local yn
    if [ "$AUTO_YES" = true ]; then
        return 0
    fi
    if [ "$default" = "y" ]; then
        read -rp "  ${BOLD}${prompt} [Y/n]:${RESET} " yn
        [[ ! "$yn" =~ ^[Nn]$ ]]
    else
        read -rp "  ${BOLD}${prompt} [y/N]:${RESET} " yn
        [[ "$yn" =~ ^[Yy]$ ]]
    fi
}

spinner() {
    local pid=$1
    local message=$2
    local spin=('⠋' '⠙' '⠹' '⠸' '⠼' '⠴' '⠦' '⠧' '⠇' '⠏')
    local i=0

    while kill -0 "$pid" 2>/dev/null; do
        printf "\r  %b%s%b %s" "$CYAN" "${spin[i]}" "$RESET" "$message"
        i=$(((i + 1) % 10))
        sleep 0.1
    done
    wait "$pid" 2>/dev/null
    local rc=$?
    printf "\r"
    if [ $rc -eq 0 ]; then
        echo -e "  ${GREEN}${CHECK}${RESET} ${GREEN}${message}${RESET}"
    else
        echo -e "  ${RED}${CROSS}${RESET} ${RED}${message}${RESET}"
    fi
    return $rc
}

# ── Cleanup ────────────────────────────────────────────────────────
cleanup() {
    if [ -n "${SUDO_KEEPER_PID:-}" ]; then
        kill "$SUDO_KEEPER_PID" 2>/dev/null || true
    fi
}
trap cleanup EXIT INT TERM

# ── Banner ─────────────────────────────────────────────────────────
clear
header

echo -e "  ${BOLD}A hackable shell for Hyprland${RESET}"
echo -e "  ${DIM}https://github.com/S4NKALP/Modus${RESET}"
echo ""

# ── Pre-flight checks ─────────────────────────────────────────────
section "Pre-flight checks"

step "Checking operating system..."
if ! grep -qi "arch" /etc/os-release; then
    error "This script requires Arch Linux or an Arch-based distribution"
    exit 1
fi
success "Arch Linux detected"

step "Checking user permissions..."
if [ "$(id -u)" -eq 0 ]; then
    error "Please run this script as a regular user, not as root"
    exit 1
fi
success "Running as regular user"

step "Checking git..."
if ! command -v git &>/dev/null; then
    error "git is not installed. Run: sudo pacman -S git"
    exit 1
fi
success "git found"

# ── Package list ──────────────────────────────────────────────────
section "Packages"

if [ "$DRY_RUN" = true ]; then
    echo ""
    printf "  ${DIM}%s${RESET}\n" "${PACKAGES[@]}"
    echo ""
    info "Dry run — no packages will be installed"
    exit 0
fi

info "Total: ${#PACKAGES[@]} packages"

if ! confirm "Proceed with installation?"; then
    warn "Cancelled"
    exit 0
fi

# ── Sudo ───────────────────────────────────────────────────────────
section "Permissions"

info "Some packages require root privileges"
if ! sudo -v 2>/dev/null; then
    error "Sudo authentication failed"
    exit 1
fi
success "Sudo authenticated"

while true; do
    sudo -n true
    sleep 60
    kill -0 "$$" || exit
done 2>/dev/null &
SUDO_KEEPER_PID=$!

# ── AUR helper ─────────────────────────────────────────────────────
section "AUR helper"

AUR=""
if command -v paru &>/dev/null; then
    AUR="paru"
    success "Using paru"
elif command -v yay &>/dev/null; then
    AUR="yay"
    success "Using yay"
else
    step "Installing yay-bin..."
    tmpdir=$(mktemp -d)
    (
        git clone --quiet --depth=1 https://aur.archlinux.org/yay-bin.git "$tmpdir/yay-bin"
        cd "$tmpdir/yay-bin"
        makepkg -si --noconfirm >/dev/null 2>&1
    ) &
    spinner $! "Building yay-bin"
    wait $! || {
        error "Failed to install yay-bin"
        rm -rf "$tmpdir"
        exit 1
    }
    rm -rf "$tmpdir"
    AUR="yay"
    success "yay-bin installed"
fi

# ── Repository ─────────────────────────────────────────────────────
section "Repository"

if [ -d "$INSTALL_DIR" ]; then
    step "Pulling latest changes..."
    git -C "$INSTALL_DIR" pull --quiet 2>/dev/null || true
    success "Repository updated"
else
    step "Cloning repository..."
    git clone --quiet "$REPO_URL" "$INSTALL_DIR" 2>/dev/null || true
    success "Repository cloned"
fi
info "${INSTALL_DIR}"

# ── Install packages ──────────────────────────────────────────────
section "Installing packages"

step "Syncing databases..."
$AUR -Syy --noconfirm >/dev/null 2>&1 || true
success "Databases synced"

installed=0
failed=0
failed_pkgs=()
total=${#PACKAGES[@]}

for pkg in "${PACKAGES[@]}"; do
    if $AUR -S --needed --noconfirm "$pkg" >/dev/null 2>&1; then
        installed=$((installed + 1))
    else
        failed=$((failed + 1))
        failed_pkgs+=("$pkg")
    fi
    pct=$((installed * 100 / total))
    printf "\r  ${CYAN}${ARROW}${RESET} [%-50s] %3d%% (%d/%d)" "$(printf '#%.0s' $(seq 1 $((pct / 2))))" "$pct" "$installed" "$total"
done
echo ""

if [ $failed -eq 0 ]; then
    success "All ${installed} packages installed"
else
    warn "${failed} package(s) failed:"
    for pkg in "${failed_pkgs[@]}"; do
        echo -e "    ${RED}${CROSS}${RESET} ${pkg}"
    done
fi

# ── Build native modules ──────────────────────────────────────────
section "Building native modules"

# Global Menu shim
step "Compiling libmenu_button_shim.so..."
SHIM_SRC="$INSTALL_DIR/src/window/globalmenu/libmenu_button_shim.c"
SHIM_OUT="$INSTALL_DIR/src/window/globalmenu/libmenu_button_shim.so"
if [ -f "$SHIM_SRC" ]; then
    if gcc -shared -fPIC -O2 -o "$SHIM_OUT" "$SHIM_SRC" "$(pkg-config --cflags --libs gtk+-3.0)" -ldl 2>/dev/null; then
        success "libmenu_button_shim.so built"
    else
        warn "Failed to compile shim — global menu may not work"
    fi
else
    warn "Shim source not found — skipped"
fi

# App Capture
step "Compiling libappcapture.so..."
if [ -d "$INSTALL_DIR/src/window/switcher/app-capture" ]; then
    if (
        cd "$INSTALL_DIR/src/window/switcher/app-capture"
        meson setup builddir --wipe >/dev/null 2>&1 || meson setup builddir >/dev/null 2>&1
        meson compile -C builddir >/dev/null 2>&1
    ); then
        success "libappcapture.so built"
    else
        warn "Failed to compile app-capture"
    fi
else
    warn "App-capture source not found — skipped"
fi

# ── Hyprland config ───────────────────────────────────────────────
section "Hyprland configuration"

HYPR_CONFIG="$HOME/.config/hypr/hyprland.lua"
MODUS_MODULE_LINE="dofile(\"$INSTALL_DIR/config/hypr/modus.lua\")"

if [ -f "$HYPR_CONFIG" ]; then
    if grep -qF "$MODUS_MODULE_LINE" "$HYPR_CONFIG"; then
        success "Modus module already in hyprland.lua"
    else
        step "Adding Modus module to hyprland.lua..."
        {
            echo ""
            echo "-- Modus configuration"
            echo "$MODUS_MODULE_LINE"
        } >> "$HYPR_CONFIG"
        success "Module added"
    fi
else
    warn "hyprland.lua not found at ${HYPR_CONFIG}"
    info "Add manually: ${MODUS_MODULE_LINE}"
fi

step "Symlinking hypridle.conf..."
HYPR_DIR="$HOME/.config/hypr"
HYPRIDLE_CONF="$INSTALL_DIR/config/hypr/hypridle.conf"
HYPRIDLE_TARGET="$HYPR_DIR/hypridle.conf"
mkdir -p "$HYPR_DIR"
if [ -f "$HYPRIDLE_CONF" ]; then
    ln -sf "$HYPRIDLE_CONF" "$HYPRIDLE_TARGET"
    success "hypridle.conf symlinked"
else
    warn "hypridle.conf not found — skipped"
fi

# ── Environment ───────────────────────────────────────────────────
section "Global environment"

APP_CONF_DIR="$HOME/.config/environment.d"
APP_CONF_FILE="$APP_CONF_DIR/appmenu.conf"

step "Writing environment.d config..."
mkdir -p "$APP_CONF_DIR"
cat > "$APP_CONF_FILE" << 'EOF'
GTK_MODULES=appmenu-gtk-module
UBUNTU_MENUPROXY=1
EOF
success "environment.d/appmenu.conf written"

PAM_FILE="$HOME/.pam_environment"
step "Updating pam_environment..."
for entry in "GTK_MODULES DEFAULT=appmenu-gtk-module" "UBUNTU_MENUPROXY DEFAULT=1"; do
    var_name="${entry%% *}"
    if ! grep -q "^${var_name} " "$PAM_FILE" 2>/dev/null; then
        echo "$entry" >> "$PAM_FILE"
    fi
done
success "pam_environment updated"

# ── Matugen ────────────────────────────────────────────────────────
section "Matugen"

MATUGEN_CONFIG="$HOME/.config/matugen/config.toml"

MODUS_BLOCK='[templates.modus]
input_path = "~/.config/Modus/config/matugen/templates/modus.css"
output_path = "~/.config/Modus/src/shared/styles/colors.css"
post_hook = "fabric-cli exec modus '\''app.set_css()'\'' &"'

HYPR_BLOCK='[templates.hyprland]
input_path = "~/.config/Modus/config/matugen/templates/hyprland-colors.lua"
output_path = "~/.config/Modus/config/matugen/colors.lua"'

if [ -f "$MATUGEN_CONFIG" ]; then
    if grep -qF "[templates.modus]" "$MATUGEN_CONFIG"; then
        success "Modus template already configured"
    else
        step "Adding Modus template..."
        echo "" >> "$MATUGEN_CONFIG"
        echo "$MODUS_BLOCK" >> "$MATUGEN_CONFIG"
        success "Modus template added"
    fi

    if grep -qF "[templates.hyprland]" "$MATUGEN_CONFIG"; then
        success "Hyprland template already configured"
    else
        step "Adding Hyprland template..."
        echo "" >> "$MATUGEN_CONFIG"
        echo "$HYPR_BLOCK" >> "$MATUGEN_CONFIG"
        success "Hyprland template added"
    fi
else
    warn "matugen config not found at ${MATUGEN_CONFIG}"
    info "Install matugen first, then re-run this script"
fi

# ── Launch ─────────────────────────────────────────────────────────
section "Launch"

step "Stopping existing instances..."
if killall modus 2>/dev/null; then
    success "Stopped running instance"
    sleep 1
else
    info "No existing instance found"
fi

step "Starting Modus..."
uwsm app -- uv run --project "$INSTALL_DIR" start >/dev/null 2>&1 &
disown
sleep 2
if pgrep -x "modus" >/dev/null; then
    success "Modus is running"
else
    warn "Modus may not have started — check logs"
fi

# ── Summary ────────────────────────────────────────────────────────
echo ""
echo -e "  ${GREEN}${BOLD}╔══════════════════════════════════════════╗${RESET}"
echo -e "  ${GREEN}${BOLD}║${RESET}                                          ${GREEN}${BOLD}║${RESET}"
echo -e "  ${GREEN}${BOLD}║${RESET}   ${GREEN}${BOLD}Installation complete!${RESET}                 ${GREEN}${BOLD}║${RESET}"
echo -e "  ${GREEN}${BOLD}║${RESET}                                          ${GREEN}${BOLD}║${RESET}"
echo -e "  ${GREEN}${BOLD}╚══════════════════════════════════════════╝${RESET}"
echo ""
divider
info "Packages: ${GREEN}${installed}${RESET} installed${RED:+, ${failed} failed}"
info "Location: ${INSTALL_DIR}"
info "Config:   ${INSTALL_DIR}/config/"
divider
echo ""
