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
#  Repository: https://github.com/S4NKALP/Modus --branch macos
#  License: GPLv3

set -e
set -u
set -o pipefail

AUTO_YES=false
for arg in "$@"; do
    case "$arg" in
        -y|--yes) AUTO_YES=true ;;
    esac
done

REPO_URL="https://github.com/S4NKALP/Modus.git"
INSTALL_DIR="$HOME/.config/Modus"

PACKAGES=(
    uv
    fabric-cli-git
    cliphist
    gnome-bluetooth-3.0
    slurp
    ffmpeg
    hypridle
    hyprsunset
    hyprpicker
    hyprshot
    grim
    libnotify
    matugen-bin
    playerctl
    gtk-session-lock
    awww
    apple-fonts
    swappy
    wl-clipboard
    webp-pixbuf-loader
    wf-recorder
    acpi
    brightnessctl
    power-profiles-daemon
    uwsm
    cinnamon-desktop
    ddcutil
    at-spi2-core
    gcc
    make
    pkgconf
    appmenu-gtk-module
    libdbusmenu-gtk3
    libdbusmenu-qt5
    meson
    ninja
    wayland-protocols
    libmediaart
)

# Colors and formatting
if [ -t 1 ]; then
    GREEN=$(tput setaf 2)
    YELLOW=$(tput setaf 3)
    RED=$(tput setaf 1)
    CYAN=$(tput setaf 6)
    BLUE=$(tput setaf 4)
    BOLD=$(tput bold)
    DIM=$(tput dim)
    RESET=$(tput sgr0)
else
    GREEN="" YELLOW="" RED="" CYAN="" BLUE="" BOLD="" DIM="" RESET=""
fi

# Status symbols
ARROW="→"
CHECK="✔"
CROSS="✖"
INFO="ℹ"
WARN="⚠"

# Progress tracking
TOTAL_STEPS=12
CURRENT_STEP=0

# Function for progress indicator
progress() {
    CURRENT_STEP=$((CURRENT_STEP + 1))
    echo -e "\n${BOLD}${BLUE}[${CURRENT_STEP}/${TOTAL_STEPS}]${RESET} ${BOLD}$1${RESET}"
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
    echo -e "\n${RED}${CROSS}${RESET} ${RED}${BOLD}ERROR:${RESET} ${RED}$1${RESET}\n" >&2
}

info() {
    echo -e "  ${BLUE}${INFO}${RESET} ${DIM}$1${RESET}"
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
    printf "\r"
}

# Cleanup handler
cleanup() {
    if [ -n "${SUDO_KEEPER_PID:-}" ]; then
        kill $SUDO_KEEPER_PID 2>/dev/null || true
    fi
}
trap cleanup EXIT INT TERM

# Header
clear
echo -e "${BOLD}${CYAN}"
cat << "EOF"
  ███╗   ███╗ ██████╗ ██████╗ ██╗   ██╗███████╗
  ████╗ ████║██╔═══██╗██╔══██╗██║   ██║██╔════╝
  ██╔████╔██║██║   ██║██║  ██║██║   ██║███████╗
  ██║╚██╔╝██║██║   ██║██║  ██║██║   ██║╚════██║
  ██║ ╚═╝ ██║╚██████╔╝██████╔╝╚██████╔╝███████║
  ╚═╝     ╚═╝ ╚═════╝ ╚═════╝  ╚═════╝ ╚══════╝
EOF
echo -e "${RESET}"
echo -e "${BOLD}  A hackable shell for Hyprland${RESET}"
echo -e "${DIM}  Installation Script v1.0${RESET}\n"

# Pre-flight checks
progress "Pre-flight checks"

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

step "Checking system requirements..."
if ! command -v git &>/dev/null; then
    error "git is not installed. Please install it first: sudo pacman -S git"
    exit 1
fi
success "All requirements met"

# Sudo authentication
progress "Requesting permissions"

info "Some packages require root privileges for installation"
echo ""
if ! sudo -v; then
    error "Sudo authentication failed"
    exit 1
fi
success "Permissions granted"

# Keep sudo alive
while true; do
    sudo -n true
    sleep 60
    kill -0 "$$" || exit
done 2>/dev/null &
SUDO_KEEPER_PID=$!

# Show package list
progress "Package information"

info "Total packages to install: ${BOLD}${#PACKAGES[@]}${RESET}"
echo ""
if [ "$AUTO_YES" = false ]; then
    read -rp "  ${YELLOW}${INFO}${RESET} View full package list? (y/N): " view_packages
else
    view_packages="n"
fi
if [[ "$view_packages" =~ ^[Yy]$ ]]; then
    echo ""
    printf "  ${DIM}• %s${RESET}\n" "${PACKAGES[@]}"
    echo ""
fi

# Confirmation
if [ "$AUTO_YES" = false ]; then
    read -rp "  ${BOLD}Proceed with installation? (y/N):${RESET} " confirm
else
    confirm="y"
fi
if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
    warn "Installation cancelled by user"
    exit 0
fi

# AUR helper setup
progress "Setting up AUR helper"

aur_helper="yay"
if command -v paru &>/dev/null; then
    aur_helper="paru"
    success "Found paru"
elif command -v yay &>/dev/null; then
    success "Found yay"
else
    step "Installing yay-bin..."
    tmpdir=$(mktemp -d)
    (
        git clone --quiet --depth=1 https://aur.archlinux.org/yay-bin.git "$tmpdir/yay-bin" 2>/dev/null || true
        cd "$tmpdir/yay-bin"
        makepkg -si --noconfirm >/dev/null 2>&1
    ) &
    spinner $! "Building yay-bin..."
    wait $! || {
        error "Failed to install yay-bin"
        rm -rf "$tmpdir"
        exit 1
    }
    rm -rf "$tmpdir"
    success "yay-bin installed successfully"
fi

# Repository setup
progress "Setting up Modus repository"

if [ -d "$INSTALL_DIR" ]; then
    step "Updating existing repository..."
    git -C "$INSTALL_DIR" pull --quiet 2>/dev/null || true
    success "Repository updated"
else
    step "Cloning repository..."
    git clone --quiet "$REPO_URL" "$INSTALL_DIR" 2>/dev/null || true
    success "Repository cloned"
fi
info "Location: ${INSTALL_DIR}"

# Package installation
progress "Installing packages"

step "Syncing package databases..."
$aur_helper -Syy --noconfirm >/dev/null 2>&1 || true
success "Database synced"

step "Installing required packages (this may take a while)..."
installed=0
failed=0
for pkg in "${PACKAGES[@]}"; do
    if $aur_helper -S --needed --noconfirm "$pkg" >/dev/null 2>&1; then
        installed=$((installed + 1))
    else
        failed=$((failed + 1))
        warn "Failed to install: $pkg"
    fi
    printf "\r  %b%s%b Progress: %s/%s packages" "$CYAN" "$ARROW" "$RESET" "$installed" "${#PACKAGES[@]}"
done
echo ""

if [ $failed -eq 0 ]; then
    success "All packages installed successfully"
else
    warn "$failed package(s) failed to install"
fi

# Update check
step "Checking for package updates..."
outdated=$($aur_helper -Qu 2>/dev/null | awk '{print $1}' || true)
to_update=()
for pkg in "${PACKAGES[@]}"; do
    if echo "$outdated" | grep -q "^$pkg\$"; then
        to_update+=("$pkg")
    fi
done

if [ ${#to_update[@]} -gt 0 ]; then
    step "Updating ${#to_update[@]} outdated package(s)..."
    $aur_helper -S --noconfirm "${to_update[@]}" >/dev/null 2>&1 || true
    success "Packages updated"
else
    success "All packages are up-to-date"
fi

progress "Building Global Menu shim"

step "Compiling libmenu_button_shim.so..."
SHIM_SRC="$INSTALL_DIR/src/window/globalmenu/libmenu_button_shim.c"
SHIM_OUT="$INSTALL_DIR/src/window/globalmenu/libmenu_button_shim.so"
if [ -f "$SHIM_SRC" ]; then
    if gcc -shared -fPIC -O2 -o "$SHIM_OUT" "$SHIM_SRC" "$(pkg-config --cflags --libs gtk+-3.0)" -ldl 2>/dev/null; then
        success "libmenu_button_shim.so built successfully"
    else
        warn "Failed to compile libmenu_button_shim.so - global menu may not work"
    fi
else
    warn "libmenu_button_shim.c not found - skipping shim build"
fi

progress "Building App Capture module"

step "Compiling libappcapture.so..."
if [ -d "$INSTALL_DIR/src/window/switcher/app-capture" ]; then
    if (
        cd "$INSTALL_DIR/src/window/switcher/app-capture"
        meson setup builddir --wipe >/dev/null 2>&1 || meson setup builddir >/dev/null 2>&1
        meson compile -C builddir >/dev/null 2>&1
    ); then
        success "libappcapture.so built successfully"
    else
        warn "Failed to compile App Capture module"
    fi
else
    warn "App Capture module directory not found"
fi

progress "Configuring Hyprland"

HYPR_CONFIG="$HOME/.config/hypr/hyprland.lua"
MODUS_MODULE_LINE="dofile(\"$INSTALL_DIR/config/hypr/modus.lua\")"

if [ -f "$HYPR_CONFIG" ]; then
    step "Checking Hyprland Lua configuration..."

    if grep -qF "$MODUS_MODULE_LINE" "$HYPR_CONFIG"; then
        success "Modus module already loaded"
    else
        step "Adding Modus module to Hyprland Lua config..."

        {
            echo ""
            echo "-- Modus configuration"
            echo "$MODUS_MODULE_LINE"
        } >> "$HYPR_CONFIG"

        success "Modus configuration added"
    fi
else
    warn "Hyprland Lua config not found at $HYPR_CONFIG"
    info "You may need to manually add: $MODUS_MODULE_LINE"
fi

step "Symlinking hypridle.conf..."
HYPR_DIR="$HOME/.config/hypr"
HYPRIDLE_CONF="$INSTALL_DIR/config/hypr/hypridle.conf"
HYPRIDLE_TARGET="$HYPR_DIR/hypridle.conf"
mkdir -p "$HYPR_DIR"
if [ -f "$HYPRIDLE_CONF" ]; then
    if [ -L "$HYPRIDLE_TARGET" ]; then
        rm "$HYPRIDLE_TARGET"
    fi
    ln -sf "$HYPRIDLE_CONF" "$HYPRIDLE_TARGET"
    success "hypridle.conf symlinked"
else
    warn "hypridle.conf not found at $HYPRIDLE_CONF"
fi

progress "Configuring global environment"

APP_CONF_DIR="$HOME/.config/environment.d"
APP_CONF_FILE="$APP_CONF_DIR/appmenu.conf"

step "Writing environment.d config..."
mkdir -p "$APP_CONF_DIR"
cat > "$APP_CONF_FILE" << 'EOF'
GTK_MODULES=appmenu-gtk-module
UBUNTU_MENUPROXY=1
EOF
success "Environment config written to $APP_CONF_FILE"

PAM_FILE="$HOME/.pam_environment"
step "Updating pam_environment..."
for entry in "GTK_MODULES DEFAULT=appmenu-gtk-module" "UBUNTU_MENUPROXY DEFAULT=1"; do
    var_name="${entry%% *}"
    if ! grep -q "^${var_name} " "$PAM_FILE" 2>/dev/null; then
        echo "$entry" >> "$PAM_FILE"
    fi
done
success ".pam_environment updated"

progress "Configuring Matugen"
MATUGEN_CONFIG="$HOME/.config/matugen/config.toml"

MODUS_BLOCK='[templates.modus]
input_path = "~/.config/Modus/config/matugen/templates/modus.css"
output_path = "~/.config/Modus/src/shared/styles/colors.css"
post_hook = "fabric-cli exec modus '\''app.set_css()'\'' &"'

HYPR_BLOCK='[templates.hyprland]
input_path = "~/.config/Modus/config/matugen/templates/hyprland-colors.lua"
output_path = "~/.config/Modus/config/matugen/colors.lua"'

if [ -f "$MATUGEN_CONFIG" ]; then
    step "Checking matugen config..."

    # ---- Modus1 ----
    if grep -qF "[templates.modus]" "$MATUGEN_CONFIG"; then
        success "modus1 template already exists"
    else
        step "Adding modus1 template..."
        echo "" >> "$MATUGEN_CONFIG"
        echo "$MODUS_BLOCK" >> "$MATUGEN_CONFIG"
        success "modus template added"
    fi

    # ---- Hyprland ----
    if grep -qF "[templates.hyprland]" "$MATUGEN_CONFIG"; then
        success "hyprland template already exists"
    else
        step "Adding hyprland template..."
        echo "" >> "$MATUGEN_CONFIG"
        echo "$HYPR_BLOCK" >> "$MATUGEN_CONFIG"
        success "hyprland template added"
    fi

else
    warn "matugen config not found at $MATUGEN_CONFIG"
    info "Create it first or install matugen"
fi

progress "Launching Modus"

step "Stopping existing instances..."
if killall modus 2>/dev/null; then
    success "Stopped running instance"
    sleep 1
else
    info "No existing instance found"
fi

step "Starting Modus..."
if uwsm app -- uv run --project "$INSTALL_DIR" start >/dev/null 2>&1 & then
    disown
    sleep 2
    if pgrep -x "modus" >/dev/null; then
        success "Modus is now running"
    else
        warn "Modus may not have started correctly"
    fi
else
    error "Failed to start Modus"
    exit 1
fi

# Completion
echo ""
echo -e "${GREEN}${BOLD}╔════════════════════════════════════════╗${RESET}"
echo -e "${GREEN}${BOLD}║                                        ║${RESET}"
echo -e "${GREEN}${BOLD}║     Installation completed!            ║${RESET}"
echo -e "${GREEN}${BOLD}║                                        ║${RESET}"
echo -e "${GREEN}${BOLD}╚════════════════════════════════════════╝${RESET}"
echo ""
info "Modus is running in the background"
info "Config location: ${INSTALL_DIR}"
info "Repository: ${REPO_URL}"
echo ""
