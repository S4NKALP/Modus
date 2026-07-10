-- local modus = os.getenv("HOME") .. "/.config/Modus"
local modus = os.getenv("HOME") .. "/Projects/dev/Modus"
local colors = dofile(modus .. "/config/hypr/colors.lua")
local fabricSend = "fabric-cli exec modus1"

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
hl.bind("SUPER + ALT + B", hl.dsp.exec_cmd("killall modus1; cd " .. modus .. " && uwsm app -- uv run start"))

-- Fabric Launcher Binds
for key, method in pairs({
	-- ["SUPER + SHIFT + Y"] = "app.set_css()", -- Reload CSS
	["ALT + TAB"] = "switcher.show_switcher()", -- Application Switcher
	["SUPER + Z"] = "screencapture.toggle()", -- ScreenCapture
	["SUPER + S"] = 'screencapture.toggle(ss="region")', -- Screenshot Region
	["ALT + SPACE"] = "switch_keyboard_layout()", -- KB_Layout Switcher
}) do
	hl.bind(key, hl.dsp.exec_cmd(fabricSend .. " '" .. method .. "'"))
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
