"""Popup Diagnostic Console, Progressive Hints, and Solution Reveal window."""

from __future__ import annotations

from collections.abc import Callable
import tkinter as tk
from tkinter import scrolledtext


class DiagnosticConsolePopup:
    """Persistent popup window (`tk.Toplevel`) for diagnostic logs, hints, and solution reveal."""

    def __init__(
        self,
        root: tk.Tk,
        *,
        on_hint: Callable[[], None],
        on_reveal: Callable[[], None],
    ) -> None:
        self.window = tk.Toplevel(root)
        self.window.title("💡 NetDoctor NOC — Diagnostic Console & Solution Reveal")
        self.window.geometry("720x580")
        self.window.minsize(520, 400)
        self.window.configure(bg="#1e293b", padx=14, pady=12)
        self.window.protocol("WM_DELETE_WINDOW", self.window.withdraw)
        self.window.withdraw()

        help_bar = tk.Frame(self.window, bg="#1e293b")
        help_bar.pack(fill="x", pady=(0, 8))

        tk.Label(
            help_bar,
            text="💡 DIAGNOSTIC CONSOLE & SOLUTION REVEAL",
            bg="#1e293b",
            fg="#38bdf8",
            font=("Segoe UI", 12, "bold"),
        ).pack(side="left")

        help_btns = tk.Frame(self.window, bg="#1e293b")
        help_btns.pack(fill="x", pady=(0, 10))

        self.hint_btn = tk.Button(
            help_btns,
            text="💡 Get Progressive Hint (1/3)",
            command=on_hint,
            bg="#d97706",
            fg="#ffffff",
            activebackground="#b45309",
            activeforeground="#ffffff",
            relief="flat",
            padx=12,
            pady=6,
            font=("Segoe UI", 9, "bold"),
            cursor="hand2",
        )
        self.hint_btn.pack(side="left", padx=(0, 8))

        tk.Button(
            help_btns,
            text="🔓 Reveal What Was Wrong (Solution)",
            command=on_reveal,
            bg="#dc2626",
            fg="#ffffff",
            activebackground="#b91c1c",
            activeforeground="#ffffff",
            relief="flat",
            padx=12,
            pady=6,
            font=("Segoe UI", 9, "bold"),
            cursor="hand2",
        ).pack(side="left")

        self.console_log = scrolledtext.ScrolledText(
            self.window,
            bg="#0f172a",
            fg="#e2e8f0",
            insertbackground="#ffffff",
            font=("Consolas", 9),
            wrap="word",
            relief="flat",
            padx=10,
            pady=10,
        )
        self.console_log.pack(fill="both", expand=True)
        self.console_log.tag_config("heading", foreground="#38bdf8", font=("Consolas", 10, "bold"))
        self.console_log.tag_config("pass", foreground="#4ade80", font=("Consolas", 9, "bold"))
        self.console_log.tag_config("fail", foreground="#f87171", font=("Consolas", 9, "bold"))
        self.console_log.tag_config("warn", foreground="#fbbf24", font=("Consolas", 9, "bold"))
        self.console_log.tag_config("muted", foreground="#94a3b8")

    def open(self) -> None:
        self.window.deiconify()
        self.window.lift()
        self.window.focus_force()

    def log(self, text: str, tag: str | None = None) -> None:
        self.console_log.configure(state="normal")
        if tag:
            self.console_log.insert("end", text + "\n", tag)
        else:
            self.console_log.insert("end", text + "\n")
        self.console_log.see("end")
        self.console_log.configure(state="disabled")

    def clear(self) -> None:
        self.console_log.configure(state="normal")
        self.console_log.delete("1.0", "end")
        self.console_log.configure(state="disabled")

