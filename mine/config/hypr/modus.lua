local modus = "/home/sankalp/.config/Modus"

hl.on("hyprland.start", function()
	local cmds = {
		"uwsm app -- awww-daemon",
		"wl-paste --type text --watch cliphist store",
		"wl-paste --type image --watch cliphist store",
		"pgrep -x hypridle >/dev/null || uwsm app -- hypridle",
		"cd " .. modus .. " && uwsm app -- uv run main.py",
	}
	for i = 1, #cmds do
		local cmd = cmds[i]
		hl.exec_cmd(cmd)
	end
end)

local fabricSend = "uwsm app -- fabric-cli exec modus "

-- notification testing
for key, cmd in pairs({
	["ALT + F12"] = 'notify-send \'Test notification\' "Here\'s a really long message to test truncation and wrapping\\nYou can middle click or flick this notification to dismiss it!" -a \'terminal\' -A "Test1=I got it!" -A "Test2=Another action"',
	["ALT + Equal"] = "notify-send 'hmm' ${SLURP_ARGS}",
	["SHIFT + ALT + N"] = 'notify-send "Hello" "FIRE IN THE HOLE‼️🗣️🔥🕳️" -i "/home/sankalp/.face.icon" -A "🗣️" -A "🔥" -A "🕳️" -a "Source Code"',
}) do
	hl.bind(key, hl.dsp.exec_cmd(cmd))
end

-- Reload Modus
hl.bind("ALT + SHIFT + R", hl.dsp.exec_cmd("killall modus; cd " .. modus .. " && uwsm app -- uv run main.py"))

-- Fabric Launcher Binds
for key, method in pairs({
	["SUPER + D"] = "launcher.toggle()", -- Launcher
	["SUPER + E"] = "launcher.toggle('em')", -- Emoji
	["SUPER + V"] = "launcher.toggle('clip')", -- Clipboard
	["SUPER + W"] = "launcher.toggle('wall')", -- Wallpaper
	["SUPER + X"] = "launcher.toggle('pm')", -- Powermenu
	["SUPER + Z"] = "launcher.toggle('sc')", -- Screencapture
	["SUPER + O"] = "launcher.toggle('otp')", -- OTP
	["SUPER + SHIFT + P"] = "launcher.toggle('pass')", -- Password Manager
	["SUPER + S"] = "launcher.toggle('sc region', external=True)", -- Screenshot region
	["ALT + SHIFT + W"] = "launcher.toggle('wr', external=True)", -- Random Wallpaper
	["SUPER + G"] = "launcher.toggle('gg')", -- Google Search
	["ALT + W"] = "launcher.toggle('win')", -- Window Switcher
	["SUPER + T"] = "launcher.toggle('tmux')", -- Tmux
	["ALT + SPACE"] = "switch_keyboard_layout()", -- KB_Layout Switcher
}) do
	hl.bind(key, hl.dsp.exec_cmd(fabricSend .. '"' .. method .. '"'))
end

-- Audio keys
for key, cmd in pairs({
	AudioRaiseVolume = "wpctl set-volume -l 1 @DEFAULT_AUDIO_SINK@ 5%+",
	AudioLowerVolume = "wpctl set-volume @DEFAULT_AUDIO_SINK@ 5%-",
	AudioMute = "wpctl set-mute @DEFAULT_AUDIO_SINK@ toggle",
	AudioMicMute = "wpctl set-mute @DEFAULT_AUDIO_SOURCE@ toggle",
}) do
	hl.bind(
		"XF86" .. key,
		hl.dsp.exec_cmd(cmd .. " && " .. fabricSend .. '"osd_show_audio()"'),
		{ locked = true, repeating = true }
	)
end

-- Brightness keys
for key, cmd in pairs({
	MonBrightnessUp = "brightnessctl -e4 -n2 set 5%+",
	MonBrightnessDown = "brightnessctl -e4 -n2 set 5%-",
}) do
	hl.bind(
		"XF86" .. key,
		hl.dsp.exec_cmd(cmd .. " && " .. fabricSend .. '"osd_show_brightness()"'),
		{ locked = true, repeating = true }
	)
end

hl.layer_rule({
	match = {
		namespace = "fabric",
	},
	no_anim = true,
})

local colors = dofile(modus .. "/config/hypr/colors.lua")

hl.config({
	general = {
		col = {
			active_border = colors.primary,
			inactive_border = colors.surface,
		},
		gaps_in = 2,
		gaps_out = 4,
		border_size = 2,
		layout = "scrolling",
	},
	decoration = {
		blur = {
			enabled = false,
			size = 5,
			passes = 3,
			new_optimizations = true,
			contrast = 1,
			brightness = 1,
		},
		rounding = 14,
		shadow = {
			enabled = false,
			range = 10,
			render_power = 2,
			color = "rgba(0, 0, 0, 0.25)",
		},
	},
	animations = {
		enabled = true,
	},
})

-- Curves
hl.curve("expressiveFastSpatial", { type = "bezier", points = { { 0.42, 1.67 }, { 0.21, 0.90 } } })
hl.curve("expressiveSlowSpatial", { type = "bezier", points = { { 0.39, 1.29 }, { 0.35, 0.98 } } })
hl.curve("expressiveDefaultSpatial", { type = "bezier", points = { { 0.38, 1.21 }, { 0.22, 1.00 } } })
hl.curve("emphasizedDecel", { type = "bezier", points = { { 0.05, 0.7 }, { 0.1, 1 } } })
hl.curve("emphasizedAccel", { type = "bezier", points = { { 0.3, 0 }, { 0.8, 0.15 } } })
hl.curve("standardDecel", { type = "bezier", points = { { 0, 0 }, { 0, 1 } } })
hl.curve("menu_decel", { type = "bezier", points = { { 0.1, 1 }, { 0, 1 } } })
hl.curve("menu_accel", { type = "bezier", points = { { 0.52, 0.03 }, { 0.72, 0.08 } } })
hl.curve("stall", { type = "bezier", points = { { 1, -0.1 }, { 0.7, 0.85 } } })

-- Configs
-- Animations
local animations = {
	-- leaf, speed, bezier, style
	{ "windowsIn", 3, "emphasizedDecel", "popin 80%" },
	{ "fadeIn", 3, "emphasizedDecel" },
	{ "windowsOut", 2, "emphasizedDecel", "popin 90%" },
	{ "fadeOut", 2, "emphasizedDecel" },
	{ "windowsMove", 3, "emphasizedDecel", "slide" },
	{ "border", 10, "emphasizedDecel" },
	{ "layersIn", 2.7, "emphasizedDecel", "popin 93%" },
	{ "layersOut", 2.4, "menu_accel", "popin 94%" },
	{ "fadeLayersIn", 0.5, "menu_decel" },
	{ "fadeLayersOut", 2.7, "stall" },
	{ "workspaces", 7, "menu_decel", "slide" },
	{ "specialWorkspaceIn", 2.8, "emphasizedDecel", "slidevert" },
	{ "specialWorkspaceOut", 1.2, "emphasizedAccel", "slidevert" },
	{ "zoomFactor", 3, "standardDecel" },
}

for _, anim in ipairs(animations) do
	hl.animation({ leaf = anim[1], enabled = true, speed = anim[2], bezier = anim[3], style = anim[4] })
end
