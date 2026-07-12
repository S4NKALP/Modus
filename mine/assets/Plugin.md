# Launcher Plugins Documentation

This document provides comprehensive usage information for all available launcher plugins.

## Table of Contents

- [Application (default)](#application-default)
- [Bookmark (`bm`)](#bookmark-bm)
- [Calculator (`calc`)](#calculator-calc)
- [Clipboard (`clip`)](#clipboard-clip)
- [Emoji (`em`)](#emoji-em)
- [Google Lens (`lens`)](#google-lens-lens)
- [Color Picker (`color`)](#color-picker-color)
- [Google Search (`gg`)](#google-search-gg)
- [YouTube Search (`yt`)](#youtube-search-yt)
- [Link Opener (`lk`)](#link-opener-lk)
- [OTP (`otp`)](#otp-otp)
- [Password (`pass`)](#password-pass)
- [Power Menu (`pm`)](#power-menu-pm)
- [Power Profile (`power`)](#power-profile-power)
- [Caffeine (`caff`)](#caffeine-caff)
- [Reminder (`rem`)](#reminder-rem)
- [ScreenCapture (`sc`)](#screencapture-sc)
- [Todo (`todo`)](#todo-todo)
- [Tmux (`tmux`)](#tmux-tmux)
- [Wallpaper (`wall`)](#wallpaper-wall)
- [Window Switcher (`win`)](#window-switcher-win)
- [SSH Manager (`ssh`)](#ssh-manager-ssh)
- [Network Manager (`net`)](#network-manager-net)
- [Bluetooth (`bt`)](#bluetooth-bt)

---

## Application (default)

Launch desktop applications with fuzzy search.

### Usage

```
application_name
```

### Examples

- `firefox` — Launch Firefox
- `code` — Launch VS Code
- `terminal` — Launch terminal

### Features

- Fuzzy search across desktop files
- Smart matching prioritizing exact/common apps

### Interactive Features

- Click: launch application
- Enter: launch selected application

---

## Bookmark (`bm`)

Store and manage bookmarks for URLs, file paths, commands, or any text.

### Commands

#### Add Bookmark
```
bm add name content -description(optional) -tags(optional);
```

#### Remove Bookmark
```
bm remove name;
```

#### Update Bookmark
```
bm update name field new_value;
```
Fields: `content`, `description`, `tags`

#### Show Help
```
bm help
```

#### Show Bookmark List
```
bm add
bm remove
bm update
```

### Interactive Features

- Click: copy content to clipboard
- Shift+Enter: remove bookmark

---

## Calculator (`calc`)

Perform mathematical calculations.

### Usage
```
calc expression
```

### Examples

- `calc 2 + 2`
- `calc sqrt(16)`
- `calc 100 USD to EUR`

### Interactive Features

- Click/Enter: execute calculation in terminal

---

## Clipboard (`clip`)

Access and search clipboard history.

### Usage
```
clip [search_term]
```

### Interactive Features

- Click/Enter: copy to clipboard

---

## Emoji (`em`)

Search and insert emojis by name/description.

### Usage
```
em emoji_name
```

### Interactive Features

- Click/Enter: copy selected emoji

---

## Google Lens (`lens`)

Capture a region of the screen and search with Google Lens.

### Usage
```
lens
```
or
```
google lens
```

### Behavior

- Activates region selection (slurp)
- Captures screenshot of selected region (grim)
- Uploads image to temporary host
- Opens default browser with Google Lens results

### Interactive Features

- Enter: start capture

---

## Color Picker (`color`)

Pick a color and copy as HEX/RGB/HSV.

### Usage
```
color [hex|rgb|hsv]
```

### Examples

- `color` — Show options
- `color hex` — Pick HEX
- `color rgb` — Pick RGB
- `color hsv` — Pick HSV

### Interactive Features

- Click/Enter: start color picking in chosen format

---

## Google Search (`gg`)

Perform Google searches directly.

### Usage
```
gg search_query
```

### Examples

- `gg python tutorial`
- `gg weather today`

### Behavior

- Opens browser directly (no in-launcher results)

---

## YouTube Search (`yt`)

Perform YouTube searches directly.

### Usage
```
yt search_query
```

### Behavior

- Opens browser directly

---

## Link Opener (`lk`)

Open URLs and links directly.

### Usage
```
lk url_or_domain
```

### Behavior

- Adds `https://` if protocol is missing
- Opens in default browser

---

## OTP (`otp`)

Generate and manage TOTP.

### Commands

#### Add OTP Account
```
otp add account_name qr
otp add account_name secret_key
```

#### Remove OTP Account
```
otp remove account_name
```

#### Show Help/List
```
otp help
otp remove
```

### Interactive Features

- Click: copy OTP code
- Shift+Enter: remove account

---

## Password (`pass`)

Secure passwords with master password protection.

### Prompt UX

- If a master password exists and the vault is locked, searching with `pass ...` or using add/remove/update/list will show an inline prompt.
- Type master password and press Enter (no semicolon). The launcher stays open and the list refreshes.
- Press Enter on empty input to cancel.

### Commands

#### First-Time Setup

On first use (no master password set), typing `pass` will show an inline prompt to set a master password. Type the password and press Enter. No semicolon is required.

#### Lock Password Vault
```
pass lock
```

#### Add Password
```
pass add name username password -website(optional) -notes(optional);
```

#### Remove Password
```
pass remove name;
```

#### Update Password
```
pass update name field new_value;
```
Fields: `username`, `password`

#### Show Help/List
```
pass help
pass remove
pass update
```

### Interactive Features

- Click: copy password
- Shift+Enter: remove password

---

## Power Menu (`pm`)

System power actions (shutdown, reboot, etc.).

### Usage
```
pm [option]
```

### External

- `pm shutdown`, `pm reboot`, etc. via external toggle

---

## Power Profile (`power`)

Switch system power profiles.

### Usage
```
power [performance|balanced|power-saver]
```

### Behavior

- Shows current profile, switch on Enter/click

---

## Caffeine (`caff`)

Prevent idle/sleep.

### Usage
```
caff [on|off|<duration>]
```
Examples: `caff on`, `caff 30m`, `caff 1h`, `caff 45s`, `caff 600`

---

## Reminder (`rem`)

Schedule reminders with flexible time formats.

### Usage
```
rem [time] [optional message]
```
Examples: `rem 10m`, `rem 1h30m`, `rem 21:30`, `rem 45`, `rem 10m Take a break`

### Interactive Features

- Click/Enter: schedule reminder

---

## ScreenCapture (`sc`)

Screenshots and screen recording.

### External (no UI)

- `sc fs` — Fullscreen
- `sc region` — Region
- `sc record` — Toggle recording
- `sc record mute` — Recording muted
- `sc stop` — Stop recording

---

## Todo (`todo`)

Manage todos with priorities.

### Commands
```
todo add title [-d description] [-p low|medium|high];
todo done title;
todo remove title;
todo edit title field new_value;
```
- Clear: `todo clear`
- Help/List: `todo help`, and `todo add|done|remove|edit`

### Interactive Features

- Click: toggle completion
- Shift+Enter: toggle completion
- Alt+Enter: remove todo

---

## Tmux (`tmux`)

Manage tmux sessions.

### Commands
```
tmux new session_name [directory];
tmux kill session_name;
tmux rename old_name new_name;
tmux terminal terminal_name
```
- Help/List: `tmux help`, `tmux new|kill|rename|terminal`

### Interactive Features

- Click: attach to session
- Shift+Enter: kill session

---

## Wallpaper (`wall`)

Browse and set wallpapers.

### Usage
```
wall [search_term]
```

### Interactive Features

- Click/Enter: set wallpaper

---

## Window Switcher (`win`)

Switch between open windows/applications.

### Usage
```
win [window_name]
```

### Interactive Features

- Click/Enter: focus window

---

## SSH Manager (`ssh`)

List and connect to SSH hosts from config/known_hosts.

### Commands
- Terminal preference: `ssh terminal terminal_name`
- Help: `ssh help`

### Interactive Features

- Click/Enter: open terminal & connect
- Shift+Enter: copy ssh command

---

## Network Manager (`net`)

Browse, scan, connect to, and manage NetworkManager Wi‑Fi connections.

### Usage
```
net [connection_prefix] [ifname]
```

### Direct
```
net connect <ssid> <password> [ifname]
net disconnect [ifname]
net scan [ifname]
net forget <name|uuid>
```

### Prompt UX

- When a password/identity prompt is open, the launcher captures input until Enter (submit) or empty Enter (cancel).

### Interactive Features

- Click/Enter on saved network: connect/disconnect
- Click/Enter on access point: connect (prompts if needed)
- Shift+Enter on saved network: forget

---

## Bluetooth (`bt`)

Manage Bluetooth power, scanning, and device connections.

### Commands
```
bt power on;
bt power off;
bt scan start;
bt scan stop;
bt connect Device Name;
bt disconnect Device Name;
```
- Help/List: `bt help`, `bt`

### Notes

- Commands with arguments require a trailing semicolon (`;`).

---

## Quick Reference

| Plugin            | Keyword  | What it does / commands                                             | Semicolon Required                |
| ----------------- | -------- | ------------------------------------------------------------------- | --------------------------------- |
| Application       | —        | Application search (default)                                        | No                                |
| Bookmark          | bm       | add, remove, update                                                 | Yes                               |
| Calculator        | calc     | Evaluate expressions                                                | No                                |
| Clipboard         | clip     | Clipboard history                                                   | No                                |
| Emoji             | em       | Emoji search                                                        | No                                |
| Google Lens       | lens     | Capture region and search                                           | No                                |
| Google Search     | gg       | Web search (opens browser)                                          | No                                |
| YouTube Search    | yt       | YouTube search (opens browser)                                      | No                                |
| Link Opener       | lk       | Open URL/domain (adds https://)                                     | No                                |
| Color Picker      | color    | HEX/RGB/HSV                                                         | No                                |
| OTP               | otp      | add, remove                                                         | No                                |
| Password          | pass     | add, remove, update; auto-prompt for master password when needed   | Yes (lock/help/list: No); prompts: No |
| Power Menu        | pm       | Power actions (shutdown, reboot, etc.)                              | No                                |
| Power Profile     | power    | performance, balanced, power-saver                                  | No                                |
| Caffeine          | caff     | on, off, durations (30m, 1h, 45s, 600)                              | No                                |
| Reminder          | rem      | Flexible times with optional message                                | No                                |
| Todo              | todo     | add, done, remove, edit, clear                                      | Yes (clear/help/list: No)         |
| Tmux              | tmux     | new, kill, rename, terminal                                         | Yes (terminal/help/list: No)      |
| Wallpaper         | wall     | Browse/apply wallpapers                                             | No                                |
| Window Switcher   | win      | Switch between windows                                              | No                                |
| SSH Manager       | ssh      | Hosts, terminal, help                                               | No                                |
| Network Manager   | net      | scan/connect/disconnect/forget; inline password prompt when needed  | No                                |
| Bluetooth         | bt       | power on/off, scan start/stop, connect/disconnect                   | Yes                               |

Notes:
- Inline prompts (Wi‑Fi password, master password) capture input until Enter (submit) or empty Enter (cancel); no semicolon is used in prompts.
