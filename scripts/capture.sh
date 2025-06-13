
#!/bin/bash

# Print usage information
print_usage() {
	cat <<"EOF"
Usage: screen-tools.sh [mode] [option]
Modes:
    screenshot [option]    Take a screenshot
        Options:
            p     Print all screens
            s     Snip current screen
            sf    Snip current screen (frozen)
            m     Print focused monitor
            [mockup]  Optional: Add mockup effect to screenshot

    record               Start/Stop screen recording

    ocr                  Perform OCR on selected area
EOF
}

# OCR functionality using hyprshot
do_ocr() {
	sleep 0.25

	# Temporary file to store the snipped image
	temp_ocr_image="$(mktemp --suffix=.png)"
	hyprshot -s -z -m region -o "$(dirname "$temp_ocr_image")" -f "$(basename "$temp_ocr_image")"

	if [ ! -f "$temp_ocr_image" ]; then
		notify-send -a "Modus" "OCR Failed" "No image captured"
		exit 1
	fi

	# Perform OCR with tesseract
	ocr_text=$(tesseract "$temp_ocr_image" - -l eng 2>/dev/null)

	rm -f "$temp_ocr_image" # Clean up temp file

	# Check if OCR was successful
	if [[ -n "$ocr_text" ]]; then
		echo -n "$ocr_text" | wl-copy
		notify-send -a "Modus" "OCR Success" "Text copied to clipboard"
	else
		notify-send -a "Modus" "OCR Failed" "No text recognized or operation failed"
	fi
}

# Screen recording functionality
do_screenrecord() {
	if [ -z "$XDG_VIDEOS_DIR" ]; then
		XDG_VIDEOS_DIR="$HOME/Videos"
	fi
	local save_dir="${XDG_VIDEOS_DIR:-$HOME/Videos}/Recordings"
	mkdir -p "$save_dir"

	if pgrep -f "gpu-screen-recorder" >/dev/null; then
		pkill -SIGINT -f "gpu-screen-recorder"
		sleep 1

		local last_video=$(ls -t "$save_dir"/*.mp4 2>/dev/null | head -n 1)
		local action=$(notify-send -a "Modus" "⬜ Recording stopped" -A "view=View" -A "open=Open folder")

		if [ "$action" = "view" ] && [ -n "$last_video" ]; then
			xdg-open "$last_video"
		elif [ "$action" = "open" ]; then
			xdg-open "$save_dir"
		fi
		exit 0
	fi

	local output_file="$save_dir/$(date +%Y-%m-%d-%H-%M-%S).mp4"
	notify-send -a "Modus" "🔴 Recording started"
	gpu-screen-recorder -w screen -q ultra -a default_output -ac opus -cr full -f 60 -o "$output_file"
}

# Screenshot functionality
do_screenshot() {
	sleep 0.25

	if [ -z "$XDG_PICTURES_DIR" ]; then
		XDG_PICTURES_DIR="$HOME/Pictures"
	fi

	local save_dir="${3:-$XDG_PICTURES_DIR/Screenshots}"
	local save_file=$(date +'%y%m%d_%Hh%Mm%Ss_screenshot.png')
	local full_path="$save_dir/$save_file"
	mkdir -p "$save_dir"

	local mockup_mode="$2"

	case $1 in
	p) hyprshot -s -m output -o "$save_dir" -f "$save_file" ;;
	s) hyprshot -s -m region -o "$save_dir" -f "$save_file" ;;
	sf) hyprshot -s -z -m region -o "$save_dir" -f "$save_file" ;;
	m) hyprshot -s -m output -m active -o "$save_dir" -f "$save_file" ;;
	*)
		echo "Invalid screenshot mode"
		print_usage
		exit 1
		;;
	esac

	if [ -f "$full_path" ]; then
		if [ "$mockup_mode" != "mockup" ]; then
			if command -v wl-copy >/dev/null 2>&1; then
				wl-copy <"$full_path"
			elif command -v xclip >/dev/null 2>&1; then
				xclip -selection clipboard -t image/png <"$full_path"
			fi
		fi

		# Process as mockup if requested
		if [ "$mockup_mode" = "mockup" ]; then
			temp_file="${full_path%.png}_temp.png"
			cropped_file="${full_path%.png}_cropped.png"
			mockup_file="${full_path%.png}_mockup.png"
			mockup_success=true

			# Crop top pixel
			convert "$full_path" -crop +0+1 +repage "$cropped_file" || mockup_success=false

			# Rounded corners and transparency
			if [ "$mockup_success" = true ]; then
				convert "$cropped_file" \
					\( +clone -alpha extract -draw 'fill black polygon 0,0 0,20 20,0 fill white circle 20,20 20,0' \
					\( +clone -flip \) -compose Multiply -composite \
					\( +clone -flop \) -compose Multiply -composite \
					\) -alpha off -compose CopyOpacity -composite "$temp_file" || mockup_success=false
			fi

			# Add shadow
			if [ "$mockup_success" = true ]; then
				convert "$temp_file" \
					\( +clone -background black -shadow 60x20+0+10 -alpha set -channel A -evaluate multiply 1 +channel \) \
					+swap -background none -layers merge +repage "$mockup_file" || mockup_success=false
			fi

			# Finalize
			if [ "$mockup_success" = true ] && [ -f "$mockup_file" ]; then
				rm "$temp_file" "$cropped_file"
				mv "$mockup_file" "$full_path"
				if command -v wl-copy >/dev/null 2>&1; then
					wl-copy <"$full_path"
				elif command -v xclip >/dev/null 2>&1; then
					xclip -selection clipboard -t image/png <"$full_path"
				fi
			else
				echo "Warning: Mockup processing failed for $full_path." >&2
				rm -f "$temp_file" "$cropped_file" "$mockup_file"
				if [ "$mockup_mode" = "mockup" ]; then
					if command -v wl-copy >/dev/null 2>&1; then
						wl-copy <"$full_path"
					elif command -v xclip >/dev/null 2>&1; then
						xclip -selection clipboard -t image/png <"$full_path"
					fi
				fi
			fi
		fi

		local action=$(notify-send -a "Modus" -i "$full_path" "Screenshot saved" "in $full_path" \
			-A "view=View" -A "edit=Edit" -A "open=Open Folder")

		case "$action" in
		view) xdg-open "$full_path" ;;
		edit) swappy -f "$full_path" ;;
		open) xdg-open "$save_dir" ;;
		esac
	else
		notify-send -a "Modus" "Screenshot Aborted"
	fi
}

# Handle command line arguments
if [ $# -eq 0 ]; then
	print_usage
	exit 1
fi

case "$1" in
screenshot)
	if [ $# -lt 2 ]; then
		echo "Error: Screenshot mode requires an option"
		print_usage
		exit 1
	fi
	do_screenshot "$2" "$3"
	;;
record)
	do_screenrecord
	;;
ocr)
	do_ocr
	;;
*)
	echo "Error: Invalid mode '$1'"
	print_usage
	exit 1
	;;
esac
