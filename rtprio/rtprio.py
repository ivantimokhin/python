#!/usr/bin/env python3

import subprocess
import tkinter as tk
from tkinter import ttk

PROCESS_NAMES = ("reaper", "klick")
MIN_PRIORITY = 1
MAX_PRIORITY = 95


def find_pid(process_name: str):
    try:
        result = subprocess.run(
            ["pgrep", "-x", process_name],
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return None

    if result.returncode != 0:
        return None

    pids = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if not pids:
        return None
    return int(pids[0])


def current_rtprio(process_name: str):
    pid = find_pid(process_name)
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


def set_rtprio(process_name: str, priority: int):
    pid = find_pid(process_name)
    if pid is None:
        return False, f"Process '{process_name}' is not running."

    try:
        result = subprocess.run(
            ["chrt", "-f", "-p", str(priority), str(pid)],
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return False, "The 'chrt' command is not available on this system."

    if result.returncode != 0:
        error_text = (result.stderr or result.stdout).strip() or "Permission denied. Run as root or with sudo."
        return False, error_text

    return True, f"{process_name} priority set to {priority}."


class RtprioWindow:
    def __init__(self, root):
        self.root = root
        self.root.title("RT Priority Controls")
        self.root.geometry("480x220")
        self.root.minsize(420, 200)

        self.status_var = tk.StringVar(value="Ready")
        self.process_vars = {}

        main = ttk.Frame(root, padding=12)
        main.pack(fill=tk.BOTH, expand=True)

        for process_name in PROCESS_NAMES:
            row = ttk.Frame(main)
            row.pack(fill=tk.X, pady=8)

            label = ttk.Label(row, text=process_name.title(), width=12, anchor="w")
            label.pack(side=tk.LEFT)

            value_var = tk.IntVar(value=current_rtprio(process_name) or MIN_PRIORITY)
            self.process_vars[process_name] = value_var

            slider = ttk.Scale(
                row,
                from_=MIN_PRIORITY,
                to=MAX_PRIORITY,
                orient=tk.HORIZONTAL,
                variable=value_var,
                # use a handler that snaps the scale to integer steps
                command=lambda value, proc=process_name, var=value_var, s=None: None,
            )
            slider.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(8, 10))
            # schedule resize after geometry is calculated to make the slider 10px shorter
            def _shorten(s=slider):
                try:
                    w = s.winfo_width()
                    if w and w > 10:
                        s.configure(length=max(0, w - 10))
                except tk.TclError:
                    pass

            self.root.after(0, _shorten)

            # replace the placeholder command with a proper integer-snapping handler
            def _attach_handler(s=slider, proc=process_name, var=value_var):
                def _handler(value):
                    try:
                        iv = int(round(float(value)))
                    except (TypeError, ValueError):
                        return
                    # snap the displayed variable to integer (don't call s.set() — that re-triggers the command)
                    var.set(iv)
                    # apply integer priority
                    self.apply_priority(proc, iv)

                s.configure(command=_handler)

            self.root.after(1, _attach_handler)

            value_label = ttk.Label(row, textvariable=value_var, width=4)
            value_label.pack(side=tk.RIGHT)

        status = ttk.Label(main, textvariable=self.status_var, foreground="#1f5fbf")
        status.pack(anchor="w", pady=(8, 0))

    def apply_priority(self, process_name: str, value: int):
        ok, message = set_rtprio(process_name, value)
        if ok:
            # show integer priority in status (no float/dot)
            self.status_var.set(f"{process_name}: {int(value)}")
        else:
            self.status_var.set(f"{process_name}: {message}")

            current = current_rtprio(process_name)
            if current is not None:
                self.process_vars[process_name].set(current)


if __name__ == "__main__":
    root = tk.Tk()
    RtprioWindow(root)
    root.mainloop()
