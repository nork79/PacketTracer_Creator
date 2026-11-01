"""Level 2 CCNA (200-301 v2.0) Switching, VLANs, 802.1Q Trunks, Router-on-a-Stick & EtherChannel fault catalog."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import random
import xml.etree.ElementTree as ET

from pkt_generator.game.models import FaultRecord
from pkt_generator.network import SimpleNetwork

ALL_LEVEL2_FAULT_TYPES: list[str] = [
    # VLANs & Access Ports (CCNA 2.1, 2.2)
    "access_port_wrong_vlan",
    "vlan_missing_from_db",
    "voice_vlan_mismatch",
    # 802.1Q Trunks & DTP (CCNA 2.1, 2.2, 2.3)
    "trunk_left_as_access",
    "trunk_allowed_vlan_missing",
    "trunk_native_vlan_mismatch",
    "dtp_mode_mismatch",
    # Router-on-a-Stick / Inter-VLAN Routing (CCNA 3.1)
    "roas_wrong_dot1q_tag",
    "roas_subif_wrong_ip",
    "roas_parent_port_shutdown",
    "roas_switch_uplink_not_trunk",
    # Layer 2 EtherChannel (CCNA 2.4)
    "etherchannel_mode_mismatch",
]

_INTERSWITCH_TRUNK_FAULTS = {
    "trunk_left_as_access",
    "trunk_allowed_vlan_missing",
    "trunk_native_vlan_mismatch",
    "dtp_mode_mismatch",
    "etherchannel_mode_mismatch",
}

_ROAS_UPLINK_FAULTS = {
    "roas_wrong_dot1q_tag",
    "roas_subif_wrong_ip",
    "roas_parent_port_shutdown",
    "roas_switch_uplink_not_trunk",
}


def select_compatible_level2_faults(
    rng: random.Random, k: int, allowed_pool: list[str] | None = None
) -> list[str]:
    """Select `k` distinct Level 2 fault types without conflicting switch/router ports."""
    pool = [
        f
        for f in (allowed_pool or ALL_LEVEL2_FAULT_TYPES)
        if f in ALL_LEVEL2_FAULT_TYPES
    ]
    if not pool:
        pool = list(ALL_LEVEL2_FAULT_TYPES)
    rng.shuffle(pool)
    chosen: list[str] = []
    for cand in pool:
        if len(chosen) >= k:
            break
        if cand in _INTERSWITCH_TRUNK_FAULTS and any(
            c in _INTERSWITCH_TRUNK_FAULTS for c in chosen
        ):
            continue
        if cand in _ROAS_UPLINK_FAULTS and any(
            c in _ROAS_UPLINK_FAULTS for c in chosen
        ):
            continue
        chosen.append(cand)
    return chosen


@dataclass
class Level2FaultContext:
    """Context passed to `inject_level2_fault` for mutating the Level 2 network."""

    idx: int
    net: SimpleNetwork
    post_xml_mutations: list[Callable[[ET.Element], None]]
    rtr_name: str
    sw1_name: str
    sw2_name: str
    srv_name: str
    vlan_a: int
    vlan_a_name: str
    subnet_a_cidr: str
    gw_a: str
    vlan_b: int
    vlan_b_name: str
    subnet_b_cidr: str
    gw_b: str
    netmask: str
    prefix_len: int
    # Specific client targets on SW2 / SW1
    pc_vlan_a_sw2: str
    pc_vlan_a_sw2_port: str
    pc_vlan_a_sw2_ip: str
    pc_vlan_b_sw2: str
    pc_vlan_b_sw2_port: str
    pc_vlan_b_sw2_ip: str
    pc_vlan_a_sw1: str
    pc_vlan_a_sw1_port: str
    # Inter-switch trunk ports (SW1 <-> SW2)
    sw1_to_sw2_port: str
    sw2_to_sw1_port: str
    # EtherChannel secondary member ports (SW1 <-> SW2)
    sw1_ec_port2: str
    sw2_ec_port2: str
    # Router-on-a-Stick uplink (R1 Gi0/0 <-> SW1 Gi0/1)
    rtr_roas_port: str
    sw1_to_rtr_port: str


def inject_level2_fault(ftype: str, ctx: Level2FaultContext) -> FaultRecord:
    """Inject a Level 2 CCNA Switching/VLAN/Trunk/RoaS/EtherChannel fault into `ctx.net`."""
    idx = ctx.idx
    net = ctx.net

    # 1. Access Port Assigned to Wrong VLAN ID (CCNA 2.1)
    if ftype == "access_port_wrong_vlan":
        sw_dev = net.devices[ctx.sw2_name]
        pcfg = sw_dev.ports[ctx.pc_vlan_a_sw2_port]
        pcfg.access_vlan = ctx.vlan_b
        return FaultRecord(
            fault_id=f"F{idx+1}_ACCESS_WRONG_VLAN",
            title=f"Access Port Assigned to Wrong VLAN on {ctx.sw2_name} ({ctx.pc_vlan_a_sw2_port})",
            category="CCNA 2.1 — Access Port VLAN Membership",
            device=ctx.sw2_name,
            interface=ctx.pc_vlan_a_sw2_port,
            symptom=(
                f"Workstation {ctx.pc_vlan_a_sw2} ({ctx.pc_vlan_a_sw2_ip} in VLAN {ctx.vlan_a}) on {ctx.sw2_name} "
                f"cannot ping its VLAN {ctx.vlan_a} peer ({ctx.pc_vlan_a_sw1}) or default gateway ({ctx.gw_a})."
            ),
            expected_state=f"{ctx.sw2_name} {ctx.pc_vlan_a_sw2_port}: switchport mode access, switchport access vlan {ctx.vlan_a}",
            faulty_state=f"{ctx.sw2_name} {ctx.pc_vlan_a_sw2_port}: switchport access vlan {ctx.vlan_b}",
            hints=[
                f"Hint 1 (CCNA 2.1): Check which VLAN {ctx.pc_vlan_a_sw2} ({ctx.pc_vlan_a_sw2_ip}) belongs to in the Network Blueprint.",
                f"Hint 2 (Device): Run 'show vlan brief' and 'show running-config interface {ctx.pc_vlan_a_sw2_port}' on switch '{ctx.sw2_name}'.",
                f"Hint 3 (Exact Issue): {ctx.sw2_name} {ctx.pc_vlan_a_sw2_port} is assigned to VLAN {ctx.vlan_b} instead of VLAN {ctx.vlan_a}. Configure 'switchport access vlan {ctx.vlan_a}'.",
            ],
            explanation=(
                f"{ctx.pc_vlan_a_sw2} is addressed in subnet {ctx.subnet_a_cidr} (VLAN {ctx.vlan_a} — {ctx.vlan_a_name}), "
                f"but its switch access port ({ctx.sw2_name} {ctx.pc_vlan_a_sw2_port}) was mistakenly placed in VLAN {ctx.vlan_b}, "
                f"isolating its Layer 2 frames from the VLAN {ctx.vlan_a} broadcast domain."
            ),
            fix_steps=[
                f"1. Open switch '{ctx.sw2_name}' -> 'CLI' tab.",
                "2. Reassign the access port to the correct VLAN:\n"
                "     enable\n"
                "     configure terminal\n"
                f"     interface {ctx.pc_vlan_a_sw2_port}\n"
                "     switchport mode access\n"
                f"     switchport access vlan {ctx.vlan_a}\n"
                "     end",
                "3. Save the .pkt file (Ctrl+S) and click 'Quick-Check Current .pkt'.",
            ],
            verify_spec={
                "type": "switch_access_vlan",
                "device": ctx.sw2_name,
                "interface": ctx.pc_vlan_a_sw2_port,
                "expected_vlan": ctx.vlan_a,
            },
        )

    # 2. Missing / Inactive VLAN in Switch VLAN Database (CCNA 2.1)
    if ftype == "vlan_missing_from_db":
        sw_dev = net.devices[ctx.sw2_name]
        sw_dev.vlans.pop(ctx.vlan_b, None)

        def _strip_vlan_from_sw2_xml(root: ET.Element) -> None:
            for d in root.findall(".//NETWORK/DEVICES/DEVICE"):
                if (d.findtext("ENGINE/NAME") or "").strip() == ctx.sw2_name:
                    vlans_el = d.find("ENGINE/VLANS")
                    if vlans_el is not None:
                        for v_el in list(vlans_el.findall("VLAN")):
                            if v_el.get("number") == str(ctx.vlan_b):
                                vlans_el.remove(v_el)

        ctx.post_xml_mutations.append(_strip_vlan_from_sw2_xml)
        return FaultRecord(
            fault_id=f"F{idx+1}_VLAN_MISSING_DB",
            title=f"VLAN {ctx.vlan_b} ({ctx.vlan_b_name}) Missing from {ctx.sw2_name} VLAN Database",
            category="CCNA 2.1 — Switch VLAN Database (vlan.dat)",
            device=ctx.sw2_name,
            interface=f"VLAN {ctx.vlan_b} ({ctx.pc_vlan_b_sw2_port})",
            symptom=(
                f"Host {ctx.pc_vlan_b_sw2} ({ctx.pc_vlan_b_sw2_ip} in VLAN {ctx.vlan_b}) on {ctx.sw2_name} "
                f"cannot reach server {ctx.srv_name} or gateway {ctx.gw_b}; 'show vlan brief' on {ctx.sw2_name} "
                f"does not list VLAN {ctx.vlan_b}!"
            ),
            expected_state=f"{ctx.sw2_name} VLAN Database: VLAN {ctx.vlan_b} ({ctx.vlan_b_name}) active",
            faulty_state=f"{ctx.sw2_name} VLAN Database: VLAN {ctx.vlan_b} missing (port {ctx.pc_vlan_b_sw2_port} stranded)",
            hints=[
                f"Hint 1 (CCNA 2.1): Even if a trunk or access port references VLAN {ctx.vlan_b}, a switch will not forward frames for a VLAN that does not exist in its local VLAN database.",
                f"Hint 2 (Device): Run 'show vlan brief' on '{ctx.sw2_name}' and check if VLAN {ctx.vlan_b} is present.",
                f"Hint 3 (Exact Issue): VLAN {ctx.vlan_b} is missing from '{ctx.sw2_name}'. Create it in global configuration mode ('vlan {ctx.vlan_b}' -> 'name {ctx.vlan_b_name}').",
            ],
            explanation=(
                f"VLAN {ctx.vlan_b} ({ctx.vlan_b_name}) was never created in {ctx.sw2_name}'s VLAN database (vlan.dat), "
                f"or was deleted. Without an active VLAN {ctx.vlan_b} entry in the switch database, access port {ctx.pc_vlan_b_sw2_port} "
                f"and trunk forwarding for VLAN {ctx.vlan_b} are inactive on {ctx.sw2_name}."
            ),
            fix_steps=[
                f"1. Open switch '{ctx.sw2_name}' -> 'CLI' tab.",
                "2. Create the missing VLAN and verify the access port:\n"
                "     enable\n"
                "     configure terminal\n"
                f"     vlan {ctx.vlan_b}\n"
                f"     name {ctx.vlan_b_name}\n"
                f"     interface {ctx.pc_vlan_b_sw2_port}\n"
                "     switchport mode access\n"
                f"     switchport access vlan {ctx.vlan_b}\n"
                "     end",
                "3. Save the .pkt file (Ctrl+S) and verify.",
            ],
            verify_spec={
                "type": "vlan_exists_in_db",
                "device": ctx.sw2_name,
                "expected_vlan": ctx.vlan_b,
                "access_port": ctx.pc_vlan_b_sw2_port,
            },
        )

    # 3. Voice & Data Access Port VLAN Misconfiguration (CCNA 2.1)
    if ftype == "voice_vlan_mismatch":
        sw_dev = net.devices[ctx.sw1_name]
        pcfg = sw_dev.ports[ctx.pc_vlan_a_sw1_port]
        # Set wrong data VLAN (vlan_b) and omit voice_vlan (should be Data=vlan_a, Voice=vlan_b)
        pcfg.access_vlan = ctx.vlan_b
        pcfg.voice_vlan = None
        return FaultRecord(
            fault_id=f"F{idx+1}_VOICE_DATA_VLAN",
            title=f"Voice & Data VLAN Misconfiguration on {ctx.sw1_name} {ctx.pc_vlan_a_sw1_port}",
            category="CCNA 2.1 — Data & Voice VLAN Access Port",
            device=ctx.sw1_name,
            interface=ctx.pc_vlan_a_sw1_port,
            symptom=(
                f"Workstation {ctx.pc_vlan_a_sw1} on {ctx.sw1_name} {ctx.pc_vlan_a_sw1_port} was placed in the Voice/Services "
                f"VLAN ({ctx.vlan_b}) instead of Data VLAN {ctx.vlan_a}, and the auxiliary Voice VLAN ({ctx.vlan_b}) command is missing."
            ),
            expected_state=(
                f"{ctx.sw1_name} {ctx.pc_vlan_a_sw1_port}: switchport access vlan {ctx.vlan_a} + switchport voice vlan {ctx.vlan_b}"
            ),
            faulty_state=(
                f"{ctx.sw1_name} {ctx.pc_vlan_a_sw1_port}: switchport access vlan {ctx.vlan_b}, no switchport voice vlan configured"
            ),
            hints=[
                f"Hint 1 (CCNA 2.1): On a converged IP Phone + PC switch port, Data traffic uses 'switchport access vlan' and Voice traffic uses 'switchport voice vlan'.",
                f"Hint 2 (Device): Inspect interface {ctx.pc_vlan_a_sw1_port} on switch '{ctx.sw1_name}'.",
                f"Hint 3 (Exact Issue): On '{ctx.sw1_name}' {ctx.pc_vlan_a_sw1_port}, configure 'switchport access vlan {ctx.vlan_a}' and 'switchport voice vlan {ctx.vlan_b}'.",
            ],
            explanation=(
                f"Port {ctx.pc_vlan_a_sw1_port} on {ctx.sw1_name} had its untagged access VLAN set to {ctx.vlan_b} instead of "
                f"Data VLAN {ctx.vlan_a}, and lacked 'switchport voice vlan {ctx.vlan_b}'."
            ),
            fix_steps=[
                f"1. Open switch '{ctx.sw1_name}' -> 'CLI' tab.",
                "2. Configure both the Data VLAN and Voice VLAN on the port:\n"
                "     enable\n"
                "     configure terminal\n"
                f"     interface {ctx.pc_vlan_a_sw1_port}\n"
                "     switchport mode access\n"
                f"     switchport access vlan {ctx.vlan_a}\n"
                f"     switchport voice vlan {ctx.vlan_b}\n"
                "     end",
                "3. Save the .pkt file (Ctrl+S) and verify.",
            ],
            verify_spec={
                "type": "switch_voice_and_data_vlan",
                "device": ctx.sw1_name,
                "interface": ctx.pc_vlan_a_sw1_port,
                "expected_data_vlan": ctx.vlan_a,
                "expected_voice_vlan": ctx.vlan_b,
            },
        )

    # 4. Inter-Switch Uplink Left in Access Mode (CCNA 2.2)
    if ftype == "trunk_left_as_access":
        sw2_dev = net.devices[ctx.sw2_name]
        pcfg = sw2_dev.ports[ctx.sw2_to_sw1_port]
        pcfg.trunk = False
        pcfg.switchport_mode = "access"
        pcfg.access_vlan = 1
        return FaultRecord(
            fault_id=f"F{idx+1}_TRUNK_AS_ACCESS",
            title=f"Inter-Switch Uplink Left in Access Mode on {ctx.sw2_name} ({ctx.sw2_to_sw1_port})",
            category="CCNA 2.2 — 802.1Q Inter-Switch Trunking",
            device=ctx.sw2_name,
            interface=ctx.sw2_to_sw1_port,
            symptom=(
                f"No hosts on IDF switch {ctx.sw2_name} ({ctx.pc_vlan_a_sw2}, {ctx.pc_vlan_b_sw2}) can reach "
                f"MDF switch {ctx.sw1_name}, server {ctx.srv_name}, or router {ctx.rtr_name} across the inter-switch link."
            ),
            expected_state=f"{ctx.sw2_name} {ctx.sw2_to_sw1_port}: switchport mode trunk (802.1Q Trunk to {ctx.sw1_name})",
            faulty_state=f"{ctx.sw2_name} {ctx.sw2_to_sw1_port}: switchport mode access (VLAN 1)",
            hints=[
                f"Hint 1 (CCNA 2.2): Traffic from neither VLAN {ctx.vlan_a} nor VLAN {ctx.vlan_b} can cross the uplink between {ctx.sw1_name} and {ctx.sw2_name}.",
                f"Hint 2 (Device): Run 'show interfaces trunk' and 'show running-config interface {ctx.sw2_to_sw1_port}' on '{ctx.sw2_name}'.",
                f"Hint 3 (Exact Issue): '{ctx.sw2_name}' interface {ctx.sw2_to_sw1_port} is set to 'switchport mode access'. Change it to 'switchport mode trunk'.",
            ],
            explanation=(
                f"While {ctx.sw1_name} {ctx.sw1_to_sw2_port} is configured as an 802.1Q trunk, {ctx.sw2_name} {ctx.sw2_to_sw1_port} "
                f"was left in static access mode ('switchport mode access'), preventing 802.1Q tagged frames for VLANs {ctx.vlan_a} and {ctx.vlan_b} from traversing the link."
            ),
            fix_steps=[
                f"1. Open switch '{ctx.sw2_name}' -> 'CLI' tab.",
                "2. Configure the inter-switch uplink as an 802.1Q trunk:\n"
                "     enable\n"
                "     configure terminal\n"
                f"     interface {ctx.sw2_to_sw1_port}\n"
                "     switchport mode trunk\n"
                "     end",
                "3. Save the .pkt file (Ctrl+S) and verify.",
            ],
            verify_spec={
                "type": "switch_port_trunk",
                "device": ctx.sw2_name,
                "interface": ctx.sw2_to_sw1_port,
                "required_vlans": [ctx.vlan_a, ctx.vlan_b],
            },
        )

    # 5. 802.1Q Trunk Allowed VLAN List Filtering Traffic (CCNA 2.2)
    if ftype == "trunk_allowed_vlan_missing":
        sw1_dev = net.devices[ctx.sw1_name]
        pcfg = sw1_dev.ports[ctx.sw1_to_sw2_port]
        pcfg.trunk = True
        pcfg.allowed_vlans = [ctx.vlan_a]
        return FaultRecord(
            fault_id=f"F{idx+1}_TRUNK_ALLOWED_VLAN",
            title=f"802.1Q Trunk Allowed VLAN List Pruning VLAN {ctx.vlan_b} on {ctx.sw1_name} ({ctx.sw1_to_sw2_port})",
            category="CCNA 2.2 — 802.1Q Trunk Allowed VLANs",
            device=ctx.sw1_name,
            interface=ctx.sw1_to_sw2_port,
            symptom=(
                f"VLAN {ctx.vlan_a} host {ctx.pc_vlan_a_sw2} on {ctx.sw2_name} has full network connectivity, "
                f"but VLAN {ctx.vlan_b} host {ctx.pc_vlan_b_sw2} on {ctx.sw2_name} is completely cut off from {ctx.sw1_name} and {ctx.rtr_name}."
            ),
            expected_state=(
                f"{ctx.sw1_name} {ctx.sw1_to_sw2_port}: Trunk allowing both VLAN {ctx.vlan_a} and VLAN {ctx.vlan_b}"
            ),
            faulty_state=(
                f"{ctx.sw1_name} {ctx.sw1_to_sw2_port}: switchport trunk allowed vlan {ctx.vlan_a} (VLAN {ctx.vlan_b} filtered!)"
            ),
            hints=[
                f"Hint 1 (CCNA 2.2): VLAN {ctx.vlan_a} crosses the trunk between {ctx.sw1_name} and {ctx.sw2_name}, but VLAN {ctx.vlan_b} is blocked.",
                f"Hint 2 (Device): Run 'show interfaces trunk' on '{ctx.sw1_name}' and inspect 'Vlans allowed on trunk'.",
                f"Hint 3 (Exact Issue): '{ctx.sw1_name}' {ctx.sw1_to_sw2_port} has 'switchport trunk allowed vlan {ctx.vlan_a}'. Permit VLAN {ctx.vlan_b} using 'switchport trunk allowed vlan {ctx.vlan_a},{ctx.vlan_b}' (or 'no switchport trunk allowed vlan').",
            ],
            explanation=(
                f"Interface {ctx.sw1_to_sw2_port} on {ctx.sw1_name} had a restrictive 'switchport trunk allowed vlan {ctx.vlan_a}' statement "
                f"that dropped all 802.1Q frames tagged with VLAN {ctx.vlan_b}."
            ),
            fix_steps=[
                f"1. Open switch '{ctx.sw1_name}' -> 'CLI' tab.",
                "2. Update the allowed VLAN list on the trunk interface:\n"
                "     enable\n"
                "     configure terminal\n"
                f"     interface {ctx.sw1_to_sw2_port}\n"
                f"     switchport trunk allowed vlan {ctx.vlan_a},{ctx.vlan_b}\n"
                "     end",
                "3. Save the .pkt file (Ctrl+S) and verify.",
            ],
            verify_spec={
                "type": "trunk_allowed_vlans",
                "device": ctx.sw1_name,
                "interface": ctx.sw1_to_sw2_port,
                "required_vlans": [ctx.vlan_a, ctx.vlan_b],
            },
        )

    # 6. 802.1Q Native VLAN Mismatch Across Trunk Link (CCNA 2.2)
    if ftype == "trunk_native_vlan_mismatch":
        sw2_dev = net.devices[ctx.sw2_name]
        sw2_dev.vlans[99] = sw2_dev.vlans.get(99) or net.add_vlan(ctx.sw2_name, 99, "NATIVE_MISMATCH")
        pcfg = sw2_dev.ports[ctx.sw2_to_sw1_port]
        pcfg.trunk = True
        pcfg.native_vlan = 99
        return FaultRecord(
            fault_id=f"F{idx+1}_NATIVE_VLAN_MISMATCH",
            title=f"802.1Q Trunk Native VLAN Mismatch (VLAN 99 vs VLAN 1) on {ctx.sw2_name} ({ctx.sw2_to_sw1_port})",
            category="CCNA 2.2 — 802.1Q Native VLAN",
            device=ctx.sw2_name,
            interface=ctx.sw2_to_sw1_port,
            symptom=(
                f"CDP and Spanning Tree report `%CDP-4-NATIVE_VLAN_MISMATCH` and PVID inconsistency blocking "
                f"on the trunk link between {ctx.sw1_name} ({ctx.sw1_to_sw2_port}) and {ctx.sw2_name} ({ctx.sw2_to_sw1_port})."
            ),
            expected_state=f"Native VLAN 1 matching on both {ctx.sw1_name} ({ctx.sw1_to_sw2_port}) and {ctx.sw2_name} ({ctx.sw2_to_sw1_port})",
            faulty_state=f"{ctx.sw2_name} {ctx.sw2_to_sw1_port}: switchport trunk native vlan 99 (mismatches {ctx.sw1_name} Native VLAN 1)",
            hints=[
                "Hint 1 (CCNA 2.2): Check 'show interfaces trunk' on both switches for a Native VLAN mismatch.",
                f"Hint 2 (Device): Compare the Native VLAN on '{ctx.sw2_name}' {ctx.sw2_to_sw1_port} against '{ctx.sw1_name}' {ctx.sw1_to_sw2_port}.",
                f"Hint 3 (Exact Issue): '{ctx.sw2_name}' {ctx.sw2_to_sw1_port} has 'switchport trunk native vlan 99'. Reset it to VLAN 1 ('no switchport trunk native vlan' or 'switchport trunk native vlan 1').",
            ],
            explanation=(
                f"802.1Q trunks require both ends to agree on the untagged Native VLAN. {ctx.sw2_name} {ctx.sw2_to_sw1_port} was set to "
                f"Native VLAN 99 while {ctx.sw1_name} {ctx.sw1_to_sw2_port} used default Native VLAN 1, triggering STP PVID inconsistency."
            ),
            fix_steps=[
                f"1. Open switch '{ctx.sw2_name}' -> 'CLI' tab.",
                "2. Restore the Native VLAN on the trunk to VLAN 1:\n"
                "     enable\n"
                "     configure terminal\n"
                f"     interface {ctx.sw2_to_sw1_port}\n"
                "     no switchport trunk native vlan\n"
                "     end",
                "3. Save the .pkt file (Ctrl+S) and verify.",
            ],
            verify_spec={
                "type": "trunk_native_vlan_match",
                "device": ctx.sw2_name,
                "interface": ctx.sw2_to_sw1_port,
                "peer_device": ctx.sw1_name,
                "peer_interface": ctx.sw1_to_sw2_port,
                "expected_native_vlan": 1,
            },
        )

    # 7. DTP Negotiation Failure (dynamic auto vs dynamic auto) (CCNA 2.3)
    if ftype == "dtp_mode_mismatch":
        p1 = net.devices[ctx.sw1_name].ports[ctx.sw1_to_sw2_port]
        p2 = net.devices[ctx.sw2_name].ports[ctx.sw2_to_sw1_port]
        p1.trunk = False
        p1.switchport_mode = "dynamic auto"
        p2.trunk = False
        p2.switchport_mode = "dynamic auto"
        return FaultRecord(
            fault_id=f"F{idx+1}_DTP_AUTO_AUTO",
            title=f"DTP Trunk Negotiation Failure (dynamic auto / dynamic auto) Between {ctx.sw1_name} & {ctx.sw2_name}",
            category="CCNA 2.3 — Dynamic Trunking Protocol (DTP)",
            device=ctx.sw2_name,
            interface=ctx.sw2_to_sw1_port,
            symptom=(
                f"The inter-switch link between {ctx.sw1_name} ({ctx.sw1_to_sw2_port}) and {ctx.sw2_name} ({ctx.sw2_to_sw1_port}) "
                f"is UP, but 'show interfaces trunk' is empty and VLANs {ctx.vlan_a} & {ctx.vlan_b} cannot cross between switches."
            ),
            expected_state=(
                f"Static 'switchport mode trunk' (or DTP desirable) on {ctx.sw1_name} {ctx.sw1_to_sw2_port} & {ctx.sw2_name} {ctx.sw2_to_sw1_port}"
            ),
            faulty_state=(
                f"Both {ctx.sw1_name} {ctx.sw1_to_sw2_port} and {ctx.sw2_name} {ctx.sw2_to_sw1_port} set to 'switchport mode dynamic auto' (negotiates Access mode!)"
            ),
            hints=[
                "Hint 1 (CCNA 2.3): When both ends of an inter-switch link are set to 'dynamic auto', neither switch actively initiates DTP trunking, so the link becomes a static access port.",
                f"Hint 2 (Device): Inspect 'show interfaces {ctx.sw2_to_sw1_port} switchport' on '{ctx.sw2_name}' and '{ctx.sw1_to_sw2_port}' on '{ctx.sw1_name}'.",
                f"Hint 3 (Exact Issue): Configure 'switchport mode trunk' on '{ctx.sw1_name}' {ctx.sw1_to_sw2_port} and '{ctx.sw2_name}' {ctx.sw2_to_sw1_port}.",
            ],
            explanation=(
                f"In Cisco DTP (CCNA 2.3), two ports configured as 'dynamic auto' wait passively for the peer to request a trunk. "
                f"As a result, the link falls back to a VLAN 1 access link. Setting 'switchport mode trunk' (or 'dynamic desirable') brings up the 802.1Q trunk."
            ),
            fix_steps=[
                f"1. On '{ctx.sw1_name}' CLI, configure:\n"
                "     enable\n"
                "     configure terminal\n"
                f"     interface {ctx.sw1_to_sw2_port}\n"
                "     switchport mode trunk\n"
                "     end",
                f"2. On '{ctx.sw2_name}' CLI, configure:\n"
                "     enable\n"
                "     configure terminal\n"
                f"     interface {ctx.sw2_to_sw1_port}\n"
                "     switchport mode trunk\n"
                "     end",
                "3. Save the .pkt file (Ctrl+S) and verify.",
            ],
            verify_spec={
                "type": "dtp_trunk_operational",
                "device": ctx.sw2_name,
                "interface": ctx.sw2_to_sw1_port,
                "peer_device": ctx.sw1_name,
                "peer_interface": ctx.sw1_to_sw2_port,
            },
        )

    # 8. Router Subinterface Wrong 802.1Q Tag (CCNA 3.1)
    if ftype == "roas_wrong_dot1q_tag":
        rtr_dev = net.devices[ctx.rtr_name]
        wrong_tag = ctx.vlan_b + 5
        for sub in rtr_dev.subinterfaces:
            if sub.vlan_id == ctx.vlan_b:
                sub.dot1q_tag = wrong_tag
                break
        subif_name = f"{ctx.rtr_roas_port}.{ctx.vlan_b}"
        return FaultRecord(
            fault_id=f"F{idx+1}_ROAS_DOT1Q_TAG",
            title=f"Router-on-a-Stick Wrong 802.1Q VLAN Tag on {ctx.rtr_name} ({subif_name})",
            category="CCNA 3.1 — Router-on-a-Stick Inter-VLAN Routing",
            device=ctx.rtr_name,
            interface=subif_name,
            symptom=(
                f"Hosts in VLAN {ctx.vlan_b} ({ctx.pc_vlan_b_sw2}, {ctx.srv_name}) can ping each other at Layer 2, "
                f"but cannot ping their default gateway ({ctx.gw_b}) or communicate with VLAN {ctx.vlan_a}."
            ),
            expected_state=f"{ctx.rtr_name} {subif_name}: encapsulation dot1Q {ctx.vlan_b}, ip address {ctx.gw_b} {ctx.netmask}",
            faulty_state=f"{ctx.rtr_name} {subif_name}: encapsulation dot1Q {wrong_tag} (Wrong 802.1Q VLAN ID!)",
            hints=[
                f"Hint 1 (CCNA 3.1): Inter-VLAN routing works for VLAN {ctx.vlan_a}, but router {ctx.rtr_name} is ignoring 802.1Q frames from VLAN {ctx.vlan_b}.",
                f"Hint 2 (Device): Run 'show running-config' on router '{ctx.rtr_name}' and inspect subinterface {subif_name}.",
                f"Hint 3 (Exact Issue): '{ctx.rtr_name}' {subif_name} has 'encapsulation dot1Q {wrong_tag}' instead of 'encapsulation dot1Q {ctx.vlan_b}', and re-apply IP '{ctx.gw_b} {ctx.netmask}'.",
            ],
            explanation=(
                f"Subinterface {subif_name} on {ctx.rtr_name} was configured with 'encapsulation dot1Q {wrong_tag}' instead of "
                f"'encapsulation dot1Q {ctx.vlan_b}'. Because the 802.1Q tag does not match VLAN {ctx.vlan_b}, the router drops all frames arriving on VLAN {ctx.vlan_b}."
            ),
            fix_steps=[
                f"1. Open router '{ctx.rtr_name}' -> 'CLI' tab.",
                "2. Fix the 802.1Q encapsulation tag and IP address on the subinterface:\n"
                "     enable\n"
                "     configure terminal\n"
                f"     interface {subif_name}\n"
                f"     encapsulation dot1Q {ctx.vlan_b}\n"
                f"     ip address {ctx.gw_b} {ctx.netmask}\n"
                "     end",
                "3. Save the .pkt file (Ctrl+S) and verify.",
            ],
            verify_spec={
                "type": "roas_subinterface_config",
                "device": ctx.rtr_name,
                "parent_port": ctx.rtr_roas_port,
                "vlan_id": ctx.vlan_b,
                "expected_ip": ctx.gw_b,
                "expected_mask": ctx.netmask,
            },
        )

    # 9. Router Subinterface Wrong Gateway IP / Subnet Mask (CCNA 3.1)
    if ftype == "roas_subif_wrong_ip":
        rtr_dev = net.devices[ctx.rtr_name]
        parts = ctx.gw_b.split(".")
        bad_oct3 = str((int(parts[2]) + 11) % 250 or 77)
        bad_gw = f"{parts[0]}.{parts[1]}.{bad_oct3}.{parts[3]}"
        for sub in rtr_dev.subinterfaces:
            if sub.vlan_id == ctx.vlan_b:
                sub.ip = bad_gw
                break
        subif_name = f"{ctx.rtr_roas_port}.{ctx.vlan_b}"
        return FaultRecord(
            fault_id=f"F{idx+1}_ROAS_WRONG_IP",
            title=f"Router Subinterface Wrong Gateway IPv4 on {ctx.rtr_name} ({subif_name})",
            category="CCNA 3.1 — Router-on-a-Stick Subinterface Addressing",
            device=ctx.rtr_name,
            interface=subif_name,
            symptom=(
                f"VLAN {ctx.vlan_b} hosts ({ctx.pc_vlan_b_sw2}, {ctx.srv_name}) on {ctx.subnet_b_cidr} cannot reach their "
                f"default gateway ({ctx.gw_b}) or route traffic to VLAN {ctx.vlan_a}."
            ),
            expected_state=f"{ctx.rtr_name} {subif_name}: ip address {ctx.gw_b} {ctx.netmask}",
            faulty_state=f"{ctx.rtr_name} {subif_name}: ip address {bad_gw} {ctx.netmask}",
            hints=[
                f"Hint 1 (CCNA 3.1): Check the IPv4 address assigned to the VLAN {ctx.vlan_b} subinterface on router '{ctx.rtr_name}'.",
                f"Hint 2 (Device): Run 'show ip interface brief' on '{ctx.rtr_name}' and compare {subif_name} with the Blueprint.",
                f"Hint 3 (Exact Issue): '{ctx.rtr_name}' {subif_name} has IP {bad_gw}. Change it to 'ip address {ctx.gw_b} {ctx.netmask}'.",
            ],
            explanation=(
                f"Router {ctx.rtr_name}'s subinterface {subif_name} had an IPv4 octet typo ({bad_gw} instead of {ctx.gw_b}), "
                f"putting the subinterface outside VLAN {ctx.vlan_b}'s subnet ({ctx.subnet_b_cidr})."
            ),
            fix_steps=[
                f"1. Open router '{ctx.rtr_name}' -> 'CLI' tab.",
                "2. Correct the subinterface IPv4 address:\n"
                "     enable\n"
                "     configure terminal\n"
                f"     interface {subif_name}\n"
                f"     ip address {ctx.gw_b} {ctx.netmask}\n"
                "     end",
                "3. Save the .pkt file (Ctrl+S) and verify.",
            ],
            verify_spec={
                "type": "roas_subinterface_config",
                "device": ctx.rtr_name,
                "parent_port": ctx.rtr_roas_port,
                "vlan_id": ctx.vlan_b,
                "expected_ip": ctx.gw_b,
                "expected_mask": ctx.netmask,
            },
        )

    # 10. Router Physical Parent Interface Administratively Down (CCNA 3.1)
    if ftype == "roas_parent_port_shutdown":
        rtr_dev = net.devices[ctx.rtr_name]
        rtr_dev.ports[ctx.rtr_roas_port].shutdown = True
        return FaultRecord(
            fault_id=f"F{idx+1}_ROAS_PARENT_SHUT",
            title=f"Router-on-a-Stick Physical Parent Interface Shutdown on {ctx.rtr_name} ({ctx.rtr_roas_port})",
            category="CCNA 3.1 — Router-on-a-Stick Physical Parent State",
            device=ctx.rtr_name,
            interface=ctx.rtr_roas_port,
            symptom=(
                f"All inter-VLAN routing between VLAN {ctx.vlan_a} and VLAN {ctx.vlan_b} is down, and both subinterfaces "
                f"{ctx.rtr_roas_port}.{ctx.vlan_a} and {ctx.rtr_roas_port}.{ctx.vlan_b} show 'administratively down'!"
            ),
            expected_state=f"{ctx.rtr_name} {ctx.rtr_roas_port}: UP (no shutdown)",
            faulty_state=f"{ctx.rtr_name} {ctx.rtr_roas_port}: Administratively DOWN (shutdown)",
            hints=[
                f"Hint 1 (CCNA 3.1): Even when 802.1Q subinterfaces are configured, they inherit the physical state of their parent interface ({ctx.rtr_roas_port}).",
                f"Hint 2 (Device): Run 'show ip interface brief' on '{ctx.rtr_name}'.",
                f"Hint 3 (Exact Issue): Physical interface {ctx.rtr_roas_port} on '{ctx.rtr_name}' is shutdown. Enter 'interface {ctx.rtr_roas_port}' and run 'no shutdown'.",
            ],
            explanation=(
                f"On {ctx.rtr_name}, the physical parent interface {ctx.rtr_roas_port} was left in 'shutdown' state, "
                f"forcing all of its child 802.1Q subinterfaces (.{ctx.vlan_a} and .{ctx.vlan_b}) down."
            ),
            fix_steps=[
                f"1. Open router '{ctx.rtr_name}' -> 'CLI' tab.",
                "2. Enable the physical parent interface:\n"
                "     enable\n"
                "     configure terminal\n"
                f"     interface {ctx.rtr_roas_port}\n"
                "     no shutdown\n"
                "     end",
                "3. Save the .pkt file (Ctrl+S) and verify.",
            ],
            verify_spec={
                "type": "roas_parent_up",
                "device": ctx.rtr_name,
                "parent_port": ctx.rtr_roas_port,
                "vlan_ids": [ctx.vlan_a, ctx.vlan_b],
            },
        )

    # 11. Switch-to-Router Uplink Not Configured as 802.1Q Trunk (CCNA 3.1)
    if ftype == "roas_switch_uplink_not_trunk":
        sw1_dev = net.devices[ctx.sw1_name]
        pcfg = sw1_dev.ports[ctx.sw1_to_rtr_port]
        pcfg.trunk = False
        pcfg.switchport_mode = "access"
        pcfg.access_vlan = 1
        return FaultRecord(
            fault_id=f"F{idx+1}_ROAS_SW_NOT_TRUNK",
            title=f"Switch-to-Router Uplink Left in Access Mode on {ctx.sw1_name} ({ctx.sw1_to_rtr_port})",
            category="CCNA 3.1 — Router-on-a-Stick Switch Trunk Uplink",
            device=ctx.sw1_name,
            interface=ctx.sw1_to_rtr_port,
            symptom=(
                f"Hosts within VLAN {ctx.vlan_a} can ping each other across switches, and router {ctx.rtr_name}'s "
                f"subinterfaces are UP, yet NO host in VLAN {ctx.vlan_a} or VLAN {ctx.vlan_b} can ping its default gateway!"
            ),
            expected_state=f"{ctx.sw1_name} {ctx.sw1_to_rtr_port} (to {ctx.rtr_name}): switchport mode trunk",
            faulty_state=f"{ctx.sw1_name} {ctx.sw1_to_rtr_port} (to {ctx.rtr_name}): switchport mode access (VLAN 1)",
            hints=[
                f"Hint 1 (CCNA 3.1): Router-on-a-Stick requires the switch port connected to {ctx.rtr_name} ({ctx.rtr_roas_port}) to be configured as an 802.1Q trunk.",
                f"Hint 2 (Device): Check 'show interfaces trunk' and 'show running-config interface {ctx.sw1_to_rtr_port}' on '{ctx.sw1_name}'.",
                f"Hint 3 (Exact Issue): '{ctx.sw1_name}' {ctx.sw1_to_rtr_port} is set to 'switchport mode access'. Configure 'switchport mode trunk' on {ctx.sw1_to_rtr_port}.",
            ],
            explanation=(
                f"Because Cisco routers do not run DTP, the switch port connected to a Router-on-a-Stick ({ctx.sw1_name} {ctx.sw1_to_rtr_port}) "
                f"must be manually configured with 'switchport mode trunk' to tag VLAN {ctx.vlan_a} and VLAN {ctx.vlan_b} frames."
            ),
            fix_steps=[
                f"1. Open switch '{ctx.sw1_name}' -> 'CLI' tab.",
                "2. Set the router uplink port to trunk mode:\n"
                "     enable\n"
                "     configure terminal\n"
                f"     interface {ctx.sw1_to_rtr_port}\n"
                "     switchport mode trunk\n"
                "     end",
                "3. Save the .pkt file (Ctrl+S) and verify.",
            ],
            verify_spec={
                "type": "switch_port_trunk",
                "device": ctx.sw1_name,
                "interface": ctx.sw1_to_rtr_port,
                "required_vlans": [ctx.vlan_a, ctx.vlan_b],
            },
        )

    # 12. Layer 2 EtherChannel Protocol Mismatch (LACP vs PAgP) (CCNA 2.4)
    # Default fallback for 'etherchannel_mode_mismatch'
    sw1_dev = net.devices[ctx.sw1_name]
    sw2_dev = net.devices[ctx.sw2_name]
    # Add second physical link between SW1 and SW2 if not already present
    if ctx.sw1_ec_port2 not in sw1_dev.used_ports and ctx.sw2_ec_port2 not in sw2_dev.used_ports:
        net.connect(
            ctx.sw1_name,
            ctx.sw2_name,
            port_a=ctx.sw1_ec_port2,
            port_b=ctx.sw2_ec_port2,
            trunk=True,
        )
    # SW1 uses LACP 'active' on both member ports; SW2 is misconfigured with PAgP 'desirable'
    for p_name in (ctx.sw1_to_sw2_port, ctx.sw1_ec_port2):
        sw1_dev.ports[p_name].trunk = True
        sw1_dev.ports[p_name].channel_group = (1, "active")
    for p_name in (ctx.sw2_to_sw1_port, ctx.sw2_ec_port2):
        sw2_dev.ports[p_name].trunk = True
        sw2_dev.ports[p_name].channel_group = (1, "desirable")

    return FaultRecord(
        fault_id=f"F{idx+1}_ETHERCHANNEL_MISMATCH",
        title=f"Layer 2 EtherChannel Protocol Mismatch (LACP vs PAgP) on {ctx.sw2_name} (Port-channel1)",
        category="CCNA 2.4 — Layer 2 EtherChannel (LACP)",
        device=ctx.sw2_name,
        interface=f"Port-channel1 ({ctx.sw2_to_sw1_port}, {ctx.sw2_ec_port2})",
        symptom=(
            f"The dual-link EtherChannel bundle (Port-channel1) between {ctx.sw1_name} and {ctx.sw2_name} "
            f"fails to bundle (shows down/suspended in 'show etherchannel summary'), breaking trunk connectivity."
        ),
        expected_state=(
            f"LACP ('channel-group 1 mode active') on both {ctx.sw1_name} ({ctx.sw1_to_sw2_port}, {ctx.sw1_ec_port2}) "
            f"and {ctx.sw2_name} ({ctx.sw2_to_sw1_port}, {ctx.sw2_ec_port2}) with Port-channel1 in trunk mode"
        ),
        faulty_state=(
            f"{ctx.sw1_name} configured for LACP ('mode active'), but {ctx.sw2_name} configured for Cisco PAgP ('mode desirable')"
        ),
        hints=[
            "Hint 1 (CCNA 2.4): Run 'show etherchannel summary' on both switches to check the bundling protocol (LACP vs PAgP).",
            f"Hint 2 (Device): Inspect interfaces {ctx.sw2_to_sw1_port} and {ctx.sw2_ec_port2} on '{ctx.sw2_name}'.",
            f"Hint 3 (Exact Issue): '{ctx.sw2_name}' member ports use PAgP ('channel-group 1 mode desirable') while '{ctx.sw1_name}' uses LACP ('mode active'). Reconfigure {ctx.sw2_name} member ports to 'channel-group 1 mode active' and ensure 'interface Port-channel1' is 'switchport mode trunk'.",
        ],
        explanation=(
            f"{ctx.sw1_name} was configured for IEEE 802.3ad LACP ('channel-group 1 mode active'), whereas {ctx.sw2_name} "
            f"was configured with Cisco-proprietary PAgP ('channel-group 1 mode desirable'). Incompatible EtherChannel protocols "
            f"prevent Port-channel1 from forming."
        ),
        fix_steps=[
            f"1. Open switch '{ctx.sw2_name}' -> 'CLI' tab.",
            "2. Switch the member ports from PAgP to LACP and ensure Port-channel1 is a trunk:\n"
            "     enable\n"
            "     configure terminal\n"
            f"     interface range {ctx.sw2_to_sw1_port}, {ctx.sw2_ec_port2}\n"
            "     no channel-group 1\n"
            "     channel-group 1 mode active\n"
            "     switchport mode trunk\n"
            "     interface Port-channel1\n"
            "     switchport mode trunk\n"
            "     no shutdown\n"
            "     end",
            "3. Save the .pkt file (Ctrl+S) and verify.",
        ],
        verify_spec={
            "type": "etherchannel_lacp_valid",
            "device": ctx.sw2_name,
            "member_ports": [ctx.sw2_to_sw1_port, ctx.sw2_ec_port2],
            "peer_device": ctx.sw1_name,
            "peer_member_ports": [ctx.sw1_to_sw2_port, ctx.sw1_ec_port2],
            "group_number": 1,
        },
    )

