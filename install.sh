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

set -e          # Exit immediately if a command exits with a non-zero status
set -u          # Treat unset variables as an error
set -o pipefail # Prevent errors in a pipeline from being masked

REPO_URL="https://github.com/S4NKALP/Modus.git"
INSTALL_DIR="$HOME/.config/Modus1"

PACKAGES=(
    python-fabric-git
    fabric-cli-git
    glace-git
    cliphist
    gnome-bluetooth-3.0
    gobject-introspection
    slurp
    ffmpeg
    hypridle
    hyprsunset
    hyprpicker
    imagemagick
    libnotify
    matugen-bin
    playerctl
    python-fabric-git
    python-gobject
    python-pillow
    python-setproctitle
    python-toml
    python-requests
    python-numpy
    python-pywayland
    python-pyxdg
    python-ijson
    python-watchdog
    python-pyotp
    pyzbar
    python-pywayland
    python-psutil
    python-pydbus
    python-thefuzz
    python-pam
    gtk-session-lock
    swww
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
)

# Colors
GREEN=$(tput setaf 2)
YELLOW=$(tput setaf 3)
RED=$(tput setaf 1)
CYAN=$(tput setaf 6)
RESET=$(tput sgr0)

# Function for status messages
step() {
    echo -e "${CYAN}→${RESET} $1"
}
success() {
    echo -e "${GREEN}✔${RESET} $1"
}
warn() {
    echo -e "${YELLOW}!${RESET} $1"
}
error() {
    echo -e "${RED}✖${RESET} $1"
}

echo -e "${GREEN}=================================="
echo "   Modus Installer for Arch Linux"
echo -e "==================================${RESET}"

# OS check
if ! grep -qi "arch" /etc/os-release; then
    error "This script is designed for Arch Linux or Arch-based distro."
    exit 1
fi

# Root check
if [ "$(id -u)" -eq 0 ]; then
    error "Please do not run as root."
    exit 1
fi

# Warn about sudo
echo -e "\n${YELLOW}Some packages require root privileges (e.g., glace-git).${RESET}"
echo "You will be prompted for your sudo password now so the installation runs smoothly."
sudo -v || {
    error "Sudo authentication failed."
    exit 1
}

# Keep sudo alive until script finishes
while true; do
    sudo -n true
    sleep 60
    kill -0 "$$" || exit
done 2>/dev/null &

# Confirm installation
echo -e "\nThis will install Modus and the following packages:"
printf "%s\n" "${PACKAGES[@]}"
read -rp "$(echo -e "${YELLOW}""Proceed? (y/N): ""${RESET}")" confirm
if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
    warn "Installation cancelled."
    exit 0
fi

aur_helper="yay"

# Check if paru exists, otherwise use yay
if command -v paru &>/dev/null; then
    aur_helper="paru"
elif ! command -v yay &>/dev/null; then
    echo "Installing yay-bin..."
    tmpdir=$(mktemp -d)
    git clone --depth=1 https://aur.archlinux.org/yay-bin.git "$tmpdir/yay-bin"
    (cd "$tmpdir/yay-bin" && makepkg -si --noconfirm)
    rm -rf "$tmpdir"
fi

# Clone or update repo
if [ -d "$INSTALL_DIR" ]; then
    step "Updating Modus repository..."
    git -C "$INSTALL_DIR" pull
else
    step "Cloning Modus repository..."
    git clone "$REPO_URL" "$INSTALL_DIR"
fi
success "Repository ready."

# Install packages
step "Installing required packages..."
$aur_helper -Syy --needed --noconfirm "${PACKAGES[@]}" || warn "Some packages failed to install."

# Update outdated packages
step "Checking for outdated packages..."
outdated=$($aur_helper -Qu | awk '{print $1}' || true)
to_update=()
for pkg in "${PACKAGES[@]}"; do
    if echo "$outdated" | grep -q "^$pkg\$"; then
        to_update+=("$pkg")
    fi
done

if [ ${#to_update[@]} -gt 0 ]; then
    step "Updating outdated packages..."
    $aur_helper -S --noconfirm "${to_update[@]}"
else
    success "All packages are up-to-date."
fi

#  Run config
# step "Running configuration..."
# python "$INSTALL_DIR/config/config.py"

# Start Modus
step "Starting Modus..."
killall modus 2>/dev/null || true
uwsm app -- python "$INSTALL_DIR/main.py" >/dev/null 2>&1 &
disown
success "Modus started successfully."

echo -e "\n${GREEN}Installation complete!${RESET}"
