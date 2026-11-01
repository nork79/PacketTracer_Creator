"""Level 1 CCNA (200-301 v2.0) NOC Fault Generator with randomized subnets and topologies."""

from __future__ import annotations

from collections.abc import Callable
import ipaddress
from pathlib import Path
import random
import xml.etree.ElementTree as ET

from pkt_generator.game.models import (
    BlueprintDeviceRow,
    BlueprintLinkRow,
    ChallengeTicket,
    FaultRecord,
)
from pkt_generator.network import SimpleNetwork, encode


# Randomized site/department personas for replayability
_SITE_PERSONAS: list[tuple[str, str]] = [
    ("FIN", "Finance Branch Office"),
    ("MED", "Westside Medical Clinic"),
    ("LAB", "Engineering R&D Lab"),
    ("LOG", "Harbor Logistics Depot"),
    ("RET", "Downtown Retail Store"),
    ("LAW", "Apex Legal Partners"),
    ("HR", "Human Resources Wing"),
    ("OPS", "Plant Operations Floor"),
]


ALL_LEVEL1_FAULT_TYPES: list[str] = [
    # Layer 1 — Physical, Power, Cabling & Speed/Duplex (CCNA Obj 1.4, 1.5)
    "device_powered_off",
    "missing_patch_cable",
    "host_nic_disabled",
    "speed_duplex_mismatch",
    "wrong_router_port_cabled",
    # Layer 2 — Switch Port State & Management SVI (CCNA Obj 1.4, 2.1)
    "router_port_shutdown",
    "switch_port_shutdown",
    "switch_mgmt_fault",
    # Layer 3 — IPv4 Addressing, Mask, Gateway & Conflicts (CCNA Obj 1.6, 1.11)
    "host_wrong_subnet_ip",
    "host_wrong_default_gateway",
    "host_wrong_subnet_mask",
    "duplicate_ip_conflict",
    "router_wrong_ip_or_mask",
    "server_ip_or_gateway_fault",
    # Network Services — DHCP/APIPA & DNS (CCNA Obj 4.3, 4.6)
    "host_dhcp_apipa",
    "host_wrong_dns",
]

# Faults that target the router uplink interface (cannot be paired together)
_ROUTER_UPLINK_FAULTS = {
    "router_port_shutdown",
    "wrong_router_port_cabled",
    "router_wrong_ip_or_mask",
}

# Faults that target the server (cannot be paired together)
_SERVER_FAULTS = {
    "device_powered_off",
    "server_ip_or_gateway_fault",
    "duplicate_ip_conflict",
}


def _pick_random_lan_network(rng: random.Random) -> ipaddress.IPv4Network:
    """Pick a randomized private IPv4 subnet with prefix /24, /25, /26, or /27."""
    family = rng.choice(["10", "172", "192"])
    if family == "10":
        b2 = rng.choice([10, 20, 30, 40, 50, 80, 100])
        b3 = rng.choice([1, 5, 10, 15, 20, 35, 50, 75, 110])
        base = f"10.{b2}.{b3}.0/24"
    elif family == "172":
        b2 = rng.randint(16, 31)
        b3 = rng.choice([1, 4, 8, 12, 20, 30, 60, 90])
        base = f"172.{b2}.{b3}.0/24"
    else:
        b3 = rng.choice([1, 2, 10, 15, 25, 40, 55, 70, 88, 120, 200])
        base = f"192.168.{b3}.0/24"

    base_net = ipaddress.IPv4Network(base)
    prefix_len = rng.choice([24, 25, 26, 27])
    if prefix_len == 24:
        return base_net
    subnets = list(base_net.subnets(new_prefix=prefix_len))
    return rng.choice(subnets)


def _select_compatible_faults(rng: random.Random, k: int) -> list[str]:
    """Pick `k` distinct fault types without conflicting targets."""
    pool = list(ALL_LEVEL1_FAULT_TYPES)
    rng.shuffle(pool)
    chosen: list[str] = []
    for cand in pool:
        if len(chosen) >= k:
            break
        if cand in _ROUTER_UPLINK_FAULTS and any(c in _ROUTER_UPLINK_FAULTS for c in chosen):
            continue
        if cand in _SERVER_FAULTS and any(c in _SERVER_FAULTS for c in chosen):
            continue
        chosen.append(cand)
    return chosen


def _pt_to_canvas(pt_x: int, pt_y: int) -> tuple[int, int]:
    """Map Packet Tracer logical workspace coordinates (x in 180..830, y in 130..530)
    proportionally onto the NetDoctor Tkinter Topology Canvas (760 x 350).
    """
    cx = int(85 + (pt_x - 180) * 0.90)
    cy = int(42 + (pt_y - 130) * 0.67)
    return max(75, min(685, cx)), max(34, min(318, cy))


TOPOLOGY_ARCHETYPES: list[str] = [
    "left_to_right_pipeline",
    "mdf_idf_two_closet",
    "radial_star_office",
    "split_wing_east_west",
    "right_to_left_backoffice",
    "diagonal_corner_suite",
]


def _build_layout_positions(
    archetype: str, num_clients: int
) -> tuple[str, bool, dict[str, tuple[int, int]]]:
    """Return (archetype_label, has_second_switch, positions_map) in Packet Tracer coordinates."""
    pos: dict[str, tuple[int, int]] = {}

    if archetype == "left_to_right_pipeline":
        label = "Left-to-Right Enterprise Demarc Flow"
        has_sw2 = False
        pos["rtr"] = (190, 330)
        pos["sw1"] = (430, 330)
        pos["srv"] = (430, 140)
        # Clients stacked vertically along the right wing
        y_slots = (
            [220, 440]
            if num_clients == 2
            else [160, 330, 500]
            if num_clients == 3
            else [135, 265, 395, 525]
        )
        for i in range(num_clients):
            pos[f"c{i}"] = (740 + (45 if i % 2 == 1 else 0), y_slots[i])

    elif archetype == "mdf_idf_two_closet":
        label = "Two-Closet MDF + IDF Floorplan (2 Switches)"
        has_sw2 = True
        # Left Wing: MDF Room (Router + SW1 + Server + 1 Admin Workstation)
        pos["rtr"] = (200, 150)
        pos["sw1"] = (350, 310)
        pos["srv"] = (190, 480)
        pos["c0"] = (370, 510)
        # Right Wing: IDF Closet (SW2 + remaining floor workstations)
        pos["sw2"] = (590, 310)
        idf_slots = [(620, 140), (810, 260), (790, 480)]
        for i in range(1, num_clients):
            pos[f"c{i}"] = idf_slots[i - 1]

    elif archetype == "radial_star_office":
        label = "Central Wiring Closet Radial Star"
        has_sw2 = False
        pos["sw1"] = (500, 320)
        pos["rtr"] = (240, 150)
        pos["srv"] = (760, 150)
        radial_slots = [
            (200, 350),  # West pod
            (340, 515),  # South-West pod
            (660, 515),  # South-East pod
            (800, 350),  # East pod
        ]
        for i in range(num_clients):
            pos[f"c{i}"] = radial_slots[i]

    elif archetype == "split_wing_east_west":
        label = "Bottom Fiber Demarc + East/West Split Wings"
        has_sw2 = False
        pos["rtr"] = (500, 520)
        pos["sw1"] = (500, 330)
        pos["srv"] = (500, 140)
        wing_slots = [
            (210, 220),  # West Upper
            (790, 220),  # East Upper
            (210, 430),  # West Lower
            (790, 430),  # East Lower
        ]
        for i in range(num_clients):
            pos[f"c{i}"] = wing_slots[i]

    elif archetype == "right_to_left_backoffice":
        label = "Right-to-Left Back-Office Rack & Desk Pods"
        has_sw2 = False
        pos["rtr"] = (800, 175)
        pos["srv"] = (800, 485)
        pos["sw1"] = (580, 330)
        pod_slots = [
            (350, 155),
            (195, 255),
            (195, 415),
            (350, 515),
        ]
        for i in range(num_clients):
            pos[f"c{i}"] = pod_slots[i]

    else:  # diagonal_corner_suite
        label = "L-Shaped Corner Suite Floorplan"
        has_sw2 = False
        pos["rtr"] = (220, 510)
        pos["sw1"] = (430, 330)
        pos["srv"] = (205, 190)
        l_slots = [
            (460, 140),
            (710, 165),
            (780, 340),
            (700, 510),
        ]
        for i in range(num_clients):
            pos[f"c{i}"] = l_slots[i]

    return label, has_sw2, pos


def generate_level1_challenge(
    out_dir: str | Path,
    *,
    num_faults: int = 1,
    seed: int | None = None,
    fault_types: list[str] | None = None,
    archetype: str | None = None,
) -> ChallengeTicket:
    """Generate a Level 1 (CCNA v2.0 Tier 1 Helpdesk — Single LAN) faulty .pkt file and NOC Ticket.

    Randomizes:
    - Physical topology layout & floorplan archetype (6 real-world layouts, including 2-switch MDF+IDF)
    - Subnet prefix (/24, /25, /26, /27) and private block (10.x, 172.16-31.x, 192.168.x)
    - Gateway convention (First Usable Host vs. Last Usable Host)
    - Router model (2911, 1941, 2901)
    - Endpoint count (2 to 4 clients mixing PC-PT and Laptop-PT) + 1 Server-PT
    """
    rng = random.Random(seed)
    code, dept_name = rng.choice(_SITE_PERSONAS)
    net_obj = _pick_random_lan_network(rng)
    prefix_len = net_obj.prefixlen
    netmask = str(net_obj.netmask)
    subnet_cidr = str(net_obj)
    hosts = [str(ip) for ip in net_obj.hosts()]

    # Randomize router model, client count (2 to 4 clients + 1 server), and physical layout archetype
    rtr_model = rng.choice(["2911", "1941", "2901"])
    sw_model = "2960-24TT"
    num_clients = rng.choice([2, 3, 4])
    chosen_archetype = archetype if archetype in TOPOLOGY_ARCHETYPES else rng.choice(TOPOLOGY_ARCHETYPES)
    layout_label, has_sw2, pt_pos = _build_layout_positions(chosen_archetype, num_clients)

    # Randomize gateway convention: "first" (hosts[0]) or "last" (hosts[-1])
    gw_convention = rng.choice(["first", "last"])
    if gw_convention == "first":
        gw_ip = hosts[0]
        sw_ip = hosts[1]
        sw2_ip = hosts[2]
        srv_ip = hosts[-2]  # High usable address near end of subnet
        client_base_idx = 4
        gw_convention_note = f"First usable host ({gw_ip})"
    else:
        gw_ip = hosts[-1]
        sw_ip = hosts[0]
        sw2_ip = hosts[1]
        srv_ip = hosts[-3]  # High usable address near end of subnet
        client_base_idx = 3
        gw_convention_note = f"Last usable host ({gw_ip})"

    # Reserve spare unused IPs inside the subnet for realistic typo injection
    unused_inside_subnet = [
        hosts[-4],
        hosts[-5],
        hosts[-6],
        hosts[2] if gw_convention == "last" else hosts[3],
    ]

    rtr_name = f"{code}-R1"
    sw_name = f"{code}-SW1"
    sw2_name = f"{code}-SW2"
    srv_name = f"{code}-SRV1"

    # Build client specs (mixing PC-PT and Laptop-PT, across SW1 and optional SW2)
    client_specs: list[dict[str, str]] = []
    sw1_port_counter = 1
    sw2_port_counter = 1
    for i in range(1, num_clients + 1):
        is_laptop = (i == num_clients and num_clients >= 3 and rng.random() < 0.5)
        c_model = "Laptop-PT" if is_laptop else "PC-PT"
        c_prefix = "LT" if is_laptop else "PC"
        c_name = f"{code}-{c_prefix}{i}"
        c_ip = hosts[client_base_idx + i - 1]
        if has_sw2 and i >= 2:
            assigned_sw = sw2_name
            c_sw_port = f"FastEthernet0/{sw2_port_counter}"
            sw2_port_counter += 1
        else:
            assigned_sw = sw_name
            c_sw_port = f"FastEthernet0/{sw1_port_counter}"
            sw1_port_counter += 1
        client_specs.append(
            {
                "name": c_name,
                "model": c_model,
                "role": f"{'Laptop' if is_laptop else 'Workstation'} {i}",
                "ip": c_ip,
                "sw_name": assigned_sw,
                "sw_port": c_sw_port,
                "pos_key": f"c{i-1}",
            }
        )

    srv_sw_port = f"FastEthernet0/{sw1_port_counter}"
    pc_port_map = {c["name"]: (c["sw_name"], c["sw_port"], c["ip"]) for c in client_specs}

    # Golden (Intended) Network Blueprint
    device_rows = [
        BlueprintDeviceRow(
            device=rtr_name,
            model=rtr_model,
            role="Default Gateway Router",
            interface="GigabitEthernet0/0",
            expected_ip=gw_ip,
            expected_mask=netmask,
            expected_gateway="-",
            expected_dns="-",
            notes=f"LAN Gateway ({gw_convention_note}, UP / no shutdown)",
        ),
        BlueprintDeviceRow(
            device=sw_name,
            model=sw_model,
            role="MDF Core/Access Switch" if has_sw2 else "Access Switch",
            interface="Vlan1",
            expected_ip=sw_ip,
            expected_mask=netmask,
            expected_gateway=gw_ip,
            expected_dns="-",
            notes="Switch Management SVI (UP + ip default-gateway)",
        ),
    ]
    if has_sw2:
        device_rows.append(
            BlueprintDeviceRow(
                device=sw2_name,
                model=sw_model,
                role="IDF Expansion Switch",
                interface="Vlan1",
                expected_ip=sw2_ip,
                expected_mask=netmask,
                expected_gateway=gw_ip,
                expected_dns="-",
                notes="IDF Floor Switch Management SVI (VLAN 1)",
            )
        )
    for c in client_specs:
        device_rows.append(
            BlueprintDeviceRow(
                device=c["name"],
                model=c["model"],
                role=c["role"],
                interface="FastEthernet0",
                expected_ip=c["ip"],
                expected_mask=netmask,
                expected_gateway=gw_ip,
                expected_dns=srv_ip,
                notes=f"Connected to {c['sw_name']} {c['sw_port']} ({subnet_cidr})",
            )
        )
    device_rows.append(
        BlueprintDeviceRow(
            device=srv_name,
            model="Server-PT",
            role="Internal Web/DNS Server",
            interface="FastEthernet0",
            expected_ip=srv_ip,
            expected_mask=netmask,
            expected_gateway=gw_ip,
            expected_dns=srv_ip,
            notes="Powered ON, Static IPv4 Server",
        )
    )

    link_rows = [
        BlueprintLinkRow(
            dev_a=rtr_name,
            port_a="GigabitEthernet0/0",
            dev_b=sw_name,
            port_b="GigabitEthernet0/1",
            cable_type="Copper Straight-Through",
            mode_or_vlan="Uplink (VLAN 1, Auto)",
        ),
    ]
    if has_sw2:
        link_rows.append(
            BlueprintLinkRow(
                dev_a=sw_name,
                port_a="GigabitEthernet0/2",
                dev_b=sw2_name,
                port_b="GigabitEthernet0/1",
                cable_type="Copper Cross-Over / Auto-MDIX",
                mode_or_vlan="MDF-to-IDF Uplink (VLAN 1, Auto)",
            )
        )
    for c in client_specs:
        link_rows.append(
            BlueprintLinkRow(
                dev_a=c["sw_name"],
                port_a=c["sw_port"],
                dev_b=c["name"],
                port_b="FastEthernet0",
                cable_type="Copper Straight-Through",
                mode_or_vlan="Access (VLAN 1, Auto)",
            )
        )
    link_rows.append(
        BlueprintLinkRow(
            dev_a=sw_name,
            port_a=srv_sw_port,
            dev_b=srv_name,
            port_b="FastEthernet0",
            cable_type="Copper Straight-Through",
            mode_or_vlan="Access (VLAN 1, Auto)",
        )
    )

    # Build golden baseline network with realistic floorplan coordinates
    net = SimpleNetwork()
    rx, ry = pt_pos["rtr"]
    sx, sy = pt_pos["sw1"]
    net.add_router(rtr_name, model=rtr_model, x=rx, y=ry)
    net.add_switch(
        sw_name,
        model=sw_model,
        x=sx,
        y=sy,
        management_ip=f"{sw_ip}/{prefix_len}",
        default_gateway=gw_ip,
    )
    if has_sw2:
        s2x, s2y = pt_pos["sw2"]
        net.add_switch(
            sw2_name,
            model=sw_model,
            x=s2x,
            y=s2y,
            management_ip=f"{sw2_ip}/{prefix_len}",
            default_gateway=gw_ip,
        )

    for c in client_specs:
        cx, cy = pt_pos[c["pos_key"]]
        net.add_device(
            c["name"],
            c["model"],
            ip=f"{c['ip']}/{prefix_len}",
            gateway=gw_ip,
            dns=srv_ip,
            x=cx,
            y=cy,
        )

    srv_x, srv_y = pt_pos["srv"]
    net.add_server(
        srv_name,
        ip=f"{srv_ip}/{prefix_len}",
        gateway=gw_ip,
        dns=srv_ip,
        x=srv_x,
        y=srv_y,
    )

    net.connect(
        rtr_name,
        sw_name,
        port_a="GigabitEthernet0/0",
        port_b="GigabitEthernet0/1",
        ip_a=f"{gw_ip}/{prefix_len}",
    )
    if has_sw2:
        net.connect(
            sw_name,
            sw2_name,
            port_a="GigabitEthernet0/2",
            port_b="GigabitEthernet0/1",
        )
    for c in client_specs:
        net.connect(c["sw_name"], c["name"], port_a=c["sw_port"], port_b="FastEthernet0")
    net.connect(sw_name, srv_name, port_a=srv_sw_port, port_b="FastEthernet0")

    if fault_types:
        chosen_types = list(fault_types)
    else:
        chosen_types = _select_compatible_faults(rng, max(1, min(num_faults, 2)))

    host_targets = [c["name"] for c in client_specs]
    rng.shuffle(host_targets)

    injected_faults: list[FaultRecord] = []
    post_xml_mutations: list[Callable[[ET.Element], None]] = []

    for idx, ftype in enumerate(chosen_types):
        target_pc = host_targets[idx % len(host_targets)]
        target_dev = net.devices[target_pc]
        sw_for_pc, sw_port_for_pc, expected_pc_ip = pc_port_map[target_pc]

        # ------------------------------------------------------------------
        # 1. Host Wrong Subnet IP (CCNA Obj 1.6 / 1.11)
        # ------------------------------------------------------------------
        if ftype == "host_wrong_subnet_ip":
            parts = expected_pc_ip.split(".")
            wrong_third = str((int(parts[2]) + 17) % 250 or 99)
            bad_ip = f"{parts[0]}.{parts[1]}.{wrong_third}.{parts[3]}"
            target_dev.ip = bad_ip
            injected_faults.append(
                FaultRecord(
                    fault_id=f"F{idx+1}_WRONG_SUBNET_IP",
                    title=f"Wrong Subnet IPv4 Address on {target_pc}",
                    category="CCNA 1.6 / 1.11 — Host IPv4 Addressing",
                    device=target_pc,
                    interface="FastEthernet0",
                    symptom=(
                        f"User on {target_pc} reports complete inability to reach the internal server "
                        f"({srv_name} at {srv_ip}) or the default gateway ({gw_ip})."
                    ),
                    expected_state=f"IP: {expected_pc_ip}, Mask: {netmask} (/{prefix_len})",
                    faulty_state=f"IP: {bad_ip}, Mask: {netmask}",
                    hints=[
                        f"Hint 1 (CCNA 1.11): Verify IPv4 client parameters against subnet {subnet_cidr}.",
                        f"Hint 2 (Device): Inspect the IP configuration on '{target_pc}'.",
                        f"Hint 3 (Exact Issue): '{target_pc}' has IP {bad_ip} (outside {subnet_cidr}). Change it to {expected_pc_ip}.",
                    ],
                    explanation=(
                        f"{target_pc} was configured with IP address {bad_ip}/{prefix_len} instead of {expected_pc_ip}/{prefix_len}. "
                        f"Because {bad_ip} does not belong to {subnet_cidr}, local ARP and gateway communication fail."
                    ),
                    fix_steps=[
                        f"1. In Packet Tracer, click on '{target_pc}' -> 'Desktop' -> 'IP Configuration'.",
                        f"2. Change the IPv4 Address from '{bad_ip}' to '{expected_pc_ip}'.",
                        "3. Save the .pkt file (Ctrl+S) and click 'Upload / Verify .pkt' in NetDoctor.",
                    ],
                    verify_spec={
                        "type": "end_device_ip",
                        "device": target_pc,
                        "expected_ip": expected_pc_ip,
                        "expected_mask": netmask,
                    },
                )
            )

        # ------------------------------------------------------------------
        # 2. Host Wrong Default Gateway (CCNA Obj 1.11)
        # ------------------------------------------------------------------
        elif ftype == "host_wrong_default_gateway":
            bad_gw = unused_inside_subnet[0]
            target_dev.gateway = bad_gw
            injected_faults.append(
                FaultRecord(
                    fault_id=f"F{idx+1}_WRONG_GATEWAY",
                    title=f"Incorrect Default Gateway on {target_pc}",
                    category="CCNA 1.11 — Client Default Gateway",
                    device=target_pc,
                    interface="FastEthernet0",
                    symptom=(
                        f"Host {target_pc} can ping local peers on {subnet_cidr}, but cannot route "
                        f"off-network traffic through {rtr_name} due to an invalid Default Gateway."
                    ),
                    expected_state=f"Default Gateway: {gw_ip} ({gw_convention_note})",
                    faulty_state=f"Default Gateway: {bad_gw}",
                    hints=[
                        "Hint 1 (CCNA 1.11): One host can communicate on the local switch but has a wrong Default Gateway.",
                        f"Hint 2 (Device): Compare the Default Gateway on '{target_pc}' against the Network Blueprint.",
                        f"Hint 3 (Exact Issue): '{target_pc}' has Default Gateway {bad_gw} instead of {gw_ip}.",
                    ],
                    explanation=(
                        f"{target_pc} had its Default Gateway set to {bad_gw}. "
                        f"On this subnet ({subnet_cidr}), router {rtr_name}'s GigabitEthernet0/0 interface is at {gw_ip} ({gw_convention_note})."
                    ),
                    fix_steps=[
                        f"1. In Packet Tracer, click on '{target_pc}' -> 'Desktop' -> 'IP Configuration'.",
                        f"2. Change 'Default Gateway' from '{bad_gw}' to '{gw_ip}'.",
                        "3. Save the .pkt file (Ctrl+S) and verify.",
                    ],
                    verify_spec={
                        "type": "end_device_gateway",
                        "device": target_pc,
                        "expected_gateway": gw_ip,
                    },
                )
            )

        # ------------------------------------------------------------------
        # 3. Host Restrictive Subnet Mask (CCNA Obj 1.6)
        # ------------------------------------------------------------------
        elif ftype == "host_wrong_subnet_mask":
            # Use /29 (255.255.255.248, 6 hosts) so srv_ip (near top of subnet) is always cut off!
            bad_mask = "255.255.255.248"
            bad_prefix = 29
            target_dev.netmask = bad_mask
            injected_faults.append(
                FaultRecord(
                    fault_id=f"F{idx+1}_WRONG_MASK",
                    title=f"Incorrect Subnet Mask (/{bad_prefix}) on {target_pc}",
                    category="CCNA 1.6 — IPv4 Subnetting & Netmask",
                    device=target_pc,
                    interface="FastEthernet0",
                    symptom=(
                        f"{target_pc} ({expected_pc_ip}) has a mismatched subnet mask ({bad_mask}), "
                        f"causing it to treat server {srv_name} ({srv_ip}) as a remote network."
                    ),
                    expected_state=f"Subnet Mask: {netmask} (/{prefix_len})",
                    faulty_state=f"Subnet Mask: {bad_mask} (/{bad_prefix})",
                    hints=[
                        f"Hint 1 (CCNA 1.6): Check that all hosts on {subnet_cidr} use the /{prefix_len} subnet mask ({netmask}).",
                        f"Hint 2 (Device): Inspect the Subnet Mask configured on '{target_pc}'.",
                        f"Hint 3 (Exact Issue): '{target_pc}' has Subnet Mask {bad_mask} (/{bad_prefix}) instead of {netmask} (/{prefix_len}).",
                    ],
                    explanation=(
                        f"The LAN is subnetted as {subnet_cidr} (mask {netmask}), but {target_pc} was configured "
                        f"with a /{bad_prefix} mask ({bad_mask}), shrinking its perceived local broadcast domain to just 6 hosts."
                    ),
                    fix_steps=[
                        f"1. In Packet Tracer, click on '{target_pc}' -> 'Desktop' -> 'IP Configuration'.",
                        f"2. Change 'Subnet Mask' from '{bad_mask}' to '{netmask}'.",
                        "3. Save the .pkt file (Ctrl+S) and verify.",
                    ],
                    verify_spec={
                        "type": "end_device_mask",
                        "device": target_pc,
                        "expected_mask": netmask,
                    },
                )
            )

        # ------------------------------------------------------------------
        # 4. Duplicate IPv4 Conflict (CCNA Obj 1.6 / 1.11)
        # ------------------------------------------------------------------
        elif ftype == "duplicate_ip_conflict":
            target_dev.ip = srv_ip
            injected_faults.append(
                FaultRecord(
                    fault_id=f"F{idx+1}_DUPLICATE_IP",
                    title=f"Duplicate IPv4 Address Conflict ({srv_ip}) on {target_pc}",
                    category="CCNA 1.6 — Duplicate IPv4 Address Conflict",
                    device=target_pc,
                    interface="FastEthernet0",
                    symptom=(
                        f"Users report intermittent ARP/connectivity failures to server {srv_name} ({srv_ip}), "
                        f"and host {target_pc} experiences address conflict errors."
                    ),
                    expected_state=f"{target_pc} IP: {expected_pc_ip} (Unique)",
                    faulty_state=f"{target_pc} IP: {srv_ip} (Collides with {srv_name}!)",
                    hints=[
                        f"Hint 1 (CCNA 1.6): Two hosts on {subnet_cidr} are configured with the exact same IPv4 address ({srv_ip}).",
                        f"Hint 2 (Device): Check the IPv4 address on '{target_pc}' compared to '{srv_name}'.",
                        f"Hint 3 (Exact Issue): '{target_pc}' is set to {srv_ip}. Change it to its assigned address {expected_pc_ip}.",
                    ],
                    explanation=(
                        f"{target_pc} was assigned {srv_ip}, colliding with {srv_name}. "
                        f"Duplicate IPs corrupt ARP tables across the broadcast domain."
                    ),
                    fix_steps=[
                        f"1. In Packet Tracer, open '{target_pc}' -> 'Desktop' -> 'IP Configuration'.",
                        f"2. Change its IPv4 Address from '{srv_ip}' to '{expected_pc_ip}'.",
                        "3. Save the .pkt file (Ctrl+S) and verify.",
                    ],
                    verify_spec={
                        "type": "end_device_ip",
                        "device": target_pc,
                        "expected_ip": expected_pc_ip,
                        "expected_mask": netmask,
                    },
                )
            )

        # ------------------------------------------------------------------
        # 5. Router Gateway Interface Shutdown (CCNA Obj 1.4 / 1.6)
        # ------------------------------------------------------------------
        elif ftype == "router_port_shutdown":
            net.devices[rtr_name].ports["GigabitEthernet0/0"].shutdown = True
            injected_faults.append(
                FaultRecord(
                    fault_id=f"F{idx+1}_ROUTER_SHUTDOWN",
                    title=f"Router Gateway Interface Administratively Down on {rtr_name}",
                    category="CCNA 1.4 — Interface Administrative State",
                    device=rtr_name,
                    interface="GigabitEthernet0/0",
                    symptom=(
                        f"Hosts can ping each other and {srv_name} through {sw_name}, "
                        f"but NO host can ping Default Gateway {gw_ip} and the link to {rtr_name} is red."
                    ),
                    expected_state=f"{rtr_name} GigabitEthernet0/0: UP (no shutdown)",
                    faulty_state=f"{rtr_name} GigabitEthernet0/0: Administratively DOWN (shutdown)",
                    hints=[
                        "Hint 1 (CCNA 1.4): Check the physical link lights between the switch and the default gateway router.",
                        f"Hint 2 (Device): Run 'show ip interface brief' on router '{rtr_name}'.",
                        f"Hint 3 (Exact Issue): Interface GigabitEthernet0/0 on '{rtr_name}' is administratively down. Issue 'no shutdown'.",
                    ],
                    explanation=(
                        f"Router {rtr_name}'s LAN interface (GigabitEthernet0/0) has IP {gw_ip}/{prefix_len} configured, "
                        f"but is in 'administratively down' ('shutdown') state."
                    ),
                    fix_steps=[
                        f"1. In Packet Tracer, open router '{rtr_name}' -> 'CLI' tab.",
                        "2. Enable the interface:\n"
                        "     enable\n"
                        "     configure terminal\n"
                        "     interface GigabitEthernet0/0\n"
                        "     no shutdown\n"
                        "     end\n"
                        "     write memory",
                        "3. Save the .pkt file (Ctrl+S) and verify.",
                    ],
                    verify_spec={
                        "type": "router_port_up",
                        "device": rtr_name,
                        "interface": "GigabitEthernet0/0",
                        "expected_ip": gw_ip,
                    },
                )
            )

        # ------------------------------------------------------------------
        # 6. Router Uplink Cabled to Wrong Port (CCNA Obj 1.4 / 1.5)
        # ------------------------------------------------------------------
        elif ftype == "wrong_router_port_cabled":
            for lk in net.links:
                if lk.dev_a == rtr_name and lk.port_a == "GigabitEthernet0/0":
                    lk.port_a = "GigabitEthernet0/1"
            injected_faults.append(
                FaultRecord(
                    fault_id=f"F{idx+1}_WRONG_ROUTER_PORT",
                    title=f"Uplink Cable Plugged into Wrong Interface on {rtr_name}",
                    category="CCNA 1.5 — Physical Interface Cabling",
                    device=rtr_name,
                    interface="GigabitEthernet0/0 vs GigabitEthernet0/1",
                    symptom=(
                        f"The uplink between {sw_name} and {rtr_name} stays down even though "
                        f"GigabitEthernet0/0 on {rtr_name} is configured with {gw_ip}/{prefix_len} and 'no shutdown'."
                    ),
                    expected_state=f"Cable connected to {rtr_name} GigabitEthernet0/0",
                    faulty_state=f"Cable plugged into {rtr_name} GigabitEthernet0/1 (unconfigured port)",
                    hints=[
                        "Hint 1 (CCNA 1.5): Compare 'show ip interface brief' on the router against the physical cable attachment.",
                        f"Hint 2 (Device): Inspect which port on '{rtr_name}' the copper cable from '{sw_name}' is plugged into.",
                        f"Hint 3 (Exact Issue): The cable is plugged into '{rtr_name}' GigabitEthernet0/1 instead of GigabitEthernet0/0.",
                    ],
                    explanation=(
                        f"{rtr_name} has its LAN gateway IP ({gw_ip}/{prefix_len}) configured on GigabitEthernet0/0, "
                        f"but the patch cable from {sw_name} was physically plugged into GigabitEthernet0/1."
                    ),
                    fix_steps=[
                        f"1. In Packet Tracer, move the copper cable on '{rtr_name}' from GigabitEthernet0/1 to GigabitEthernet0/0.",
                        "2. Save the .pkt file (Ctrl+S) and verify.",
                    ],
                    verify_spec={
                        "type": "router_cabled_port_matches_ip",
                        "device": rtr_name,
                        "peer_device": sw_name,
                        "expected_port": "GigabitEthernet0/0",
                        "expected_ip": gw_ip,
                    },
                )
            )

        # ------------------------------------------------------------------
        # 7. Device Physically Powered Off (CCNA Obj 1.1 / Layer 1)
        # ------------------------------------------------------------------
        elif ftype == "device_powered_off":
            net.devices[srv_name].power = False
            injected_faults.append(
                FaultRecord(
                    fault_id=f"F{idx+1}_DEVICE_POWER_OFF",
                    title=f"Server {srv_name} Physically Powered Off",
                    category="CCNA 1.1 / Layer 1 — Physical Device Power",
                    device=srv_name,
                    interface="Power Supply Switch",
                    symptom=(
                        f"All hosts can ping each other and the Default Gateway ({gw_ip}), "
                        f"but internal server {srv_name} ({srv_ip}) is completely offline and its switch link light is red."
                    ),
                    expected_state=f"{srv_name} Power: ON (<POWER>true</POWER>)",
                    faulty_state=f"{srv_name} Power: OFF (<POWER>false</POWER>)",
                    hints=[
                        f"Hint 1 (Layer 1): Check the link light between '{sw_name}' {srv_sw_port} and '{srv_name}'.",
                        f"Hint 2 (Device): Open '{srv_name}' and try viewing its Desktop/Services tab — Packet Tracer will alert you if power is off.",
                        f"Hint 3 (Exact Issue): '{srv_name}' is switched OFF! Open its 'Physical' tab and click the power button to turn it on.",
                    ],
                    explanation=(
                        f"The physical power switch on {srv_name} was turned off, keeping its NIC and services down."
                    ),
                    fix_steps=[
                        f"1. In Packet Tracer, click on server '{srv_name}'.",
                        "2. On the 'Physical' tab, zoom in on the chassis power button and click it so the green power LED illuminates.",
                        "3. Save the .pkt file (Ctrl+S) and verify.",
                    ],
                    verify_spec={
                        "type": "device_powered_on",
                        "device": srv_name,
                    },
                )
            )

        # ------------------------------------------------------------------
        # 8. Unplugged / Missing Patch Cable (CCNA Obj 1.5)
        # ------------------------------------------------------------------
        elif ftype == "missing_patch_cable":
            net.links = [
                lk
                for lk in net.links
                if not (lk.dev_a == sw_for_pc and lk.dev_b == target_pc)
            ]
            injected_faults.append(
                FaultRecord(
                    fault_id=f"F{idx+1}_MISSING_CABLE",
                    title=f"Disconnected Copper Patch Cable for {target_pc}",
                    category="CCNA 1.5 — Copper Ethernet Cabling",
                    device=target_pc,
                    interface=f"FastEthernet0 <-> {sw_for_pc} {sw_port_for_pc}",
                    symptom=(
                        f"Host {target_pc} shows 'No Link / Unplugged' and cannot reach any host on {subnet_cidr}."
                    ),
                    expected_state=f"Copper Straight-Through cable between {target_pc} FastEthernet0 and {sw_for_pc} {sw_port_for_pc}",
                    faulty_state=f"No physical cable attached to {target_pc}",
                    hints=[
                        "Hint 1 (CCNA 1.5): Visually inspect the workspace topology for a host missing its Ethernet cable.",
                        f"Hint 2 (Device): Look at '{target_pc}' and check the Expected Cabling tab in the Blueprint.",
                        f"Hint 3 (Exact Issue): Connect '{target_pc}' FastEthernet0 to '{sw_for_pc}' {sw_port_for_pc} using a Copper Straight-Through cable.",
                    ],
                    explanation=(
                        f"A host-to-switch connection (MDI-X to MDI) requires a Copper Straight-Through patch cable "
                        f"between {target_pc} FastEthernet0 and {sw_for_pc} {sw_port_for_pc}."
                    ),
                    fix_steps=[
                        "1. In Packet Tracer, click 'Connections' (lightning bolt icon) -> select 'Copper Straight-Through' (solid black line).",
                        f"2. Click '{target_pc}' -> select 'FastEthernet0'.",
                        f"3. Click '{sw_for_pc}' -> select '{sw_port_for_pc}'.",
                        "4. Save the .pkt file (Ctrl+S) and verify.",
                    ],
                    verify_spec={
                        "type": "link_present",
                        "device": target_pc,
                        "device_port": "FastEthernet0",
                        "peer_device": sw_for_pc,
                        "expected_peer_port": sw_port_for_pc,
                    },
                )
            )

        # ------------------------------------------------------------------
        # 9. Workstation NIC Adapter Disabled (CCNA Obj 1.4 / 1.11)
        # ------------------------------------------------------------------
        elif ftype == "host_nic_disabled":
            def _disable_nic(root_el: ET.Element, pc_name: str = target_pc) -> None:
                for d in root_el.findall(".//NETWORK/DEVICES/DEVICE"):
                    if (d.findtext("ENGINE/NAME") or "").strip() == pc_name:
                        pw = d.find(".//PORT/POWER")
                        if pw is not None:
                            pw.text = "false"

            post_xml_mutations.append(_disable_nic)
            injected_faults.append(
                FaultRecord(
                    fault_id=f"F{idx+1}_HOST_NIC_DISABLED",
                    title=f"Network Adapter (FastEthernet0) Disabled on {target_pc}",
                    category="CCNA 1.4 — Interface Status",
                    device=target_pc,
                    interface="FastEthernet0",
                    symptom=(
                        f"The cable between {target_pc} and {sw_for_pc} {sw_port_for_pc} is plugged in and the switch port "
                        f"is 'no shutdown', yet the link light on {target_pc} remains red."
                    ),
                    expected_state=f"{target_pc} FastEthernet0 Port Status: ON (<PORT><POWER>true</POWER>)",
                    faulty_state=f"{target_pc} FastEthernet0 Port Status: OFF (<PORT><POWER>false</POWER>)",
                    hints=[
                        f"Hint 1 (CCNA 1.4): The switch port is enabled, so why is the link to '{target_pc}' still down?",
                        f"Hint 2 (Device): Open '{target_pc}' -> 'Config' tab -> 'FastEthernet0'.",
                        f"Hint 3 (Exact Issue): On '{target_pc}', the 'Port Status: On' checkbox for FastEthernet0 is unchecked!",
                    ],
                    explanation=(
                        f"Even though {sw_for_pc} {sw_port_for_pc} is up and the IP address on {target_pc} is valid, "
                        f"the host's FastEthernet0 NIC had its Port Status turned off."
                    ),
                    fix_steps=[
                        f"1. In Packet Tracer, click on '{target_pc}'.",
                        "2. Open the 'Config' tab -> select 'FastEthernet0' under INTERFACE.",
                        "3. Check the 'Port Status: On' checkbox.",
                        "4. Save the .pkt file (Ctrl+S) and verify.",
                    ],
                    verify_spec={
                        "type": "end_device_nic_enabled",
                        "device": target_pc,
                    },
                )
            )

        # ------------------------------------------------------------------
        # 10. Speed / Duplex Mismatch (CCNA Obj 1.4b)
        # ------------------------------------------------------------------
        elif ftype == "speed_duplex_mismatch":
            net.add_ios_commands(
                sw_for_pc,
                [
                    f"interface {sw_port_for_pc}",
                    " speed 100",
                    " duplex full",
                ],
            )

            def _force_pc_10_half(root_el: ET.Element, pc_name: str = target_pc) -> None:
                for d in root_el.findall(".//NETWORK/DEVICES/DEVICE"):
                    if (d.findtext("ENGINE/NAME") or "").strip() == pc_name:
                        port_el = d.find(".//PORT")
                        if port_el is not None:
                            for tag, val in (
                                ("AUTONEGOTIATEBANDWIDTH", "false"),
                                ("AUTONEGOTIATEDUPLEX", "false"),
                                ("BANDWIDTH", "10000"),
                                ("FULLDUPLEX", "false"),
                            ):
                                e = port_el.find(tag)
                                if e is None:
                                    e = ET.SubElement(port_el, tag)
                                e.text = val

            post_xml_mutations.append(_force_pc_10_half)
            injected_faults.append(
                FaultRecord(
                    fault_id=f"F{idx+1}_SPEED_DUPLEX_MISMATCH",
                    title=f"Speed / Duplex Mismatch Between {sw_for_pc} ({sw_port_for_pc}) and {target_pc}",
                    category="CCNA 1.4b — Speed & Duplex Mismatch",
                    device=target_pc,
                    interface=f"FastEthernet0 <-> {sw_for_pc} {sw_port_for_pc}",
                    symptom=(
                        f"Link between {sw_for_pc} ({sw_port_for_pc}) and {target_pc} fails to come up despite "
                        f"valid cabling and both ends being enabled."
                    ),
                    expected_state="Matching Speed/Duplex (Auto-Negotiate ON or both 100 Mbps / Full Duplex)",
                    faulty_state=f"{sw_for_pc} {sw_port_for_pc} forced to 100/Full, while {target_pc} NIC forced to 10 Mbps / Half Duplex",
                    hints=[
                        "Hint 1 (CCNA 1.4b): Both ends of a link are enabled, yet Layer 1/2 stays down — check speed and duplex settings.",
                        f"Hint 2 (Device): Check 'Config -> FastEthernet0' on '{target_pc}' and 'show running-config interface {sw_port_for_pc}' on '{sw_for_pc}'.",
                        f"Hint 3 (Exact Issue): '{target_pc}' FastEthernet0 has Bandwidth=10 Mbps & Duplex=Half while '{sw_for_pc}' {sw_port_for_pc} is 100/Full. Re-enable Auto on '{target_pc}' (or match 100/Full).",
                    ],
                    explanation=(
                        f"Per CCNA Objective 1.4b, hardcoding one end of a FastEthernet link to 100 Mbps / Full Duplex "
                        f"({sw_for_pc} {sw_port_for_pc}) while the peer ({target_pc}) is hardcoded to 10 Mbps / Half Duplex "
                        f"prevents link synchronization."
                    ),
                    fix_steps=[
                        f"1. In Packet Tracer, click '{target_pc}' -> 'Config' tab -> 'FastEthernet0'.",
                        "2. Check 'Auto' for both Bandwidth and Duplex (or set Bandwidth to 100 Mbps and Duplex to Full Duplex).",
                        "3. Save the .pkt file (Ctrl+S) and verify.",
                    ],
                    verify_spec={
                        "type": "speed_duplex_match",
                        "device": target_pc,
                        "switch_device": sw_for_pc,
                        "switch_port": sw_port_for_pc,
                    },
                )
            )

        # ------------------------------------------------------------------
        # 11. Switch Access Port Administratively Down (CCNA Obj 1.4 / 2.1)
        # ------------------------------------------------------------------
        elif ftype == "switch_port_shutdown":
            net.devices[sw_for_pc].ports[sw_port_for_pc].shutdown = True
            injected_faults.append(
                FaultRecord(
                    fault_id=f"F{idx+1}_SWITCH_PORT_SHUTDOWN",
                    title=f"Switch Access Port {sw_port_for_pc} Administratively Down on {sw_for_pc}",
                    category="CCNA 2.1 — Switch Port Administrative State",
                    device=sw_for_pc,
                    interface=sw_port_for_pc,
                    symptom=(
                        f"Only host {target_pc} has a red link light and no network access; "
                        f"all other hosts and {srv_name} work normally."
                    ),
                    expected_state=f"{sw_for_pc} {sw_port_for_pc}: UP (no shutdown)",
                    faulty_state=f"{sw_for_pc} {sw_port_for_pc}: Administratively DOWN (shutdown)",
                    hints=[
                        f"Hint 1 (CCNA 2.1): Only '{target_pc}' has a red link light. Check the switch port it connects to.",
                        f"Hint 2 (Device): Run 'show ip interface brief' or 'show interfaces status' on switch '{sw_for_pc}'.",
                        f"Hint 3 (Exact Issue): Port {sw_port_for_pc} on '{sw_for_pc}' is administratively shut down. Issue 'no shutdown'.",
                    ],
                    explanation=(
                        f"On {sw_for_pc}, access port {sw_port_for_pc} (connected to {target_pc}) was left in 'shutdown' state."
                    ),
                    fix_steps=[
                        f"1. In Packet Tracer, open switch '{sw_for_pc}' -> 'CLI' tab.",
                        f"2. Enable the switch port:\n"
                        f"     enable\n"
                        f"     configure terminal\n"
                        f"     interface {sw_port_for_pc}\n"
                        f"     no shutdown\n"
                        f"     end\n"
                        f"     write memory",
                        "3. Save the .pkt file (Ctrl+S) and verify.",
                    ],
                    verify_spec={
                        "type": "switch_port_up",
                        "device": sw_for_pc,
                        "interface": sw_port_for_pc,
                    },
                )
            )

        # ------------------------------------------------------------------
        # 12. Switch Management SVI & Default Gateway Fault (CCNA Obj 2.1)
        # ------------------------------------------------------------------
        elif ftype == "switch_mgmt_fault":
            bad_mgmt_ip = unused_inside_subnet[1]
            bad_sw_gw = unused_inside_subnet[0]
            net.devices[sw_name].management_ip = bad_mgmt_ip
            net.devices[sw_name].default_gateway = bad_sw_gw
            net.add_ios_commands(sw_name, ["interface Vlan1", " shutdown"])
            injected_faults.append(
                FaultRecord(
                    fault_id=f"F{idx+1}_SWITCH_MGMT_SVI",
                    title=f"Switch Management SVI (Vlan1) Down & Misconfigured on {sw_name}",
                    category="CCNA 2.1 — Switch Management SVI & Default Gateway",
                    device=sw_name,
                    interface="Vlan1",
                    symptom=(
                        f"All hosts can ping each other, {srv_name}, and {rtr_name}, "
                        f"but NOC engineers cannot ping or manage switch {sw_name} at its assigned IP ({sw_ip})."
                    ),
                    expected_state=f"{sw_name} Vlan1: IP {sw_ip} {netmask}, UP (no shutdown), ip default-gateway {gw_ip}",
                    faulty_state=f"{sw_name} Vlan1: IP {bad_mgmt_ip}, DOWN (shutdown), ip default-gateway {bad_sw_gw}",
                    hints=[
                        "Hint 1 (CCNA 2.1): Layer 2 switching works even when a switch's management SVI is broken. Check Vlan1 on the switch.",
                        f"Hint 2 (Device): Run 'show running-config' on '{sw_name}' and inspect 'interface Vlan1' and 'ip default-gateway'.",
                        f"Hint 3 (Exact Issue): Set '{sw_name}' interface Vlan1 to 'ip address {sw_ip} {netmask}' + 'no shutdown', and set 'ip default-gateway {gw_ip}'.",
                    ],
                    explanation=(
                        f"A Layer 2 switch forwards frames in hardware regardless of its SVI state, but remote management "
                        f"requires 'interface Vlan1' to have the correct IP ({sw_ip}/{prefix_len}), 'no shutdown', and 'ip default-gateway {gw_ip}'."
                    ),
                    fix_steps=[
                        f"1. In Packet Tracer, open switch '{sw_name}' -> 'CLI' tab.",
                        f"2. Run:\n"
                        f"     enable\n"
                        f"     configure terminal\n"
                        f"     ip default-gateway {gw_ip}\n"
                        f"     interface Vlan1\n"
                        f"     ip address {sw_ip} {netmask}\n"
                        f"     no shutdown\n"
                        f"     end\n"
                        f"     write memory",
                        "3. Save the .pkt file (Ctrl+S) and verify.",
                    ],
                    verify_spec={
                        "type": "switch_mgmt_svi",
                        "device": sw_name,
                        "expected_ip": sw_ip,
                        "expected_mask": netmask,
                        "expected_gateway": gw_ip,
                    },
                )
            )

        # ------------------------------------------------------------------
        # 13. Host Left on DHCP with No DHCP Server / APIPA (CCNA Obj 1.11 / 4.6)
        # ------------------------------------------------------------------
        elif ftype == "host_dhcp_apipa":
            target_dev.dhcp = True
            target_dev.ip = None
            target_dev.netmask = None
            target_dev.gateway = None
            injected_faults.append(
                FaultRecord(
                    fault_id=f"F{idx+1}_HOST_DHCP_APIPA",
                    title=f"Host {target_pc} Set to DHCP on a Static LAN (169.254.x.x APIPA)",
                    category="CCNA 1.11 / 4.6 — Static vs. DHCP Addressing (APIPA)",
                    device=target_pc,
                    interface="FastEthernet0",
                    symptom=(
                        f"Host {target_pc} fails to reach any network resource and displays "
                        f"a self-assigned 169.254.x.x / 255.255.0.0 address."
                    ),
                    expected_state=f"Static IPv4: {expected_pc_ip} / {netmask}, Gateway: {gw_ip}",
                    faulty_state="DHCP Enabled (No DHCP server on LAN -> 169.254.x.x APIPA)",
                    hints=[
                        "Hint 1 (CCNA 4.6): A 169.254.x.x/16 address means a host is requesting DHCP where no DHCP server exists.",
                        f"Hint 2 (Device): Open 'Desktop -> IP Configuration' on '{target_pc}'.",
                        f"Hint 3 (Exact Issue): Switch '{target_pc}' from 'DHCP' to 'Static' and configure IP {expected_pc_ip}, Mask {netmask}, Gateway {gw_ip}.",
                    ],
                    explanation=(
                        f"Because this branch LAN uses static addressing and has no DHCP server configured, "
                        f"leaving {target_pc} in DHCP mode causes it to fall back to Link-Local APIPA (169.254.0.0/16)."
                    ),
                    fix_steps=[
                        f"1. In Packet Tracer, click '{target_pc}' -> 'Desktop' -> 'IP Configuration'.",
                        "2. Select the 'Static' radio button.",
                        f"3. Enter IPv4 Address: {expected_pc_ip}, Subnet Mask: {netmask}, Default Gateway: {gw_ip}, DNS Server: {srv_ip}.",
                        "4. Save the .pkt file (Ctrl+S) and verify.",
                    ],
                    verify_spec={
                        "type": "end_device_static_not_dhcp",
                        "device": target_pc,
                        "expected_ip": expected_pc_ip,
                        "expected_mask": netmask,
                        "expected_gateway": gw_ip,
                    },
                )
            )

        # ------------------------------------------------------------------
        # 14. Router Gateway IP / Mask Typo (CCNA Obj 1.6)
        # ------------------------------------------------------------------
        elif ftype == "router_wrong_ip_or_mask":
            bad_rtr_ip = unused_inside_subnet[2]
            net.devices[rtr_name].ports["GigabitEthernet0/0"].ip = bad_rtr_ip
            injected_faults.append(
                FaultRecord(
                    fault_id=f"F{idx+1}_ROUTER_WRONG_IP",
                    title=f"Wrong IPv4 Address Configured on Router {rtr_name} Gateway Interface",
                    category="CCNA 1.6 — Router Interface IPv4 Configuration",
                    device=rtr_name,
                    interface="GigabitEthernet0/0",
                    symptom=(
                        f"All hosts and {srv_name} have green link lights and can ping each other, "
                        f"but NONE of them can ping the Default Gateway at {gw_ip}."
                    ),
                    expected_state=f"{rtr_name} GigabitEthernet0/0: IP {gw_ip} {netmask}",
                    faulty_state=f"{rtr_name} GigabitEthernet0/0: IP {bad_rtr_ip} {netmask}",
                    hints=[
                        f"Hint 1 (CCNA 1.6): All hosts point to {gw_ip} as their gateway and the router link is green, yet {gw_ip} does not reply to ping.",
                        f"Hint 2 (Device): Run 'show ip interface brief' on router '{rtr_name}'.",
                        f"Hint 3 (Exact Issue): '{rtr_name}' GigabitEthernet0/0 was configured with IP {bad_rtr_ip} instead of {gw_ip}!",
                    ],
                    explanation=(
                        f"While the interface GigabitEthernet0/0 on {rtr_name} was 'no shutdown', its IP address "
                        f"had a typo ({bad_rtr_ip} instead of {gw_ip}), leaving no device answering at the default gateway IP."
                    ),
                    fix_steps=[
                        f"1. In Packet Tracer, open router '{rtr_name}' -> 'CLI' tab.",
                        f"2. Correct the interface IP:\n"
                        f"     enable\n"
                        f"     configure terminal\n"
                        f"     interface GigabitEthernet0/0\n"
                        f"     ip address {gw_ip} {netmask}\n"
                        f"     end\n"
                        f"     write memory",
                        "3. Save the .pkt file (Ctrl+S) and verify.",
                    ],
                    verify_spec={
                        "type": "router_port_up",
                        "device": rtr_name,
                        "interface": "GigabitEthernet0/0",
                        "expected_ip": gw_ip,
                    },
                )
            )

        # ------------------------------------------------------------------
        # 15. Server IP / Gateway Misconfiguration (CCNA Obj 1.6 / 1.11)
        # ------------------------------------------------------------------
        elif ftype == "server_ip_or_gateway_fault":
            bad_srv_ip = unused_inside_subnet[1]
            bad_srv_gw = unused_inside_subnet[0]
            net.devices[srv_name].ip = bad_srv_ip
            net.devices[srv_name].gateway = bad_srv_gw
            injected_faults.append(
                FaultRecord(
                    fault_id=f"F{idx+1}_SERVER_MISCONFIG",
                    title=f"Misconfigured IPv4 Address & Gateway on Server {srv_name}",
                    category="CCNA 1.11 — Server IPv4 Endpoint Configuration",
                    device=srv_name,
                    interface="FastEthernet0",
                    symptom=(
                        f"All hosts can ping the Default Gateway ({gw_ip}) and each other, "
                        f"but nobody can reach the internal server {srv_name} at {srv_ip}."
                    ),
                    expected_state=f"{srv_name}: IP {srv_ip}, Mask {netmask}, Gateway {gw_ip}",
                    faulty_state=f"{srv_name}: IP {bad_srv_ip}, Mask {netmask}, Gateway {bad_srv_gw}",
                    hints=[
                        f"Hint 1 (CCNA 1.11): Every client host is configured properly, yet nobody can reach the server at {srv_ip}.",
                        f"Hint 2 (Device): Inspect 'Desktop -> IP Configuration' on server '{srv_name}'.",
                        f"Hint 3 (Exact Issue): '{srv_name}' has IP {bad_srv_ip} and Gateway {bad_srv_gw}. Set IP to {srv_ip} and Gateway to {gw_ip}.",
                    ],
                    explanation=(
                        f"Users blamed the network, but {srv_name} itself was misconfigured with IP {bad_srv_ip} "
                        f"(instead of {srv_ip}) and Default Gateway {bad_srv_gw} (instead of {gw_ip})."
                    ),
                    fix_steps=[
                        f"1. In Packet Tracer, click on server '{srv_name}' -> 'Desktop' -> 'IP Configuration'.",
                        f"2. Change IPv4 Address to '{srv_ip}' and Default Gateway to '{gw_ip}'.",
                        "3. Save the .pkt file (Ctrl+S) and verify.",
                    ],
                    verify_spec={
                        "type": "end_device_full_ip_gw",
                        "device": srv_name,
                        "expected_ip": srv_ip,
                        "expected_mask": netmask,
                        "expected_gateway": gw_ip,
                    },
                )
            )

        # ------------------------------------------------------------------
        # 16. Wrong DNS Server IP on Workstation (CCNA Obj 4.3)
        # ------------------------------------------------------------------
        elif ftype == "host_wrong_dns":
            bad_dns = unused_inside_subnet[3]
            target_dev.dns = bad_dns
            injected_faults.append(
                FaultRecord(
                    fault_id=f"F{idx+1}_WRONG_DNS",
                    title=f"Incorrect DNS Server IP on {target_pc}",
                    category="CCNA 4.3 — DNS Client Configuration",
                    device=target_pc,
                    interface="FastEthernet0",
                    symptom=(
                        f"User on {target_pc} can ping the server by IP address ({srv_ip}), "
                        f"but cannot resolve internal hostnames via DNS."
                    ),
                    expected_state=f"{target_pc} DNS Server: {srv_ip}",
                    faulty_state=f"{target_pc} DNS Server: {bad_dns}",
                    hints=[
                        "Hint 1 (CCNA 4.3): When ping by IP address works but hostname resolution fails, check DNS settings.",
                        f"Hint 2 (Device): Check the DNS Server IP configured on '{target_pc}'.",
                        f"Hint 3 (Exact Issue): '{target_pc}' has DNS Server set to {bad_dns} instead of {srv_ip}.",
                    ],
                    explanation=(
                        f"{target_pc} has valid IP, mask, and gateway settings, so ICMP echo to {srv_ip} succeeds, "
                        f"but its DNS Server field points to {bad_dns} instead of {srv_name} ({srv_ip})."
                    ),
                    fix_steps=[
                        f"1. In Packet Tracer, click '{target_pc}' -> 'Desktop' -> 'IP Configuration'.",
                        f"2. Change 'DNS Server' from '{bad_dns}' to '{srv_ip}'.",
                        "3. Save the .pkt file (Ctrl+S) and verify.",
                    ],
                    verify_spec={
                        "type": "end_device_dns",
                        "device": target_pc,
                        "expected_dns": srv_ip,
                    },
                )
            )

    # Build and write the .pkt file
    out_folder = Path(out_dir)
    out_folder.mkdir(parents=True, exist_ok=True)
    ticket_num = rng.randint(1000, 9999)
    ticket_id = f"NOC-{ticket_num}"
    pkt_path = out_folder / f"level1_{ticket_id.lower()}.pkt"

    lab = net.build_lab()
    for post_fn in post_xml_mutations:
        post_fn(lab.base)

    xml_bytes = ET.tostring(lab.base, encoding="unicode").encode("utf-8")
    encode(str(pkt_path), xml_bytes, "pkt")

    symptoms_combined = "  • " + "\n  • ".join(f.symptom for f in injected_faults)

    # Map Packet Tracer floorplan positions directly onto the GUI Topology Canvas
    crx, cry = _pt_to_canvas(*pt_pos["rtr"])
    csx, csy = _pt_to_canvas(*pt_pos["sw1"])
    canvas_nodes = [
        {"name": rtr_name, "role": "router", "sub": f"Gi0/0: {gw_ip}/{prefix_len}", "x": crx, "y": cry},
        {"name": sw_name, "role": "switch", "sub": f"Vlan1: {sw_ip}/{prefix_len}", "x": csx, "y": csy},
    ]
    canvas_edges = [
        (rtr_name, sw_name, "Gi0/0", "Gi0/1"),
    ]
    if has_sw2:
        cs2x, cs2y = _pt_to_canvas(*pt_pos["sw2"])
        canvas_nodes.append(
            {
                "name": sw2_name,
                "role": "switch",
                "sub": f"Vlan1: {sw2_ip}/{prefix_len}",
                "x": cs2x,
                "y": cs2y,
            }
        )
        canvas_edges.append((sw_name, sw2_name, "Gi0/2", "Gi0/1"))

    for c in client_specs:
        cnx, cny = _pt_to_canvas(*pt_pos[c["pos_key"]])
        canvas_nodes.append(
            {
                "name": c["name"],
                "role": "pc",
                "sub": f"{c['ip']}/{prefix_len}\nGW: {gw_ip}",
                "x": cnx,
                "y": cny,
            }
        )
        short_sw_port = c["sw_port"].replace("FastEthernet", "Fa")
        canvas_edges.append((c["sw_name"], c["name"], short_sw_port, "Fa0"))

    csrvx, csrvy = _pt_to_canvas(*pt_pos["srv"])
    canvas_nodes.append(
        {
            "name": srv_name,
            "role": "server",
            "sub": f"{srv_ip}/{prefix_len}\nGW: {gw_ip}",
            "x": csrvx,
            "y": csrvy,
        }
    )
    canvas_edges.append((sw_name, srv_name, srv_sw_port.replace("FastEthernet", "Fa"), "Fa0"))

    sw_note = (
        f"MDF Switch {sw_name} Vlan1 is {sw_ip}/{prefix_len} and IDF Switch {sw2_name} Vlan1 is {sw2_ip}/{prefix_len} (both default-gateway {gw_ip})."
        if has_sw2
        else f"Switch {sw_name} Management SVI (interface Vlan1) is {sw_ip}/{prefix_len} with ip default-gateway {gw_ip}."
    )

    return ChallengeTicket(
        ticket_id=ticket_id,
        level=1,
        level_name="Level 1 — CCNA v2.0 Tier 1 Helpdesk (Single LAN)",
        scenario_title=f"{dept_name} ({subnet_cidr}) — {layout_label}",
        symptom_summary=symptoms_combined,
        pkt_path=pkt_path,
        subnet_cidr=subnet_cidr,
        device_rows=device_rows,
        link_rows=link_rows,
        service_notes=[
            f"Physical Floorplan Layout: {layout_label}.",
            f"Allocated Subnet: {subnet_cidr} | Subnet Mask: {netmask} | Usable Range: {hosts[0]} – {hosts[-1]}.",
            f"Default Gateway Policy: {gw_convention_note} on {rtr_name} ({rtr_model}) GigabitEthernet0/0.",
            sw_note,
            f"Internal DNS/Web Server ({srv_name}) is located at {srv_ip} (all hosts use {srv_ip} for DNS).",
        ],
        faults=injected_faults,
        canvas_nodes=canvas_nodes,
        canvas_edges=canvas_edges,
    )
