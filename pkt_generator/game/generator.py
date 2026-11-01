"""Level 1 CCNA (200-301 v2.0) NOC Fault & Setup Generator orchestrator."""

from __future__ import annotations

from collections.abc import Callable
import ipaddress
from pathlib import Path
import random
import xml.etree.ElementTree as ET

from pkt_generator.game.faults_level1 import (
    ALL_LEVEL1_FAULT_TYPES,
    FaultInjectionContext,
    inject_level1_fault,
    select_compatible_faults,
)
from pkt_generator.game.layouts import (
    TOPOLOGY_ARCHETYPES,
    build_layout_positions,
    pt_to_canvas,
)
from pkt_generator.game.models import (
    BlueprintDeviceRow,
    BlueprintLinkRow,
    ChallengeTicket,
    FaultRecord,
)
from pkt_generator.game.settings import GameSettings
from pkt_generator.network import SimpleNetwork, encode

__all__ = [
    "ALL_LEVEL1_FAULT_TYPES",
    "TOPOLOGY_ARCHETYPES",
    "generate_level1_challenge",
]


def _pick_random_lan_network(
    rng: random.Random, allowed_prefixes: list[int] | None = None
) -> ipaddress.IPv4Network:
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
    valid_prefixes = [
        p for p in (allowed_prefixes or [24, 25, 26, 27]) if p in (24, 25, 26, 27)
    ]
    prefix_len = rng.choice(valid_prefixes or [24, 25, 26, 27])
    if prefix_len == 24:
        return base_net
    subnets = list(base_net.subnets(new_prefix=prefix_len))
    return rng.choice(subnets)


def generate_level1_challenge(
    out_dir: str | Path,
    *,
    num_faults: int = 1,
    seed: int | None = None,
    fault_types: list[str] | None = None,
    archetype: str | None = None,
    settings: GameSettings | None = None,
    allowed_prefixes: list[int] | None = None,
    allowed_archetypes: list[str] | None = None,
    allowed_fault_pool: list[str] | None = None,
    task_kind: str = "fault",
) -> ChallengeTicket:
    """Generate a Level 1 (CCNA v2.0 Tier 1 Helpdesk — Single LAN) faulty .pkt file and NOC Ticket.

    Uses player_name, company_name, and departments from `game_settings.json` (via `GameSettings`).
    """
    cfg = settings if settings is not None else GameSettings.load()
    rng = random.Random(seed)
    code, dept_name = rng.choice(cfg.departments)
    net_obj = _pick_random_lan_network(rng, allowed_prefixes=allowed_prefixes)
    prefix_len = net_obj.prefixlen
    netmask = str(net_obj.netmask)
    subnet_cidr = str(net_obj)
    hosts = [str(ip) for ip in net_obj.hosts()]

    # Randomize router model, client count (2 to 4 clients + 1 server), and physical layout archetype
    rtr_model = rng.choice(["2911", "1941", "2901"])
    sw_model = "2960-24TT"
    base_clients = rng.choice([2, 3, 4])
    num_clients = max(base_clients, min(4, max(1, num_faults)))
    valid_arch_pool = [
        a
        for a in (allowed_archetypes or TOPOLOGY_ARCHETYPES)
        if a in TOPOLOGY_ARCHETYPES
    ]
    chosen_archetype = (
        archetype
        if archetype in TOPOLOGY_ARCHETYPES
        else rng.choice(valid_arch_pool or TOPOLOGY_ARCHETYPES)
    )
    layout_label, num_switches, client_sw_indices, pt_pos = build_layout_positions(
        chosen_archetype, num_clients
    )

    # Randomize gateway convention: "first" (hosts[0]) or "last" (hosts[-1])
    gw_convention = rng.choice(["first", "last"])
    if gw_convention == "first":
        gw_ip = hosts[0]
        sw_ip = hosts[1]
        sw2_ip = hosts[2]
        sw3_ip = hosts[3]
        srv_ip = hosts[-2]
        client_base_idx = 5
        gw_convention_note = f"First usable host ({gw_ip})"
    else:
        gw_ip = hosts[-1]
        sw_ip = hosts[0]
        sw2_ip = hosts[1]
        sw3_ip = hosts[2]
        srv_ip = hosts[-3]
        client_base_idx = 4
        gw_convention_note = f"Last usable host ({gw_ip})"

    unused_inside_subnet = [
        hosts[-4],
        hosts[-5],
        hosts[-6],
        hosts[3] if gw_convention == "last" else hosts[4],
    ]

    rtr_name = f"{code}-R1"
    sw_name = f"{code}-SW1"
    sw2_name = f"{code}-SW2"
    sw3_name = f"{code}-SW3"
    srv_name = f"{code}-SRV1"

    sw_names_by_idx = {1: sw_name, 2: sw2_name, 3: sw3_name}
    sw_port_counters = {1: 1, 2: 1, 3: 1}

    client_specs: list[dict[str, str]] = []
    for i in range(1, num_clients + 1):
        is_laptop = i == num_clients and num_clients >= 3 and rng.random() < 0.5
        c_model = "Laptop-PT" if is_laptop else "PC-PT"
        c_prefix = "LT" if is_laptop else "PC"
        c_name = f"{code}-{c_prefix}{i}"
        c_ip = hosts[client_base_idx + i - 1]
        sw_idx = client_sw_indices[i - 1]
        assigned_sw = sw_names_by_idx[sw_idx]
        c_sw_port = f"FastEthernet0/{sw_port_counters[sw_idx]}"
        sw_port_counters[sw_idx] += 1
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

    srv_sw_port = f"FastEthernet0/{sw_port_counters[1]}"
    pc_port_map = {
        c["name"]: (c["sw_name"], c["sw_port"], c["ip"]) for c in client_specs
    }

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
            role="MDF Core/Access Switch" if num_switches >= 2 else "Access Switch",
            interface="Vlan1",
            expected_ip=sw_ip,
            expected_mask=netmask,
            expected_gateway=gw_ip,
            expected_dns="-",
            notes="Switch Management SVI (UP + ip default-gateway)",
        ),
    ]
    if num_switches >= 2:
        device_rows.append(
            BlueprintDeviceRow(
                device=sw2_name,
                model=sw_model,
                role="West IDF Switch" if num_switches == 3 else "IDF Expansion Switch",
                interface="Vlan1",
                expected_ip=sw2_ip,
                expected_mask=netmask,
                expected_gateway=gw_ip,
                expected_dns="-",
                notes="IDF Floor Switch Management SVI (VLAN 1)",
            )
        )
    if num_switches >= 3:
        device_rows.append(
            BlueprintDeviceRow(
                device=sw3_name,
                model=sw_model,
                role="East IDF Switch",
                interface="Vlan1",
                expected_ip=sw3_ip,
                expected_mask=netmask,
                expected_gateway=gw_ip,
                expected_dns="-",
                notes="East Wing IDF Switch Management SVI (VLAN 1)",
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
                notes=f"Static IPv4 on {subnet_cidr}, Port Status ON, Auto Speed/Duplex",
            )
        )
    device_rows.append(
        BlueprintDeviceRow(
            device=srv_name,
            model="Server-PT",
            role="Internal Web / DNS Server",
            interface="FastEthernet0",
            expected_ip=srv_ip,
            expected_mask=netmask,
            expected_gateway=gw_ip,
            expected_dns=srv_ip,
            notes="Power ON, Static IPv4, HTTP & DNS Services Enabled",
        )
    )

    link_rows = [
        BlueprintLinkRow(
            dev_a=rtr_name,
            port_a="GigabitEthernet0/0",
            dev_b=sw_name,
            port_b="GigabitEthernet0/1",
            cable_type="Copper Straight-Through",
            mode_or_vlan="VLAN 1 (Gateway Uplink)",
        ),
    ]
    if num_switches >= 2:
        link_rows.append(
            BlueprintLinkRow(
                dev_a=sw_name,
                port_a="GigabitEthernet0/2",
                dev_b=sw2_name,
                port_b="GigabitEthernet0/1",
                cable_type="Copper Cross-Over / Auto-MDIX",
                mode_or_vlan="VLAN 1 (MDF-to-IDF Inter-Switch Link)",
            )
        )
    if num_switches >= 3:
        link_rows.append(
            BlueprintLinkRow(
                dev_a=sw_name,
                port_a="FastEthernet0/24",
                dev_b=sw3_name,
                port_b="GigabitEthernet0/1",
                cable_type="Copper Cross-Over / Auto-MDIX",
                mode_or_vlan="VLAN 1 (MDF-to-East IDF Uplink)",
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
                mode_or_vlan="Access VLAN 1 (Auto Speed/Duplex)",
            )
        )
    link_rows.append(
        BlueprintLinkRow(
            dev_a=sw_name,
            port_a=srv_sw_port,
            dev_b=srv_name,
            port_b="FastEthernet0",
            cable_type="Copper Straight-Through",
            mode_or_vlan="Access VLAN 1 (Server Port)",
        )
    )

    # Build baseline SimpleNetwork using layout archetype positions
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
    if num_switches >= 2:
        s2x, s2y = pt_pos["sw2"]
        net.add_switch(
            sw2_name,
            model=sw_model,
            x=s2x,
            y=s2y,
            management_ip=f"{sw2_ip}/{prefix_len}",
            default_gateway=gw_ip,
        )
    if num_switches >= 3:
        s3x, s3y = pt_pos["sw3"]
        net.add_switch(
            sw3_name,
            model=sw_model,
            x=s3x,
            y=s3y,
            management_ip=f"{sw3_ip}/{prefix_len}",
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
    if num_switches >= 2:
        net.connect(
            sw_name,
            sw2_name,
            port_a="GigabitEthernet0/2",
            port_b="GigabitEthernet0/1",
        )
    if num_switches >= 3:
        net.connect(
            sw_name,
            sw3_name,
            port_a="FastEthernet0/24",
            port_b="GigabitEthernet0/1",
        )
    for c in client_specs:
        net.connect(c["sw_name"], c["name"], port_a=c["sw_port"], port_b="FastEthernet0")
    net.connect(sw_name, srv_name, port_a=srv_sw_port, port_b="FastEthernet0")

    # Select and inject faults / setup items
    if fault_types:
        chosen_types = list(fault_types)
    else:
        chosen_types = select_compatible_faults(
            rng, max(1, min(num_faults, 4)), allowed_pool=allowed_fault_pool
        )

    host_targets = [c["name"] for c in client_specs]
    rng.shuffle(host_targets)

    injected_faults: list[FaultRecord] = []
    post_xml_mutations: list[Callable[[ET.Element], None]] = []

    for idx, ftype in enumerate(chosen_types):
        target_pc = host_targets[idx % len(host_targets)]
        sw_for_pc, sw_port_for_pc, expected_pc_ip = pc_port_map[target_pc]
        ctx = FaultInjectionContext(
            idx=idx,
            net=net,
            post_xml_mutations=post_xml_mutations,
            rtr_name=rtr_name,
            sw_name=sw_name,
            srv_name=srv_name,
            srv_sw_port=srv_sw_port,
            target_pc=target_pc,
            sw_for_pc=sw_for_pc,
            sw_port_for_pc=sw_port_for_pc,
            expected_pc_ip=expected_pc_ip,
            gw_ip=gw_ip,
            gw_convention_note=gw_convention_note,
            sw_ip=sw_ip,
            srv_ip=srv_ip,
            netmask=netmask,
            prefix_len=prefix_len,
            subnet_cidr=subnet_cidr,
            unused_inside_subnet=unused_inside_subnet,
        )
        injected_faults.append(inject_level1_fault(ftype, ctx))

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

    if task_kind == "setup":
        scenario_title = f"[NETWORK SETUP] {cfg.company_name}: {dept_name} ({subnet_cidr}) — {layout_label}"
        symptoms_combined = (
            f"🏗️ PROVISIONING WORK ORDER ({dept_name}): Complete physical cabling, power on hardware, "
            f"enable interfaces, and configure IPv4 addressing per the Network Blueprint:\n  • "
            + "\n  • ".join(f.symptom for f in injected_faults)
        )
    else:
        scenario_title = f"{cfg.company_name}: {dept_name} ({subnet_cidr}) — {layout_label}"
        symptoms_combined = "  • " + "\n  • ".join(f.symptom for f in injected_faults)

    # Map Packet Tracer floorplan positions directly onto the GUI Topology Canvas
    crx, cry = pt_to_canvas(*pt_pos["rtr"])
    csx, csy = pt_to_canvas(*pt_pos["sw1"])
    canvas_nodes = [
        {"name": rtr_name, "role": "router", "sub": f"Gi0/0: {gw_ip}/{prefix_len}", "x": crx, "y": cry},
        {"name": sw_name, "role": "switch", "sub": f"Vlan1: {sw_ip}/{prefix_len}", "x": csx, "y": csy},
    ]
    canvas_edges = [
        (rtr_name, sw_name, "Gi0/0", "Gi0/1"),
    ]
    if num_switches >= 2:
        cs2x, cs2y = pt_to_canvas(*pt_pos["sw2"])
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
    if num_switches >= 3:
        cs3x, cs3y = pt_to_canvas(*pt_pos["sw3"])
        canvas_nodes.append(
            {
                "name": sw3_name,
                "role": "switch",
                "sub": f"Vlan1: {sw3_ip}/{prefix_len}",
                "x": cs3x,
                "y": cs3y,
            }
        )
        canvas_edges.append((sw_name, sw3_name, "Fa0/24", "Gi0/1"))

    for c in client_specs:
        cnx, cny = pt_to_canvas(*pt_pos[c["pos_key"]])
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

    csrvx, csrvy = pt_to_canvas(*pt_pos["srv"])
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

    if num_switches == 3:
        sw_note = (
            f"Switches: MDF {sw_name} ({sw_ip}/{prefix_len}), West IDF {sw2_name} ({sw2_ip}/{prefix_len}), "
            f"East IDF {sw3_name} ({sw3_ip}/{prefix_len}) — all with default-gateway {gw_ip}."
        )
    elif num_switches == 2:
        sw_note = (
            f"MDF Switch {sw_name} Vlan1 is {sw_ip}/{prefix_len} and IDF Switch {sw2_name} Vlan1 is {sw2_ip}/{prefix_len} (both default-gateway {gw_ip})."
        )
    else:
        sw_note = (
            f"Switch {sw_name} Management SVI (interface Vlan1) is {sw_ip}/{prefix_len} with ip default-gateway {gw_ip}."
        )

    return ChallengeTicket(
        ticket_id=ticket_id,
        level=1,
        level_name=f"Level 1 — {cfg.company_name} Tier 1 Helpdesk (Single LAN)",
        scenario_title=scenario_title,
        symptom_summary=symptoms_combined,
        pkt_path=pkt_path,
        subnet_cidr=subnet_cidr,
        device_rows=device_rows,
        link_rows=link_rows,
        service_notes=[
            f"Physical Floorplan Layout: {layout_label}.",
            f"Assigned Engineer: {cfg.player_name} | Organization: {cfg.company_name} — {dept_name} ({code}).",
            f"Allocated Subnet: {subnet_cidr} | Subnet Mask: {netmask} | Usable Range: {hosts[0]} – {hosts[-1]}.",
            f"Default Gateway Policy: {gw_convention_note} on {rtr_name} ({rtr_model}) GigabitEthernet0/0.",
            sw_note,
            f"Internal DNS/Web Server ({srv_name}) is located at {srv_ip} (all hosts use {srv_ip} for DNS).",
        ],
        faults=injected_faults,
        canvas_nodes=canvas_nodes,
        canvas_edges=canvas_edges,
    )
