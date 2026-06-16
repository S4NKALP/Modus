import re


def hypr_patch(cmd):
    if not isinstance(cmd, str) or "dispatch" not in cmd:
        return cmd

    if "hyprctl dispatch" in cmd:
        match = re.search(r"hyprctl dispatch (\w+)(.*)", cmd)
        if match:
            disp, args = match.group(1), match.group(2).strip(" '\"")
            if disp == "workspace":
                lua = f"hl.dsp.focus({{workspace=[[{args}]]}})"
            elif disp == "movetoworkspace":
                lua = f"hl.dsp.window.move({{workspace=[[{args}]]}})"
            else:
                disp = "exec_cmd" if disp == "exec" else disp
                lua = f"hl.dsp.{disp}([[{args}]])" if args else f"hl.dsp.{disp}()"
            cmd = cmd.replace(match.group(0), f"hyprctl eval '{lua}'")

    cmd = re.sub(
        r"dispatch workspace ([^\s;]+)",
        r"dispatch hl.dsp.focus({workspace=[[\1]]})",
        cmd,
    )
    cmd = re.sub(
        r"dispatch movetoworkspace ([^\s;]+)",
        r"dispatch hl.dsp.window.move({workspace=[[\1]]})",
        cmd,
    )

    return cmd


print(hypr_patch("batch/dispatch workspace 1"))
print(hypr_patch("hyprctl dispatch exec 'uwsm app -- kitty'"))
print(hypr_patch("hyprctl dispatch workspace e+1"))
