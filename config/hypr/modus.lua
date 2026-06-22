local modus = "$HOME/.config/Modus"

-- Global Menu: auto-set env vars so Qt/GTK apps export their menus
hl.env("GTK_MODULES", "appmenu-gtk-module")

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

-- Layer Rules for Blurs and Animations
local layer_rules = {
	{
		match = { namespace = "modus-notifications" },
		blur = true,
		xray = 0,
		blur_popups = true,
		ignore_alpha = 0,
		no_anim = true,
	},
	{ match = { namespace = "lockscreen" }, animation = "popin" },
	{
		match = { namespace = "modus-launcher" },
		blur = true,
		xray = 0,
		blur_popups = true,
		ignore_alpha = 0,
		animation = "popin",
	},
	{
		match = { namespace = "fabric" },
		blur = true,
		ignore_alpha = 0,
		xray = 0,
		blur_popups = true,
	},
	{
		match = { namespace = "modus" },
		blur = true,
		xray = 0,
		blur_popups = true,
		ignore_alpha = 0,
	},
	{ match = { namespace = "notification-center" }, animation = "slide right" },
}

for _, rule in ipairs(layer_rules) do
	hl.layer_rule(rule)
end


local fabricSend = "fabric-cli exec modus1"

-- Reload Modus
hl.bind("SUPER + ALT + B", hl.dsp.exec_cmd("killall modus; cd " .. modus .. " && uwsm app -- uv run start"))

-- Fabric Launcher Binds
for key, method in pairs({
	["SUPER + SHIFT + Y"] = "app.set_css()", -- Reload CSS
	["ALT + TAB"] = "switcher.show_switcher()", -- Application Switcher
	["SUPER + SPACE"] = "launcher.show_launcher()", -- App Launcher
	["SUPER + V"] = "launcher.show_launcher('clip')", -- Clipboard History
	["SUPER + W"] = "launcher.show_launcher('wall')", -- Wallpapers
	["ALT + SHIFT + W"] = "launcher.show_launcher('wall random', external=True)", -- Random Wallpaper
	["SUPER + Period"] = "launcher.show_launcher('em')", -- Emoji Picker
	["SUPER + ESCAPE"] = "launcher.show_launcher('power')", -- Power Menu
	["SUPER + SHIFT + M"] = "launcher.show_launcher('caffeine on', external=True)", -- Toggle Caffeine
}) do
	hl.bind(key, hl.dsp.exec_cmd(fabricSend .. " '" .. method .. "'"))
end
