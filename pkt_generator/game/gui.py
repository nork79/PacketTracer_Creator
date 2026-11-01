"""Tkinter Desktop GUI controller for the NetDoctor NOC Packet Tracer Game."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from pkt_generator.game.generator import generate_level1_challenge
from pkt_generator.game.models import ChallengeTicket
from pkt_generator.game.settings import GameSettings
from pkt_generator.game.ui import (
    ADDRESSING_HELP_OPTIONS,
    BUILD_LEVEL_OPTIONS,
    CABLING_MODE_OPTIONS,
    DiagnosticConsolePopup,
    FAULT_FILTER_OPTIONS,
    LEVEL2_FAULT_FILTER_OPTIONS,
    MISSION_MODES,
    TROUBLESHOOT_LEVEL_OPTIONS,
    TopologyDiagramView,
    configure_ttk_styles,
)
from pkt_generator.game.verifier import verify_pkt_file


class NetDoctorApp:
    """Main Tkinter application window for NetDoctor NOC."""

    def __init__(
        self,
        root: tk.Tk,
        challenges_dir: str | Path | None = None,
        settings_path: str | Path | None = None,
    ) -> None:
        self.root = root
        self.root.title("NetDoctor NOC — Packet Tracer Troubleshooting Game")
        self.root.geometry("1320x820")
        self.root.minsize(1080, 700)
        self.root.configure(bg="#0f172a")

        self.challenges_dir = (
            Path(challenges_dir)
            if challenges_dir
            else Path(__file__).resolve().parent.parent.parent / "challenges"
        )
        self.challenges_dir.mkdir(parents=True, exist_ok=True)

        self.current_ticket: ChallengeTicket | None = None
        self.hint_index: int = 0
        self.tickets_solved: int = 0
        self.settings: GameSettings = GameSettings.load(settings_path)

        configure_ttk_styles(self.root)
        self._build_ui()

        self.generate_new_challenge()

    def _build_ui(self) -> None:
        # ---------------- Top Header & Mission Setup Bar ----------------
        top_bar = tk.Frame(
            self.root,
            bg="#1e293b",
            padx=14,
            pady=10,
            highlightthickness=1,
            highlightbackground="#334155",
        )
        top_bar.pack(fill="x", padx=12, pady=(10, 6))

        header_row = tk.Frame(top_bar, bg="#1e293b")
        header_row.pack(fill="x", pady=(0, 8))

        title_col = tk.Frame(header_row, bg="#1e293b")
        title_col.pack(side="left")
        self.header_title_lbl = tk.Label(
            title_col,
            text=f"🛡️ NetDoctor NOC Console — {self.settings.company_name}",
            bg="#1e293b",
            fg="#38bdf8",
            font=("Segoe UI", 14, "bold"),
        )
        self.header_title_lbl.pack(anchor="w")
        self.subtitle_lbl = tk.Label(
            title_col,
            text=f"Engineer on Duty: {self.settings.player_name}  •  Diagnose IP & Cabling Faults in Cisco Packet Tracer (.pkt)",
            bg="#1e293b",
            fg="#94a3b8",
            font=("Segoe UI", 9),
        )
        self.subtitle_lbl.pack(anchor="w")

        self.setup_container = tk.Frame(
            top_bar,
            bg="#0f172a",
            padx=10,
            pady=8,
            highlightthickness=1,
            highlightbackground="#334155",
        )
        self.setup_container.pack(fill="x")

        # --- Row 1: Mission Type ---
        mission_row = tk.Frame(self.setup_container, bg="#0f172a")
        mission_row.pack(fill="x", pady=(0, 6))

        tk.Label(
            mission_row,
            text="Mission Type:",
            width=12,
            anchor="w",
            bg="#0f172a",
            fg="#38bdf8",
            font=("Segoe UI", 9, "bold"),
        ).pack(side="left", padx=(0, 6))

        self.mission_mode_var = tk.StringVar(value=MISSION_MODES[0])
        mode_cb = ttk.Combobox(
            mission_row,
            textvariable=self.mission_mode_var,
            values=MISSION_MODES,
            state="readonly",
            width=34,
        )
        mode_cb.pack(side="left")
        mode_cb.bind("<<ComboboxSelected>>", self._on_mission_mode_changed)

        # --- Row 2: Difficulty & Mode-Specific Controls (directly beneath Mission Type) ---
        self.mode_row_holder = tk.Frame(self.setup_container, bg="#0f172a")
        self.mode_row_holder.pack(fill="x", pady=(0, 8))

        # Frame A: Mode 1 (Break/Fix Troubleshooting) Controls
        self.mode1_ctrl_frame = tk.Frame(self.mode_row_holder, bg="#0f172a")
        self.mode1_ctrl_frame.pack(fill="x")

        tk.Label(
            self.mode1_ctrl_frame,
            text="Difficulty:",
            width=12,
            anchor="w",
            bg="#0f172a",
            fg="#cbd5e1",
            font=("Segoe UI", 9, "bold"),
        ).pack(side="left", padx=(0, 6))

        self.level_var = tk.StringVar(value=TROUBLESHOOT_LEVEL_OPTIONS[0])
        level_cb = ttk.Combobox(
            self.mode1_ctrl_frame,
            textvariable=self.level_var,
            values=TROUBLESHOOT_LEVEL_OPTIONS,
            state="readonly",
            width=34,
        )
        level_cb.pack(side="left", padx=(0, 16))
        level_cb.bind("<<ComboboxSelected>>", self._on_troubleshoot_level_changed)

        tk.Label(
            self.mode1_ctrl_frame,
            text="Fault Profile:",
            bg="#0f172a",
            fg="#cbd5e1",
            font=("Segoe UI", 9, "bold"),
        ).pack(side="left", padx=(0, 4))

        self.fault_filter_var = tk.StringVar(value=FAULT_FILTER_OPTIONS[0][0])
        self.fault_cb = ttk.Combobox(
            self.mode1_ctrl_frame,
            textvariable=self.fault_filter_var,
            values=[label for label, _ in FAULT_FILTER_OPTIONS],
            state="readonly",
            width=46,
        )
        self.fault_cb.pack(side="left", padx=(0, 14))

        tk.Label(
            self.mode1_ctrl_frame,
            text="Fault Count:",
            bg="#0f172a",
            fg="#cbd5e1",
            font=("Segoe UI", 9, "bold"),
        ).pack(side="left", padx=(0, 4))

        self.num_faults_var = tk.IntVar(value=1)
        fault_spin = ttk.Spinbox(
            self.mode1_ctrl_frame,
            from_=1,
            to=2,
            textvariable=self.num_faults_var,
            width=4,
            state="readonly",
        )
        fault_spin.pack(side="left")

        # Frame B: Mode 2 (Build Network from Scratch) Controls
        self.mode2_ctrl_frame = tk.Frame(self.mode_row_holder, bg="#0f172a")

        tk.Label(
            self.mode2_ctrl_frame,
            text="Difficulty:",
            width=12,
            anchor="w",
            bg="#0f172a",
            fg="#cbd5e1",
            font=("Segoe UI", 9, "bold"),
        ).pack(side="left", padx=(0, 6))

        self.build_level_var = tk.StringVar(value=BUILD_LEVEL_OPTIONS[0])
        build_lvl_cb = ttk.Combobox(
            self.mode2_ctrl_frame,
            textvariable=self.build_level_var,
            values=BUILD_LEVEL_OPTIONS,
            state="readonly",
            width=34,
        )
        build_lvl_cb.pack(side="left", padx=(0, 16))

        tk.Label(
            self.mode2_ctrl_frame,
            text="Addressing Help:",
            bg="#0f172a",
            fg="#cbd5e1",
            font=("Segoe UI", 9, "bold"),
        ).pack(side="left", padx=(0, 4))

        self.addressing_help_var = tk.StringVar(value=ADDRESSING_HELP_OPTIONS[0])
        addr_help_cb = ttk.Combobox(
            self.mode2_ctrl_frame,
            textvariable=self.addressing_help_var,
            values=ADDRESSING_HELP_OPTIONS,
            state="readonly",
            width=38,
        )
        addr_help_cb.pack(side="left", padx=(0, 14))

        tk.Label(
            self.mode2_ctrl_frame,
            text="Hardware State:",
            bg="#0f172a",
            fg="#cbd5e1",
            font=("Segoe UI", 9, "bold"),
        ).pack(side="left", padx=(0, 4))

        self.cabling_mode_var = tk.StringVar(value=CABLING_MODE_OPTIONS[0])
        cab_mode_cb = ttk.Combobox(
            self.mode2_ctrl_frame,
            textvariable=self.cabling_mode_var,
            values=CABLING_MODE_OPTIONS,
            state="readonly",
            width=34,
        )
        cab_mode_cb.pack(side="left")

        # --- Row 3: Generate .pkt file button & Score (beneath Difficulty dropdown) ---
        action_row = tk.Frame(self.setup_container, bg="#0f172a")
        action_row.pack(fill="x")

        self.btn_new = tk.Button(
            action_row,
            text="⚡ Generate New .pkt Challenge",
            command=self.generate_new_challenge,
            bg="#0284c7",
            fg="#ffffff",
            activebackground="#0369a1",
            activeforeground="#ffffff",
            relief="flat",
            padx=14,
            pady=5,
            font=("Segoe UI", 9, "bold"),
            cursor="hand2",
        )
        self.btn_new.pack(side="left", padx=(0, 10))

        self.score_label = tk.Label(
            action_row,
            text="Solved: 0",
            bg="#1e293b",
            fg="#4ade80",
            padx=12,
            pady=5,
            font=("Segoe UI", 9, "bold"),
        )
        self.score_label.pack(side="left")

        # ---------------- Main Workspace Frame (Full Width) ----------------
        main_frame = tk.Frame(
            self.root,
            bg="#1e293b",
            padx=14,
            pady=12,
            highlightthickness=1,
            highlightbackground="#334155",
        )
        main_frame.pack(fill="both", expand=True, padx=12, pady=(4, 12))

        self._build_main_workspace(main_frame)
        self.diag_popup = DiagnosticConsolePopup(
            self.root,
            on_hint=self.show_next_hint,
            on_reveal=self.reveal_what_was_wrong,
        )

    def _build_main_workspace(self, parent: tk.Frame) -> None:
        ticket_header = tk.Frame(parent, bg="#1e293b")
        ticket_header.pack(fill="x", pady=(0, 6))

        self.ticket_title_lbl = tk.Label(
            ticket_header,
            text="Ticket #NOC-0000 — Loading...",
            bg="#1e293b",
            fg="#38bdf8",
            font=("Segoe UI", 12, "bold"),
            anchor="w",
        )
        self.ticket_title_lbl.pack(fill="x")

        pkt_btn_bar = tk.Frame(parent, bg="#1e293b")
        pkt_btn_bar.pack(fill="x", pady=(0, 8))

        tk.Button(
            pkt_btn_bar,
            text="💾 Download .pkt File...",
            command=self.download_pkt_file,
            bg="#0d9488",
            fg="#ffffff",
            activebackground="#0f766e",
            activeforeground="#ffffff",
            relief="flat",
            padx=12,
            pady=5,
            font=("Segoe UI", 9, "bold"),
            cursor="hand2",
        ).pack(side="left", padx=(0, 8))

        tk.Button(
            pkt_btn_bar,
            text="🚀 Open .pkt in Packet Tracer",
            command=self.open_pkt_in_packet_tracer,
            bg="#2563eb",
            fg="#ffffff",
            activebackground="#1d4ed8",
            activeforeground="#ffffff",
            relief="flat",
            padx=12,
            pady=5,
            font=("Segoe UI", 9, "bold"),
            cursor="hand2",
        ).pack(side="left", padx=(0, 8))

        tk.Button(
            pkt_btn_bar,
            text="📂 Show in Folder",
            command=self.show_pkt_in_folder,
            bg="#334155",
            fg="#e2e8f0",
            activebackground="#475569",
            activeforeground="#ffffff",
            relief="flat",
            padx=10,
            pady=5,
            font=("Segoe UI", 9),
            cursor="hand2",
        ).pack(side="left")

        symptom_box = tk.Frame(
            parent,
            bg="#0f172a",
            padx=10,
            pady=8,
            highlightthickness=1,
            highlightbackground="#334155",
        )
        symptom_box.pack(fill="x", pady=(0, 8))

        self.pkt_path_lbl = tk.Label(
            symptom_box,
            text="Challenge File: -",
            bg="#0f172a",
            fg="#94a3b8",
            font=("Consolas", 9),
            anchor="w",
        )
        self.pkt_path_lbl.pack(fill="x", pady=(0, 4))

        tk.Label(
            symptom_box,
            text="REPORTED SYMPTOM / USER COMPLAINT:",
            bg="#0f172a",
            fg="#fbbf24",
            font=("Segoe UI", 9, "bold"),
            anchor="w",
        ).pack(fill="x")

        self.symptom_lbl = tk.Label(
            symptom_box,
            text="-",
            bg="#0f172a",
            fg="#f8fafc",
            font=("Segoe UI", 10),
            justify="left",
            anchor="w",
            wraplength=1150,
        )
        self.symptom_lbl.pack(fill="x", pady=(2, 0))

        inspect_card = tk.Frame(
            parent,
            bg="#0f172a",
            padx=10,
            pady=8,
            highlightthickness=1,
            highlightbackground="#334155",
        )
        inspect_card.pack(fill="x", pady=(0, 10))

        btn_row = tk.Frame(inspect_card, bg="#0f172a")
        btn_row.pack(fill="x", pady=(0, 6))

        tk.Button(
            btn_row,
            text="📤 Upload & Inspect .pkt File...",
            command=self.upload_and_inspect_pkt,
            bg="#16a34a",
            fg="#ffffff",
            activebackground="#15803d",
            activeforeground="#ffffff",
            relief="flat",
            padx=12,
            pady=5,
            font=("Segoe UI", 9, "bold"),
            cursor="hand2",
        ).pack(side="left", padx=(0, 8))

        tk.Button(
            btn_row,
            text="🔄 Quick-Check Current .pkt",
            command=self.quick_check_current_pkt,
            bg="#0284c7",
            fg="#ffffff",
            activebackground="#0369a1",
            activeforeground="#ffffff",
            relief="flat",
            padx=10,
            pady=5,
            font=("Segoe UI", 9, "bold"),
            cursor="hand2",
        ).pack(side="left", padx=(0, 8))

        tk.Button(
            btn_row,
            text="💡 Diagnostic Console & Solution Reveal",
            command=self.open_diagnostic_popup,
            bg="#7c3aed",
            fg="#ffffff",
            activebackground="#6d28d9",
            activeforeground="#ffffff",
            relief="flat",
            padx=12,
            pady=5,
            font=("Segoe UI", 9, "bold"),
            cursor="hand2",
        ).pack(side="left")

        self.status_banner = tk.Label(
            inspect_card,
            text="STATUS: Waiting for .pkt inspection...",
            bg="#1e293b",
            fg="#fbbf24",
            font=("Segoe UI", 10, "bold"),
            pady=5,
            padx=8,
            anchor="w",
        )
        self.status_banner.pack(fill="x")

        tk.Label(
            parent,
            text="📋 INTENDED NETWORK SPECIFICATION (Compare Packet Tracer against this Blueprint):",
            bg="#1e293b",
            fg="#cbd5e1",
            font=("Segoe UI", 9, "bold"),
            anchor="w",
        ).pack(fill="x", pady=(0, 4))

        self.notebook = ttk.Notebook(parent)
        self.notebook.pack(fill="both", expand=True)

        # Tab 1: Addressing Table
        tab_addr = tk.Frame(self.notebook, bg="#0f172a")
        self.notebook.add(tab_addr, text=" 1. Expected IPv4 Addressing ")

        addr_cols = ("device", "model", "interface", "ip", "mask", "gateway", "dns")
        self.addr_tree = ttk.Treeview(tab_addr, columns=addr_cols, show="headings")
        for col, heading, width in (
            ("device", "Device", 110),
            ("model", "Model", 95),
            ("interface", "Interface", 145),
            ("ip", "Expected IPv4", 130),
            ("mask", "Expected Mask", 135),
            ("gateway", "Default Gateway", 130),
            ("dns", "DNS Server", 120),
        ):
            self.addr_tree.heading(col, text=heading)
            self.addr_tree.column(col, width=width, anchor="w")
        self.addr_tree.pack(fill="both", expand=True, padx=4, pady=4)

        # Tab 2: Cabling & Port Map
        tab_links = tk.Frame(self.notebook, bg="#0f172a")
        self.notebook.add(tab_links, text=" 2. Expected Cabling & Ports ")

        link_cols = ("dev_a", "port_a", "dev_b", "port_b", "cable", "mode")
        self.link_tree = ttk.Treeview(tab_links, columns=link_cols, show="headings")
        for col, heading, width in (
            ("dev_a", "Device A", 120),
            ("port_a", "Port A", 150),
            ("dev_b", "Device B", 120),
            ("port_b", "Port B", 150),
            ("cable", "Cable Type", 170),
            ("mode", "Mode / VLAN", 150),
        ):
            self.link_tree.heading(col, text=heading)
            self.link_tree.column(col, width=width, anchor="w")
        self.link_tree.pack(fill="both", expand=True, padx=4, pady=4)

        # Tab 3: Visual Topology Diagram Component
        tab_canvas = tk.Frame(self.notebook, bg="#0f172a")
        self.notebook.add(tab_canvas, text=" 3. Visual Topology Diagram ")
        self.topology_view = TopologyDiagramView(tab_canvas)

    # ------------------------------------------------------------------
    # Delegated Component Helpers
    # ------------------------------------------------------------------
    def open_diagnostic_popup(self) -> None:
        self.diag_popup.open()

    def _log(self, text: str, tag: str | None = None) -> None:
        self.diag_popup.log(text, tag)

    def _clear_log(self) -> None:
        self.diag_popup.clear()

    def _zoom_topology(self, factor: float, event: object = None) -> None:
        self.topology_view.zoom_by(factor, event)

    def _reset_topology_zoom(self) -> None:
        self.topology_view.reset_zoom()

    # ------------------------------------------------------------------
    # Mission Mode & Challenge Generation
    # ------------------------------------------------------------------
    def _on_mission_mode_changed(self, _event: object = None) -> None:
        mode = self.mission_mode_var.get()
        if mode == MISSION_MODES[1]:
            self.mode1_ctrl_frame.pack_forget()
            self.mode2_ctrl_frame.pack(fill="x")
            self.subtitle_lbl.configure(
                text=f"Engineer on Duty: {self.settings.player_name}  •  Greenfield Provisioning: Cable, Subnet & Configure Networks from Scratch (.pkt)"
            )
            self.btn_new.configure(text="🏗️ Generate Build Mission (.pkt)")
        else:
            self.mode2_ctrl_frame.pack_forget()
            self.mode1_ctrl_frame.pack(fill="x")
            self.subtitle_lbl.configure(
                text=f"Engineer on Duty: {self.settings.player_name}  •  Diagnose IP & Cabling Faults in Cisco Packet Tracer (.pkt)"
            )
            self.btn_new.configure(text="⚡ Generate New .pkt Challenge")

    def _on_troubleshoot_level_changed(self, _event: object = None) -> None:
        if self.level_var.get() == TROUBLESHOOT_LEVEL_OPTIONS[1]:
            self.fault_cb.configure(values=[label for label, _ in LEVEL2_FAULT_FILTER_OPTIONS])
            self.fault_filter_var.set(LEVEL2_FAULT_FILTER_OPTIONS[0][0])
        else:
            self.fault_cb.configure(values=[label for label, _ in FAULT_FILTER_OPTIONS])
            self.fault_filter_var.set(FAULT_FILTER_OPTIONS[0][0])

    def generate_new_challenge(self) -> None:
        self.settings = GameSettings.load(self.settings.settings_path)
        self.header_title_lbl.configure(
            text=f"🛡️ NetDoctor NOC Console — {self.settings.company_name}"
        )
        self._on_mission_mode_changed()

        mode = self.mission_mode_var.get()

        if mode == MISSION_MODES[1]:
            self._clear_log()
            self._log("=== MISSION MODE 2: BUILD NETWORK FROM SCRATCH (UI SETUP) ===", "heading")
            self._log(f"  Selected Level     : {self.build_level_var.get()}", "warn")
            self._log(f"  Addressing Help    : {self.addressing_help_var.get()}", "warn")
            self._log(f"  Hardware State     : {self.cabling_mode_var.get()}", "warn")
            self._log("")
            self._log(
                "Mode 2 UI controls are configured! Backend generator & 4-stage commissioning "
                "verifier for 'Build from Scratch' missions are awaiting implementation.",
                "muted",
            )
            self.status_banner.configure(
                text="STATUS: Mode 2 Setup Selected (Backend implementation pending)",
                bg="#1e293b",
                fg="#38bdf8",
            )
            return

        if self.level_var.get() == TROUBLESHOOT_LEVEL_OPTIONS[1]:
            self._clear_log()
            self._log("=== LEVEL 2 TROUBLESHOOTING (UI SETUP) ===", "heading")
            self._log(f"  Selected Difficulty : {self.level_var.get()}", "warn")
            self._log(f"  Fault Profile       : {self.fault_filter_var.get()}", "warn")
            self._log(f"  Fault Count         : {self.num_faults_var.get()}", "warn")
            self._log("")
            self._log(
                "Level 2 UI dropdowns (Switching, VLANs, 802.1Q Trunks, Router-on-a-Stick & EtherChannel) "
                "are configured! Backend generator & verifier for Level 2 are awaiting implementation.",
                "muted",
            )
            self.status_banner.configure(
                text="STATUS: Level 2 Troubleshooting Selected (Backend implementation pending)",
                bg="#1e293b",
                fg="#38bdf8",
            )
            return

        selected_label = self.fault_filter_var.get()
        chosen_code: str | None = None
        for label, code in FAULT_FILTER_OPTIONS:
            if label == selected_label:
                chosen_code = code
                break

        fault_types = [chosen_code] if chosen_code else None
        num_faults = int(self.num_faults_var.get())

        ticket = generate_level1_challenge(
            self.challenges_dir,
            num_faults=num_faults,
            fault_types=fault_types,
            settings=self.settings,
        )
        self.current_ticket = ticket
        self.hint_index = 0

        self.ticket_title_lbl.configure(
            text=f"Ticket #{ticket.ticket_id} — {ticket.scenario_title}"
        )
        self.pkt_path_lbl.configure(text=f"Generated .pkt File: {ticket.pkt_path}")
        self.symptom_lbl.configure(text=ticket.symptom_summary)

        for item in self.addr_tree.get_children():
            self.addr_tree.delete(item)
        for row in ticket.device_rows:
            self.addr_tree.insert(
                "",
                "end",
                values=(
                    row.device,
                    row.model,
                    row.interface,
                    row.expected_ip,
                    row.expected_mask,
                    row.expected_gateway,
                    row.expected_dns,
                ),
            )

        for item in self.link_tree.get_children():
            self.link_tree.delete(item)
        for lrow in ticket.link_rows:
            self.link_tree.insert(
                "",
                "end",
                values=(
                    lrow.dev_a,
                    lrow.port_a,
                    lrow.dev_b,
                    lrow.port_b,
                    lrow.cable_type,
                    lrow.mode_or_vlan,
                ),
            )

        self.topology_view.draw(ticket)

        total_hints = sum(len(f.hints) for f in ticket.faults)
        self.diag_popup.hint_btn.configure(text=f"💡 Get Progressive Hint (0/{total_hints})")
        self.status_banner.configure(
            text=f"STATUS: Challenge Ready ({len(ticket.faults)} hidden fault(s) injected)",
            bg="#1e293b",
            fg="#fbbf24",
        )

        self._clear_log()
        self._log(f"=== NEW CHALLENGE GENERATED: {ticket.ticket_id} ===", "heading")
        self._log(f"File saved to: {ticket.pkt_path}", "muted")
        self._log("")
        self._log("Design Notes:", "heading")
        for note in ticket.service_notes:
            self._log(f"  • {note}")
        self._log("")
        self._log(
            "Instructions:\n"
            "  1. Click 'Open .pkt in Packet Tracer' (or open the file from the challenges/ folder).\n"
            "  2. Compare the devices in Packet Tracer against the 'Expected IPv4 Addressing' & 'Cabling' tabs.\n"
            "  3. Fix the issue(s), save in Packet Tracer (Ctrl+S), and click 'Upload & Inspect .pkt'!\n"
            "  4. If you get stuck, click 'Get Progressive Hint' or 'Reveal What Was Wrong'.",
            "muted",
        )

    # ------------------------------------------------------------------
    # File Operations, Verification & Hints
    # ------------------------------------------------------------------
    def download_pkt_file(self) -> None:
        if not self.current_ticket:
            return
        src_pkt = self.current_ticket.pkt_path
        if not src_pkt.is_file():
            messagebox.showerror("File Not Found", f"Could not find {src_pkt}")
            return

        downloads_dir = Path.home() / "Downloads"
        initial_dir = downloads_dir if downloads_dir.is_dir() else src_pkt.parent

        dest = filedialog.asksaveasfilename(
            title="Save / Download Challenge .pkt File As",
            initialdir=str(initial_dir),
            initialfile=src_pkt.name,
            defaultextension=".pkt",
            filetypes=[("Cisco Packet Tracer Files", "*.pkt"), ("All Files", "*.*")],
        )
        if not dest:
            return
        dest_path = Path(dest)
        try:
            shutil.copy2(src_pkt, dest_path)
            self.current_ticket.pkt_path = dest_path
            self.pkt_path_lbl.configure(text=f"Active .pkt File: {dest_path}")
            self._log(f"\n💾 Downloaded .pkt file to: {dest_path}", "pass")
        except Exception as exc:
            messagebox.showerror("Download Failed", f"Could not save .pkt file:\n{exc}")

    def open_pkt_in_packet_tracer(self) -> None:
        if not self.current_ticket:
            return
        pkt = self.current_ticket.pkt_path
        if not pkt.is_file():
            messagebox.showerror("File Not Found", f"Could not find {pkt}")
            return
        try:
            if sys.platform == "win32":
                os.startfile(str(pkt))  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(pkt)])
            else:
                subprocess.Popen(["xdg-open", str(pkt)])
            self._log(f"\n[Launched {pkt.name} with system default handler]", "muted")
        except Exception as exc:
            messagebox.showinfo(
                "Open in Packet Tracer",
                f"Open this file manually inside Cisco Packet Tracer:\n\n{pkt}\n\n({exc})",
            )

    def show_pkt_in_folder(self) -> None:
        if not self.current_ticket:
            return
        pkt = self.current_ticket.pkt_path
        try:
            if sys.platform == "win32":
                subprocess.Popen(["explorer", "/select,", str(pkt)])
            else:
                subprocess.Popen(["xdg-open", str(pkt.parent)])
        except Exception as exc:
            messagebox.showinfo("Challenge Folder", f"File location:\n{pkt}\n({exc})")

    def upload_and_inspect_pkt(self) -> None:
        if not self.current_ticket:
            return
        chosen = filedialog.askopenfilename(
            title="Select Fixed .pkt File to Inspect",
            initialdir=str(self.current_ticket.pkt_path.parent),
            initialfile=self.current_ticket.pkt_path.name,
            filetypes=[("Cisco Packet Tracer Files", "*.pkt"), ("All Files", "*.*")],
        )
        if not chosen:
            return
        self._run_verification(Path(chosen))

    def quick_check_current_pkt(self) -> None:
        if not self.current_ticket:
            return
        self._run_verification(self.current_ticket.pkt_path)

    def _run_verification(self, path: Path) -> None:
        if not self.current_ticket:
            return
        res = verify_pkt_file(path, self.current_ticket)
        self._log("\n" + "=" * 58, "heading")
        self._log(f"INSPECTING .PKT FILE: {path.name}", "heading")

        if res.general_errors:
            for err in res.general_errors:
                self._log(f"  [ERROR] {err}", "fail")
            self.status_banner.configure(
                text="❌ ERROR: Could not read .pkt file",
                bg="#7f1d1d",
                fg="#fecaca",
            )
            return

        for idx, item in enumerate(res.items, start=1):
            badge = "✅ PASS" if item.passed else "❌ FAIL"
            tag = "pass" if item.passed else "fail"
            self._log(f"  Check #{idx} [{item.device}]: {badge}", tag)
            self._log(f"    Observed in .pkt : {item.observed_state}")
            if item.passed:
                self._log(f"    Result           : {item.message}", "pass")
            else:
                self._log(
                    "    Result           : Fault is still present (use Hint or Reveal Solution if stuck).",
                    "warn",
                )

        if res.all_passed:
            self.tickets_solved += 1
            self.score_label.configure(text=f"Solved: {self.tickets_solved}")
            self.status_banner.configure(
                text=f"✅ TICKET RESOLVED! ({res.passed_count}/{res.total_count} checks passed)",
                bg="#14532d",
                fg="#86efac",
            )
            self._log(
                f"\n🎉 CONGRATULATIONS! All {res.total_count} fault(s) in {self.current_ticket.ticket_id} are fixed!",
                "pass",
            )
        else:
            self.status_banner.configure(
                text=f"❌ {res.total_count - res.passed_count} FAULT(S) REMAIN ({res.passed_count}/{res.total_count} fixed)",
                bg="#7f1d1d",
                fg="#fecaca",
            )

    def show_next_hint(self) -> None:
        if not self.current_ticket:
            return
        all_hints: list[tuple[str, str]] = []
        for f in self.current_ticket.faults:
            for h in f.hints:
                all_hints.append((f.device, h))

        if not all_hints:
            return
        if self.hint_index >= len(all_hints):
            self._log(
                "\n[All progressive hints have already been revealed. Click 'Reveal What Was Wrong' for the full solution.]",
                "warn",
            )
            return

        _dev, hint_text = all_hints[self.hint_index]
        self.hint_index += 1
        self.diag_popup.hint_btn.configure(
            text=f"💡 Get Progressive Hint ({self.hint_index}/{len(all_hints)})"
        )
        self._log(f"\n💡 {hint_text}", "warn")

    def reveal_what_was_wrong(self) -> None:
        if not self.current_ticket:
            return
        self._log("\n" + "=" * 58, "heading")
        self._log(
            f"🔓 FULL DIAGNOSTIC SOLUTION — TICKET {self.current_ticket.ticket_id}",
            "heading",
        )
        for i, f in enumerate(self.current_ticket.faults, start=1):
            self._log(f"\nFault #{i}: {f.title}", "fail")
            self._log(f"  Category       : {f.category}")
            self._log(f"  Device / Port  : {f.device} ({f.interface})")
            self._log(f"  Faulty State   : {f.faulty_state}", "warn")
            self._log(f"  Expected State : {f.expected_state}", "pass")
            self._log(f"\n  Why This Broke the Network:\n    {f.explanation}")
            self._log("\n  How to Fix It in Packet Tracer:", "heading")
            for step in f.fix_steps:
                self._log(f"    {step}")


def launch_gui() -> None:
    root = tk.Tk()
    NetDoctorApp(root)
    root.mainloop()


if __name__ == "__main__":
    launch_gui()
