#!/usr/bin/env python3

import csv
import os
import re
import subprocess
import tkinter as tk
from tkinter import filedialog, ttk

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
    path_match = re.search(r"(?P<path>/.*?)(?=\s+/run/user\b|\s+\d+\s*$|$)", cmdline)
    if path_match:
        plugin_path = path_match.group("path").strip()
        if plugin_path:
            plugin_name = os.path.basename(plugin_path)
            if plugin_name:
                return plugin_name

    for token in reversed(cmdline.split()):
        if token.startswith("yabridge-"):
            return token.removeprefix("yabridge-").upper()

        if "/yabridge-" in token:
            return token.rsplit("/", 1)[-1].removeprefix("yabridge-").upper()

    match = re.search(r"/yabridge-([^/\s]+)", cmdline)
    if match:
        return match.group(1).upper()

    return ""

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


def _policy_from_chrt_output(output: str):
    if not output:
        return "-r"

    match = re.search(r"current scheduling policy:\s*SCHED_?([A-Z_]+)", output, re.IGNORECASE)
    if match:
        policy_name = match.group(1).upper()
        if policy_name in {"FIFO", "SCHED_FIFO"}:
            return "-f"
        if policy_name in {"RR", "SCHED_RR"}:
            return "-r"

    return "-r"


def current_policy_for_pid(pid: int):
    if pid is None:
        return "-r"

    try:
        result = subprocess.run(
            ["chrt", "-p", str(pid)],
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return "-r"

    if result.returncode != 0:
        return "-r"

    output = (result.stdout or "") + (result.stderr or "")
    return _policy_from_chrt_output(output)


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

    for line in (result.stdout or "").splitlines():
        if "current priority" in line.lower() or "rt_priority" in line.lower() or "priority" in line.lower():
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
        self.root.geometry("540x220")
        self.root.minsize(420, 600)

        self.status_var = tk.StringVar(value="Ready")
        self.process_vars = {}
        self.saved_state = {}
        self.last_save_path = None

        style = ttk.Style(root)
        style.configure('.', font=('TkDefaultFont', 9))
        style.configure('TButton', font=('TkDefaultFont', 9))
        style.configure('TLabel', font=('TkDefaultFont', 9))
        style.configure('TCombobox', font=('TkDefaultFont', 9))

        self.main = ttk.Frame(root, padding=12)
        self.main.pack(fill=tk.BOTH, expand=True)

        toolbar = ttk.Frame(self.main)
        toolbar.pack(fill=tk.X, pady=(0, 8))

        self.refresh_button = ttk.Button(toolbar, text="Refresh", command=self.refresh_processes)
        self.refresh_button.pack(side=tk.LEFT)

        self.save_button = ttk.Button(toolbar, text="Save", command=self.save_data)
        self.save_button.pack(side=tk.LEFT, padx=(8, 0))

        self.load_button = ttk.Button(toolbar, text="Load", command=self.load_data)
        self.load_button.pack(side=tk.LEFT, padx=(8, 0))

        self.processes_frame = ttk.Frame(self.main)
        self.processes_frame.pack(fill=tk.BOTH, expand=True)

        self.status_label = ttk.Label(self.main, textvariable=self.status_var, foreground="#1f5fbf")
        self.status_label.pack(anchor="w", pady=(8, 0))

        self.refresh_processes()

    def _saved_state_for_label(self, label):
        if not label:
            return None
        return self.saved_state.get(label.strip())

    def collect_process_entries(self):
        entries = []
        for process_name in PROCESS_NAMES:
            if process_name == "yabridge-host.exe.so":
                yabridge_entries = []
                for pid in find_pids(process_name):
                    cmdline = _command_line_for_pid(pid)
                    if not cmdline or not re.search(r"(?:^|\s)\d+\s*$", cmdline):
                        continue
                    display_name = _yabridge_display_name_from_cmdline(cmdline) or f"yabridge:{pid}"
                    yabridge_entries.append({
                        "key": f"yabridge:{pid}",
                        "process_name": process_name,
                        "pid": pid,
                        "display_name": display_name,
                    })
                yabridge_entries.sort(key=lambda item: item["display_name"].lower())
                entries.extend(yabridge_entries)
            else:
                for pid in find_pids(process_name):
                    entries.append({
                        "key": f"{process_name}:{pid}",
                        "process_name": process_name,
                        "pid": pid,
                        "display_name": process_name.title(),
                    })
        return entries

    def refresh_processes(self):
        for child in self.processes_frame.winfo_children():
            child.destroy()

        self.process_vars = {}
        for entry in self.collect_process_entries():
            row = ttk.Frame(self.processes_frame)
            row.pack(fill=tk.X, pady=8)

            label_text = entry["display_name"]
            pid_for_label = entry["pid"]
            if pid_for_label is None:
                pid_for_label = find_pid(entry["process_name"])
            if pid_for_label is not None:
                label_text = f"{label_text} ({pid_for_label})"

            saved_state = self._saved_state_for_label(entry["display_name"])
            if saved_state is not None:
                current_value = int(saved_state.get("priority", MIN_PRIORITY))
                policy_value = saved_state.get("policy", "-r")
            else:
                current_value = current_rtprio_for_pid(entry["pid"]) if entry["pid"] is not None else current_rtprio(entry["process_name"]) or MIN_PRIORITY
                policy_value = current_policy_for_pid(entry["pid"]) if entry["pid"] is not None else "-r"

            label = ttk.Label(row, text=label_text, width=35, anchor="w")
            label.pack(side=tk.LEFT)

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

            value_label = ttk.Label(row, textvariable=value_var, width=4)
            value_label.pack(side=tk.RIGHT)

            policy_var = tk.StringVar(value=policy_value)
            policy_combo = ttk.Combobox(row, values=["-r", "-f"], textvariable=policy_var, width=4, state="readonly")
            policy_combo.pack(side=tk.RIGHT, padx=(0, 8))

            def _apply_slider_value(value, row_pid=entry["pid"], row_proc=entry["process_name"], row_display=entry["display_name"], row_policy_var=policy_var, row_value_var=value_var):
                try:
                    iv = int(round(float(value)))
                except (TypeError, ValueError):
                    return
                row_value_var.set(iv)
                if row_pid is not None:
                    self.apply_priority_for_pid(row_pid, row_proc, row_display, iv, row_policy_var.get())
                else:
                    self.apply_priority(row_proc, iv, row_policy_var.get())

            def _apply_selected_policy(_event=None, row_pid=entry["pid"], row_proc=entry["process_name"], row_display=entry["display_name"], row_policy_var=policy_var, row_value_var=value_var):
                _apply_slider_value(row_value_var.get(), row_pid=row_pid, row_proc=row_proc, row_display=row_display, row_policy_var=row_policy_var, row_value_var=row_value_var)

            slider.configure(command=_apply_slider_value)
            policy_combo.bind("<<ComboboxSelected>>", _apply_selected_policy)

    def _unique_saved_entries(self):
        seen = set()
        entries = []
        for entry in self.collect_process_entries():
            label = entry["display_name"].strip()
            if not label or label in seen:
                continue
            seen.add(label)
            entries.append(entry)
        return entries

    def _write_state_file(self, target):
        lines = ["label,priority,policy"]
        for entry in self._unique_saved_entries():
            pid = entry["pid"]
            label = entry["display_name"]
            priority = current_rtprio_for_pid(pid) if pid is not None else current_rtprio(entry["process_name"]) or MIN_PRIORITY
            policy = current_policy_for_pid(pid) if pid is not None else "-r"
            lines.append(f"{label},{priority},{policy}")
        with open(target, "w", encoding="utf-8", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerows([line.split(",") for line in lines])

    def save_data(self):
        target = filedialog.asksaveasfilename(
            title="Save process data",
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )
        if not target:
            return

        try:
            self._write_state_file(target)
            self.last_save_path = target
            self.status_var.set(f"Saved to {target}")
        except OSError as exc:
            self.status_var.set(f"Save failed: {exc}")

    def load_data(self, path=None):
        if path is None:
            default_dir = os.path.dirname(self.last_save_path) if self.last_save_path else None
            path = filedialog.askopenfilename(
                title="Load saved process data",
                initialdir=default_dir or os.getcwd(),
                defaultextension=".csv",
                filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            )
        if not path:
            return

        self.last_save_path = path
        self.saved_state = {}
        try:
            with open(path, "r", encoding="utf-8", newline="") as fh:
                reader = csv.DictReader(fh)
                for row in reader:
                    label = (row.get("label") or "").strip()
                    if not label:
                        continue
                    try:
                        priority = int(row.get("priority", MIN_PRIORITY))
                    except (TypeError, ValueError):
                        priority = MIN_PRIORITY
                    policy = row.get("policy") or "-r"
                    if policy not in {"-r", "-f"}:
                        policy = "-r"
                    self.saved_state[label] = {"priority": priority, "policy": policy}
        except (OSError, csv.Error):
            self.saved_state = {}
            self.status_var.set(f"Failed to load {path}")
            return

        self.refresh_processes()

        applied = []
        for entry in self.collect_process_entries():
            saved_state = self._saved_state_for_label(entry["display_name"])
            if saved_state is None:
                continue
            priority = int(saved_state.get("priority", MIN_PRIORITY))
            policy = saved_state.get("policy", "-r")
            if entry["pid"] is not None:
                ok, message = set_rtprio_for_pid(entry["pid"], priority, policy)
            else:
                ok, message = set_rtprio(entry["process_name"], priority, policy)
            if ok:
                applied.append(f"{entry['display_name']}: {priority} ({policy})")
            else:
                applied.append(f"{entry['display_name']}: {message}")

        if applied:
            self.status_var.set("; ".join(applied[:3]) + ("..." if len(applied) > 3 else ""))
        else:
            self.status_var.set(f"Loaded from {path}")

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
