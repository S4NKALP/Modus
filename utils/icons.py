# Parameters
font_family: str = "tabler-icons"
font_weight: str = "normal"

span: str = f"<span font-family='{font_family}' font-weight='{font_weight}'>"

# Panels
apps: str = "&#xf1fd;"
dashboard: str = "&#xea87;"
chat: str = "&#xf59f;"
wallpapers: str = "&#xeb01;"
windows: str = "&#xefe6;"

# Bar
colorpicker: str = "&#xebe6;"
media: str = "&#xf00d;"

# Circles
temp: str = "&#xeb38;"
disk: str = "&#xea88;"
battery: str = "&#xea38;"
memory: str = "&#xfa97;"
cpu: str = "&#xef8e;"
swap: str = "&#xeb31;"


# Wallpapers
add: str = "&#xeb0b;"
sort: str = "&#xeb5a;"
circle: str = "&#xf671;"
check_box: str = "&#xf63d;"
box: str = "&#xf59a;"
scan: str = "&#xeb13;"
scan_stop: str = "&#xed4a;"
record: str = "&#xf692;"
update: str = "&#xfa0a;"
updated: str = "&#xf704;"

# Chevrons
chevron_up: str = "&#xea62;"
chevron_down: str = "&#xea5f;"
chevron_left: str = "&#xea60;"
chevron_right: str = "&#xea61;"

# Power
lock: str = "&#xeae2;"
suspend: str = "&#xece7;"
logout: str = "&#xeba8;"
reboot: str = "&#xeb13;"
shutdown: str = "&#xeb0d;"

# Power Manager
power_saving: str = "&#xed4f;"
power_balanced: str = "&#xfa77;"
power_performance: str = "&#xec45;"
charging: str = "&#xefef;"
discharging: str = "&#xefe9;"
alert: str = "&#xefb4;"

# Applets
wifi: str = "&#xeb52;"
bluetooth: str = "&#xea37;"
night: str = "&#xeaf8;"
coffee: str = "&#xef0e;"
dnd: str = "&#xea35;"
darkmode: str = "&#xfe56;"
world: str = "&#xeb54;"

wifi_off: str = "&#xecfa;"
bluetooth_off: str = "&#xeceb;"
night_off: str = "&#xf162;"
dnd_off: str = "&#xece9;"
mic_off: str = "&#xed16;"

# Bluetooth
bluetooth_connected: str = "&#xecea;"
bluetooth_disconnected: str = "&#xf081;"


# Player
pause: str = "&#xf690;"
play: str = "&#xf691;"
stop: str = "&#xf695;"
skip_back: str = "&#xf693;"
skip_forward: str = "&#xf694;"
prev: str = "&#xf697;"
next: str = "&#xf696;"
shuffle: str = "&#xf000;"
repeat: str = "&#xeb72;"
music: str = "&#xeafc;"
rewind_backward_5: str = "&#xfabf;"
rewind_forward_5: str = "&#xfac7;"

# Volume
vol_off: str = "&#xf1c3;"
vol_mute: str = "&#xeb50;"
vol_medium: str = "&#xeb4f;"
vol_high: str = "&#xeb51;"

# Network
lan: str = "&#xeb9d;"
moderate_signal: str = "&#xeba4;"
good_signal: str = "&#xeba5;"
no_signal: str = "&#xf063;"
weak_signal: str = "&#xeba3;"

# Overview
circle_plus: str = "&#xea69;"

# Pins
copy_plus: str = "&#xfdae;"
paperclip: str = "&#xeb02;"

# Confirm
accept: str = "&#xea5e;"
cancel: str = "&#xeb55;"
trash: str = "&#xeb41;"
clear: str = "&#xef88;"

# Config
config: str = "&#xeb20;"

# Icons
firefox: str = "&#xecfd;"
chromium: str = "&#xec18;"
spotify: str = "&#xfe86;"
disc: str = "&#x1003e;"
disc_off: str = "&#xf118;"

# Misc
dot: str = "&#xf698;"
palette: str = "&#xeb01;"

exceptions: list[str] = ["font_family", "font_weight", "span"]


def apply_span() -> None:
    global_dict = globals()
    for key in global_dict:
        if key not in exceptions and not key.startswith("__"):
            global_dict[key] = f"{span}{global_dict[key]}</span>"


apply_span()
