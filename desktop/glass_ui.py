"""Glass-style presentation for the existing Vox Rescue audio engine."""

from __future__ import annotations

import math
import os
import tkinter as tk
from tkinter import ttk


class GlassSwitch(tk.Checkbutton):
    """A native keyboard-accessible toggle, styled as a compact pill."""

    def __init__(self, parent, *, variable, command, colors, **kwargs):
        super().__init__(
            parent, variable=variable, command=command, indicatoron=False,
            text="OFF", width=6, font=("Segoe UI", 9, "bold"),
            bg=colors["panel2"], fg=colors["muted"],
            selectcolor=colors["accent"], activebackground=colors["accent"],
            activeforeground="#08121d", disabledforeground="#66758e",
            relief="flat", offrelief="flat", overrelief="flat",
            bd=0, padx=8, pady=7, cursor="hand2", takefocus=True,
            highlightthickness=1, highlightbackground=colors["line"],
            highlightcolor=colors["accent"], **kwargs,
        )
        self._variable = variable
        self._colors = colors
        variable.trace_add("write", self._refresh)
        self._refresh()

    def _refresh(self, *_args):
        enabled = self._variable.get()
        self.configure(text="ON" if enabled else "OFF",
                       fg="white" if enabled else self._colors["muted"])


class GlassCard(tk.Canvas):
    def __init__(self, parent, width, height, colors):
        super().__init__(parent, width=width, height=height, bg=colors["bg"],
                         highlightthickness=0, bd=0)
        r = 14
        points = [r, 1, width-r, 1, width-1, 1, width-1, r,
                  width-1, height-r, width-1, height-1, width-r, height-1,
                  r, height-1, 1, height-1, 1, height-r, 1, r, 1, 1]
        self.create_polygon(points, smooth=True, splinesteps=32,
                            fill=colors["panel"], outline=colors["line"])
        self.create_line(25, 2, width-25, 2, fill="#ffffff")
        self.body = tk.Frame(self, bg=colors["panel"])
        self.create_window(width/2, height/2, window=self.body,
                           width=width-34, height=height-24)


def apply_window_material(app):
    """Use native light chrome and rounded corners where Windows supports them."""
    if os.name != "nt":
        return
    try:
        import ctypes
        from ctypes import wintypes
        app.update_idletasks()
        user = ctypes.WinDLL("user32", use_last_error=True)
        user.GetParent.argtypes = [wintypes.HWND]
        user.GetParent.restype = wintypes.HWND
        hwnd = user.GetParent(app.winfo_id())
        dwm = ctypes.WinDLL("dwmapi")
        dwm.DwmSetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD,
                                            ctypes.c_void_p, wintypes.DWORD]
        for attribute, value in ((20, 0), (33, 2), (35, 0xF8F8F6), (36, 0x262621)):
            data = ctypes.c_int(value)
            dwm.DwmSetWindowAttribute(hwnd, attribute, ctypes.byref(data), ctypes.sizeof(data))
    except (OSError, AttributeError, tk.TclError):
        pass


def build_ui(app, c):
    """A compact white controller; every visible status comes from the engine."""
    app.geometry("360x420")
    app.minsize(360, 420)
    app.maxsize(360, 420)
    app.configure(bg=c["bg"])
    app.option_add("*TCombobox*Listbox.background", c["panel"])
    app.option_add("*TCombobox*Listbox.foreground", c["text"])
    app.option_add("*TCombobox*Listbox.selectBackground", c["accent"])
    app.option_add("*TCombobox*Listbox.selectForeground", "white")
    root = tk.Frame(app, bg=c["bg"])
    root.pack(fill="both", expand=True)

    def label(parent, text=None, *, size=9, color=None, weight="normal", **kw):
        return tk.Label(parent, text=text, bg=parent.cget("bg"), fg=color or c["text"],
                        font=("Segoe UI", size, weight), bd=0, **kw)

    header = tk.Frame(root, bg=c["bg"])
    header.place(x=16, y=12, width=328, height=32)
    if app._header_icon is not None:
        label(header, image=app._header_icon).pack(side="left", padx=(0, 6))
    label(header, "Vox Rescue", size=14, weight="bold").pack(side="left")

    app.status_pill = label(root, textvariable=app.status_var, size=8,
                            color=c["muted"], anchor="w", justify="left",
                            wraplength=308, padx=10)
    app.status_pill.configure(bg=c["panel2"])
    app.status_pill.place(x=16, y=51, width=328, height=32)

    route = GlassCard(root, 328, 144, c)
    route.place(x=16, y=92)
    title = tk.Frame(route.body, bg=c["panel"])
    title.pack(fill="x", pady=(0, 2))
    label(title, "AUDIO DEVICES", size=7, color=c["muted"], weight="bold").pack(side="left")
    tk.Button(title, text="↻ Refresh", command=app.refresh_devices,
              bg=c["panel"], fg=c["muted"], activebackground=c["panel2"],
              activeforeground=c["text"], relief="flat", bd=0,
              font=("Segoe UI", 8), cursor="hand2", pady=0).pack(side="right")
    for name, variable, is_input in (("Microphone", app.input_var, True),
                                      ("Headphones / return", app.output_var, False)):
        label(route.body, name, size=8, color=c["muted"]).pack(anchor="w", pady=(1, 2))
        combo = ttk.Combobox(route.body, textvariable=variable, state="readonly",
                             style="Compact.TCombobox", font=("Segoe UI", 9))
        combo.pack(fill="x", pady=(0, 3))
        combo.bind("<<ComboboxSelected>>", lambda _e, item=combo, inp=is_input:
                   app.change_device(inp, item.get()))
        if is_input:
            app.input_combo = combo
        else:
            app.output_combo = combo

    engine = GlassCard(root, 328, 92, c)
    engine.place(x=16, y=244)
    for title, subtitle, var, command, attribute in (
        ("AI enhancement", None, app.ai_var, app.toggle_ai, "ai_check"),
        ("Hear my return", None, app.monitor_var, app.toggle_monitor, "return_check"),
    ):
        row = tk.Frame(engine.body, bg=c["panel"])
        row.pack(fill="x", pady=(0, 5))
        label(row, title, size=10, weight="bold" if attribute == "ai_check" else "normal").pack(side="left", pady=5)
        switch = GlassSwitch(row, variable=var, command=command, colors=c,
                              state="disabled" if attribute == "ai_check" else "normal")
        switch.configure(width=4, font=("Segoe UI", 8, "bold"), padx=7, pady=4)
        switch.pack(side="right")
        setattr(app, attribute, switch)
    # Engine state and timing stay compact, below the actual controls.
    meter = tk.Frame(root, bg=c["bg"])
    meter.place(x=18, y=344, width=324, height=31)
    app.model_status_label = label(meter, "LOADING AI ENGINE", size=7, color=c["warn"], weight="bold")
    app.model_status_label.pack(side="left", anchor="n")
    label(meter, textvariable=app.performance_var, size=7, color=c["muted"]).pack(side="right", anchor="n")
    app.signal_track = tk.Frame(root, height=4, bg=c["line"])
    app.signal_track.place(x=18, y=365, width=324, height=4)
    app.signal_fill = tk.Frame(app.signal_track, bg=c["accent2"], height=4)
    app.signal_fill.place(x=0, y=0, relwidth=0)

    foot = tk.Frame(root, bg=c["bg"])
    foot.place(x=18, y=382, width=324, height=30)
    tk.Button(foot, text="Exit", command=app.close, bg=c["bg"], fg=c["muted"],
              activebackground=c["panel2"], activeforeground=c["text"],
              relief="flat", bd=0, font=("Segoe UI", 8), cursor="hand2", pady=0).pack(side="right", anchor="n")
    app.virtual_status_label = tk.Button(
        foot, textvariable=app.virtual_mic_var, command=app.open_virtual_cable_setup,
        bg=c["bg"], fg=c["warn"], activebackground=c["bg"], activeforeground=c["accent"],
        disabledforeground=c["accent2"], font=("Segoe UI", 7, "bold"),
        relief="flat", bd=0, padx=0, pady=0, cursor="hand2",
    )
    app.virtual_status_label.pack(anchor="w")
    label(foot, textvariable=app.latency_var, size=7, color=c["muted"]).pack(anchor="w", pady=(2, 0))
    apply_window_material(app)
