#!/usr/bin/env python3

import re
import subprocess
import tkinter as tk
from tkinter import ttk

PROCESS_NAMES = ("jackd", "reaper", "klick", "jack_capture", "yabridge-host.exe.so")
MIN_PRIORITY = 0
MAX_PRIORITY = 95


def _command_line_for_pid(pid: int):
    try:
        result = subprocess.run(
            ["ps", "-o", "args=", "-p", str(pid)],
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return None

    if result.returncode != 0:
        return None

    cmdline = result.stdout.strip()
    return cmdline or None


def _yabridge_display_name_from_cmdline(cmdline: str):
    for token in reversed(cmdline.split()):
        if token.startswith("yabridge-"):
            return token.removeprefix("yabridge-").upper()

        if "/yabridge-" in token:
            return token.rsplit("/", 1)[-1].removeprefix("yabridge-").upper()

    match = re.search(r"/yabridge-([^/\s]+)", cmdline)
    if match:
        return match.group(1).upper()

    return "SYTRUS"


def _yabridge_display_name(process_name: str):
    if process_name != "yabridge-host.exe.so":
        return process_name.title()

    pid = find_pid(process_name)
    if pid is None:
        return "SYTRUS"

    cmdline = _command_line_for_pid(pid)
    if not cmdline:
        return "SYTRUS"

    return _yabridge_display_name_from_cmdline(cmdline)


def find_pids(process_name: str):
    try:
        if len(process_name) > 15:
            result = subprocess.run(
                ["pgrep", "-f", "--", process_name],
                check=False,
                capture_output=True,
                text=True,
            )
        else:
            result = subprocess.run(
                ["pgrep", "-x", process_name],
                check=False,
                capture_output=True,
                text=True,
            )
    except FileNotFoundError:
        return []

    if result.returncode != 0:
        return []

    pids = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if not pids:
        return []

    if process_name != "yabridge-host.exe.so":
        return [int(pid) for pid in pids if pid.isdigit()]

    matches = []
    for pid in pids:
        try:
            pid_value = int(pid)
        except ValueError:
            continue

        cmdline = _command_line_for_pid(pid_value)
        if not cmdline:
            continue

        if re.search(r"(?:^|\s)\d+\s*$", cmdline):
            matches.append(pid_value)

    return matches


def find_pid(process_name: str):
    pids = find_pids(process_name)
    return pids[0] if pids else None


def current_rtprio_for_pid(pid: int):
    if pid is None:
        return None

    try:
        result = subprocess.run(
            ["chrt", "-p", str(pid)],
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return None

    if result.returncode != 0:
        return None

    for line in result.stdout.splitlines():
        if "current priority" in line.lower() or "priority" in line.lower():
            parts = line.split()
            for idx, part in enumerate(parts):
                if part.isdigit() and idx > 0:
                    return int(part)
    return None


def current_rtprio(process_name: str):
    pid = find_pid(process_name)
    if pid is None:
        return None
    return current_rtprio_for_pid(pid)


def set_rtprio_for_pid(pid: int, priority: int, policy: str = "-r"):
    if priority == 0:
        command = ["chrt", "-o", "-p", "0", str(pid)]
    else:
        command = ["chrt", policy, "-p", str(priority), str(pid)]

    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return False, "The 'chrt' command is not available on this system."

    if result.returncode != 0:
        error_text = (result.stderr or result.stdout).strip() or "Permission denied. Run as root or with sudo."
        return False, error_text

    if priority == 0:
        return True, f"PID {pid} real-time priority removed."
    return True, f"PID {pid} priority set to {priority} ({policy})."


def set_rtprio(process_name: str, priority: int, policy: str = "-r"):
    pid = find_pid(process_name)
    if pid is None:
        return False, f"Process '{process_name}' is not running."

    return set_rtprio_for_pid(pid, priority, policy)


class RtprioWindow:
    def __init__(self, root):
        self.root = root
        self.root.title("RT Priority Controls")
        self.root.geometry("480x220")
        self.root.minsize(420, 600)

        self.status_var = tk.StringVar(value="Ready")
        self.process_vars = {}

        main = ttk.Frame(root, padding=12)
        main.pack(fill=tk.BOTH, expand=True)

        process_entries = []
        for process_name in PROCESS_NAMES:
            if process_name == "yabridge-host.exe.so":
                for pid in find_pids(process_name):
                    cmdline = _command_line_for_pid(pid)
                    if not cmdline or not re.search(r"(?:^|\s)\d+\s*$", cmdline):
                        continue
                    process_entries.append({
                        "key": f"yabridge:{pid}",
                        "process_name": process_name,
                        "pid": pid,
                        "display_name": _yabridge_display_name_from_cmdline(cmdline),
                    })
            else:
                for pid in find_pids(process_name):
                    process_entries.append({
                        "key": f"{process_name}:{pid}",
                        "process_name": process_name,
                        "pid": pid,
                        "display_name": process_name.title(),
                    })

        for entry in process_entries:
            row = ttk.Frame(main)
            row.pack(fill=tk.X, pady=8)

            label_text = entry["display_name"]
            pid_for_label = entry["pid"]
            if pid_for_label is None:
                pid_for_label = find_pid(entry["process_name"])
            if pid_for_label is not None:
                label_text = f"{label_text} ({pid_for_label})"

            label = ttk.Label(row, text=label_text, width=22, anchor="w")
            label.pack(side=tk.LEFT)

            current_value = current_rtprio_for_pid(entry["pid"]) if entry["pid"] is not None else current_rtprio(entry["process_name"]) or MIN_PRIORITY
            value_var = tk.IntVar(value=current_value)
            self.process_vars[entry["key"]] = value_var

            slider = ttk.Scale(
                row,
                from_=MIN_PRIORITY,
                to=MAX_PRIORITY,
                orient=tk.HORIZONTAL,
                variable=value_var,
                command=lambda value, proc=entry["process_name"], var=value_var, pid=entry["pid"], display=entry["display_name"], s=None: None,
            )
            slider.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(8, 10))

            def _shorten(s=slider):
                try:
                    w = s.winfo_width()
                    if w and w > 10:
                        s.configure(length=max(0, w - 10))
                except tk.TclError:
                    pass

            self.root.after(0, _shorten)

            def _attach_handler(s=slider, proc=entry["process_name"], var=value_var, pid=entry["pid"], display=entry["display_name"]):
                def _handler(value):
                    try:
                        iv = int(round(float(value)))
                    except (TypeError, ValueError):
                        return
                    var.set(iv)
                    if pid is not None:
                        self.apply_priority_for_pid(pid, proc, display, iv)
                    else:
                        self.apply_priority(proc, iv)

                s.configure(command=_handler)

            self.root.after(1, _attach_handler)

            value_label = ttk.Label(row, textvariable=value_var, width=4)
            value_label.pack(side=tk.RIGHT)

            policy_var = tk.StringVar(value="-r")
            policy_combo = ttk.Combobox(row, values=["-r", "-f"], textvariable=policy_var, width=4, state="readonly")
            policy_combo.pack(side=tk.RIGHT, padx=(0, 8))

            def _apply_slider_value(value, pid=entry["pid"], proc=entry["process_name"], display=entry["display_name"], policy_var=policy_var):
                try:
                    iv = int(round(float(value)))
                except (TypeError, ValueError):
                    return
                if pid is not None:
                    self.apply_priority_for_pid(pid, proc, display, iv, policy_var.get())
                else:
                    self.apply_priority(proc, iv, policy_var.get())

            slider.configure(command=_apply_slider_value)

        status = ttk.Label(main, textvariable=self.status_var, foreground="#1f5fbf")
        status.pack(anchor="w", pady=(8, 0))

    def apply_priority_for_pid(self, pid: int, process_name: str, display_name: str, value: int, policy: str = "-r"):
        ok, message = set_rtprio_for_pid(pid, value, policy)
        if ok:
            self.status_var.set(f"{display_name}: {int(value)} ({policy})")
        else:
            self.status_var.set(f"{display_name}: {message}")

            current = current_rtprio_for_pid(pid)
            if current is not None:
                self.process_vars[f"yabridge:{pid}"].set(current)

    def apply_priority(self, process_name: str, value: int, policy: str = "-r"):
        ok, message = set_rtprio(process_name, value, policy)
        if ok:
            self.status_var.set(f"{process_name}: {int(value)} ({policy})")
        else:
            self.status_var.set(f"{process_name}: {message}")

            current = current_rtprio(process_name)
            if current is not None:
                self.process_vars[process_name].set(current)


if __name__ == "__main__":
    root = tk.Tk()
    RtprioWindow(root)
    root.mainloop()
