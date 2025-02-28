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
	wlinhibit
	power-profile-daemon
	ttf-google-sans
	ttf-opensans
	ttf-tabler-icons
)

if ! grep -q "arch" /etc/os-release; then
	echo "This script is designed to run on Arch Linux."
	exit 1
fi

# Prevent running as root
if [ "$(id -u)" -eq 0 ]; then
	echo "Please do not run this script as root."
	exit 1
fi

aur_helper=""
if command -v yay &>/dev/null; then
	aur_helper="yay"
	echo $aur_helper
elif command -v paru &>/dev/null; then
	aur_helper="paru"
	echo $aur_helper
else
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

# Install required packages using $aur_helper (only if missing
echo "Installing required packages..."
$aur_helper -Syy --needed --noconfirm "${PACKAGES[@]}" || true

# Update outdated packages from the list
echo "Updating outdated required packages..."
# Get a list of outdated packages
outdated=$($aur_helper -Qu | awk '{print $1}')
to_update=()
for pkg in "${PACKAGES[@]}"; do
	if echo "$outdated" | grep -q "^$pkg\$"; then
		to_update+=("$pkg")
	fi
done

if [ ${#to_update[@]} -gt 0 ]; then
	$aur_helper -S --noconfirm "${to_update[@]}" || true
else
	echo "All required packages are up-to-date."
fi

# Backup and replace GTK configs
echo "Updating GTK configurations..."
mkdir -p "$HOME/.config"
[[ -d "$HOME/.config/gtk-3.0" ]] && mv "$HOME/.config/gtk-3.0" "$HOME/.config/gtk-3.0-bk"
[[ -d "$HOME/.config/gtk-4.0" ]] && mv "$HOME/.config/gtk-4.0" "$HOME/.config/gtk-4.0-bk"

cp -r "$INSTALL_DIR/assets/gtk-3.0" "$HOME/.config/"
cp -r "$INSTALL_DIR/assets/gtk-4.0" "$HOME/.config/"

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
