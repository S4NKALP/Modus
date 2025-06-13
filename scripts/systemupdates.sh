#!/bin/bash

# Word of caution: Changing this may break the update module, be careful!

# Function to check updates for Arch-based distros
check_arch_updates() {
	official_updates=0
	aur_updates=0
	flatpak_updates=0
	tooltip=""

	# Get the number of official updates
	official_updates=$(checkupdates 2>/dev/null | wc -l)

	# Determine the AUR helper
	if command -v paru &>/dev/null; then
		aur_helper="paru"
	else
		aur_helper="yay"
	fi

	# Get the number of AUR updates
	aur_updates=$($aur_helper -Qum 2>/dev/null | wc -l)

	# Check for Flatpak updates
	if command -v flatpak &>/dev/null; then
		flatpak_updates=$(flatpak remote-ls --updates | wc -l)
	fi

	# Calculate total updates
	total_updates=$((official_updates + aur_updates + flatpak_updates))

	# Build the tooltip
	tooltip="󰣇 Official: $official_updates\n󰮯 AUR: $aur_updates\n Flatpak: $flatpak_updates"

	# Output JSON
	echo "{\"total\":\"$total_updates\", \"tooltip\":\"$tooltip\"}"
}

# Function to check updates for Ubuntu-based distros
check_ubuntu_updates() {
	official_updates=0
	flatpak_updates=0
	tooltip=""

	# Get the number of official updates
	official_updates=$(apt-get -s -o Debug::NoLocking=true upgrade | grep -c ^Inst)

	# Check for Flatpak updates
	if command -v flatpak &>/dev/null; then
		flatpak_updates=$(flatpak remote-ls --updates | wc -l)
	fi

	# Calculate total updates
	total_updates=$((official_updates + flatpak_updates))

	# Build the tooltip
	tooltip="󰕈 Official: $official_updates\n Flatpak: $flatpak_updates"

	# Output JSON
	echo "{\"total\":\"$total_updates\", \"tooltip\":\"$tooltip\"}"
}

# Function to check updates for Fedora-based distros
check_fedora_updates() {
	official_updates=0
	flatpak_updates=0
	tooltip=""

	# Get the number of official updates
	official_updates=$(dnf list updates -q | tail -n +2 | wc -l)

	# Check for Flatpak updates
	if command -v flatpak &>/dev/null; then
		flatpak_updates=$(flatpak remote-ls --updates | wc -l)
	fi

	# Calculate total updates
	total_updates=$((official_updates + flatpak_updates))

	# Build the tooltip
	tooltip="󰣛 Official: $official_updates\n Flatpak: $flatpak_updates"

	# Output JSON
	echo "{\"total\":\"$total_updates\", \"tooltip\":\"$tooltip\"}"
}

# Function to check updates for openSUSE-based distros
check_opensuse_updates() {
	official_updates=0
	flatpak_updates=0
	tooltip=""

	# Get the number of official updates (skip header lines)
	official_updates=$(zypper lu | tail -n +3 | wc -l)

	# Check for Flatpak updates
	if command -v flatpak &>/dev/null; then
		flatpak_updates=$(flatpak remote-ls --updates | wc -l)
	fi

	# Calculate total updates
	total_updates=$((official_updates + flatpak_updates))

	# Build the tooltip
	tooltip=" Official: $official_updates\n Flatpak: $flatpak_updates"

	# Output JSON
	echo "{\"total\":\"$total_updates\", \"tooltip\":\"$tooltip\"}"
}

# Function to update Arch-based distros
update_arch() {
	kitty --title "System Update" sh -c "
		fastfetch
		yay -Syu
		read -n 1 -p 'Press any key to continue...'
	"
}

# Function to update Ubuntu-based distros
update_ubuntu() {
	kitty --title "System Update" sh -c "
		neofetch
		sudo apt update && sudo apt upgrade -y
		read -n 1 -p 'Press any key to continue...'
	"
}

# Function to update Fedora-based distros
update_fedora() {
	kitty --title "System Update" sh -c "
		neofetch
		sudo dnf upgrade -y
		read -n 1 -p 'Press any key to continue...'
	"
}

# Function to update openSUSE-based distros
update_opensuse() {
	kitty --title "System Update" sh -c "
		neofetch
		sudo zypper up -y
		read -n 1 -p 'Press any key to continue...'
	"
}

# Main case handling for different distributions
case "$1" in
-arch)
	if [ -z "$2" ]; then
		check_arch_updates
	else
		update_arch
	fi
	;;
-ubuntu)
	if [ -z "$2" ]; then
		check_ubuntu_updates
	else
		update_ubuntu
	fi
	;;
-fedora)
	if [ -z "$2" ]; then
		check_fedora_updates
	else
		update_fedora
	fi
	;;
-suse)
	if [ -z "$2" ]; then
		check_opensuse_updates
	else
		update_opensuse
	fi
	;;
*)
	echo "Usage: $0 [-arch|-ubuntu|-fedora|-suse] [up (optional)]"
	exit 1
	;;
esac
