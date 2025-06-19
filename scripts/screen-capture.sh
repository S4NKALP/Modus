#!/bin/env bash

# Script name
SCRIPT_NAME=$(basename "$0")

# Function to display usage
usage() {
	cat <<EOF
Usage: $SCRIPT_NAME <command> [options]

Commands:
  screenshot <target>     Take a screenshot
    Targets:
      selection            - Screenshot selected area
      eDP-1               - Screenshot eDP-1 display
      HDMI-A-1            - Screenshot HDMI-A-1 display
      both                - Screenshot both displays

  record <target>        Start/stop recording (with audio)
    Targets:
      selection           - Record selected area
      eDP-1              - Record eDP-1 display
      HDMI-A-1           - Record HDMI-A-1 display
      stop               - Stop current recording

  record-noaudio <target> Start/stop recording (no audio)
    Targets:
      selection           - Record selected area without audio
      eDP-1              - Record eDP-1 display without audio
      HDMI-A-1           - Record HDMI-A-1 display without audio
      stop               - Stop current recording

  record-hq <target>     Start/stop high-quality recording (for YouTube)
    Targets:
      selection           - Record selected area in high quality
      eDP-1              - Record eDP-1 display in high quality
      HDMI-A-1           - Record HDMI-A-1 display in high quality
      stop               - Stop current recording

  record-gif <target>    Start/stop GIF recording
    Targets:
      selection           - Record selected area as GIF
      eDP-1              - Record eDP-1 display as GIF
      HDMI-A-1           - Record HDMI-A-1 display as GIF
      stop               - Stop current recording

  status                 Check if recording is active (exit 0 if recording, 1 if not)

  convert <format>       Convert recordings
    Formats:
      webm               - Convert MKV files to WebM
      iphone             - Convert MKV files for iPhone
      youtube            - Convert MKV files for YouTube (high quality)
      gif                - Convert MKV/MP4 files to GIF

Examples:
  $SCRIPT_NAME screenshot selection
  $SCRIPT_NAME record eDP-1
  $SCRIPT_NAME record-noaudio selection
  $SCRIPT_NAME record-hq eDP-1
  $SCRIPT_NAME record-gif selection
  $SCRIPT_NAME record stop
  $SCRIPT_NAME convert gif

EOF
	exit 1
}

# Check if no arguments provided
if [ $# -eq 0 ]; then
	usage
fi

# Function to send screenshot notification with action buttons
send_screenshot_notification() {
	local full_path="$1"
	local save_dir=$(dirname "$full_path")

	ACTION=$(notify-send -a "Modus" -i "$full_path" "Screenshot saved" "in $full_path" \
		-A "view=View" -A "edit=Edit" -A "open=Open Folder")

	case "$ACTION" in
		view) xdg-open "$full_path" ;;
		edit) swappy -f "$full_path" ;;
		open) xdg-open "$save_dir" ;;
	esac
}

# Function to send recording notification with action buttons
send_recording_notification() {
	local full_path="$1"
	local save_dir=$(dirname "$full_path")

	ACTION=$(notify-send -a "Modus" -i "camera-video-symbolic" "Recording saved" "in $full_path" \
		-A "view=View" -A "open=Open Folder")

	case "$ACTION" in
		view) xdg-open "$full_path" ;;
		open) xdg-open "$save_dir" ;;
	esac
}

wf-recorder_check() {
	if pgrep -x "wf-recorder" >/dev/null; then
		pkill -INT -x wf-recorder
		# Get the recording file path and send notification with actions
		if [ -f /tmp/recording.txt ]; then
			recording_file=$(cat /tmp/recording.txt)
			wl-copy <"$recording_file"
			send_recording_notification "$recording_file"
		else
			notify-send "Recording stopped" "wf-recorder process terminated"
		fi
		exit 0
	fi
}

# Function to record with standard settings
record_video() {
	local output_file="$1"
	shift

	wf-recorder "$@" -f "$output_file" -c libvpx-vp9 --pixel-format yuv420p -F "eq=brightness=0.12:contrast=1.1"
}

# Function to record without audio
record_video_noaudio() {
	local output_file="$1"
	shift

	wf-recorder "$@" -f "$output_file" -c libvpx-vp9 --pixel-format yuv420p -F "eq=brightness=0.12:contrast=1.1" --no-audio
}

record_high_quality() {
	local output_file="$1"
	shift

	# High quality settings for YouTube uploads
	# - h264_vaapi for hardware encoding (if available) or libx264 for software
	# - yuv420p pixel format for maximum compatibility
	# - High bitrate (8000k) for quality
	# - GOP size of 30 for better seeking
	# - Preset 'slow' for better compression efficiency
	# - CRF 18 for high quality (lower = better quality, 0-51 scale)
	# - Audio at 192k bitrate
	# - 60 FPS for smooth motion
	# - No color filters to maintain original colors

	# Check if VAAPI hardware encoding is available
	if vainfo &>/dev/null && wf-recorder --help | grep -q "h264_vaapi"; then
		# Use hardware encoding for better performance
		wf-recorder "$@" -f "$output_file" \
			-c h264_vaapi \
			-p "preset=slow" \
			-p "crf=18" \
			-r 60 \
			-b 8000000 \
			-B 192000 \
			--pixel-format yuv420p \
			-g 30
	else
		# Fallback to software encoding
		wf-recorder "$@" -f "$output_file" \
			-c libx264 \
			-p "preset=slow" \
			-p "crf=18" \
			-r 60 \
			-b 8000000 \
			-B 192000 \
			--pixel-format yuv420p \
			-g 30
	fi
}

record_gif() {
	local output_file="$1"
	shift

	# Record temporary video first (MKV format for better quality)
	local temp_video="/tmp/gif_recording_$(date +%s).mkv"
	echo "$temp_video" >/tmp/gif_temp_video.txt

	# GIF-optimized recording settings:
	# - Lower framerate (15 fps) for smaller file size
	# - No audio recording
	# - Standard codec for compatibility
	wf-recorder "$@" -f "$temp_video" \
		-c libvpx-vp9 \
		-r 15 \
		--pixel-format yuv420p \
		--no-audio

	# After recording stops, convert to GIF
	if [ -f "$temp_video" ]; then
		notify-send "Converting to GIF" "Processing recording..."

		# Create high-quality GIF with optimized palette
		# Using ffmpeg with palette generation for better colors
		ffmpeg -i "$temp_video" \
			-vf "fps=15,scale=iw:-1:flags=lanczos,split[s0][s1];[s0]palettegen=max_colors=128:stats_mode=diff[p];[s1][p]paletteuse=dither=bayer:bayer_scale=5:diff_mode=rectangle" \
			-loop 0 \
			"$output_file" 2>/tmp/gif_conversion.log

		if [ $? -eq 0 ]; then
			# Clean up temp file
			rm -f "$temp_video"
			rm -f /tmp/gif_temp_video.txt

			# Copy to clipboard and send notification with actions
			wl-copy <"$output_file"
			send_recording_notification "$output_file"
		else
			error=$(cat /tmp/gif_conversion.log | tail -n 5)
			notify-send "GIF Conversion Failed" "Error: $error"
			rm -f "$temp_video"
			rm -f /tmp/gif_temp_video.txt
		fi
	fi
}

# Parse command
COMMAND="$1"
TARGET="$2"

# Set up file paths
IMG="${HOME}/Pictures/Screenshots/$(date +%Y-%m-%d_%H-%m-%s).png"
VID="${HOME}/Videos/Recordings/$(date +%Y-%m-%d_%H-%m-%s).mkv"

case "$COMMAND" in
"screenshot")
	case "$TARGET" in
	"selection")
		grim -g "$(slurp)" "$IMG"
		wl-copy <"$IMG"
		send_screenshot_notification "$IMG"
		;;
	"eDP-1")
		grim -c -o eDP-1 "$IMG"
		wl-copy <"$IMG"
		send_screenshot_notification "$IMG"
		;;
	"HDMI-A-1")
		grim -c -o HDMI-A-1 "$IMG"
		wl-copy <"$IMG"
		send_screenshot_notification "$IMG"
		;;
	"both")
		grim -c -o eDP-1 "${IMG//.png/-eDP-1.png}"
		grim -c -o HDMI-A-1 "${IMG//.png/-HDMI-A-1.png}"
		montage "${IMG//.png/-eDP-1.png}" "${IMG//.png/-HDMI-A-1.png}" -tile 2x1 -geometry +0+0 "$IMG"
		wl-copy <"$IMG"
		rm "${IMG//.png/-eDP-1.png}" "${IMG//.png/-HDMI-A-1.png}"
		send_screenshot_notification "$IMG"
		;;
	*)
		echo "Error: Invalid screenshot target '$TARGET'"
		usage
		;;
	esac
	;;

"record")
	case "$TARGET" in
	"stop")
		wf-recorder_check
		;;
	"selection")
		wf-recorder_check
		echo "$VID" >/tmp/recording.txt
		record_video "$VID" -g "$(slurp)"
		;;
	"eDP-1")
		wf-recorder_check
		echo "$VID" >/tmp/recording.txt
		record_video "$VID" -a -o eDP-1
		;;
	"HDMI-A-1")
		wf-recorder_check
		echo "$VID" >/tmp/recording.txt
		record_video "$VID" -a -o HDMI-A-1
		;;
	*)
		echo "Error: Invalid record target '$TARGET'"
		usage
		;;
	esac
	;;

"record-noaudio")
	case "$TARGET" in
	"stop")
		wf-recorder_check
		;;
	"selection")
		wf-recorder_check
		echo "$VID" >/tmp/recording.txt
		record_video_noaudio "$VID" -g "$(slurp)"
		;;
	"eDP-1")
		wf-recorder_check
		echo "$VID" >/tmp/recording.txt
		record_video_noaudio "$VID" -o eDP-1
		;;
	"HDMI-A-1")
		wf-recorder_check
		echo "$VID" >/tmp/recording.txt
		record_video_noaudio "$VID" -o HDMI-A-1
		;;
	*)
		echo "Error: Invalid record-noaudio target '$TARGET'"
		usage
		;;
	esac
	;;

"record-hq")
	# Change file extension to mp4 for high quality recordings
	VID_HQ="${HOME}/Videos/Recordings/$(date +%Y-%m-%d_%H-%m-%s)-hq.mp4"

	case "$TARGET" in
	"stop")
		wf-recorder_check
		;;
	"selection")
		wf-recorder_check
		echo "$VID_HQ" >/tmp/recording.txt
		notify-send "High Quality Recording" "Starting YouTube-quality recording..."
		record_high_quality "$VID_HQ" -g "$(slurp)"
		;;
	"eDP-1")
		wf-recorder_check
		echo "$VID_HQ" >/tmp/recording.txt
		notify-send "High Quality Recording" "Starting YouTube-quality recording on eDP-1..."
		record_high_quality "$VID_HQ" -a -o eDP-1
		;;
	"HDMI-A-1")
		wf-recorder_check
		echo "$VID_HQ" >/tmp/recording.txt
		notify-send "High Quality Recording" "Starting YouTube-quality recording on HDMI-A-1..."
		record_high_quality "$VID_HQ" -a -o HDMI-A-1
		;;
	*)
		echo "Error: Invalid record-hq target '$TARGET'"
		usage
		;;
	esac
	;;

"record-gif")
	# GIF files go to a specific location
	GIF="${HOME}/Videos/Recordings/$(date +%Y-%m-%d_%H-%m-%s).gif"

	case "$TARGET" in
	"stop")
		wf-recorder_check
		;;
	"selection")
		wf-recorder_check
		echo "$GIF" >/tmp/recording.txt
		notify-send "GIF Recording" "Starting GIF recording (15 FPS)..."
		record_gif "$GIF" -g "$(slurp)"
		;;
	"eDP-1")
		wf-recorder_check
		echo "$GIF" >/tmp/recording.txt
		notify-send "GIF Recording" "Starting GIF recording on eDP-1..."
		record_gif "$GIF" -o eDP-1
		;;
	"HDMI-A-1")
		wf-recorder_check
		echo "$GIF" >/tmp/recording.txt
		notify-send "GIF Recording" "Starting GIF recording on HDMI-A-1..."
		record_gif "$GIF" -o HDMI-A-1
		;;
	*)
		echo "Error: Invalid record-gif target '$TARGET'"
		usage
		;;
	esac
	;;

"status")
	# Check if wf-recorder is running
	if pgrep -x "wf-recorder" >/dev/null; then
		echo "true"
		exit 0
	else
		echo "false"
		exit 0
	fi
	;;

"convert")
	case "$TARGET" in
	"webm")
		# Check if ffmpeg is installed
		if ! command -v ffmpeg >/dev/null 2>&1; then
			notify-send "Error" "ffmpeg is not installed. Please install it to use this feature."
			exit 1
		fi

		RECORDING_DIR="${HOME}/Videos/Recordings"
		CONVERTED=0
		TOTAL=0

		for mkv_file in "${RECORDING_DIR}"/*.mkv; do
			if [ -f "$mkv_file" ]; then
				TOTAL=$((TOTAL + 1))
				webm_file="${mkv_file%.mkv}.webm"

				# Check if webm version doesn't already exist
				if [ ! -f "$webm_file" ]; then
					# Simpler ffmpeg command with basic settings
					ffmpeg -y -i "$mkv_file" -c:v libvpx -b:v 1M -c:a libvorbis "$webm_file" 2>/tmp/ffmpeg_error.log

					if [ $? -eq 0 ]; then
						CONVERTED=$((CONVERTED + 1))
						notify-send "Converted to WebM" "$(basename "$mkv_file")"
					else
						error=$(cat /tmp/ffmpeg_error.log | tail -n 5)
						notify-send "Conversion Failed" "Error: $error"
					fi
				fi
			fi
		done

		if [ $TOTAL -eq 0 ]; then
			notify-send "WebM Conversion" "No MKV files found in Recordings folder"
		else
			notify-send "WebM Conversion Complete" "Converted $CONVERTED out of $TOTAL MKV files"
		fi
		;;

	"iphone")
		# Check if ffmpeg is installed
		if ! command -v ffmpeg >/dev/null 2>&1; then
			notify-send "Error" "ffmpeg is not installed. Please install it to use this feature."
			exit 1
		fi

		RECORDING_DIR="${HOME}/Videos/Recordings"
		CONVERTED=0
		SKIPPED_IPHONE=0
		SKIPPED_EXISTING=0
		TOTAL_FILES=0

		for mkv_file in "${RECORDING_DIR}"/*.mkv; do
			if [ -f "$mkv_file" ]; then
				TOTAL_FILES=$((TOTAL_FILES + 1))
				base_filename=$(basename "$mkv_file")

				# Skip files with "iphone" in the filename
				if [[ $base_filename == *"iphone"* ]]; then
					SKIPPED_IPHONE=$((SKIPPED_IPHONE + 1))
					continue
				fi

				iphone_file="${mkv_file%.mkv}-iphone.mp4"

				# Check if iPhone version doesn't already exist
				if [ ! -f "$iphone_file" ]; then
					# Simpler ffmpeg command for iPhone compatibility
					ffmpeg -y -i "$mkv_file" -vcodec h264 -acodec aac "$iphone_file" 2>/tmp/ffmpeg_error.log

					if [ $? -eq 0 ]; then
						CONVERTED=$((CONVERTED + 1))
						notify-send "Converted for iPhone" "$(basename "$mkv_file")"
					else
						error=$(cat /tmp/ffmpeg_error.log | tail -n 5)
						notify-send "Conversion Failed" "Error: $error"
					fi
				else
					SKIPPED_EXISTING=$((SKIPPED_EXISTING + 1))
				fi
			fi
		done

		if [ $TOTAL_FILES -eq 0 ]; then
			notify-send "iPhone Conversion" "No MKV files found in Recordings folder"
		else
			notify-send "iPhone Conversion Complete" "Converted: $CONVERTED files
Skipped (already iPhone): $SKIPPED_IPHONE files
Skipped (has iPhone version): $SKIPPED_EXISTING files
Total files checked: $TOTAL_FILES"
		fi
		;;

	"youtube")
		# Check if ffmpeg is installed
		if ! command -v ffmpeg >/dev/null 2>&1; then
			notify-send "Error" "ffmpeg is not installed. Please install it to use this feature."
			exit 1
		fi

		RECORDING_DIR="${HOME}/Videos/Recordings"
		CONVERTED=0
		SKIPPED_YOUTUBE=0
		SKIPPED_EXISTING=0
		TOTAL_FILES=0

		# Process both MKV and MP4 files
		for video_file in "${RECORDING_DIR}"/*.{mkv,mp4}; do
			if [ -f "$video_file" ]; then
				TOTAL_FILES=$((TOTAL_FILES + 1))
				base_filename=$(basename "$video_file")

				# Skip files already marked as YouTube uploads
				if [[ $base_filename == *"youtube"* ]]; then
					SKIPPED_YOUTUBE=$((SKIPPED_YOUTUBE + 1))
					continue
				fi

				# Create YouTube optimized filename
				youtube_file="${video_file%.*}-youtube.mp4"

				# Check if YouTube version doesn't already exist
				if [ ! -f "$youtube_file" ]; then
					notify-send "Converting for YouTube" "Processing: $(basename "$video_file")"

					# YouTube recommended settings:
					# - H.264 codec with High profile
					# - 1080p or source resolution
					# - 60fps or source framerate
					# - High bitrate for quality (8-12 Mbps for 1080p60)
					# - AAC audio at 384kbps
					# - yuv420p pixel format for compatibility
					# - Keyframe interval of 2 seconds (GOP)
					# - No filters to preserve original colors

					ffmpeg -y -i "$video_file" \
						-c:v libx264 \
						-profile:v high \
						-preset slow \
						-crf 18 \
						-pix_fmt yuv420p \
						-c:a aac \
						-b:a 384k \
						-movflags +faststart \
						"$youtube_file" 2>/tmp/ffmpeg_error.log

					if [ $? -eq 0 ]; then
						CONVERTED=$((CONVERTED + 1))
						file_size=$(du -h "$youtube_file" | cut -f1)
						notify-send "YouTube Conversion Success" "$(basename "$video_file") → $(basename "$youtube_file") ($file_size)"
					else
						error=$(cat /tmp/ffmpeg_error.log | tail -n 5)
						notify-send "YouTube Conversion Failed" "Error converting $(basename "$video_file"): $error"
					fi
				else
					SKIPPED_EXISTING=$((SKIPPED_EXISTING + 1))
				fi
			fi
		done

		if [ $TOTAL_FILES -eq 0 ]; then
			notify-send "YouTube Conversion" "No video files found in Recordings folder"
		else
			notify-send "YouTube Conversion Complete" "Converted: $CONVERTED files
Skipped (already YouTube): $SKIPPED_YOUTUBE files
Skipped (has YouTube version): $SKIPPED_EXISTING files
Total files checked: $TOTAL_FILES"
		fi
		;;

	"gif")
		# Check if ffmpeg is installed
		if ! command -v ffmpeg >/dev/null 2>&1; then
			notify-send "Error" "ffmpeg is not installed. Please install it to use this feature."
			exit 1
		fi

		RECORDING_DIR="${HOME}/Videos/Recordings"
		CONVERTED=0
		SKIPPED_GIF=0
		SKIPPED_EXISTING=0
		TOTAL_FILES=0

		# Process both MKV and MP4 files
		for video_file in "${RECORDING_DIR}"/*.{mkv,mp4}; do
			if [ -f "$video_file" ]; then
				TOTAL_FILES=$((TOTAL_FILES + 1))
				base_filename=$(basename "$video_file")

				# Skip files already GIFs
				if [[ $base_filename == *.gif ]]; then
					SKIPPED_GIF=$((SKIPPED_GIF + 1))
					continue
				fi

				# Create GIF filename
				gif_file="${video_file%.*}.gif"

				# Check if GIF version doesn't already exist
				if [ ! -f "$gif_file" ]; then
					notify-send "Converting to GIF" "Processing: $(basename "$video_file")"

					# Get video dimensions for scaling
					width=$(ffprobe -v error -select_streams v:0 -show_entries stream=width -of csv=s=x:p=0 "$video_file")

					# Scale down if wider than 800px to keep file size reasonable
					if [ "$width" -gt 800 ]; then
						scale_filter="scale=800:-1:flags=lanczos,"
					else
						scale_filter=""
					fi

					# Create high-quality GIF with optimized palette
					ffmpeg -i "$video_file" \
						-vf "${scale_filter}fps=15,split[s0][s1];[s0]palettegen=max_colors=256:stats_mode=diff[p];[s1][p]paletteuse=dither=bayer:bayer_scale=5:diff_mode=rectangle" \
						-loop 0 \
						"$gif_file" 2>/tmp/ffmpeg_error.log

					if [ $? -eq 0 ]; then
						CONVERTED=$((CONVERTED + 1))
						send_recording_notification "$gif_file"
					else
						error=$(cat /tmp/ffmpeg_error.log | tail -n 5)
						notify-send "GIF Conversion Failed" "Error converting $(basename "$video_file"): $error"
					fi
				else
					SKIPPED_EXISTING=$((SKIPPED_EXISTING + 1))
				fi
			fi
		done

		if [ $TOTAL_FILES -eq 0 ]; then
			notify-send "GIF Conversion" "No video files found in Recordings folder"
		else
			notify-send "GIF Conversion Complete" "Converted: $CONVERTED files
Skipped (already GIF): $SKIPPED_GIF files
Skipped (has GIF version): $SKIPPED_EXISTING files
Total files checked: $TOTAL_FILES"
		fi
		;;

	*)
		echo "Error: Invalid convert format '$TARGET'"
		usage
		;;
	esac
	;;

*)
	echo "Error: Invalid command '$COMMAND'"
	usage
	;;
esac
