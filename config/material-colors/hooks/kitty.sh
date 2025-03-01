#!/bin/bash
# Define the cache path where your colors-kitty.conf file is stored.
CACHE_PATH="${HOME}/.cache/material"
COLORS_FILE="${CACHE_PATH}/colors-kitty.conf"

if [ -f "$COLORS_FILE" ]; then
	# Reload kitty colors using kitty's remote control.
	kitty @ set-colors --all "$COLORS_FILE"
	# Send the USR1 signal to kitty to complete the reload process.
	pkill -USR1 kitty
	echo "Kitty colors reloaded successfully."
else
	echo "Colors file not found at $COLORS_FILE."
fi
