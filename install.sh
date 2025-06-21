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

REPO_URL="https://github.com/S4NKALP/Modus"
INSTALL_DIR="$HOME/Modus"

PACKAGES=(
	fabric-cli-git
	cava
	cliphist
	gnome-bluetooth-3.0
  	gobject-introspection
	slurp
	ffmpeg
	grimblast
	hypridle
	hyprlock
	hyprpicker
	imagemagick
	libnotify
	matugen-bin
  	noto-fonts-emoji
 	nvtop
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
	ttf-nerd-fonts-symbols-mono
	swww
	swappy
	wl-clipboard
	webp-pixbuf-loader
	wf-recorder
	acpi
	brightnessctl
	power-profile-daemon
	ttf-tabler-icons
	uwsm
)

echo "Starting Modus installation..."
echo "=================================="

# Ensure running on Arch Linux
if ! grep -q "arch" /etc/os-release; then
	echo "This script is designed to run on Arch Linux."
	exit 1
fi

# Prevent running as root
if [ "$(id -u)" -eq 0 ]; then
	echo "Please do not run this script as root."
	exit 1
fi

# Check for AUR helper (yay or paru)
aur_helper=""
if command -v yay &>/dev/null; then
	aur_helper="yay"
elif command -v paru &>/dev/null; then
	aur_helper="paru"
else
	echo "Installing paru..."
	tmpdir=$(mktemp -d)
	git clone https://aur.archlinux.org/paru.git "$tmpdir/paru"
	cd "$tmpdir/paru"
	makepkg -si --noconfirm
	cd - >/dev/null
	rm -rf "$tmpdir"
	aur_helper="paru"
fi

echo "Using AUR helper: $aur_helper"

# Clone or update the Modus repository
if [ -d "$INSTALL_DIR" ]; then
	echo "Updating Modus..."
	git -C "$INSTALL_DIR" pull
else
	echo "Cloning Modus..."
	git clone "$REPO_URL" "$INSTALL_DIR"
fi

# Install required packages using the AUR helper
echo "Installing required packages..."
$aur_helper -Syy --needed --noconfirm "${PACKAGES[@]}" || true

# Update outdated packages
echo "Checking for outdated packages..."
outdated=$($aur_helper -Qu | awk '{print $1}' || true)
to_update=()
for pkg in "${PACKAGES[@]}"; do
	if echo "$outdated" | grep -q "^$pkg\$"; then
		to_update+=("$pkg")
	fi
done

if [ ${#to_update[@]} -gt 0 ]; then
	echo "⬆Updating outdated packages..."
	$aur_helper -S --noconfirm "${to_update[@]}" || true
else
	echo "All required packages are up-to-date."
fi


python "$INSTALL_DIR/config/config.py"
echo "Starting Modus..."
killall modus 2>/dev/null || true
uwsm app -- python "$INSTALL_DIR/main.py" > /dev/null 2>&1 & disown


echo "Installation complete!"
