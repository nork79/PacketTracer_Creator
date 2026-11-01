"""Level 2 CCNA (200-301 v2.0) Fault Challenge & Mode 2 Greenfield Build Mission Generators."""

from __future__ import annotations

from collections.abc import Callable
import ipaddress
from pathlib import Path
import random
import xml.etree.ElementTree as ET

from pkt_generator.game.faults_level2 import (
    ALL_LEVEL2_FAULT_TYPES,
    Level2FaultContext,
    inject_level2_fault,
    select_compatible_level2_faults,
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
from pkt_generator.network import PortConfig, SimpleNetwork, encode

LEVEL2_MULTI_SWITCH_ARCHETYPES: list[str] = [
    "mdf_idf_two_closet",
    "multi_floor_riser",
    "three_switch_wings",
    "server_cage_and_user_pod",
    "linear_warehouse_bays",
    "u_shaped_courtyard",
]


def _pick_level2_vlan_subnets(
    rng: random.Random, code: str, allowed_prefixes: list[int] | None = None
) -> tuple[int, str, ipaddress.IPv4Network, int, str, ipaddress.IPv4Network]:
    """Return (vlan_a, vlan_a_name, net_a, vlan_b, vlan_b_name, net_b) for a Level 2 dual-VLAN topology."""
    vlan_pairs = [
        (10, f"{code}_DATA", 20, f"{code}_VOICE_SRV"),
        (10, f"{code}_USERS", 30, f"{code}_SERVERS"),
        (20, f"{code}_STAFF", 40, f"{code}_VOICE_OPS"),
        (15, f"{code}_CORP", 25, f"{code}_ENG_SRV"),
        (100, f"{code}_WORKSTATIONS", 200, f"{code}_SERVICES"),
    ]
    vlan_a, vlan_a_name, vlan_b, vlan_b_name = rng.choice(vlan_pairs)

    valid_prefixes = [
        p for p in (allowed_prefixes or [24, 25, 26]) if p in (24, 25, 26)
    ]
    prefix_len = rng.choice(valid_prefixes or [24, 25, 26])

    family = rng.choice(["10", "172", "192"])
    if family == "10":
        b2 = rng.choice([10, 20, 30, 50, 80])
        base_a = ipaddress.IPv4Network(f"10.{b2}.{vlan_a}.0/24")
        base_b = ipaddress.IPv4Network(f"10.{b2}.{vlan_b}.0/24")
    elif family == "172":
        b2 = rng.randint(16, 31)
        base_a = ipaddress.IPv4Network(f"172.{b2}.{vlan_a}.0/24")
        base_b = ipaddress.IPv4Network(f"172.{b2}.{vlan_b}.0/24")
    else:
        base_a = ipaddress.IPv4Network(f"192.168.{vlan_a}.0/24")
        base_b = ipaddress.IPv4Network(f"192.168.{vlan_b}.0/24")

    if prefix_len == 24:
        net_a, net_b = base_a, base_b
    else:
        net_a = list(base_a.subnets(new_prefix=prefix_len))[0]
        net_b = list(base_b.subnets(new_prefix=prefix_len))[0]

    return vlan_a, vlan_a_name, net_a, vlan_b, vlan_b_name, net_b


def generate_level2_challenge(
    out_dir: str | Path,
    *,
    num_faults: int = 1,
    seed: int | None = None,
    fault_types: list[str] | None = None,
    archetype: str | None = None,
    settings: GameSettings | None = None,
    allowed_prefixes: list[int] | None = None,
) -> ChallengeTicket:
    """Generate a Level 2 (CCNA v2.0 Switching, VLANs, 802.1Q Trunks, Router-on-a-Stick & EtherChannel) challenge."""
    cfg = settings if settings is not None else GameSettings.load()
    rng = random.Random(seed)
    code, dept_name = rng.choice(cfg.departments)

    vlan_a, vlan_a_name, net_a, vlan_b, vlan_b_name, net_b = _pick_level2_vlan_subnets(
        rng, code, allowed_prefixes=allowed_prefixes
    )
    prefix_len = net_a.prefixlen
    netmask = str(net_a.netmask)
    subnet_a_cidr = str(net_a)
    subnet_b_cidr = str(net_b)
    hosts_a = [str(ip) for ip in net_a.hosts()]
    hosts_b = [str(ip) for ip in net_b.hosts()]

    # Gateway convention (1st usable host in each VLAN subnet)
    gw_a = hosts_a[0]
    sw1_ip = hosts_a[1]
    sw2_ip = hosts_a[2]
    sw3_ip = hosts_a[3]
    pc1_ip = hosts_a[9]
    pc2_ip = hosts_a[10]

    gw_b = hosts_b[0]
    pc3_ip = hosts_b[9]
    pc4_ip = hosts_b[10]
    srv_ip = hosts_b[-2]

    rtr_model = rng.choice(["2911", "1941", "2901"])
    sw_model = "2960-24TT"
    num_clients = rng.choice([3, 4])
    chosen_archetype = (
        archetype
        if archetype in LEVEL2_MULTI_SWITCH_ARCHETYPES
        else rng.choice(LEVEL2_MULTI_SWITCH_ARCHETYPES)
    )
    layout_label, num_switches, _client_sw_indices, pt_pos = build_layout_positions(
        chosen_archetype, num_clients
    )

    rtr_name = f"{code}-R1"
    sw1_name = f"{code}-SW1"
    sw2_name = f"{code}-SW2"
    sw3_name = f"{code}-SW3"
    srv_name = f"{code}-SRV1"

    pc1_name = f"{code}-PC1"
    pc2_name = f"{code}-PC2"
    pc3_name = f"{code}-PC3"
    pc4_name = f"{code}-LT4" if num_clients == 4 else ""

    if fault_types:
        chosen_types = list(fault_types)
    else:
        chosen_types = select_compatible_level2_faults(rng, max(1, min(num_faults, 4)))

    has_voice_fault = "voice_vlan_mismatch" in chosen_types
    has_ec_fault = "etherchannel_mode_mismatch" in chosen_types

    # Port assignments
    rtr_roas_port = "GigabitEthernet0/0"
    sw1_to_rtr_port = "GigabitEthernet0/1"
    sw1_to_sw2_port = "GigabitEthernet0/2"
    sw2_to_sw1_port = "GigabitEthernet0/1"
    sw1_ec_port2 = "FastEthernet0/23"
    sw2_ec_port2 = "FastEthernet0/23"

    pc1_sw_port = "FastEthernet0/1"
    srv_sw_port = "FastEthernet0/2"
    pc2_sw_port = "FastEthernet0/1"
    pc3_sw_port = "FastEthernet0/2"
    pc4_sw_port = "FastEthernet0/3" if num_switches == 2 else "FastEthernet0/1"
    pc4_sw_name = sw2_name if num_switches == 2 else sw3_name

    # Build Golden (Intended) Network Blueprint
    device_rows: list[BlueprintDeviceRow] = [
        BlueprintDeviceRow(
            device=rtr_name,
            model=rtr_model,
            role=f"RoaS Gateway (VLAN {vlan_a})",
            interface=f"{rtr_roas_port}.{vlan_a}",
            expected_ip=gw_a,
            expected_mask=netmask,
            expected_gateway="-",
            expected_dns="-",
            notes=f"encapsulation dot1Q {vlan_a} ({vlan_a_name}), parent {rtr_roas_port} UP",
        ),
        BlueprintDeviceRow(
            device=rtr_name,
            model=rtr_model,
            role=f"RoaS Gateway (VLAN {vlan_b})",
            interface=f"{rtr_roas_port}.{vlan_b}",
            expected_ip=gw_b,
            expected_mask=netmask,
            expected_gateway="-",
            expected_dns="-",
            notes=f"encapsulation dot1Q {vlan_b} ({vlan_b_name}), parent {rtr_roas_port} UP",
        ),
        BlueprintDeviceRow(
            device=sw1_name,
            model=sw_model,
            role="MDF Core Switch",
            interface=f"Vlan{vlan_a}",
            expected_ip=sw1_ip,
            expected_mask=netmask,
            expected_gateway=gw_a,
            expected_dns="-",
            notes=f"VLANs {vlan_a},{vlan_b} in DB; trunks on {sw1_to_rtr_port} & {sw1_to_sw2_port}",
        ),
        BlueprintDeviceRow(
            device=sw2_name,
            model=sw_model,
            role="IDF Access Switch",
            interface=f"Vlan{vlan_a}",
            expected_ip=sw2_ip,
            expected_mask=netmask,
            expected_gateway=gw_a,
            expected_dns="-",
            notes=f"VLANs {vlan_a},{vlan_b} in DB; trunk on {sw2_to_sw1_port}",
        ),
    ]
    if num_switches >= 3:
        device_rows.append(
            BlueprintDeviceRow(
                device=sw3_name,
                model=sw_model,
                role="East IDF Switch",
                interface=f"Vlan{vlan_a}",
                expected_ip=sw3_ip,
                expected_mask=netmask,
                expected_gateway=gw_a,
                expected_dns="-",
                notes=f"VLANs {vlan_a},{vlan_b} in DB; trunk on GigabitEthernet0/1",
            )
        )

    device_rows.extend(
        [
            BlueprintDeviceRow(
                device=pc1_name,
                model="PC-PT",
                role=f"VLAN {vlan_a} Workstation",
                interface="FastEthernet0",
                expected_ip=pc1_ip,
                expected_mask=netmask,
                expected_gateway=gw_a,
                expected_dns=srv_ip,
                notes=f"Connected to {sw1_name} {pc1_sw_port} (Access VLAN {vlan_a}"
                + (f" + Voice VLAN {vlan_b})" if has_voice_fault else ")"),
            ),
            BlueprintDeviceRow(
                device=pc2_name,
                model="PC-PT",
                role=f"VLAN {vlan_a} Workstation",
                interface="FastEthernet0",
                expected_ip=pc2_ip,
                expected_mask=netmask,
                expected_gateway=gw_a,
                expected_dns=srv_ip,
                notes=f"Connected to {sw2_name} {pc2_sw_port} (Access VLAN {vlan_a})",
            ),
            BlueprintDeviceRow(
                device=pc3_name,
                model="PC-PT",
                role=f"VLAN {vlan_b} Workstation",
                interface="FastEthernet0",
                expected_ip=pc3_ip,
                expected_mask=netmask,
                expected_gateway=gw_b,
                expected_dns=srv_ip,
                notes=f"Connected to {sw2_name} {pc3_sw_port} (Access VLAN {vlan_b})",
            ),
        ]
    )
    if num_clients == 4:
        device_rows.append(
            BlueprintDeviceRow(
                device=pc4_name,
                model="Laptop-PT",
                role=f"VLAN {vlan_b} Laptop",
                interface="FastEthernet0",
                expected_ip=pc4_ip,
                expected_mask=netmask,
                expected_gateway=gw_b,
                expected_dns=srv_ip,
                notes=f"Connected to {pc4_sw_name} {pc4_sw_port} (Access VLAN {vlan_b})",
            )
        )
    device_rows.append(
        BlueprintDeviceRow(
            device=srv_name,
            model="Server-PT",
            role=f"VLAN {vlan_b} DNS/Web Server",
            interface="FastEthernet0",
            expected_ip=srv_ip,
            expected_mask=netmask,
            expected_gateway=gw_b,
            expected_dns=srv_ip,
            notes=f"Connected to {sw1_name} {srv_sw_port} (Access VLAN {vlan_b})",
        )
    )

    link_rows: list[BlueprintLinkRow] = [
        BlueprintLinkRow(
            dev_a=rtr_name,
            port_a=rtr_roas_port,
            dev_b=sw1_name,
            port_b=sw1_to_rtr_port,
            cable_type="Copper Straight-Through",
            mode_or_vlan=f"802.1Q Trunk (VLANs {vlan_a},{vlan_b} RoaS)",
        ),
        BlueprintLinkRow(
            dev_a=sw1_name,
            port_a=sw1_to_sw2_port,
            dev_b=sw2_name,
            port_b=sw2_to_sw1_port,
            cable_type="Copper Cross-Over / Auto-MDIX",
            mode_or_vlan=(
                f"802.1Q Trunk + LACP Po1 (VLANs {vlan_a},{vlan_b}, Native 1)"
                if has_ec_fault
                else f"802.1Q Trunk (VLANs {vlan_a},{vlan_b}, Native VLAN 1)"
            ),
        ),
    ]
    if has_ec_fault:
        link_rows.append(
            BlueprintLinkRow(
                dev_a=sw1_name,
                port_a=sw1_ec_port2,
                dev_b=sw2_name,
                port_b=sw2_ec_port2,
                cable_type="Copper Cross-Over / Auto-MDIX",
                mode_or_vlan="LACP Port-channel1 Member (mode active, Trunk)",
            )
        )
    if num_switches >= 3:
        link_rows.append(
            BlueprintLinkRow(
                dev_a=sw1_name,
                port_a="FastEthernet0/24",
                dev_b=sw3_name,
                port_b="GigabitEthernet0/1",
                cable_type="Copper Cross-Over / Auto-MDIX",
                mode_or_vlan=f"802.1Q Trunk (VLANs {vlan_a},{vlan_b})",
            )
        )

    link_rows.extend(
        [
            BlueprintLinkRow(
                dev_a=sw1_name,
                port_a=pc1_sw_port,
                dev_b=pc1_name,
                port_b="FastEthernet0",
                cable_type="Copper Straight-Through",
                mode_or_vlan=(
                    f"Access VLAN {vlan_a} + Voice VLAN {vlan_b}"
                    if has_voice_fault
                    else f"Access VLAN {vlan_a} ({vlan_a_name})"
                ),
            ),
            BlueprintLinkRow(
                dev_a=sw2_name,
                port_a=pc2_sw_port,
                dev_b=pc2_name,
                port_b="FastEthernet0",
                cable_type="Copper Straight-Through",
                mode_or_vlan=f"Access VLAN {vlan_a} ({vlan_a_name})",
            ),
            BlueprintLinkRow(
                dev_a=sw2_name,
                port_a=pc3_sw_port,
                dev_b=pc3_name,
                port_b="FastEthernet0",
                cable_type="Copper Straight-Through",
                mode_or_vlan=f"Access VLAN {vlan_b} ({vlan_b_name})",
            ),
        ]
    )
    if num_clients == 4:
        link_rows.append(
            BlueprintLinkRow(
                dev_a=pc4_sw_name,
                port_a=pc4_sw_port,
                dev_b=pc4_name,
                port_b="FastEthernet0",
                cable_type="Copper Straight-Through",
                mode_or_vlan=f"Access VLAN {vlan_b} ({vlan_b_name})",
            )
        )
    link_rows.append(
        BlueprintLinkRow(
            dev_a=sw1_name,
            port_a=srv_sw_port,
            dev_b=srv_name,
            port_b="FastEthernet0",
            cable_type="Copper Straight-Through",
            mode_or_vlan=f"Access VLAN {vlan_b} ({vlan_b_name})",
        )
    )

    # Construct baseline Golden SimpleNetwork
    net = SimpleNetwork()
    rx, ry = pt_pos["rtr"]
    s1x, s1y = pt_pos["sw1"]
    s2x, s2y = pt_pos["sw2"]
    net.add_router(rtr_name, model=rtr_model, x=rx, y=ry)
    net.add_switch(sw1_name, model=sw_model, x=s1x, y=s1y, default_gateway=gw_a)
    net.add_switch(sw2_name, model=sw_model, x=s2x, y=s2y, default_gateway=gw_a)

    net.add_vlan(sw1_name, vlan_a, vlan_a_name, svi_ip=f"{sw1_ip}/{prefix_len}")
    net.add_vlan(sw1_name, vlan_b, vlan_b_name)
    net.add_vlan(sw2_name, vlan_a, vlan_a_name, svi_ip=f"{sw2_ip}/{prefix_len}")
    net.add_vlan(sw2_name, vlan_b, vlan_b_name)

    if num_switches >= 3:
        s3x, s3y = pt_pos["sw3"]
        net.add_switch(sw3_name, model=sw_model, x=s3x, y=s3y, default_gateway=gw_a)
        net.add_vlan(sw3_name, vlan_a, vlan_a_name, svi_ip=f"{sw3_ip}/{prefix_len}")
        net.add_vlan(sw3_name, vlan_b, vlan_b_name)

    c0x, c0y = pt_pos["c0"]
    c1x, c1y = pt_pos["c1"]
    c2x, c2y = pt_pos["c2"]
    net.add_pc(pc1_name, ip=f"{pc1_ip}/{prefix_len}", gateway=gw_a, dns=srv_ip, x=c0x, y=c0y)
    net.add_pc(pc2_name, ip=f"{pc2_ip}/{prefix_len}", gateway=gw_a, dns=srv_ip, x=c1x, y=c1y)
    net.add_pc(pc3_name, ip=f"{pc3_ip}/{prefix_len}", gateway=gw_b, dns=srv_ip, x=c2x, y=c2y)
    if num_clients == 4:
        c3x, c3y = pt_pos["c3"]
        net.add_laptop(pc4_name, ip=f"{pc4_ip}/{prefix_len}", gateway=gw_b, dns=srv_ip, x=c3x, y=c3y)

    srv_x, srv_y = pt_pos["srv"]
    net.add_server(srv_name, ip=f"{srv_ip}/{prefix_len}", gateway=gw_b, dns=srv_ip, x=srv_x, y=srv_y)

    # Connect links
    net.connect(rtr_name, sw1_name, port_a=rtr_roas_port, port_b=sw1_to_rtr_port, trunk=True)
    net.add_subinterface(rtr_name, rtr_roas_port, vlan_a, f"{gw_a}/{prefix_len}", description=vlan_a_name)
    net.add_subinterface(rtr_name, rtr_roas_port, vlan_b, f"{gw_b}/{prefix_len}", description=vlan_b_name)

    net.connect(sw1_name, sw2_name, port_a=sw1_to_sw2_port, port_b=sw2_to_sw1_port, trunk=True)
    if num_switches >= 3:
        net.connect(sw1_name, sw3_name, port_a="FastEthernet0/24", port_b="GigabitEthernet0/1", trunk=True)

    net.connect(sw1_name, pc1_name, port_a=pc1_sw_port, port_b="FastEthernet0", vlan=vlan_a)
    if has_voice_fault:
        net.devices[sw1_name].ports[pc1_sw_port].voice_vlan = vlan_b

    net.connect(sw2_name, pc2_name, port_a=pc2_sw_port, port_b="FastEthernet0", vlan=vlan_a)
    net.connect(sw2_name, pc3_name, port_a=pc3_sw_port, port_b="FastEthernet0", vlan=vlan_b)
    if num_clients == 4:
        net.connect(pc4_sw_name, pc4_name, port_a=pc4_sw_port, port_b="FastEthernet0", vlan=vlan_b)
    net.connect(sw1_name, srv_name, port_a=srv_sw_port, port_b="FastEthernet0", vlan=vlan_b)

    # Inject Level 2 faults
    injected_faults: list[FaultRecord] = []
    post_xml_mutations: list[Callable[[ET.Element], None]] = []

    for idx, ftype in enumerate(chosen_types):
        ctx = Level2FaultContext(
            idx=idx,
            net=net,
            post_xml_mutations=post_xml_mutations,
            rtr_name=rtr_name,
            sw1_name=sw1_name,
            sw2_name=sw2_name,
            srv_name=srv_name,
            vlan_a=vlan_a,
            vlan_a_name=vlan_a_name,
            subnet_a_cidr=subnet_a_cidr,
            gw_a=gw_a,
            vlan_b=vlan_b,
            vlan_b_name=vlan_b_name,
            subnet_b_cidr=subnet_b_cidr,
            gw_b=gw_b,
            netmask=netmask,
            prefix_len=prefix_len,
            pc_vlan_a_sw2=pc2_name,
            pc_vlan_a_sw2_port=pc2_sw_port,
            pc_vlan_a_sw2_ip=pc2_ip,
            pc_vlan_b_sw2=pc3_name,
            pc_vlan_b_sw2_port=pc3_sw_port,
            pc_vlan_b_sw2_ip=pc3_ip,
            pc_vlan_a_sw1=pc1_name,
            pc_vlan_a_sw1_port=pc1_sw_port,
            sw1_to_sw2_port=sw1_to_sw2_port,
            sw2_to_sw1_port=sw2_to_sw1_port,
            sw1_ec_port2=sw1_ec_port2,
            sw2_ec_port2=sw2_ec_port2,
            rtr_roas_port=rtr_roas_port,
            sw1_to_rtr_port=sw1_to_rtr_port,
        )
        injected_faults.append(inject_level2_fault(ftype, ctx))

    out_folder = Path(out_dir)
    out_folder.mkdir(parents=True, exist_ok=True)
    ticket_num = rng.randint(1000, 9999)
    ticket_id = f"NOC-{ticket_num}"
    pkt_path = out_folder / f"level2_{ticket_id.lower()}.pkt"

    lab = net.build_lab()
    for post_fn in post_xml_mutations:
        post_fn(lab.base)

    xml_bytes = ET.tostring(lab.base, encoding="unicode").encode("utf-8")
    encode(str(pkt_path), xml_bytes, "pkt")

    scenario_title = (
        f"[L2 VLAN/ROAS] {cfg.company_name}: {dept_name} "
        f"(VLAN {vlan_a}: {subnet_a_cidr} | VLAN {vlan_b}: {subnet_b_cidr}) — {layout_label}"
    )
    symptoms_combined = "  • " + "\n  • ".join(f.symptom for f in injected_faults)

    # Canvas nodes & edges
    crx, cry = pt_to_canvas(*pt_pos["rtr"])
    cs1x, cs1y = pt_to_canvas(*pt_pos["sw1"])
    cs2x, cs2y = pt_to_canvas(*pt_pos["sw2"])
    canvas_nodes = [
        {
            "name": rtr_name,
            "role": "router",
            "sub": f".{vlan_a}: {gw_a}/{prefix_len}\n.{vlan_b}: {gw_b}/{prefix_len}",
            "x": crx,
            "y": cry,
        },
        {
            "name": sw1_name,
            "role": "switch",
            "sub": f"Vlan{vlan_a}: {sw1_ip}\nVLANs {vlan_a},{vlan_b}",
            "x": cs1x,
            "y": cs1y,
        },
        {
            "name": sw2_name,
            "role": "switch",
            "sub": f"Vlan{vlan_a}: {sw2_ip}\nVLANs {vlan_a},{vlan_b}",
            "x": cs2x,
            "y": cs2y,
        },
    ]
    canvas_edges = [
        (rtr_name, sw1_name, "Gi0/0 (RoaS)", "Gi0/1 (Trunk)"),
        (
            sw1_name,
            sw2_name,
            "Po1 (Gi0/2,Fa0/23)" if has_ec_fault else "Gi0/2 (Trunk)",
            "Po1 (Gi0/1,Fa0/23)" if has_ec_fault else "Gi0/1 (Trunk)",
        ),
    ]
    if num_switches >= 3:
        cs3x, cs3y = pt_to_canvas(*pt_pos["sw3"])
        canvas_nodes.append(
            {
                "name": sw3_name,
                "role": "switch",
                "sub": f"Vlan{vlan_a}: {sw3_ip}\nVLANs {vlan_a},{vlan_b}",
                "x": cs3x,
                "y": cs3y,
            }
        )
        canvas_edges.append((sw1_name, sw3_name, "Fa0/24 (Trunk)", "Gi0/1 (Trunk)"))

    client_canvas_items = [
        (pc1_name, "c0", sw1_name, "Fa0/1", vlan_a, pc1_ip, gw_a),
        (pc2_name, "c1", sw2_name, "Fa0/1", vlan_a, pc2_ip, gw_a),
        (pc3_name, "c2", sw2_name, "Fa0/2", vlan_b, pc3_ip, gw_b),
    ]
    if num_clients == 4:
        client_canvas_items.append(
            (pc4_name, "c3", pc4_sw_name, pc4_sw_port.replace("FastEthernet", "Fa"), vlan_b, pc4_ip, gw_b)
        )

    for c_name, pos_key, sw_n, short_port, v_id, c_ip, c_gw in client_canvas_items:
        cnx, cny = pt_to_canvas(*pt_pos[pos_key])
        canvas_nodes.append(
            {
                "name": c_name,
                "role": "pc",
                "sub": f"VLAN {v_id}: {c_ip}/{prefix_len}\nGW: {c_gw}",
                "x": cnx,
                "y": cny,
            }
        )
        canvas_edges.append((sw_n, c_name, f"{short_port} (V{v_id})", "Fa0"))

    csrvx, csrvy = pt_to_canvas(*pt_pos["srv"])
    canvas_nodes.append(
        {
            "name": srv_name,
            "role": "server",
            "sub": f"VLAN {vlan_b}: {srv_ip}/{prefix_len}\nGW: {gw_b}",
            "x": csrvx,
            "y": csrvy,
        }
    )
    canvas_edges.append((sw1_name, srv_name, f"Fa0/2 (V{vlan_b})", "Fa0"))

    return ChallengeTicket(
        ticket_id=ticket_id,
        level=2,
        level_name=f"Level 2 — {cfg.company_name} Switching, VLANs, 802.1Q Trunks & RoaS",
        scenario_title=scenario_title,
        symptom_summary=symptoms_combined,
        pkt_path=pkt_path,
        subnet_cidr=f"VLAN {vlan_a}: {subnet_a_cidr} | VLAN {vlan_b}: {subnet_b_cidr}",
        device_rows=device_rows,
        link_rows=link_rows,
        service_notes=[
            f"Physical Floorplan Layout: {layout_label}.",
            f"Assigned Engineer: {cfg.player_name} | Organization: {cfg.company_name} — {dept_name} ({code}).",
            f"VLAN {vlan_a} ({vlan_a_name}): Subnet {subnet_a_cidr} (Mask {netmask}), Default Gateway {gw_a} on {rtr_name} {rtr_roas_port}.{vlan_a}.",
            f"VLAN {vlan_b} ({vlan_b_name}): Subnet {subnet_b_cidr} (Mask {netmask}), Default Gateway {gw_b} on {rtr_name} {rtr_roas_port}.{vlan_b}.",
            f"802.1Q Trunks: {sw1_name} {sw1_to_rtr_port} <-> {rtr_name} {rtr_roas_port} (RoaS) and {sw1_name} {sw1_to_sw2_port} <-> {sw2_name} {sw2_to_sw1_port} (Native VLAN 1).",
            f"Internal DNS/Web Server ({srv_name}) is in VLAN {vlan_b} at {srv_ip} (all hosts use {srv_ip} for DNS).",
        ],
        faults=injected_faults,
        canvas_nodes=canvas_nodes,
        canvas_edges=canvas_edges,
    )


def generate_build_mission(
    out_dir: str | Path,
    *,
    level: int = 1,
    addressing_help: str = "guided",
    cabling_mode: str = "uncabled",
    seed: int | None = None,
    settings: GameSettings | None = None,
) -> ChallengeTicket:
    """Generate a Mode 2 ('Build Network from Scratch') greenfield commissioning mission for Level 1 or Level 2."""
    cfg = settings if settings is not None else GameSettings.load()
    rng = random.Random(seed)
    code, dept_name = rng.choice(cfg.departments)
    is_subnet_challenge = "subnetting" in addressing_help.lower() or "challenge" in addressing_help.lower()
    is_uncabled = "uncabled" in cabling_mode.lower() or "scratch" in cabling_mode.lower()

    out_folder = Path(out_dir)
    out_folder.mkdir(parents=True, exist_ok=True)
    ticket_num = rng.randint(1000, 9999)
    ticket_id = f"BLD-{ticket_num}"

    if level == 1:
        # Level 1 Build Mission: Single-LAN Branch Bring-Up
        base_b3 = rng.choice([10, 20, 30, 40, 50, 88])
        prefix_len = rng.choice([24, 25, 26])
        net_obj = list(ipaddress.IPv4Network(f"192.168.{base_b3}.0/24").subnets(new_prefix=prefix_len))[0]
        netmask = str(net_obj.netmask)
        subnet_cidr = str(net_obj)
        hosts = [str(ip) for ip in net_obj.hosts()]

        gw_ip = hosts[0]
        sw_ip = hosts[1]
        pc1_ip = hosts[9]
        pc2_ip = hosts[10]
        srv_ip = hosts[-2]

        rtr_name = f"{code}-R1"
        sw_name = f"{code}-SW1"
        pc1_name = f"{code}-PC1"
        pc2_name = f"{code}-PC2"
        srv_name = f"{code}-SRV1"

        chosen_arch = rng.choice(["left_to_right_pipeline", "radial_star_office", "right_to_left_backoffice"])
        layout_label, _, _, pt_pos = build_layout_positions(chosen_arch, 2)

        def _fmt_ip(exact_ip: str, rule_desc: str) -> str:
            return f"{rule_desc} ({subnet_cidr})" if is_subnet_challenge else exact_ip

        def _fmt_mask() -> str:
            return f"/{prefix_len} mask" if is_subnet_challenge else netmask

        device_rows = [
            BlueprintDeviceRow(
                device=rtr_name,
                model="2911",
                role="Default Gateway Router",
                interface="GigabitEthernet0/0",
                expected_ip=_fmt_ip(gw_ip, "1st usable host"),
                expected_mask=_fmt_mask(),
                expected_gateway="-",
                expected_dns="-",
                notes="Configure IP & 'no shutdown'",
            ),
            BlueprintDeviceRow(
                device=sw_name,
                model="2960-24TT",
                role="Access Switch",
                interface="Vlan1",
                expected_ip=_fmt_ip(sw_ip, "2nd usable host"),
                expected_mask=_fmt_mask(),
                expected_gateway=_fmt_ip(gw_ip, "1st usable host"),
                expected_dns="-",
                notes="Configure interface Vlan1 ('no shutdown') & 'ip default-gateway'",
            ),
            BlueprintDeviceRow(
                device=pc1_name,
                model="PC-PT",
                role="Workstation 1",
                interface="FastEthernet0",
                expected_ip=_fmt_ip(pc1_ip, "10th usable host"),
                expected_mask=_fmt_mask(),
                expected_gateway=_fmt_ip(gw_ip, "1st usable host"),
                expected_dns=_fmt_ip(srv_ip, "2nd-to-last usable host"),
                notes="Static IPv4 on Desktop -> IP Configuration",
            ),
            BlueprintDeviceRow(
                device=pc2_name,
                model="PC-PT",
                role="Workstation 2",
                interface="FastEthernet0",
                expected_ip=_fmt_ip(pc2_ip, "11th usable host"),
                expected_mask=_fmt_mask(),
                expected_gateway=_fmt_ip(gw_ip, "1st usable host"),
                expected_dns=_fmt_ip(srv_ip, "2nd-to-last usable host"),
                notes="Static IPv4 on Desktop -> IP Configuration",
            ),
            BlueprintDeviceRow(
                device=srv_name,
                model="Server-PT",
                role="Internal DNS/Web Server",
                interface="FastEthernet0",
                expected_ip=_fmt_ip(srv_ip, "2nd-to-last usable host"),
                expected_mask=_fmt_mask(),
                expected_gateway=_fmt_ip(gw_ip, "1st usable host"),
                expected_dns=_fmt_ip(srv_ip, "2nd-to-last usable host"),
                notes="Static IPv4 on Desktop -> IP Configuration",
            ),
        ]

        link_rows = [
            BlueprintLinkRow(rtr_name, "GigabitEthernet0/0", sw_name, "GigabitEthernet0/1", "Copper Straight-Through", "VLAN 1 Uplink"),
            BlueprintLinkRow(sw_name, "FastEthernet0/1", pc1_name, "FastEthernet0", "Copper Straight-Through", "Access VLAN 1"),
            BlueprintLinkRow(sw_name, "FastEthernet0/2", pc2_name, "FastEthernet0", "Copper Straight-Through", "Access VLAN 1"),
            BlueprintLinkRow(sw_name, "FastEthernet0/3", srv_name, "FastEthernet0", "Copper Straight-Through", "Access VLAN 1"),
        ]

        # Build unconfigured .pkt
        net = SimpleNetwork()
        net.add_router(rtr_name, model="2911", x=pt_pos["rtr"][0], y=pt_pos["rtr"][1])
        net.add_switch(sw_name, model="2960-24TT", x=pt_pos["sw1"][0], y=pt_pos["sw1"][1])
        net.add_pc(pc1_name, x=pt_pos["c0"][0], y=pt_pos["c0"][1])
        net.add_pc(pc2_name, x=pt_pos["c1"][0], y=pt_pos["c1"][1])
        net.add_server(srv_name, x=pt_pos["srv"][0], y=pt_pos["srv"][1])

        net.devices[rtr_name].ports["GigabitEthernet0/0"] = PortConfig(port="GigabitEthernet0/0", shutdown=True)
        if not is_uncabled:
            net.connect(rtr_name, sw_name, port_a="GigabitEthernet0/0", port_b="GigabitEthernet0/1")
            net.connect(sw_name, pc1_name, port_a="FastEthernet0/1", port_b="FastEthernet0")
            net.connect(sw_name, pc2_name, port_a="FastEthernet0/2", port_b="FastEthernet0")
            net.connect(sw_name, srv_name, port_a="FastEthernet0/3", port_b="FastEthernet0")
            net.devices[rtr_name].ports["GigabitEthernet0/0"].shutdown = True

        pkt_path = out_folder / f"build_lvl1_{ticket_id.lower()}.pkt"
        lab = net.build_lab()
        xml_bytes = ET.tostring(lab.base, encoding="unicode").encode("utf-8")
        encode(str(pkt_path), xml_bytes, "pkt")

        stages: list[FaultRecord] = []
        if is_uncabled:
            stages.append(
                FaultRecord(
                    fault_id="STAGE1_CABLING",
                    title="Stage 1: Physical Copper Cabling",
                    category="CCNA 1.3 — Physical Layer Cabling",
                    device=sw_name,
                    interface="Gi0/1, Fa0/1-3",
                    symptom=f"Wire {rtr_name}, {sw_name}, {pc1_name}, {pc2_name}, and {srv_name} according to '2. Expected Cabling & Ports'.",
                    expected_state="All 4 copper straight-through links connected on exact blueprint ports",
                    faulty_state="Hardware uncabled on floorplan",
                    hints=[
                        f"Hint 1: Connect {rtr_name} GigabitEthernet0/0 to {sw_name} GigabitEthernet0/1.",
                        f"Hint 2: Connect {sw_name} FastEthernet0/1 -> {pc1_name}, FastEthernet0/2 -> {pc2_name}, and FastEthernet0/3 -> {srv_name}.",
                        "Hint 3: Use Copper Straight-Through cables from Packet Tracer's Connections palette.",
                    ],
                    explanation="All four physical links must be connected on their designated interfaces before Layer 2/3 bring-up.",
                    fix_steps=[
                        f"1. Cable {rtr_name} Gi0/0 <-> {sw_name} Gi0/1.",
                        f"2. Cable {sw_name} Fa0/1 <-> {pc1_name} Fa0, Fa0/2 <-> {pc2_name} Fa0, and Fa0/3 <-> {srv_name} Fa0.",
                    ],
                    verify_spec={
                        "type": "all_links_present",
                        "device": sw_name,
                        "expected_links": [
                            {"dev_a": rtr_name, "port_a": "GigabitEthernet0/0", "dev_b": sw_name, "port_b": "GigabitEthernet0/1"},
                            {"dev_a": sw_name, "port_a": "FastEthernet0/1", "dev_b": pc1_name, "port_b": "FastEthernet0"},
                            {"dev_a": sw_name, "port_a": "FastEthernet0/2", "dev_b": pc2_name, "port_b": "FastEthernet0"},
                            {"dev_a": sw_name, "port_a": "FastEthernet0/3", "dev_b": srv_name, "port_b": "FastEthernet0"},
                        ],
                    },
                )
            )

        stages.extend(
            [
                FaultRecord(
                    fault_id="STAGE2_ROUTER_GW",
                    title=f"Stage 2: Default Gateway Router ({rtr_name} Gi0/0)",
                    category="CCNA 1.4 / 1.6 — Router Interface Bring-Up",
                    device=rtr_name,
                    interface="GigabitEthernet0/0",
                    symptom=f"Configure {rtr_name} GigabitEthernet0/0 with IP {gw_ip}/{prefix_len} ({netmask}) and bring the port UP ('no shutdown').",
                    expected_state=f"{rtr_name} Gi0/0: IP {gw_ip} {netmask}, no shutdown",
                    faulty_state=f"{rtr_name} Gi0/0: unconfigured & shutdown",
                    hints=[
                        f"Hint 1: Subnet {subnet_cidr} uses mask {netmask}. The 1st usable host is {gw_ip}.",
                        f"Hint 2: On {rtr_name} CLI, enter 'interface GigabitEthernet0/0', 'ip address {gw_ip} {netmask}', and 'no shutdown'.",
                    ],
                    explanation=f"{rtr_name} GigabitEthernet0/0 serves as the default gateway ({gw_ip}) for {subnet_cidr}.",
                    fix_steps=[
                        f"1. On {rtr_name} CLI:\n     enable\n     configure terminal\n     interface GigabitEthernet0/0\n     ip address {gw_ip} {netmask}\n     no shutdown\n     end",
                    ],
                    verify_spec={
                        "type": "router_port_up",
                        "device": rtr_name,
                        "interface": "GigabitEthernet0/0",
                        "expected_ip": gw_ip,
                        "expected_mask": netmask,
                    },
                ),
                FaultRecord(
                    fault_id="STAGE3_SWITCH_SVI",
                    title=f"Stage 3: Switch Management SVI ({sw_name} Vlan1)",
                    category="CCNA 2.1 — Switch Management SVI & Default Gateway",
                    device=sw_name,
                    interface="Vlan1",
                    symptom=f"Configure {sw_name} interface Vlan1 with {sw_ip} {netmask} ('no shutdown') and 'ip default-gateway {gw_ip}'.",
                    expected_state=f"{sw_name} Vlan1: {sw_ip} {netmask} (UP), default-gateway {gw_ip}",
                    faulty_state=f"{sw_name} Vlan1: unconfigured",
                    hints=[
                        f"Hint 1: The 2nd usable host in {subnet_cidr} is {sw_ip}.",
                        f"Hint 2: On {sw_name} CLI, configure 'interface Vlan1' -> 'ip address {sw_ip} {netmask}' -> 'no shutdown' and global 'ip default-gateway {gw_ip}'.",
                    ],
                    explanation=f"{sw_name} requires management SVI Vlan1 at {sw_ip}/{prefix_len} and default-gateway {gw_ip}.",
                    fix_steps=[
                        f"1. On {sw_name} CLI:\n     enable\n     configure terminal\n     interface Vlan1\n     ip address {sw_ip} {netmask}\n     no shutdown\n     exit\n     ip default-gateway {gw_ip}\n     end",
                    ],
                    verify_spec={
                        "type": "switch_mgmt_svi",
                        "device": sw_name,
                        "svi_interface": "Vlan1",
                        "expected_ip": sw_ip,
                        "expected_mask": netmask,
                        "expected_gateway": gw_ip,
                    },
                ),
                FaultRecord(
                    fault_id="STAGE4_END_HOSTS",
                    title=f"Stage 4: Workstations & Server Addressing ({pc1_name}, {pc2_name}, {srv_name})",
                    category="CCNA 1.11 — Endpoint IPv4, Mask & Gateway",
                    device=pc1_name,
                    interface="FastEthernet0",
                    symptom=f"Assign static IPv4, Subnet Mask ({netmask}), Default Gateway ({gw_ip}), and DNS ({srv_ip}) on {pc1_name}, {pc2_name}, and {srv_name}.",
                    expected_state=f"{pc1_name}={pc1_ip}, {pc2_name}={pc2_ip}, {srv_name}={srv_ip} (Mask {netmask}, GW {gw_ip})",
                    faulty_state="Endpoints unconfigured",
                    hints=[
                        f"Hint 1: {pc1_name} gets {pc1_ip}, {pc2_name} gets {pc2_ip}, and {srv_name} gets {srv_ip} (all mask {netmask}, GW {gw_ip}, DNS {srv_ip}).",
                    ],
                    explanation="All endpoints must be configured with their static IPv4 address, mask, default gateway, and DNS server.",
                    fix_steps=[
                        f"1. Configure {pc1_name}: IP {pc1_ip}, Mask {netmask}, GW {gw_ip}, DNS {srv_ip}.",
                        f"2. Configure {pc2_name}: IP {pc2_ip}, Mask {netmask}, GW {gw_ip}, DNS {srv_ip}.",
                        f"3. Configure {srv_name}: IP {srv_ip}, Mask {netmask}, GW {gw_ip}, DNS {srv_ip}.",
                    ],
                    verify_spec={
                        "type": "all_hosts_ip_gw",
                        "device": pc1_name,
                        "hosts": [
                            {"device": pc1_name, "expected_ip": pc1_ip, "expected_mask": netmask, "expected_gateway": gw_ip},
                            {"device": pc2_name, "expected_ip": pc2_ip, "expected_mask": netmask, "expected_gateway": gw_ip},
                            {"device": srv_name, "expected_ip": srv_ip, "expected_mask": netmask, "expected_gateway": gw_ip},
                        ],
                    },
                ),
            ]
        )

        crx, cry = pt_to_canvas(*pt_pos["rtr"])
        csx, csy = pt_to_canvas(*pt_pos["sw1"])
        c0x, c0y = pt_to_canvas(*pt_pos["c0"])
        c1x, c1y = pt_to_canvas(*pt_pos["c1"])
        csrvx, csrvy = pt_to_canvas(*pt_pos["srv"])
        canvas_nodes = [
            {"name": rtr_name, "role": "router", "sub": f"Gi0/0: {gw_ip}/{prefix_len}", "x": crx, "y": cry},
            {"name": sw_name, "role": "switch", "sub": f"Vlan1: {sw_ip}/{prefix_len}", "x": csx, "y": csy},
            {"name": pc1_name, "role": "pc", "sub": f"{pc1_ip}/{prefix_len}\nGW: {gw_ip}", "x": c0x, "y": c0y},
            {"name": pc2_name, "role": "pc", "sub": f"{pc2_ip}/{prefix_len}\nGW: {gw_ip}", "x": c1x, "y": c1y},
            {"name": srv_name, "role": "server", "sub": f"{srv_ip}/{prefix_len}\nGW: {gw_ip}", "x": csrvx, "y": csrvy},
        ]
        canvas_edges = [
            (rtr_name, sw_name, "Gi0/0", "Gi0/1"),
            (sw_name, pc1_name, "Fa0/1", "Fa0"),
            (sw_name, pc2_name, "Fa0/2", "Fa0"),
            (sw_name, srv_name, "Fa0/3", "Fa0"),
        ]

        return ChallengeTicket(
            ticket_id=ticket_id,
            level=1,
            level_name=f"Mode 2 Build (Level 1) — {cfg.company_name} Branch LAN Bring-Up",
            scenario_title=f"[BUILD LVL 1] {cfg.company_name}: {dept_name} ({subnet_cidr}) — {layout_label}",
            symptom_summary="  • " + "\n  • ".join(s.symptom for s in stages),
            pkt_path=pkt_path,
            subnet_cidr=subnet_cidr,
            device_rows=device_rows,
            link_rows=link_rows,
            service_notes=[
                f"Greenfield Build Mission (Level 1) — Addressing Help: {addressing_help} | Hardware: {cabling_mode}.",
                f"Allocated Subnet: {subnet_cidr} (Mask {netmask}, Usable Range {hosts[0]} – {hosts[-1]}).",
            ],
            faults=stages,
            canvas_nodes=canvas_nodes,
            canvas_edges=canvas_edges,
        )

    # ------------------------------------------------------------------
    # Level 2 Build Mission: Dual-Subnet FLSM, VLANs & 802.1Q RoaS
    # ------------------------------------------------------------------
    vlan_a, vlan_a_name, net_a, vlan_b, vlan_b_name, net_b = _pick_level2_vlan_subnets(rng, code)
    prefix_len = net_a.prefixlen
    netmask = str(net_a.netmask)
    subnet_a_cidr = str(net_a)
    subnet_b_cidr = str(net_b)
    hosts_a = [str(ip) for ip in net_a.hosts()]
    hosts_b = [str(ip) for ip in net_b.hosts()]

    gw_a = hosts_a[0]
    sw1_ip = hosts_a[1]
    sw2_ip = hosts_a[2]
    pc1_ip = hosts_a[9]
    pc2_ip = hosts_a[10]

    gw_b = hosts_b[0]
    pc3_ip = hosts_b[9]
    srv_ip = hosts_b[-2]

    rtr_name = f"{code}-R1"
    sw1_name = f"{code}-SW1"
    sw2_name = f"{code}-SW2"
    pc1_name = f"{code}-PC1"
    pc2_name = f"{code}-PC2"
    pc3_name = f"{code}-PC3"
    srv_name = f"{code}-SRV1"

    chosen_arch = rng.choice(["mdf_idf_two_closet", "server_cage_and_user_pod", "multi_floor_riser", "linear_warehouse_bays", "u_shaped_courtyard"])
    layout_label, _, _, pt_pos = build_layout_positions(chosen_arch, 3)

    def _fmt_l2_ip(exact_ip: str, rule_desc: str) -> str:
        return rule_desc if is_subnet_challenge else exact_ip

    def _fmt_l2_mask() -> str:
        return f"/{prefix_len} mask" if is_subnet_challenge else netmask

    device_rows = [
        BlueprintDeviceRow(
            rtr_name, "2911", f"RoaS Gateway (VLAN {vlan_a})", f"GigabitEthernet0/0.{vlan_a}",
            _fmt_l2_ip(gw_a, f"1st usable in {subnet_a_cidr}"), _fmt_l2_mask(), "-", "-",
            f"encapsulation dot1Q {vlan_a}, parent Gi0/0 UP",
        ),
        BlueprintDeviceRow(
            rtr_name, "2911", f"RoaS Gateway (VLAN {vlan_b})", f"GigabitEthernet0/0.{vlan_b}",
            _fmt_l2_ip(gw_b, f"1st usable in {subnet_b_cidr}"), _fmt_l2_mask(), "-", "-",
            f"encapsulation dot1Q {vlan_b}, parent Gi0/0 UP",
        ),
        BlueprintDeviceRow(
            sw1_name, "2960-24TT", "MDF Core Switch", f"Vlan{vlan_a}",
            _fmt_l2_ip(sw1_ip, f"2nd usable in {subnet_a_cidr}"), _fmt_l2_mask(), _fmt_l2_ip(gw_a, f"1st usable in {subnet_a_cidr}"), "-",
            f"Create VLANs {vlan_a},{vlan_b}; Trunks Gi0/1 & Gi0/2",
        ),
        BlueprintDeviceRow(
            sw2_name, "2960-24TT", "IDF Access Switch", f"Vlan{vlan_a}",
            _fmt_l2_ip(sw2_ip, f"3rd usable in {subnet_a_cidr}"), _fmt_l2_mask(), _fmt_l2_ip(gw_a, f"1st usable in {subnet_a_cidr}"), "-",
            f"Create VLANs {vlan_a},{vlan_b}; Trunk Gi0/1",
        ),
        BlueprintDeviceRow(
            pc1_name, "PC-PT", f"VLAN {vlan_a} Workstation", "FastEthernet0",
            _fmt_l2_ip(pc1_ip, f"10th usable in {subnet_a_cidr}"), _fmt_l2_mask(), _fmt_l2_ip(gw_a, f"1st usable in {subnet_a_cidr}"), _fmt_l2_ip(srv_ip, f"2nd-to-last in {subnet_b_cidr}"),
            f"On {sw1_name} Fa0/1 (Access VLAN {vlan_a})",
        ),
        BlueprintDeviceRow(
            pc2_name, "PC-PT", f"VLAN {vlan_a} Workstation", "FastEthernet0",
            _fmt_l2_ip(pc2_ip, f"11th usable in {subnet_a_cidr}"), _fmt_l2_mask(), _fmt_l2_ip(gw_a, f"1st usable in {subnet_a_cidr}"), _fmt_l2_ip(srv_ip, f"2nd-to-last in {subnet_b_cidr}"),
            f"On {sw2_name} Fa0/1 (Access VLAN {vlan_a})",
        ),
        BlueprintDeviceRow(
            pc3_name, "PC-PT", f"VLAN {vlan_b} Workstation", "FastEthernet0",
            _fmt_l2_ip(pc3_ip, f"10th usable in {subnet_b_cidr}"), _fmt_l2_mask(), _fmt_l2_ip(gw_b, f"1st usable in {subnet_b_cidr}"), _fmt_l2_ip(srv_ip, f"2nd-to-last in {subnet_b_cidr}"),
            f"On {sw2_name} Fa0/2 (Access VLAN {vlan_b})",
        ),
        BlueprintDeviceRow(
            srv_name, "Server-PT", f"VLAN {vlan_b} Server", "FastEthernet0",
            _fmt_l2_ip(srv_ip, f"2nd-to-last in {subnet_b_cidr}"), _fmt_l2_mask(), _fmt_l2_ip(gw_b, f"1st usable in {subnet_b_cidr}"), _fmt_l2_ip(srv_ip, f"2nd-to-last in {subnet_b_cidr}"),
            f"On {sw1_name} Fa0/2 (Access VLAN {vlan_b})",
        ),
    ]

    link_rows = [
        BlueprintLinkRow(rtr_name, "GigabitEthernet0/0", sw1_name, "GigabitEthernet0/1", "Copper Straight-Through", f"802.1Q Trunk (VLANs {vlan_a},{vlan_b})"),
        BlueprintLinkRow(sw1_name, "GigabitEthernet0/2", sw2_name, "GigabitEthernet0/1", "Copper Cross-Over", f"802.1Q Trunk (VLANs {vlan_a},{vlan_b})"),
        BlueprintLinkRow(sw1_name, "FastEthernet0/1", pc1_name, "FastEthernet0", "Copper Straight-Through", f"Access VLAN {vlan_a}"),
        BlueprintLinkRow(sw1_name, "FastEthernet0/2", srv_name, "FastEthernet0", "Copper Straight-Through", f"Access VLAN {vlan_b}"),
        BlueprintLinkRow(sw2_name, "FastEthernet0/1", pc2_name, "FastEthernet0", "Copper Straight-Through", f"Access VLAN {vlan_a}"),
        BlueprintLinkRow(sw2_name, "FastEthernet0/2", pc3_name, "FastEthernet0", "Copper Straight-Through", f"Access VLAN {vlan_b}"),
    ]

    net = SimpleNetwork()
    net.add_router(rtr_name, model="2911", x=pt_pos["rtr"][0], y=pt_pos["rtr"][1])
    net.add_switch(sw1_name, model="2960-24TT", x=pt_pos["sw1"][0], y=pt_pos["sw1"][1])
    net.add_switch(sw2_name, model="2960-24TT", x=pt_pos["sw2"][0], y=pt_pos["sw2"][1])
    net.add_pc(pc1_name, x=pt_pos["c0"][0], y=pt_pos["c0"][1])
    net.add_pc(pc2_name, x=pt_pos["c1"][0], y=pt_pos["c1"][1])
    net.add_pc(pc3_name, x=pt_pos["c2"][0], y=pt_pos["c2"][1])
    net.add_server(srv_name, x=pt_pos["srv"][0], y=pt_pos["srv"][1])

    net.devices[rtr_name].ports["GigabitEthernet0/0"] = PortConfig(port="GigabitEthernet0/0", shutdown=True)
    if not is_uncabled:
        net.connect(rtr_name, sw1_name, port_a="GigabitEthernet0/0", port_b="GigabitEthernet0/1")
        net.connect(sw1_name, sw2_name, port_a="GigabitEthernet0/2", port_b="GigabitEthernet0/1")
        net.connect(sw1_name, pc1_name, port_a="FastEthernet0/1", port_b="FastEthernet0")
        net.connect(sw1_name, srv_name, port_a="FastEthernet0/2", port_b="FastEthernet0")
        net.connect(sw2_name, pc2_name, port_a="FastEthernet0/1", port_b="FastEthernet0")
        net.connect(sw2_name, pc3_name, port_a="FastEthernet0/2", port_b="FastEthernet0")
        net.devices[rtr_name].ports["GigabitEthernet0/0"].shutdown = True

    pkt_path = out_folder / f"build_lvl2_{ticket_id.lower()}.pkt"
    lab = net.build_lab()
    xml_bytes = ET.tostring(lab.base, encoding="unicode").encode("utf-8")
    encode(str(pkt_path), xml_bytes, "pkt")

    stages_l2: list[FaultRecord] = []
    if is_uncabled:
        stages_l2.append(
            FaultRecord(
                fault_id="STAGE1_L2_CABLING",
                title="Stage 1: Physical Campus Cabling",
                category="CCNA 1.3 — Physical Layer Cabling",
                device=sw1_name,
                interface="Gi0/1-2, Fa0/1-2",
                symptom=f"Wire all 6 links between {rtr_name}, {sw1_name}, {sw2_name}, {pc1_name}, {pc2_name}, {pc3_name}, and {srv_name}.",
                expected_state="All 6 physical links connected per Cabling Blueprint",
                faulty_state="Hardware uncabled",
                hints=[
                    f"Hint 1: Connect {rtr_name} Gi0/0 <-> {sw1_name} Gi0/1 and {sw1_name} Gi0/2 <-> {sw2_name} Gi0/1.",
                    f"Hint 2: Connect {sw1_name} Fa0/1->{pc1_name}, Fa0/2->{srv_name}; {sw2_name} Fa0/1->{pc2_name}, Fa0/2->{pc3_name}.",
                ],
                explanation="All physical cables must match the Expected Cabling & Ports specification.",
                fix_steps=["1. Connect all 6 links per the Expected Cabling & Ports tab."],
                verify_spec={
                    "type": "all_links_present",
                    "device": sw1_name,
                    "expected_links": [
                        {"dev_a": rtr_name, "port_a": "GigabitEthernet0/0", "dev_b": sw1_name, "port_b": "GigabitEthernet0/1"},
                        {"dev_a": sw1_name, "port_a": "GigabitEthernet0/2", "dev_b": sw2_name, "port_b": "GigabitEthernet0/1"},
                        {"dev_a": sw1_name, "port_a": "FastEthernet0/1", "dev_b": pc1_name, "port_b": "FastEthernet0"},
                        {"dev_a": sw1_name, "port_a": "FastEthernet0/2", "dev_b": srv_name, "port_b": "FastEthernet0"},
                        {"dev_a": sw2_name, "port_a": "FastEthernet0/1", "dev_b": pc2_name, "port_b": "FastEthernet0"},
                        {"dev_a": sw2_name, "port_a": "FastEthernet0/2", "dev_b": pc3_name, "port_b": "FastEthernet0"},
                    ],
                },
            )
        )

    stages_l2.extend(
        [
            FaultRecord(
                fault_id="STAGE2_ROAS",
                title=f"Stage 2: Router-on-a-Stick Subinterfaces on {rtr_name}",
                category="CCNA 3.1 — Router-on-a-Stick Inter-VLAN Routing",
                device=rtr_name,
                interface=f"Gi0/0, Gi0/0.{vlan_a}, Gi0/0.{vlan_b}",
                symptom=f"Enable {rtr_name} Gi0/0 ('no shutdown') and configure 802.1Q subinterfaces Gi0/0.{vlan_a} ({gw_a}/{prefix_len}) and Gi0/0.{vlan_b} ({gw_b}/{prefix_len}).",
                expected_state=f"Gi0/0 UP; .{vlan_a}=dot1Q {vlan_a} ({gw_a} {netmask}); .{vlan_b}=dot1Q {vlan_b} ({gw_b} {netmask})",
                faulty_state="Gi0/0 shutdown and subinterfaces missing",
                hints=[
                    f"Hint 1: On {rtr_name}, run 'interface GigabitEthernet0/0' -> 'no shutdown'.",
                    f"Hint 2: Configure 'interface GigabitEthernet0/0.{vlan_a}' -> 'encapsulation dot1Q {vlan_a}' -> 'ip address {gw_a} {netmask}'.",
                    f"Hint 3: Configure 'interface GigabitEthernet0/0.{vlan_b}' -> 'encapsulation dot1Q {vlan_b}' -> 'ip address {gw_b} {netmask}'.",
                ],
                explanation="Router-on-a-Stick requires the physical parent port UP and subinterfaces tagged with 802.1Q for each VLAN.",
                fix_steps=[
                    f"1. On {rtr_name} CLI:\n     enable\n     configure terminal\n     interface GigabitEthernet0/0\n     no shutdown\n     interface GigabitEthernet0/0.{vlan_a}\n     encapsulation dot1Q {vlan_a}\n     ip address {gw_a} {netmask}\n     interface GigabitEthernet0/0.{vlan_b}\n     encapsulation dot1Q {vlan_b}\n     ip address {gw_b} {netmask}\n     end",
                ],
                verify_spec={
                    "type": "roas_all_subinterfaces",
                    "device": rtr_name,
                    "parent_port": "GigabitEthernet0/0",
                    "subinterfaces": [
                        {"vlan_id": vlan_a, "expected_ip": gw_a, "expected_mask": netmask},
                        {"vlan_id": vlan_b, "expected_ip": gw_b, "expected_mask": netmask},
                    ],
                },
            ),
            FaultRecord(
                fault_id="STAGE3_SW1_VLANS_TRUNKS",
                title=f"Stage 3: MDF Switch {sw1_name} VLANs, Access Ports & 802.1Q Trunks",
                category="CCNA 2.1 / 2.2 — Switch VLANs & Trunks",
                device=sw1_name,
                interface="Gi0/1-2, Fa0/1-2",
                symptom=f"On {sw1_name}, create VLANs {vlan_a} & {vlan_b}, set Fa0/1 to VLAN {vlan_a}, Fa0/2 to VLAN {vlan_b}, and configure Gi0/1 & Gi0/2 as 802.1Q trunks.",
                expected_state=f"{sw1_name}: VLANs {vlan_a},{vlan_b}; Fa0/1=V{vlan_a}, Fa0/2=V{vlan_b}; Gi0/1 & Gi0/2=trunk",
                faulty_state=f"{sw1_name}: default VLAN 1 only",
                hints=[
                    f"Hint 1: On {sw1_name}, create 'vlan {vlan_a}' and 'vlan {vlan_b}'.",
                    f"Hint 2: Set Fa0/1 to 'switchport access vlan {vlan_a}' and Fa0/2 to 'switchport access vlan {vlan_b}'.",
                    "Hint 3: Set Gi0/1 and Gi0/2 to 'switchport mode trunk'.",
                ],
                explanation=f"{sw1_name} requires both VLANs in its database, access port assignments for {pc1_name} and {srv_name}, and 802.1Q trunks on Gi0/1 and Gi0/2.",
                fix_steps=[
                    f"1. On {sw1_name} CLI:\n     enable\n     configure terminal\n     vlan {vlan_a}\n     vlan {vlan_b}\n     interface FastEthernet0/1\n     switchport mode access\n     switchport access vlan {vlan_a}\n     interface FastEthernet0/2\n     switchport mode access\n     switchport access vlan {vlan_b}\n     interface range GigabitEthernet0/1 - 2\n     switchport mode trunk\n     end",
                ],
                verify_spec={
                    "type": "switch_vlans_and_ports",
                    "device": sw1_name,
                    "required_vlans": [vlan_a, vlan_b],
                    "access_ports": {"FastEthernet0/1": vlan_a, "FastEthernet0/2": vlan_b},
                    "trunk_ports": ["GigabitEthernet0/1", "GigabitEthernet0/2"],
                },
            ),
            FaultRecord(
                fault_id="STAGE4_SW2_VLANS_TRUNKS",
                title=f"Stage 4: IDF Switch {sw2_name} VLANs, Access Ports & 802.1Q Trunk",
                category="CCNA 2.1 / 2.2 — Switch VLANs & Trunks",
                device=sw2_name,
                interface="Gi0/1, Fa0/1-2",
                symptom=f"On {sw2_name}, create VLANs {vlan_a} & {vlan_b}, set Fa0/1 to VLAN {vlan_a}, Fa0/2 to VLAN {vlan_b}, and configure Gi0/1 as an 802.1Q trunk.",
                expected_state=f"{sw2_name}: VLANs {vlan_a},{vlan_b}; Fa0/1=V{vlan_a}, Fa0/2=V{vlan_b}; Gi0/1=trunk",
                faulty_state=f"{sw2_name}: default VLAN 1 only",
                hints=[
                    f"Hint 1: On {sw2_name}, create 'vlan {vlan_a}' and 'vlan {vlan_b}'.",
                    f"Hint 2: Set Fa0/1 to 'switchport access vlan {vlan_a}', Fa0/2 to 'switchport access vlan {vlan_b}', and Gi0/1 to 'switchport mode trunk'.",
                ],
                explanation=f"{sw2_name} requires VLANs {vlan_a} & {vlan_b}, access port assignments for {pc2_name} and {pc3_name}, and an 802.1Q trunk on Gi0/1.",
                fix_steps=[
                    f"1. On {sw2_name} CLI:\n     enable\n     configure terminal\n     vlan {vlan_a}\n     vlan {vlan_b}\n     interface FastEthernet0/1\n     switchport mode access\n     switchport access vlan {vlan_a}\n     interface FastEthernet0/2\n     switchport mode access\n     switchport access vlan {vlan_b}\n     interface GigabitEthernet0/1\n     switchport mode trunk\n     end",
                ],
                verify_spec={
                    "type": "switch_vlans_and_ports",
                    "device": sw2_name,
                    "required_vlans": [vlan_a, vlan_b],
                    "access_ports": {"FastEthernet0/1": vlan_a, "FastEthernet0/2": vlan_b},
                    "trunk_ports": ["GigabitEthernet0/1"],
                },
            ),
            FaultRecord(
                fault_id="STAGE5_L2_HOSTS",
                title=f"Stage 5: Endpoints IPv4 Addressing ({pc1_name}, {pc2_name}, {pc3_name}, {srv_name})",
                category="CCNA 1.11 — Multi-VLAN Host IPv4 Configuration",
                device=pc1_name,
                interface="FastEthernet0",
                symptom=f"Configure static IPv4, Subnet Mask ({netmask}), Default Gateway, and DNS ({srv_ip}) on {pc1_name}, {pc2_name}, {pc3_name}, and {srv_name}.",
                expected_state=f"VLAN {vlan_a}: {pc1_name}={pc1_ip}, {pc2_name}={pc2_ip} (GW {gw_a}) | VLAN {vlan_b}: {pc3_name}={pc3_ip}, {srv_name}={srv_ip} (GW {gw_b})",
                faulty_state="Endpoints unconfigured",
                hints=[
                    f"Hint 1: VLAN {vlan_a} hosts ({pc1_name}={pc1_ip}, {pc2_name}={pc2_ip}) use Default Gateway {gw_a}.",
                    f"Hint 2: VLAN {vlan_b} hosts ({pc3_name}={pc3_ip}, {srv_name}={srv_ip}) use Default Gateway {gw_b}.",
                ],
                explanation="Each host must be configured with an IP and Default Gateway matching its assigned VLAN subnet.",
                fix_steps=[
                    f"1. {pc1_name}: IP {pc1_ip}, Mask {netmask}, GW {gw_a}, DNS {srv_ip}.",
                    f"2. {pc2_name}: IP {pc2_ip}, Mask {netmask}, GW {gw_a}, DNS {srv_ip}.",
                    f"3. {pc3_name}: IP {pc3_ip}, Mask {netmask}, GW {gw_b}, DNS {srv_ip}.",
                    f"4. {srv_name}: IP {srv_ip}, Mask {netmask}, GW {gw_b}, DNS {srv_ip}.",
                ],
                verify_spec={
                    "type": "all_hosts_ip_gw",
                    "device": pc1_name,
                    "hosts": [
                        {"device": pc1_name, "expected_ip": pc1_ip, "expected_mask": netmask, "expected_gateway": gw_a},
                        {"device": pc2_name, "expected_ip": pc2_ip, "expected_mask": netmask, "expected_gateway": gw_a},
                        {"device": pc3_name, "expected_ip": pc3_ip, "expected_mask": netmask, "expected_gateway": gw_b},
                        {"device": srv_name, "expected_ip": srv_ip, "expected_mask": netmask, "expected_gateway": gw_b},
                    ],
                },
            ),
        ]
    )

    crx, cry = pt_to_canvas(*pt_pos["rtr"])
    cs1x, cs1y = pt_to_canvas(*pt_pos["sw1"])
    cs2x, cs2y = pt_to_canvas(*pt_pos["sw2"])
    c0x, c0y = pt_to_canvas(*pt_pos["c0"])
    c1x, c1y = pt_to_canvas(*pt_pos["c1"])
    c2x, c2y = pt_to_canvas(*pt_pos["c2"])
    csrvx, csrvy = pt_to_canvas(*pt_pos["srv"])
    canvas_nodes_l2 = [
        {"name": rtr_name, "role": "router", "sub": f".{vlan_a}: {gw_a}/{prefix_len}\n.{vlan_b}: {gw_b}/{prefix_len}", "x": crx, "y": cry},
        {"name": sw1_name, "role": "switch", "sub": f"VLANs {vlan_a},{vlan_b}", "x": cs1x, "y": cs1y},
        {"name": sw2_name, "role": "switch", "sub": f"VLANs {vlan_a},{vlan_b}", "x": cs2x, "y": cs2y},
        {"name": pc1_name, "role": "pc", "sub": f"VLAN {vlan_a}: {pc1_ip}/{prefix_len}", "x": c0x, "y": c0y},
        {"name": pc2_name, "role": "pc", "sub": f"VLAN {vlan_a}: {pc2_ip}/{prefix_len}", "x": c1x, "y": c1y},
        {"name": pc3_name, "role": "pc", "sub": f"VLAN {vlan_b}: {pc3_ip}/{prefix_len}", "x": c2x, "y": c2y},
        {"name": srv_name, "role": "server", "sub": f"VLAN {vlan_b}: {srv_ip}/{prefix_len}", "x": csrvx, "y": csrvy},
    ]
    canvas_edges_l2 = [
        (rtr_name, sw1_name, "Gi0/0 (RoaS)", "Gi0/1 (Trunk)"),
        (sw1_name, sw2_name, "Gi0/2 (Trunk)", "Gi0/1 (Trunk)"),
        (sw1_name, pc1_name, f"Fa0/1 (V{vlan_a})", "Fa0"),
        (sw1_name, srv_name, f"Fa0/2 (V{vlan_b})", "Fa0"),
        (sw2_name, pc2_name, f"Fa0/1 (V{vlan_a})", "Fa0"),
        (sw2_name, pc3_name, f"Fa0/2 (V{vlan_b})", "Fa0"),
    ]

    return ChallengeTicket(
        ticket_id=ticket_id,
        level=2,
        level_name=f"Mode 2 Build (Level 2) — {cfg.company_name} Dual-Subnet VLANs & 802.1Q RoaS",
        scenario_title=f"[BUILD LVL 2] {cfg.company_name}: {dept_name} (VLAN {vlan_a}: {subnet_a_cidr} | VLAN {vlan_b}: {subnet_b_cidr})",
        symptom_summary="  • " + "\n  • ".join(s.symptom for s in stages_l2),
        pkt_path=pkt_path,
        subnet_cidr=f"VLAN {vlan_a}: {subnet_a_cidr} | VLAN {vlan_b}: {subnet_b_cidr}",
        device_rows=device_rows,
        link_rows=link_rows,
        service_notes=[
            f"Greenfield Build Mission (Level 2) — Addressing Help: {addressing_help} | Hardware: {cabling_mode}.",
            f"VLAN {vlan_a} ({vlan_a_name}): {subnet_a_cidr} (GW {gw_a}) | VLAN {vlan_b} ({vlan_b_name}): {subnet_b_cidr} (GW {gw_b}).",
        ],
        faults=stages_l2,
        canvas_nodes=canvas_nodes_l2,
        canvas_edges=canvas_edges_l2,
    )

