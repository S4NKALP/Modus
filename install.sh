#!/bin/bash

set -e          # Exit immediately if a command exits with a non-zero status
set -u          # Treat unset variables as an error
set -o pipefail # Prevent errors in a pipeline from being masked

REPO_URL="https://github.com/S4NKALP/Modus"
INSTALL_DIR="$HOME/Modus"

PACKAGES=(
	fabric-cli-git
	gnome-bluetooth-3.0
	grimblast
	hypridle
	hyprlock
	hyprpicker
	imagemagick
	libnotify
	python-fabric-git
	python-materialyoucolor-git
	python-pillow
	python-setproctitle
	python-toml
	python-requests
	python-numpy
	python-pywayland
	python-pyxdg
	sddm-theme-corners-git
	swww
	swappy
	wl-clipboard
	wf-recorder
	libadwaita
	adw-gtk-theme
	brightnessctl
	power-profile-daemon
	ttf-font-awesome
	otf-font-awesome
	ttf-material-symbols-variable-git
	ttf-google-sans
	ttf-opensans
	ttf-robot
)

if ! grep -q "arch" /etc/os-release; then
	echo ":: This script is designed to run on Arch Linux."
	exit 1
fi

# Optional: Prevent running as root
if [ "$(id -u)" -eq 0 ]; then
	echo "Please do not run this script as root."
	exit 1
fi

# Install paru if not installed
if ! command -v yay &>/dev/null; then
	echo "Installing paru..."
	tmpdir=$(mktemp -d)
	git clone https://aur.archlinux.org/paru.git "$tmpdir/paru"
	cd "$tmpdir/paru"
	makepkg -si --noconfirm
	cd - >/dev/null
	rm -rf "$tmpdir"
fi

# Clone or update the repository
if [ -d "$INSTALL_DIR" ]; then
	echo "Updating Modus..."
	git -C "$INSTALL_DIR" pull
else
	echo "Cloning Modus..."
	git clone "$REPO_URL" "$INSTALL_DIR"
fi

# Install required packages using paru
echo "Installing required packages..."
paru -S --needed --noconfirm "${PACKAGES[@]}" || true

# Install Icon
echo "Installing icon theme..."
tmpdir=$(mktemp -d)
cd /tmp/install
git clone https://github.com/vinceliuice/Tela-icon-theme
cd "$tmpdir/Tela-icon-theme"
./install.sh nord

# Launch Modus without terminal output
echo "Starting Modus..."
killall modus 2>/dev/null || true
python "$INSTALL_DIR/main.py" >/dev/null 2>&1 &
disown

echo "Installation complete."
