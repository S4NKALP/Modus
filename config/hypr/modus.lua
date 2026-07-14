-- local modus = os.getenv("HOME") .. "/.config/Modus"
local modus = os.getenv("HOME") .. "/Projects/dev/Modus"
local colors = dofile(modus .. "/config/hypr/colors.lua")
local fabricSend = "fabric-cli exec modus"

-- startup
hl.on("hyprland.start", function()
	local cmds = {
		"uwsm app -- awww-daemon",
		"wl-paste --type text --watch cliphist store",
		"wl-paste --type image --watch cliphist store",
		"pgrep -x hypridle >/dev/null || uwsm app -- hypridle",
		"cd " .. modus .. " && uwsm app -- uv run start",
	}
	for i = 1, #cmds do
		local cmd = cmds[i]
		hl.exec_cmd(cmd)
	end
end)

-- Reload Modus
hl.bind("ALT + SHIFT + R", hl.dsp.exec_cmd("killall modus; cd " .. modus .. " && uwsm app -- uv run start"))

-- Fabric Binds
for key, method in pairs({
	["SUPER + SHIFT + Y"] = "app.set_css()", -- Reload CSS
	["ALT + TAB"] = "switcher.show_switcher()", -- Application Switcher
	["SUPER + Z"] = "screencapture.toggle()", -- ScreenCapture
	["SUPER + S"] = "screencapture.toggle(ss='region')", -- Screenshot Region
	["ALT + SPACE"] = "switch_keyboard_layout()", -- KB_Layout Switcher
}) do
	hl.bind(key, hl.dsp.exec_cmd(fabricSend .. ' "' .. method .. '"'))
end

-- Spotlight Binds (spawns the process; it exits when closed to free memory.
-- A second press while open forwards a toggle to the running instance.)
local spotlightCmd = "cd " .. modus .. " && uv run python start.py spotlight"
for key, args in pairs({
	["SUPER + D"] = "", -- Spotlight
	["SUPER + E"] = "em", -- Emoji
	["SUPER + V"] = "clip", -- Clipboard
	["SUPER + W"] = "wall", -- Wallpaper
	["ALT + SHIFT + W"] = "--external wr", -- Random Wallpaper
}) do
	local cmd = spotlightCmd
	if args ~= "" then
		cmd = cmd .. " " .. args
	end
	hl.bind(key, hl.dsp.exec_cmd(cmd))
end

-- Layer Rules
hl.layer_rule({
	match = {
		namespace = "^(lock|modus-.*)$",
	},
	blur = true,
	no_anim = true,
	ignore_alpha = 0,
	blur_popups = true,
})

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
			enabled = true,
			size = 10,
			noise = 0.05,
			contrast = 0.89,
			brightness = 1,
			vibrancy = 0.5,
			vibrancy_darkness = 0.5,
			passes = 3,
			ignore_opacity = false,
			new_optimizations = true,
			xray = true,
		},
		active_opacity = 0.9,
		inactive_opacity = 0.9,
		rounding = 14,
		rounding_power = 2.5,
		shadow = {
			enabled = true,
			range = 20,
			offset = { 0, 2 },
			render_power = 10,
			color = "rgba(0, 0, 0, 0.25)",
		},
		dim_inactive = true,
		dim_strength = 0.05,
		dim_special = 0.2,
	},
	animations = {
		enabled = true,
	},
})

hl.curve("easeOutQuint", { type = "bezier", points = { { 0.23, 1 }, { 0.32, 1 } } })
hl.curve("easeInOutCubic", { type = "bezier", points = { { 0.65, 0.05 }, { 0.36, 1 } } })
hl.curve("linear", { type = "bezier", points = { { 0, 0 }, { 1, 1 } } })
hl.curve("almostLinear", { type = "bezier", points = { { 0.5, 0.5 }, { 0.75, 1 } } })
hl.curve("quick", { type = "bezier", points = { { 0.15, 0 }, { 0.1, 1 } } })
hl.curve("move", { type = "bezier", points = { { 0.36, 0.13 }, { 0.1, 1.36 } } })
hl.curve("new", { type = "bezier", points = { { 0.36, 0.13 }, { 0.1, 1.26 } } })
hl.curve("workspace", { type = "bezier", points = { { 0.42, 0 }, { 0.58, 1 } } })
hl.curve("resize", { type = "bezier", points = { { 0.46, 0 }, { 0.58, 1.16 } } })

hl.curve("easy", { type = "spring", mass = 1, stiffness = 71.2633, dampening = 15.8273644 })

hl.animation({ leaf = "global", enabled = true, speed = 1, bezier = "default" })
hl.animation({ leaf = "border", enabled = true, speed = 5.39, bezier = "easeOutQuint" })
hl.animation({ leaf = "windows", enabled = true, speed = 3.5, bezier = "new" })
hl.animation({ leaf = "windowsIn", enabled = true, speed = 3.5, bezier = "move", style = "popin 87%" })
hl.animation({ leaf = "windowsOut", enabled = true, speed = 3.5, bezier = "move", style = "popin 87%" })
hl.animation({ leaf = "fadeIn", enabled = true, speed = 3.5, bezier = "default" })
hl.animation({ leaf = "fadeOut", enabled = true, speed = 3.5, bezier = "default" })
hl.animation({ leaf = "fade", enabled = true, speed = 3.03, bezier = "quick" })
hl.animation({ leaf = "layers", enabled = true, speed = 3.81, bezier = "easeOutQuint" })
hl.animation({ leaf = "layersIn", enabled = true, speed = 4, bezier = "easeOutQuint", style = "fade" })
hl.animation({ leaf = "layersOut", enabled = true, speed = 1.5, bezier = "linear", style = "fade" })
hl.animation({ leaf = "fadeLayersIn", enabled = true, speed = 1.79, bezier = "almostLinear" })
hl.animation({ leaf = "fadeLayersOut", enabled = true, speed = 1.39, bezier = "almostLinear" })
hl.animation({ leaf = "workspaces", enabled = true, speed = 2, bezier = "workspace", style = "" })
hl.animation({ leaf = "workspacesIn", enabled = true, speed = 2, bezier = "workspace", style = "" })
hl.animation({ leaf = "workspacesOut", enabled = true, speed = 2, bezier = "workspace", style = "" })
hl.animation({ leaf = "zoomFactor", enabled = true, speed = 7, bezier = "quick" })
