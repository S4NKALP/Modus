local modus = "/home/sankalp/.config/Modus"

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

-- Keybinds
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
