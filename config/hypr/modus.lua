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

-- Fabric Spotlight Binds
for key, method in pairs({
	["SUPER + D"] = "spotlight.toggle()", -- Spotlight
	["SUPER + E"] = "spotlight.toggle('em')", -- Emoji
	["SUPER + V"] = "spotlight.toggle('clip')", -- Clipboard
	["SUPER + W"] = "spotlight.toggle('wall')", -- Wallpaper
	["SUPER + SHIFT + Y"] = "app.set_css()", -- Reload CSS
	["ALT + TAB"] = "switcher.show_switcher()", -- Application Switcher
	["SUPER + Z"] = "screencapture.toggle()", -- ScreenCapture
	["SUPER + S"] = "screencapture.toggle(ss='region')", -- Screenshot Region
	["ALT + SPACE"] = "switch_keyboard_layout()", -- KB_Layout Switcher
	["ALT + SHIFT + W"] = "spotlight.toggle('wr', external=True)", -- Random Wallpaper
}) do
	hl.bind(key, hl.dsp.exec_cmd(fabricSend .. ' "' .. method .. '"'))
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
			size = 5,
			noise = 0,
			contrast = 1,
			brightness = 1,
			vibrancy = 0.1696,
			passes = 2,
			popups_ignorealpha = true,
			popups = true,
			ignore_opacity = false,
			new_optimizations = true,
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
