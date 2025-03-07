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
	python-ijson
	sddm-theme-corners-git
	swww
	swappy
	wl-clipboard
	wf-recorder
	libadwaita
	acpi
	adw-gtk-theme
	brightnessctl
	wlinhibit
	power-profile-daemon
	ttf-chakra-petch
	ttf-tabler-icons
)

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
	echo "Updating outdated packages..."
	$aur_helper -S --noconfirm "${to_update[@]}" || true
else
	echo "All required packages are up-to-date."
fi

# Backup and replace GTK configurations
echo "Updating GTK configurations..."
mkdir -p "$HOME/.config"
[[ -d "$HOME/.config/gtk-3.0" ]] && mv "$HOME/.config/gtk-3.0" "$HOME/.config/gtk-3.0-bk-$(date +%s)"
[[ -d "$HOME/.config/gtk-4.0" ]] && mv "$HOME/.config/gtk-4.0" "$HOME/.config/gtk-4.0-bk-$(date +%s)"

cp -r "$INSTALL_DIR/assets/gtk-3.0" "$HOME/.config/" || true
cp -r "$INSTALL_DIR/assets/gtk-4.0" "$HOME/.config/" || true

# Install Icon Theme
echo "Installing Tela icon theme..."
tmpdir=$(mktemp -d)
git clone https://github.com/vinceliuice/Tela-icon-theme "$tmpdir/Tela-icon-theme"
cd "$tmpdir/Tela-icon-theme"
./install.sh nord
rm -rf "$tmpdir"

# Install Vencord
echo "Installing Vencord..."
if command -v curl &>/dev/null; then
	sh -c "$(curl -sS https://raw.githubusercontent.com/Vendicated/VencordInstaller/main/install.sh)" || true
	mkdir -p "$HOME/.config/Vencord/settings/"
	ln -sf "$HOME/.cache/material/material-discord.css" "$HOME/.config/Vencord/settings/quickCss.css"
else
	echo "Skipping Vencord installation (curl not found)."
fi

# Launch Modus
echo "Starting Modus..."
killall modus 2>/dev/null || true
python "$INSTALL_DIR/main.py" >/dev/null 2>&1 &
disown

echo "Installation complete."
