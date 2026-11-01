"""UI dropdown option constants and TTK theme styles for NetDoctor NOC."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

MISSION_MODES: list[str] = [
    "🔧 Mode 1: Break/Fix Troubleshooting",
    "🏗️ Mode 2: Build Network from Scratch",
]

TROUBLESHOOT_LEVEL_OPTIONS: list[str] = [
    "Level 1: Tier 1 Helpdesk (Single LAN)",
    "Level 2: Switching, VLANs, 802.1Q Trunks & RoaS",
]

BUILD_LEVEL_OPTIONS: list[str] = [
    "Level 1: Branch LAN Bring-Up (Single LAN)",
    "Level 2: Dual-Subnet FLSM, VLANs & 802.1Q RoaS",
    "Level 3: Multi-VLAN Campus, EtherChannel & IOS DHCP",
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

LEVEL2_FAULT_FILTER_OPTIONS: list[tuple[str, str | None]] = [
    ("🎲 Random Level 2 CCNA Switching/VLAN Fault", None),
    # VLANs & Access Ports (CCNA 2.1, 2.2)
    ("[VLAN] Access Port Assigned to Wrong VLAN ID", "access_port_wrong_vlan"),
    ("[VLAN] Missing / Inactive VLAN in Switch VLAN Database", "vlan_missing_from_db"),
    ("[VLAN] Voice & Data Access Port VLAN Misconfiguration", "voice_vlan_mismatch"),
    # 802.1Q Trunks & DTP (CCNA 2.1, 2.2, 2.3)
    ("[TRUNK] Inter-Switch Uplink Left in Access Mode (No Trunk)", "trunk_left_as_access"),
    ("[TRUNK] 802.1Q Trunk Allowed VLAN List Filtering Traffic", "trunk_allowed_vlan_missing"),
    ("[TRUNK] 802.1Q Native VLAN Mismatch Across Trunk Link", "trunk_native_vlan_mismatch"),
    ("[TRUNK] DTP Negotiation Failure (dynamic auto vs auto)", "dtp_mode_mismatch"),
    # Router-on-a-Stick / Inter-VLAN Routing (CCNA 3.1)
    ("[ROAS] Router Subinterface Wrong 802.1Q Tag (encapsulation dot1Q)", "roas_wrong_dot1q_tag"),
    ("[ROAS] Router Subinterface Wrong Gateway IP / Subnet Mask", "roas_subif_wrong_ip"),
    ("[ROAS] Router Physical Parent Interface Administratively Down", "roas_parent_port_shutdown"),
    ("[ROAS] Switch-to-Router Uplink Not Configured as 802.1Q Trunk", "roas_switch_uplink_not_trunk"),
    # Layer 2 EtherChannel (CCNA 2.4)
    ("[LACP] Layer 2 EtherChannel Protocol Mismatch (LACP vs PAgP/On)", "etherchannel_mode_mismatch"),
]


def configure_ttk_styles(root: tk.Tk) -> None:
    """Configure custom dark-mode TTK styles for NetDoctor NOC."""
    style = ttk.Style(root)
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

