"""Tkinter Desktop GUI for the NetDoctor NOC Packet Tracer Troubleshooting Game."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

from pkt_generator.game.generator import generate_level1_challenge
from pkt_generator.game.models import ChallengeTicket
from pkt_generator.game.verifier import verify_pkt_file


MISSION_MODES: list[str] = [
    "🔧 Mode 1: Break/Fix Troubleshooting",
    "🏗️ Mode 2: Build Network from Scratch",
]

BUILD_LEVEL_OPTIONS: list[str] = [
    "Level 1: Branch LAN Bring-Up (Single LAN)",
    "Level 2: Dual-Subnet FLSM & IOS DHCP Server",
    "Level 3: Multi-VLAN & Router-on-a-Stick (802.1Q)",
    "Level 4: Multi-Site WAN, VLSM & OSPFv2 Routing",
    "Level 5: Enterprise Core (LACP / L3 Switch / NAT / ACLs)",
]

ADDRESSING_HELP_OPTIONS: list[str] = [
    "📘 Guided (Full IPv4 Table Provided)",
    "🧮 Subnetting Challenge (CIDR Block & Rules Only)",
]

CABLING_MODE_OPTIONS: list[str] = [
    "🔌 Uncabled Hardware (Wire from Scratch)",
    "🔗 Pre-Cabled Hardware (Focus on CLI / IPs)",
]

FAULT_FILTER_OPTIONS: list[tuple[str, str | None]] = [
    ("🎲 Random Level 1 CCNA Fault", None),
    # Layer 1 — Physical, Power, Cabling & Speed/Duplex (CCNA 1.1, 1.4, 1.5)
    ("[L1] Server Physically Powered Off", "device_powered_off"),
    ("[L1] Unplugged / Missing Copper Patch Cable", "missing_patch_cable"),
    ("[L1] Workstation NIC Adapter Disabled (Port Status Off)", "host_nic_disabled"),
    ("[L1] Speed / Duplex Mismatch (100/Full vs 10/Half)", "speed_duplex_mismatch"),
    ("[L1] Router Uplink Cabled to Wrong Port (Gi0/1)", "wrong_router_port_cabled"),
    # Layer 2 — Interface State & Switch Management SVI (CCNA 1.4, 2.1)
    ("[L2] Router Gateway Interface Shutdown (Gi0/0)", "router_port_shutdown"),
    ("[L2] Switch Access Port Shutdown (Fa0/X)", "switch_port_shutdown"),
    ("[L2] Switch Management SVI (Vlan1) & Default-Gateway Fault", "switch_mgmt_fault"),
    # Layer 3 — IPv4 Addressing, Subnetting & Gateway (CCNA 1.6, 1.11)
    ("[L3] Host Wrong Subnet IPv4 Address (Octet Typo)", "host_wrong_subnet_ip"),
    ("[L3] Host Wrong Default Gateway (.254)", "host_wrong_default_gateway"),
    ("[L3] Host Restrictive Subnet Mask (/26 vs /24)", "host_wrong_subnet_mask"),
    ("[L3] Duplicate IPv4 Address Conflict (.100)", "duplicate_ip_conflict"),
    ("[L3] Router Gateway Interface IPv4 Typo", "router_wrong_ip_or_mask"),
    ("[L3] Server IPv4 & Gateway Misconfigured", "server_ip_or_gateway_fault"),
    # Services — DHCP/APIPA & DNS (CCNA 4.3, 4.6)
    ("[SVC] Host Set to DHCP on Static LAN (169.254.x.x APIPA)", "host_dhcp_apipa"),
    ("[SVC] Host Wrong DNS Server IP", "host_wrong_dns"),
]


class NetDoctorApp:
    """Main Tkinter application window for NetDoctor NOC."""

    def __init__(self, root: tk.Tk, challenges_dir: str | Path | None = None) -> None:
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

        self._configure_styles()
        self._build_ui()

        # Generate the initial Level 1 example faulty network immediately on launch
        self.generate_new_challenge()

    def _configure_styles(self) -> None:
        style = ttk.Style(self.root)
        if "clam" in style.theme_names():
            style.theme_use("clam")

        style.configure("Main.TFrame", background="#0f172a")
        style.configure("Card.TFrame", background="#1e293b", relief="flat")
        style.configure(
            "Header.TLabel",
            background="#0f172a",
            foreground="#f8fafc",
            font=("Segoe UI", 15, "bold"),
        )
        style.configure(
            "SubHeader.TLabel",
            background="#0f172a",
            foreground="#94a3b8",
            font=("Segoe UI", 10),
        )
        style.configure(
            "CardTitle.TLabel",
            background="#1e293b",
            foreground="#38bdf8",
            font=("Segoe UI", 11, "bold"),
        )
        style.configure(
            "CardBody.TLabel",
            background="#1e293b",
            foreground="#e2e8f0",
            font=("Segoe UI", 10),
        )
        style.configure(
            "Treeview",
            background="#0f172a",
            fieldbackground="#0f172a",
            foreground="#e2e8f0",
            rowheight=26,
            font=("Consolas", 9),
        )
        style.configure(
            "Treeview.Heading",
            background="#334155",
            foreground="#f8fafc",
            font=("Segoe UI", 9, "bold"),
        )
        style.map("Treeview", background=[("selected", "#0284c7")])

        style.configure(
            "TNotebook",
            background="#1e293b",
            borderwidth=0,
        )
        style.configure(
            "TNotebook.Tab",
            background="#334155",
            foreground="#cbd5e1",
            padding=(12, 6),
            font=("Segoe UI", 9, "bold"),
        )
        style.map(
            "TNotebook.Tab",
            background=[("selected", "#0284c7")],
            foreground=[("selected", "#ffffff")],
        )

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

        # Top row: Brand Title (left) + Mission Mode Selector & Generate Button (right)
        header_row = tk.Frame(top_bar, bg="#1e293b")
        header_row.pack(fill="x", pady=(0, 8))

        title_col = tk.Frame(header_row, bg="#1e293b")
        title_col.pack(side="left")
        tk.Label(
            title_col,
            text="🛡️ NetDoctor NOC Console",
            bg="#1e293b",
            fg="#38bdf8",
            font=("Segoe UI", 14, "bold"),
        ).pack(anchor="w")
        self.subtitle_lbl = tk.Label(
            title_col,
            text="Diagnose IP & Cabling Faults in Cisco Packet Tracer (.pkt)",
            bg="#1e293b",
            fg="#94a3b8",
            font=("Segoe UI", 9),
        )
        self.subtitle_lbl.pack(anchor="w")

        mode_bar = tk.Frame(header_row, bg="#1e293b")
        mode_bar.pack(side="right")

        tk.Label(
            mode_bar,
            text="Mission Type:",
            bg="#1e293b",
            fg="#38bdf8",
            font=("Segoe UI", 9, "bold"),
        ).pack(side="left", padx=(0, 6))

        self.mission_mode_var = tk.StringVar(value=MISSION_MODES[0])
        mode_cb = ttk.Combobox(
            mode_bar,
            textvariable=self.mission_mode_var,
            values=MISSION_MODES,
            state="readonly",
            width=34,
        )
        mode_cb.pack(side="left", padx=(0, 12))
        mode_cb.bind("<<ComboboxSelected>>", self._on_mission_mode_changed)

        self.btn_new = tk.Button(
            mode_bar,
            text="⚡ Generate New .pkt Challenge",
            command=self.generate_new_challenge,
            bg="#0284c7",
            fg="#ffffff",
            activebackground="#0369a1",
            activeforeground="#ffffff",
            relief="flat",
            padx=12,
            pady=5,
            font=("Segoe UI", 9, "bold"),
            cursor="hand2",
        )
        self.btn_new.pack(side="left", padx=(0, 8))

        self.score_label = tk.Label(
            mode_bar,
            text="Solved: 0",
            bg="#0f172a",
            fg="#4ade80",
            padx=10,
            pady=5,
            font=("Segoe UI", 9, "bold"),
        )
        self.score_label.pack(side="left")

        # Second row inside top_bar: Dynamic Mode-Specific Setup Controls
        self.setup_container = tk.Frame(
            top_bar,
            bg="#0f172a",
            padx=10,
            pady=7,
            highlightthickness=1,
            highlightbackground="#334155",
        )
        self.setup_container.pack(fill="x")

        # --- Frame A: Mode 1 (Break/Fix Troubleshooting) Controls ---
        self.mode1_ctrl_frame = tk.Frame(self.setup_container, bg="#0f172a")
        self.mode1_ctrl_frame.pack(fill="x")

        tk.Label(
            self.mode1_ctrl_frame,
            text="Difficulty:",
            bg="#0f172a",
            fg="#cbd5e1",
            font=("Segoe UI", 9, "bold"),
        ).pack(side="left", padx=(0, 4))

        self.level_var = tk.StringVar(value="Level 1: Tier 1 Helpdesk (Single LAN)")
        level_cb = ttk.Combobox(
            self.mode1_ctrl_frame,
            textvariable=self.level_var,
            values=["Level 1: Tier 1 Helpdesk (Single LAN)"],
            state="readonly",
            width=32,
        )
        level_cb.pack(side="left", padx=(0, 14))

        tk.Label(
            self.mode1_ctrl_frame,
            text="Fault Profile:",
            bg="#0f172a",
            fg="#cbd5e1",
            font=("Segoe UI", 9, "bold"),
        ).pack(side="left", padx=(0, 4))

        self.fault_filter_var = tk.StringVar(value=FAULT_FILTER_OPTIONS[0][0])
        fault_cb = ttk.Combobox(
            self.mode1_ctrl_frame,
            textvariable=self.fault_filter_var,
            values=[label for label, _ in FAULT_FILTER_OPTIONS],
            state="readonly",
            width=46,
        )
        fault_cb.pack(side="left", padx=(0, 14))

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

        # --- Frame B: Mode 2 (Build Network from Scratch) Controls ---
        self.mode2_ctrl_frame = tk.Frame(self.setup_container, bg="#0f172a")

        tk.Label(
            self.mode2_ctrl_frame,
            text="Build Level:",
            bg="#0f172a",
            fg="#cbd5e1",
            font=("Segoe UI", 9, "bold"),
        ).pack(side="left", padx=(0, 4))

        self.build_level_var = tk.StringVar(value=BUILD_LEVEL_OPTIONS[0])
        build_lvl_cb = ttk.Combobox(
            self.mode2_ctrl_frame,
            textvariable=self.build_level_var,
            values=BUILD_LEVEL_OPTIONS,
            state="readonly",
            width=40,
        )
        build_lvl_cb.pack(side="left", padx=(0, 14))

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

        # ---------------- Main Split Pane ----------------
        main_pane = tk.PanedWindow(
            self.root,
            orient="horizontal",
            bg="#0f172a",
            sashwidth=6,
            sashrelief="flat",
        )
        main_pane.pack(fill="both", expand=True, padx=12, pady=(4, 12))

        left_frame = tk.Frame(main_pane, bg="#1e293b", padx=12, pady=12)
        right_frame = tk.Frame(main_pane, bg="#1e293b", padx=12, pady=12)
        main_pane.add(left_frame, minsize=620, width=730)
        main_pane.add(right_frame, minsize=420)

        self._build_left_pane(left_frame)
        self._build_right_pane(right_frame)

    def _build_left_pane(self, parent: tk.Frame) -> None:
        # Ticket summary header (full width so title never pushes buttons off-screen)
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

        # Dedicated .pkt file action bar on its own row so buttons never get clipped
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

        # File path & symptom box
        symptom_box = tk.Frame(
            parent,
            bg="#0f172a",
            padx=10,
            pady=8,
            highlightthickness=1,
            highlightbackground="#334155",
        )
        symptom_box.pack(fill="x", pady=(0, 10))

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
            wraplength=680,
        )
        self.symptom_lbl.pack(fill="x", pady=(2, 0))

        # Blueprint Notebook Tabs
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
            ("device", "Device", 95),
            ("model", "Model", 85),
            ("interface", "Interface", 125),
            ("ip", "Expected IPv4", 110),
            ("mask", "Expected Mask", 115),
            ("gateway", "Default Gateway", 110),
            ("dns", "DNS Server", 100),
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
            ("dev_a", "Device A", 100),
            ("port_a", "Port A", 130),
            ("dev_b", "Device B", 100),
            ("port_b", "Port B", 130),
            ("cable", "Cable Type", 140),
            ("mode", "Mode / VLAN", 110),
        ):
            self.link_tree.heading(col, text=heading)
            self.link_tree.column(col, width=width, anchor="w")
        self.link_tree.pack(fill="both", expand=True, padx=4, pady=4)

        # Tab 3: Visual Topology Schematic Canvas
        tab_canvas = tk.Frame(self.notebook, bg="#0f172a")
        self.notebook.add(tab_canvas, text=" 3. Visual Topology Diagram ")

        self.topo_canvas = tk.Canvas(
            tab_canvas, bg="#0f172a", highlightthickness=0
        )
        self.topo_canvas.pack(fill="both", expand=True, padx=4, pady=4)

    def _build_right_pane(self, parent: tk.Frame) -> None:
        # 1. Upload & Inspect .pkt Section
        tk.Label(
            parent,
            text="🔍 UPLOAD & INSPECT FIXED .PKT FILE",
            bg="#1e293b",
            fg="#38bdf8",
            font=("Segoe UI", 11, "bold"),
            anchor="w",
        ).pack(fill="x", pady=(0, 6))

        inspect_card = tk.Frame(
            parent,
            bg="#0f172a",
            padx=10,
            pady=10,
            highlightthickness=1,
            highlightbackground="#334155",
        )
        inspect_card.pack(fill="x", pady=(0, 12))

        tk.Label(
            inspect_card,
            text=(
                "Fix the fault(s) inside Cisco Packet Tracer, save the file (Ctrl+S), "
                "then upload or re-check the .pkt file below:"
            ),
            bg="#0f172a",
            fg="#cbd5e1",
            font=("Segoe UI", 9),
            justify="left",
            anchor="w",
            wraplength=480,
        ).pack(fill="x", pady=(0, 8))

        btn_row = tk.Frame(inspect_card, bg="#0f172a")
        btn_row.pack(fill="x", pady=(0, 8))

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
            pady=6,
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
            pady=6,
            font=("Segoe UI", 9, "bold"),
            cursor="hand2",
        ).pack(side="left")

        self.status_banner = tk.Label(
            inspect_card,
            text="STATUS: Waiting for .pkt inspection...",
            bg="#1e293b",
            fg="#fbbf24",
            font=("Segoe UI", 10, "bold"),
            pady=6,
             padx=8,
            anchor="w",
        )
        self.status_banner.pack(fill="x")

        # 2. Hints & "What Was Wrong?" Section
        help_bar = tk.Frame(parent, bg="#1e293b")
        help_bar.pack(fill="x", pady=(0, 6))

        tk.Label(
            help_bar,
            text="💡 DIAGNOSTIC CONSOLE & SOLUTION REVEAL",
            bg="#1e293b",
            fg="#38bdf8",
            font=("Segoe UI", 11, "bold"),
        ).pack(side="left")

        help_btns = tk.Frame(parent, bg="#1e293b")
        help_btns.pack(fill="x", pady=(0, 8))

        self.hint_btn = tk.Button(
            help_btns,
            text="💡 Get Progressive Hint (1/3)",
            command=self.show_next_hint,
            bg="#d97706",
            fg="#ffffff",
            activebackground="#b45309",
            activeforeground="#ffffff",
            relief="flat",
            padx=10,
            pady=5,
            font=("Segoe UI", 9, "bold"),
            cursor="hand2",
        )
        self.hint_btn.pack(side="left", padx=(0, 8))

        tk.Button(
            help_btns,
            text="🔓 Reveal What Was Wrong (Solution)",
            command=self.reveal_what_was_wrong,
            bg="#dc2626",
            fg="#ffffff",
            activebackground="#b91c1c",
            activeforeground="#ffffff",
            relief="flat",
            padx=10,
            pady=5,
            font=("Segoe UI", 9, "bold"),
            cursor="hand2",
        ).pack(side="left")

        self.console_log = scrolledtext.ScrolledText(
            parent,
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

    # ------------------------------------------------------------------
    # Actions & Event Handlers
    # ------------------------------------------------------------------
    def _log(self, text: str, tag: str | None = None) -> None:
        self.console_log.configure(state="normal")
        if tag:
            self.console_log.insert("end", text + "\n", tag)
        else:
            self.console_log.insert("end", text + "\n")
        self.console_log.see("end")
        self.console_log.configure(state="disabled")

    def _clear_log(self) -> None:
        self.console_log.configure(state="normal")
        self.console_log.delete("1.0", "end")
        self.console_log.configure(state="disabled")

    def _on_mission_mode_changed(self, _event: object = None) -> None:
        mode = self.mission_mode_var.get()
        if mode == MISSION_MODES[1]:
            # Mode 2: Build Network from Scratch
            self.mode1_ctrl_frame.pack_forget()
            self.mode2_ctrl_frame.pack(fill="x")
            self.subtitle_lbl.configure(
                text="Greenfield Provisioning: Cable, Subnet & Configure Networks from Scratch (.pkt)"
            )
            self.btn_new.configure(text="🏗️ Generate Build Mission (.pkt)")
        else:
            # Mode 1: Break/Fix Troubleshooting
            self.mode2_ctrl_frame.pack_forget()
            self.mode1_ctrl_frame.pack(fill="x")
            self.subtitle_lbl.configure(
                text="Diagnose IP & Cabling Faults in Cisco Packet Tracer (.pkt)"
            )
            self.btn_new.configure(text="⚡ Generate New .pkt Challenge")

    def generate_new_challenge(self) -> None:
        if self.mission_mode_var.get() == MISSION_MODES[1]:
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
        )
        self.current_ticket = ticket
        self.hint_index = 0

        # Update UI labels
        self.ticket_title_lbl.configure(
            text=f"Ticket #{ticket.ticket_id} — {ticket.scenario_title}"
        )
        self.pkt_path_lbl.configure(text=f"Generated .pkt File: {ticket.pkt_path}")
        self.symptom_lbl.configure(text=ticket.symptom_summary)

        # Populate Addressing Treeview
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

        # Populate Cabling Treeview
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

        # Draw Visual Topology Diagram on Canvas
        self._draw_topology_canvas(ticket)

        # Reset status & log
        total_hints = sum(len(f.hints) for f in ticket.faults)
        self.hint_btn.configure(text=f"💡 Get Progressive Hint (0/{total_hints})")
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

    def _draw_topology_canvas(self, ticket: ChallengeTicket) -> None:
        c = self.topo_canvas
        c.delete("all")

        node_pos = {n["name"]: (n["x"], n["y"]) for n in ticket.canvas_nodes}

        # Draw links
        for da, db, pa, pb in ticket.canvas_edges:
            if da in node_pos and db in node_pos:
                x1, y1 = node_pos[da]
                x2, y2 = node_pos[db]
                c.create_line(x1, y1, x2, y2, fill="#475569", width=2)
                mx, my = (x1 + x2) / 2, (y1 + y2) / 2
                c.create_text(
                    mx,
                    my - 8,
                    text=f"{pa} ↔ {pb}",
                    fill="#94a3b8",
                    font=("Consolas", 8),
                )

        # Draw nodes
        role_colors = {
            "router": ("#0284c7", "#e0f2fe"),
            "switch": ("#4f46e5", "#e0e7ff"),
            "pc": ("#0f766e", "#ccfbf1"),
            "server": ("#b45309", "#fef3c7"),
        }
        for n in ticket.canvas_nodes:
            x, y = n["x"], n["y"]
            bg_col, fg_col = role_colors.get(n["role"], ("#334155", "#f8fafc"))
            c.create_rectangle(
                x - 68,
                y - 26,
                x + 68,
                y + 26,
                fill=bg_col,
                outline="#94a3b8",
                width=1,
            )
            c.create_text(
                x,
                y - 10,
                text=n["name"],
                fill="#ffffff",
                font=("Segoe UI", 9, "bold"),
            )
            c.create_text(
                x,
                y + 9,
                text=n["sub"],
                fill=fg_col,
                font=("Consolas", 8),
                justify="center",
            )

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
            self._log("\n[All progressive hints have already been revealed. Click 'Reveal What Was Wrong' for the full solution.]", "warn")
            return

        _dev, hint_text = all_hints[self.hint_index]
        self.hint_index += 1
        self.hint_btn.configure(
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

