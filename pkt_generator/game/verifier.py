"""Inspects an uploaded .pkt file against a ChallengeTicket to verify if faults or build stages are completed."""

from __future__ import annotations

from pathlib import Path
from typing import Any
import xml.etree.ElementTree as ET

from pkt_generator.game.models import (
    ChallengeTicket,
    CheckItemResult,
    VerificationResult,
)
from pkt_generator.network import decode_bytes


def _parse_vlan_list(spec_str: str, current: set[int] | None = None) -> set[int] | None:
    """Parse an IOS VLAN list expression ('10,20', '10-20', 'add 20', 'all') into a set of VLAN IDs (or None for all)."""
    s = spec_str.strip().lower()
    if not s or s == "all":
        return None
    if s == "none":
        return set()
    is_add = False
    if s.startswith("add "):
        is_add = True
        s = s[4:].strip()
    elif s.startswith("except "):
        s = s[7:].strip()
        excluded = _parse_vlan_list(s) or set()
        return set(range(1, 1006)) - excluded
    result: set[int] = set(current) if (is_add and current is not None) else set()
    for part in s.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            lo_s, hi_s = part.split("-", 1)
            if lo_s.strip().isdigit() and hi_s.strip().isdigit():
                result.update(range(int(lo_s), int(hi_s) + 1))
        elif part.isdigit():
            result.add(int(part))
    return result


def _extract_switch_vlans(dev_el: ET.Element) -> set[int]:
    """Return the set of active VLAN IDs defined in <ENGINE><VLANS> or <RUNNINGCONFIG> on a switch."""
    vlans: set[int] = {1}
    for v_el in dev_el.findall("ENGINE/VLANS/VLAN"):
        num = (v_el.get("number") or "").strip()
        if num.isdigit():
            vlans.add(int(num))
    rc = dev_el.find("ENGINE/RUNNINGCONFIG")
    if rc is not None:
        for line_el in rc.findall("LINE"):
            raw = (line_el.text or "").strip()
            if raw.startswith("vlan "):
                tail = raw[5:].strip()
                parsed = _parse_vlan_list(tail)
                if parsed:
                    vlans.update(parsed)
    return vlans


def _parse_ios_config(dev_el: ET.Element) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    """Parse <ENGINE><RUNNINGCONFIG> on a router/switch into (interfaces_map, globals_map)."""
    rc = dev_el.find("ENGINE/RUNNINGCONFIG")
    interfaces: dict[str, dict[str, Any]] = {}
    globals_map: dict[str, str] = {"default_gateway": ""}
    if rc is None:
        return interfaces, globals_map

    cur_if: str | None = None
    for line_el in rc.findall("LINE"):
        raw = (line_el.text or "").strip()
        if raw.startswith("interface "):
            cur_if = raw.split(None, 1)[1].strip()
            interfaces.setdefault(
                cur_if,
                {
                    "ip": "",
                    "mask": "",
                    "shutdown": False,
                    "speed": "auto",
                    "duplex": "auto",
                    "trunk": False,
                    "switchport_mode": "",
                    "access_vlan": 1,
                    "voice_vlan": None,
                    "native_vlan": 1,
                    "allowed_vlans": None,  # None == all VLANs allowed
                    "dot1q_vlan": None,
                    "channel_group": None,  # (group_num, mode_str)
                    "lines": [],
                },
            )
            continue
        if raw.startswith("ip default-gateway "):
            parts = raw.split()
            if len(parts) >= 3:
                globals_map["default_gateway"] = parts[2]
            cur_if = None
            continue
        if raw == "!" or raw.startswith("vlan ") or raw.startswith("router ") or raw.startswith("line "):
            cur_if = None
            continue
        if cur_if is None:
            continue

        icfg = interfaces[cur_if]
        icfg["lines"].append(raw)
        low = raw.lower()
        if low == "shutdown":
            icfg["shutdown"] = True
        elif low == "no shutdown":
            icfg["shutdown"] = False
        elif low.startswith("ip address "):
            parts = raw.split()
            if len(parts) >= 4:
                icfg["ip"] = parts[2]
                icfg["mask"] = parts[3]
        elif low.startswith("speed "):
            icfg["speed"] = raw.split(None, 1)[1].strip()
        elif low.startswith("duplex "):
            icfg["duplex"] = raw.split(None, 1)[1].strip()
        elif low.startswith("switchport mode "):
            mode_val = low[len("switchport mode ") :].strip()
            icfg["switchport_mode"] = mode_val
            icfg["trunk"] = mode_val == "trunk"
        elif low.startswith("switchport access vlan "):
            parts = raw.split()
            if parts[-1].isdigit():
                icfg["access_vlan"] = int(parts[-1])
        elif low.startswith("switchport voice vlan "):
            parts = raw.split()
            if parts[-1].isdigit():
                icfg["voice_vlan"] = int(parts[-1])
        elif low.startswith("switchport trunk native vlan "):
            parts = raw.split()
            if parts[-1].isdigit():
                icfg["native_vlan"] = int(parts[-1])
        elif low == "no switchport trunk native vlan":
            icfg["native_vlan"] = 1
        elif low.startswith("switchport trunk allowed vlan "):
            spec_str = raw[len("switchport trunk allowed vlan ") :].strip()
            icfg["allowed_vlans"] = _parse_vlan_list(spec_str, icfg["allowed_vlans"])
        elif low == "no switchport trunk allowed vlan":
            icfg["allowed_vlans"] = None
        elif low.startswith("encapsulation dot1q "):
            parts = raw.split()
            if len(parts) >= 3 and parts[2].isdigit():
                icfg["dot1q_vlan"] = int(parts[2])
        elif low.startswith("channel-group "):
            # e.g. 'channel-group 1 mode active'
            parts = low.split()
            if len(parts) >= 4 and parts[1].isdigit() and parts[2] == "mode":
                icfg["channel_group"] = (int(parts[1]), parts[3])

    return interfaces, globals_map


def verify_pkt_file(
    pkt_path: str | Path, ticket: ChallengeTicket
) -> VerificationResult:
    """Decode `pkt_path` and verify whether every injected fault / build stage in `ticket` has been resolved."""
    path = Path(pkt_path)
    if not path.is_file():
        return VerificationResult(
            inspected_path=path,
            all_passed=False,
            passed_count=0,
            total_count=len(ticket.faults),
            general_errors=[f"File not found: {path}"],
        )

    try:
        raw = path.read_bytes()
        container = decode_bytes(raw, "pkt")
        root = ET.fromstring(container.xml)
    except Exception as exc:
        return VerificationResult(
            inspected_path=path,
            all_passed=False,
            passed_count=0,
            total_count=len(ticket.faults),
            general_errors=[f"Could not decode .pkt file: {exc}"],
        )

    # Index devices by name and by SAVE_REF_ID
    devs_by_name: dict[str, ET.Element] = {}
    name_by_sid: dict[str, str] = {}
    for d in root.findall(".//NETWORK/DEVICES/DEVICE"):
        name = (d.findtext("ENGINE/NAME") or "").strip()
        sid = (d.findtext("ENGINE/SAVE_REF_ID") or "").strip()
        if name:
            devs_by_name[name] = d
        if sid and name:
            name_by_sid[sid] = name

    # Index links: list of (dev_a_name, port_a, dev_b_name, port_b)
    links: list[tuple[str, str, str, str]] = []
    for lk in root.findall(".//NETWORK/LINKS/LINK"):
        cab = lk.find("CABLE")
        if cab is None:
            continue
        frm_sid = (cab.findtext("FROM") or "").strip()
        to_sid = (cab.findtext("TO") or "").strip()
        ports = [(p.text or "").strip() for p in cab.findall("PORT")]
        if len(ports) >= 2:
            links.append(
                (
                    name_by_sid.get(frm_sid, frm_sid),
                    ports[0],
                    name_by_sid.get(to_sid, to_sid),
                    ports[1],
                )
            )

    items: list[CheckItemResult] = []
    passed_count = 0

    for fault in ticket.faults:
        spec = fault.verify_spec
        vtype = spec.get("type", "")
        dev_name = spec.get("device", fault.device)
        dev_el = devs_by_name.get(dev_name)

        if dev_el is None and vtype not in ("all_links_present", "all_trunks_operational", "all_hosts_ip_gw"):
            items.append(
                CheckItemResult(
                    fault_id=fault.fault_id,
                    title=fault.title,
                    device=dev_name,
                    passed=False,
                    observed_state="Device missing from .pkt",
                    expected_state=fault.expected_state,
                    message=f"Device '{dev_name}' was not found in the uploaded .pkt file.",
                )
            )
            continue

        # ==================================================================
        # LEVEL 1 CHECKS
        # ==================================================================
        # 1. End device IP + Mask + No duplicate IP
        if vtype == "end_device_ip":
            assert dev_el is not None
            exp_ip = spec["expected_ip"]
            exp_mask = spec["expected_mask"]
            obs_ip = (dev_el.findtext(".//PORT/IP") or "").strip()
            obs_mask = (dev_el.findtext(".//PORT/SUBNET") or "").strip()
            dup_devs = [
                other_name
                for other_name, other_el in devs_by_name.items()
                if other_name != dev_name
                and (other_el.findtext(".//PORT/IP") or "").strip() == exp_ip
            ]
            ok = (obs_ip == exp_ip) and (obs_mask == exp_mask) and not dup_devs
            obs_str = f"IP: {obs_ip or '(empty)'}, Mask: {obs_mask or '(empty)'}"
            if dup_devs:
                obs_str += f" [Duplicate IP conflict with {', '.join(dup_devs)}]"
            items.append(
                CheckItemResult(
                    fault_id=fault.fault_id,
                    title=fault.title,
                    device=dev_name,
                    passed=ok,
                    observed_state=obs_str,
                    expected_state=fault.expected_state,
                    message=(
                        f"Fixed! {dev_name} has IP {exp_ip}/{exp_mask}."
                        if ok
                        else f"Still faulty on {dev_name}: observed {obs_str}."
                    ),
                )
            )
            if ok:
                passed_count += 1

        # 2. End device Default Gateway
        elif vtype == "end_device_gateway":
            assert dev_el is not None
            exp_gw = spec["expected_gateway"]
            eng_gw = (dev_el.findtext("ENGINE/GATEWAY") or "").strip()
            port_gw = (dev_el.findtext(".//PORT/PORT_GATEWAY") or "").strip()
            obs_gw = eng_gw or port_gw
            ok = obs_gw == exp_gw
            items.append(
                CheckItemResult(
                    fault_id=fault.fault_id,
                    title=fault.title,
                    device=dev_name,
                    passed=ok,
                    observed_state=f"Default Gateway: {obs_gw or '(empty)'}",
                    expected_state=fault.expected_state,
                    message=(
                        f"Fixed! {dev_name} Default Gateway is set to {exp_gw}."
                        if ok
                        else f"Still faulty on {dev_name}: Default Gateway is '{obs_gw}'. Expected '{exp_gw}'."
                    ),
                )
            )
            if ok:
                passed_count += 1

        # 3. End device Subnet Mask
        elif vtype == "end_device_mask":
            assert dev_el is not None
            exp_mask = spec["expected_mask"]
            obs_mask = (dev_el.findtext(".//PORT/SUBNET") or "").strip()
            ok = obs_mask == exp_mask
            items.append(
                CheckItemResult(
                    fault_id=fault.fault_id,
                    title=fault.title,
                    device=dev_name,
                    passed=ok,
                    observed_state=f"Subnet Mask: {obs_mask or '(empty)'}",
                    expected_state=fault.expected_state,
                    message=(
                        f"Fixed! {dev_name} Subnet Mask is {exp_mask}."
                        if ok
                        else f"Still faulty on {dev_name}: Subnet Mask is '{obs_mask}'. Expected '{exp_mask}'."
                    ),
                )
            )
            if ok:
                passed_count += 1

        # 4. Router interface UP + Expected IP (+ optional Mask)
        elif vtype == "router_port_up":
            assert dev_el is not None
            iface_name = spec["interface"]
            exp_ip = spec["expected_ip"]
            exp_mask = spec.get("expected_mask")
            ifaces, _ = _parse_ios_config(dev_el)
            icfg = ifaces.get(iface_name, {})
            is_shut = icfg.get("shutdown", True)
            obs_ip = icfg.get("ip", "")
            obs_mask = icfg.get("mask", "")
            mask_ok = (exp_mask is None) or (obs_mask == exp_mask)
            ok = (not is_shut) and (obs_ip == exp_ip) and mask_ok
            state_label = "Administratively DOWN (shutdown)" if is_shut else "UP (no shutdown)"
            obs_str = f"{dev_name} {iface_name}: {state_label}, IP={obs_ip or 'unassigned'}/{obs_mask or 'none'}"
            items.append(
                CheckItemResult(
                    fault_id=fault.fault_id,
                    title=fault.title,
                    device=dev_name,
                    passed=ok,
                    observed_state=obs_str,
                    expected_state=fault.expected_state,
                    message=(
                        f"Fixed! {dev_name} {iface_name} is UP with IP {obs_ip}."
                        if ok
                        else f"Still faulty: {obs_str}."
                    ),
                )
            )
            if ok:
                passed_count += 1

        # 5. Router cabled port matches configured IP
        elif vtype == "router_cabled_port_matches_ip":
            assert dev_el is not None
            peer_dev = spec["peer_device"]
            exp_ip = spec["expected_ip"]
            ifaces, _ = _parse_ios_config(dev_el)
            cabled_port = None
            for da, pa, db, pb in links:
                if da == dev_name and db == peer_dev:
                    cabled_port = pa
                    break
                if db == dev_name and da == peer_dev:
                    cabled_port = pb
                    break

            if not cabled_port:
                ok = False
                obs_str = f"No cable found between {dev_name} and {peer_dev}"
            else:
                icfg = ifaces.get(cabled_port, {})
                obs_ip = icfg.get("ip", "")
                is_shut = icfg.get("shutdown", True)
                ok = (obs_ip == exp_ip) and (not is_shut)
                obs_str = (
                    f"Cabled on {dev_name} {cabled_port} "
                    f"(IP={obs_ip or 'unassigned'}, {'DOWN' if is_shut else 'UP'})"
                )
            items.append(
                CheckItemResult(
                    fault_id=fault.fault_id,
                    title=fault.title,
                    device=dev_name,
                    passed=ok,
                    observed_state=obs_str,
                    expected_state=fault.expected_state,
                    message=(
                        f"Fixed! {dev_name} uplink to {peer_dev} is properly cabled and configured ({cabled_port})."
                        if ok
                        else f"Still faulty: {obs_str}."
                    ),
                )
            )
            if ok:
                passed_count += 1

        # 6. Device Physically Powered ON
        elif vtype == "device_powered_on":
            assert dev_el is not None
            pw = (dev_el.findtext("ENGINE/POWER") or "").strip().lower()
            ok = pw == "true"
            obs_str = f"{dev_name} Power: {'ON' if ok else 'OFF'}"
            items.append(
                CheckItemResult(
                    fault_id=fault.fault_id,
                    title=fault.title,
                    device=dev_name,
                    passed=ok,
                    observed_state=obs_str,
                    expected_state=fault.expected_state,
                    message=(
                        f"Fixed! {dev_name} is powered ON."
                        if ok
                        else f"Still faulty: {dev_name} physical power switch is still OFF."
                    ),
                )
            )
            if ok:
                passed_count += 1

        # 7. Missing Patch Cable Replaced
        elif vtype == "link_present":
            peer_dev = spec["peer_device"]
            dev_port = spec["device_port"]
            found_peer_port = None
            for da, pa, db, pb in links:
                if da == dev_name and pa == dev_port and db == peer_dev:
                    found_peer_port = pb
                    break
                if db == dev_name and pb == dev_port and da == peer_dev:
                    found_peer_port = pa
                    break
            ok = found_peer_port is not None
            obs_str = (
                f"Connected: {dev_name} {dev_port} <-> {peer_dev} {found_peer_port}"
                if ok
                else f"No cable connected between {dev_name} and {peer_dev}"
            )
            items.append(
                CheckItemResult(
                    fault_id=fault.fault_id,
                    title=fault.title,
                    device=dev_name,
                    passed=ok,
                    observed_state=obs_str,
                    expected_state=fault.expected_state,
                    message=(
                        f"Fixed! {obs_str}."
                        if ok
                        else f"Still faulty: {obs_str}."
                    ),
                )
            )
            if ok:
                passed_count += 1

        # 8. End-device NIC Port Status Enabled
        elif vtype == "end_device_nic_enabled":
            assert dev_el is not None
            pw = (dev_el.findtext(".//PORT/POWER") or "").strip().lower()
            ok = pw == "true"
            obs_str = f"{dev_name} FastEthernet0 Port Status: {'ON' if ok else 'OFF'}"
            items.append(
                CheckItemResult(
                    fault_id=fault.fault_id,
                    title=fault.title,
                    device=dev_name,
                    passed=ok,
                    observed_state=obs_str,
                    expected_state=fault.expected_state,
                    message=(
                        f"Fixed! {dev_name} FastEthernet0 NIC is enabled."
                        if ok
                        else f"Still faulty: {obs_str}."
                    ),
                )
            )
            if ok:
                passed_count += 1

        # 9. Speed / Duplex Match
        elif vtype == "speed_duplex_match":
            assert dev_el is not None
            sw_name = spec["switch_device"]
            sw_port = spec["switch_port"]
            sw_el = devs_by_name.get(sw_name)
            sw_ifaces, _ = _parse_ios_config(sw_el) if sw_el is not None else ({}, {})
            sw_icfg = sw_ifaces.get(sw_port, {"speed": "auto", "duplex": "auto"})
            sw_speed = sw_icfg.get("speed", "auto")
            sw_duplex = sw_icfg.get("duplex", "auto")

            auto_bw = (dev_el.findtext(".//PORT/AUTONEGOTIATEBANDWIDTH") or "").strip().lower() == "true"
            auto_dup = (dev_el.findtext(".//PORT/AUTONEGOTIATEDUPLEX") or "").strip().lower() == "true"
            bw = (dev_el.findtext(".//PORT/BANDWIDTH") or "").strip()
            full_dup = (dev_el.findtext(".//PORT/FULLDUPLEX") or "").strip().lower() == "true"

            pc_is_100_full = (bw == "100000") and full_dup
            pc_is_auto = auto_bw and auto_dup
            sw_is_auto = (sw_speed == "auto") and (sw_duplex == "auto")

            ok = pc_is_auto or pc_is_100_full or (sw_is_auto and pc_is_auto)
            pc_desc = (
                "Auto/Auto"
                if pc_is_auto
                else f"{'100 Mbps' if bw == '100000' else '10 Mbps'} / {'Full' if full_dup else 'Half'}"
            )
            obs_str = f"{dev_name} NIC={pc_desc} | {sw_name} {sw_port}=speed {sw_speed}, duplex {sw_duplex}"
            items.append(
                CheckItemResult(
                    fault_id=fault.fault_id,
                    title=fault.title,
                    device=dev_name,
                    passed=ok,
                    observed_state=obs_str,
                    expected_state=fault.expected_state,
                    message=(
                        f"Fixed! Speed and duplex settings are compatible ({obs_str})."
                        if ok
                        else f"Still mismatched: {obs_str}."
                    ),
                )
            )
            if ok:
                passed_count += 1

        # 10. Switch Access Port UP
        elif vtype == "switch_port_up":
            assert dev_el is not None
            iface_name = spec["interface"]
            ifaces, _ = _parse_ios_config(dev_el)
            icfg = ifaces.get(iface_name, {"shutdown": False})
            is_shut = icfg.get("shutdown", False)
            ok = not is_shut
            obs_str = f"{dev_name} {iface_name}: {'Administratively DOWN (shutdown)' if is_shut else 'UP (no shutdown)'}"
            items.append(
                CheckItemResult(
                    fault_id=fault.fault_id,
                    title=fault.title,
                    device=dev_name,
                    passed=ok,
                    observed_state=obs_str,
                    expected_state=fault.expected_state,
                    message=(
                        f"Fixed! {dev_name} {iface_name} is UP."
                        if ok
                        else f"Still faulty: {obs_str}."
                    ),
                )
            )
            if ok:
                passed_count += 1

        # 11. Switch Management SVI (Vlan1 or VlanX IP + UP + ip default-gateway)
        elif vtype == "switch_mgmt_svi":
            assert dev_el is not None
            exp_ip = spec["expected_ip"]
            exp_mask = spec["expected_mask"]
            exp_gw = spec["expected_gateway"]
            svi_name = spec.get("svi_interface", "Vlan1")
            ifaces, globals_map = _parse_ios_config(dev_el)
            svi = ifaces.get(svi_name, {"ip": "", "mask": "", "shutdown": True})
            obs_ip = svi.get("ip", "")
            obs_mask = svi.get("mask", "")
            is_shut = svi.get("shutdown", True)
            obs_gw = globals_map.get("default_gateway", "")

            ok = (obs_ip == exp_ip) and (obs_mask == exp_mask) and (not is_shut) and (obs_gw == exp_gw)
            obs_str = (
                f"{svi_name} IP={obs_ip or 'none'}/{obs_mask or 'none'} "
                f"({'DOWN' if is_shut else 'UP'}), default-gateway={obs_gw or 'none'}"
            )
            items.append(
                CheckItemResult(
                    fault_id=fault.fault_id,
                    title=fault.title,
                    device=dev_name,
                    passed=ok,
                    observed_state=obs_str,
                    expected_state=fault.expected_state,
                    message=(
                        f"Fixed! {dev_name} {svi_name} management SVI and default-gateway are properly configured."
                        if ok
                        else f"Still faulty on {dev_name}: {obs_str}."
                    ),
                )
            )
            if ok:
                passed_count += 1

        # 12. End device Static IPv4 (Not DHCP/APIPA)
        elif vtype == "end_device_static_not_dhcp":
            assert dev_el is not None
            exp_ip = spec["expected_ip"]
            exp_mask = spec["expected_mask"]
            exp_gw = spec["expected_gateway"]
            dhcp_on = (dev_el.findtext(".//PORT/PORT_DHCP_ENABLE") or "").strip().lower() == "true"
            obs_ip = (dev_el.findtext(".//PORT/IP") or "").strip()
            obs_mask = (dev_el.findtext(".//PORT/SUBNET") or "").strip()
            obs_gw = (
                (dev_el.findtext("ENGINE/GATEWAY") or "").strip()
                or (dev_el.findtext(".//PORT/PORT_GATEWAY") or "").strip()
            )
            ok = (not dhcp_on) and (obs_ip == exp_ip) and (obs_mask == exp_mask) and (obs_gw == exp_gw)
            obs_str = (
                "DHCP Enabled (APIPA)"
                if dhcp_on
                else f"Static IP={obs_ip}, Mask={obs_mask}, GW={obs_gw}"
            )
            items.append(
                CheckItemResult(
                    fault_id=fault.fault_id,
                    title=fault.title,
                    device=dev_name,
                    passed=ok,
                    observed_state=obs_str,
                    expected_state=fault.expected_state,
                    message=(
                        f"Fixed! {dev_name} is configured with static IP {exp_ip} and gateway {exp_gw}."
                        if ok
                        else f"Still faulty on {dev_name}: {obs_str}."
                    ),
                )
            )
            if ok:
                passed_count += 1

        # 13. End device Full IP + Mask + Gateway (Server / Host check)
        elif vtype == "end_device_full_ip_gw":
            assert dev_el is not None
            exp_ip = spec["expected_ip"]
            exp_mask = spec["expected_mask"]
            exp_gw = spec["expected_gateway"]
            obs_ip = (dev_el.findtext(".//PORT/IP") or "").strip()
            obs_mask = (dev_el.findtext(".//PORT/SUBNET") or "").strip()
            obs_gw = (
                (dev_el.findtext("ENGINE/GATEWAY") or "").strip()
                or (dev_el.findtext(".//PORT/PORT_GATEWAY") or "").strip()
            )
            ok = (obs_ip == exp_ip) and (obs_mask == exp_mask) and (obs_gw == exp_gw)
            obs_str = f"IP={obs_ip or 'none'}, Mask={obs_mask or 'none'}, GW={obs_gw or 'none'}"
            items.append(
                CheckItemResult(
                    fault_id=fault.fault_id,
                    title=fault.title,
                    device=dev_name,
                    passed=ok,
                    observed_state=obs_str,
                    expected_state=fault.expected_state,
                    message=(
                        f"Fixed! {dev_name} has IP {exp_ip}, Mask {exp_mask}, Gateway {exp_gw}."
                        if ok
                        else f"Still faulty on {dev_name}: {obs_str}."
                    ),
                )
            )
            if ok:
                passed_count += 1

        # 14. End device DNS Server IP
        elif vtype == "end_device_dns":
            assert dev_el is not None
            exp_dns = spec["expected_dns"]
            port_dns = (dev_el.findtext(".//PORT/PORT_DNS") or "").strip()
            eng_dns = (dev_el.findtext("ENGINE/DNS_CLIENT/SERVER_IP") or "").strip()
            obs_dns = port_dns or eng_dns
            ok = (port_dns == exp_dns) or (eng_dns == exp_dns)
            items.append(
                CheckItemResult(
                    fault_id=fault.fault_id,
                    title=fault.title,
                    device=dev_name,
                    passed=ok,
                    observed_state=f"DNS Server: {obs_dns or '(empty)'}",
                    expected_state=fault.expected_state,
                    message=(
                        f"Fixed! {dev_name} DNS Server is set to {exp_dns}."
                        if ok
                        else f"Still faulty on {dev_name}: DNS Server is '{obs_dns}'. Expected '{exp_dns}'."
                    ),
                )
            )
            if ok:
                passed_count += 1

        # ==================================================================
        # LEVEL 2 CHECKS (VLANs, 802.1Q Trunks, DTP, RoaS, EtherChannel)
        # ==================================================================
        # 15. Switch Access Port Assigned to Expected VLAN
        elif vtype == "switch_access_vlan":
            assert dev_el is not None
            iface_name = spec["interface"]
            exp_vlan = int(spec["expected_vlan"])
            ifaces, _ = _parse_ios_config(dev_el)
            icfg = ifaces.get(iface_name, {"access_vlan": 1, "trunk": False, "shutdown": False})
            obs_vlan = icfg.get("access_vlan", 1)
            is_trunk = icfg.get("trunk", False)
            is_shut = icfg.get("shutdown", False)
            ok = (not is_shut) and (not is_trunk) and (obs_vlan == exp_vlan)
            obs_str = (
                f"{dev_name} {iface_name}: mode={'trunk' if is_trunk else 'access'}, "
                f"access_vlan={obs_vlan}, {'DOWN' if is_shut else 'UP'}"
            )
            items.append(
                CheckItemResult(
                    fault_id=fault.fault_id,
                    title=fault.title,
                    device=dev_name,
                    passed=ok,
                    observed_state=obs_str,
                    expected_state=fault.expected_state,
                    message=(
                        f"Fixed! {dev_name} {iface_name} is assigned to Access VLAN {exp_vlan}."
                        if ok
                        else f"Still faulty: {obs_str}."
                    ),
                )
            )
            if ok:
                passed_count += 1

        # 16. VLAN Exists in Switch Database + Access Port Assigned
        elif vtype == "vlan_exists_in_db":
            assert dev_el is not None
            exp_vlan = int(spec["expected_vlan"])
            acc_port = spec.get("access_port")
            sw_vlans = _extract_switch_vlans(dev_el)
            ifaces, _ = _parse_ios_config(dev_el)
            vlan_present = exp_vlan in sw_vlans
            port_ok = True
            if acc_port:
                icfg = ifaces.get(acc_port, {"access_vlan": 1, "shutdown": False})
                port_ok = (icfg.get("access_vlan") == exp_vlan) and (not icfg.get("shutdown", False))
            ok = vlan_present and port_ok
            obs_str = f"{dev_name} VLANs={sorted(v for v in sw_vlans if v < 1000)}"
            if acc_port:
                obs_str += f", {acc_port} access_vlan={ifaces.get(acc_port, {}).get('access_vlan', 1)}"
            items.append(
                CheckItemResult(
                    fault_id=fault.fault_id,
                    title=fault.title,
                    device=dev_name,
                    passed=ok,
                    observed_state=obs_str,
                    expected_state=fault.expected_state,
                    message=(
                        f"Fixed! VLAN {exp_vlan} is active in {dev_name}'s VLAN database."
                        if ok
                        else f"Still faulty: {obs_str}."
                    ),
                )
            )
            if ok:
                passed_count += 1

        # 17. Voice & Data Access Port VLANs
        elif vtype == "switch_voice_and_data_vlan":
            assert dev_el is not None
            iface_name = spec["interface"]
            exp_data = int(spec["expected_data_vlan"])
            exp_voice = int(spec["expected_voice_vlan"])
            ifaces, _ = _parse_ios_config(dev_el)
            icfg = ifaces.get(iface_name, {})
            obs_data = icfg.get("access_vlan", 1)
            obs_voice = icfg.get("voice_vlan")
            is_shut = icfg.get("shutdown", False)
            ok = (not is_shut) and (obs_data == exp_data) and (obs_voice == exp_voice)
            obs_str = (
                f"{dev_name} {iface_name}: data_vlan={obs_data}, "
                f"voice_vlan={obs_voice or 'none'}, {'DOWN' if is_shut else 'UP'}"
            )
            items.append(
                CheckItemResult(
                    fault_id=fault.fault_id,
                    title=fault.title,
                    device=dev_name,
                    passed=ok,
                    observed_state=obs_str,
                    expected_state=fault.expected_state,
                    message=(
                        f"Fixed! {dev_name} {iface_name} has Data VLAN {exp_data} and Voice VLAN {exp_voice}."
                        if ok
                        else f"Still faulty: {obs_str}."
                    ),
                )
            )
            if ok:
                passed_count += 1

        # 18. Switch Port Configured as 802.1Q Trunk (and allows required VLANs)
        elif vtype == "switch_port_trunk":
            assert dev_el is not None
            iface_name = spec["interface"]
            req_vlans = {int(v) for v in spec.get("required_vlans", [])}
            ifaces, _ = _parse_ios_config(dev_el)
            icfg = ifaces.get(iface_name, {})
            is_trunk = icfg.get("trunk", False)
            is_shut = icfg.get("shutdown", False)
            allowed = icfg.get("allowed_vlans")
            vlans_ok = (allowed is None) or req_vlans.issubset(allowed)
            ok = is_trunk and (not is_shut) and vlans_ok
            mode_str = icfg.get("switchport_mode") or ("trunk" if is_trunk else "access")
            obs_str = f"{dev_name} {iface_name}: mode={mode_str}, {'DOWN' if is_shut else 'UP'}"
            items.append(
                CheckItemResult(
                    fault_id=fault.fault_id,
                    title=fault.title,
                    device=dev_name,
                    passed=ok,
                    observed_state=obs_str,
                    expected_state=fault.expected_state,
                    message=(
                        f"Fixed! {dev_name} {iface_name} is operating as an 802.1Q trunk."
                        if ok
                        else f"Still faulty: {obs_str}."
                    ),
                )
            )
            if ok:
                passed_count += 1

        # 19. Trunk Allowed VLAN List Permits All Required VLANs
        elif vtype == "trunk_allowed_vlans":
            assert dev_el is not None
            iface_name = spec["interface"]
            req_vlans = {int(v) for v in spec.get("required_vlans", [])}
            ifaces, _ = _parse_ios_config(dev_el)
            icfg = ifaces.get(iface_name, {})
            is_trunk = icfg.get("trunk", False)
            is_shut = icfg.get("shutdown", False)
            allowed = icfg.get("allowed_vlans")
            vlans_ok = (allowed is None) or req_vlans.issubset(allowed)
            ok = is_trunk and (not is_shut) and vlans_ok
            allowed_desc = "ALL (1-1005)" if allowed is None else ",".join(str(v) for v in sorted(allowed))
            obs_str = (
                f"{dev_name} {iface_name}: mode={'trunk' if is_trunk else 'access'}, "
                f"allowed_vlans={allowed_desc}"
            )
            items.append(
                CheckItemResult(
                    fault_id=fault.fault_id,
                    title=fault.title,
                    device=dev_name,
                    passed=ok,
                    observed_state=obs_str,
                    expected_state=fault.expected_state,
                    message=(
                        f"Fixed! {dev_name} {iface_name} permits all required VLANs ({sorted(req_vlans)})."
                        if ok
                        else f"Still faulty: {obs_str}."
                    ),
                )
            )
            if ok:
                passed_count += 1

        # 20. 802.1Q Trunk Native VLAN Match Across Peers
        elif vtype == "trunk_native_vlan_match":
            assert dev_el is not None
            iface_name = spec["interface"]
            peer_dev_name = spec["peer_device"]
            peer_iface = spec["peer_interface"]
            peer_el = devs_by_name.get(peer_dev_name)
            ifaces_a, _ = _parse_ios_config(dev_el)
            ifaces_b, _ = _parse_ios_config(peer_el) if peer_el is not None else ({}, {})
            icfg_a = ifaces_a.get(iface_name, {})
            icfg_b = ifaces_b.get(peer_iface, {})
            nat_a = icfg_a.get("native_vlan", 1)
            nat_b = icfg_b.get("native_vlan", 1)
            both_trunk = icfg_a.get("trunk", False) and icfg_b.get("trunk", False)
            ok = both_trunk and (nat_a == nat_b)
            obs_str = (
                f"{dev_name} {iface_name} native={nat_a} | "
                f"{peer_dev_name} {peer_iface} native={nat_b}"
            )
            items.append(
                CheckItemResult(
                    fault_id=fault.fault_id,
                    title=fault.title,
                    device=dev_name,
                    passed=ok,
                    observed_state=obs_str,
                    expected_state=fault.expected_state,
                    message=(
                        f"Fixed! Both trunk ends match on Native VLAN {nat_a}."
                        if ok
                        else f"Still mismatched: {obs_str}."
                    ),
                )
            )
            if ok:
                passed_count += 1

        # 21. DTP Negotiation / Trunk Operational Between Switches
        elif vtype == "dtp_trunk_operational":
            assert dev_el is not None
            iface_name = spec["interface"]
            peer_dev_name = spec["peer_device"]
            peer_iface = spec["peer_interface"]
            peer_el = devs_by_name.get(peer_dev_name)
            ifaces_a, _ = _parse_ios_config(dev_el)
            ifaces_b, _ = _parse_ios_config(peer_el) if peer_el is not None else ({}, {})
            icfg_a = ifaces_a.get(iface_name, {})
            icfg_b = ifaces_b.get(peer_iface, {})
            mode_a = icfg_a.get("switchport_mode") or ("trunk" if icfg_a.get("trunk") else "access")
            mode_b = icfg_b.get("switchport_mode") or ("trunk" if icfg_b.get("trunk") else "access")
            valid_modes = {"trunk", "dynamic desirable", "dynamic auto"}
            # Trunk forms if both are in valid_modes AND at least one is 'trunk' or 'dynamic desirable'
            forms_trunk = (
                mode_a in valid_modes
                and mode_b in valid_modes
                and (mode_a in {"trunk", "dynamic desirable"} or mode_b in {"trunk", "dynamic desirable"})
                and not icfg_a.get("shutdown", False)
                and not icfg_b.get("shutdown", False)
            )
            obs_str = f"{dev_name} {iface_name}='{mode_a}' <-> {peer_dev_name} {peer_iface}='{mode_b}'"
            items.append(
                CheckItemResult(
                    fault_id=fault.fault_id,
                    title=fault.title,
                    device=dev_name,
                    passed=forms_trunk,
                    observed_state=obs_str,
                    expected_state=fault.expected_state,
                    message=(
                        f"Fixed! Inter-switch link forms an operational 802.1Q trunk ({obs_str})."
                        if forms_trunk
                        else f"Still failing to form trunk: {obs_str}."
                    ),
                )
            )
            if forms_trunk:
                passed_count += 1

        # 22. Router-on-a-Stick Subinterface 802.1Q Tag + IP + Mask
        elif vtype == "roas_subinterface_config":
            assert dev_el is not None
            parent_port = spec["parent_port"]
            vlan_id = int(spec["vlan_id"])
            exp_ip = spec["expected_ip"]
            exp_mask = spec["expected_mask"]
            ifaces, _ = _parse_ios_config(dev_el)
            parent_cfg = ifaces.get(parent_port, {"shutdown": True})
            parent_up = not parent_cfg.get("shutdown", True)

            # Find subinterface matching parent_port.<vlan_id> or any subinterface on parent_port with dot1q_vlan == vlan_id
            sub_key = f"{parent_port}.{vlan_id}"
            sub_cfg = ifaces.get(sub_key)
            if sub_cfg is None:
                for k, v in ifaces.items():
                    if k.startswith(f"{parent_port}.") and v.get("dot1q_vlan") == vlan_id:
                        sub_cfg = v
                        sub_key = k
                        break

            if sub_cfg is None:
                ok = False
                obs_str = f"Subinterface {sub_key} not found on {dev_name}"
            else:
                obs_tag = sub_cfg.get("dot1q_vlan")
                obs_ip = sub_cfg.get("ip", "")
                obs_mask = sub_cfg.get("mask", "")
                sub_up = not sub_cfg.get("shutdown", False)
                ok = (
                    parent_up
                    and sub_up
                    and (obs_tag == vlan_id)
                    and (obs_ip == exp_ip)
                    and (obs_mask == exp_mask)
                )
                obs_str = (
                    f"{dev_name} {sub_key}: dot1Q={obs_tag or 'none'}, "
                    f"IP={obs_ip or 'none'}/{obs_mask or 'none'}, "
                    f"parent={'UP' if parent_up else 'DOWN'}"
                )
            items.append(
                CheckItemResult(
                    fault_id=fault.fault_id,
                    title=fault.title,
                    device=dev_name,
                    passed=ok,
                    observed_state=obs_str,
                    expected_state=fault.expected_state,
                    message=(
                        f"Fixed! {dev_name} {sub_key} is UP with dot1Q {vlan_id} and IP {exp_ip}/{exp_mask}."
                        if ok
                        else f"Still faulty: {obs_str}."
                    ),
                )
            )
            if ok:
                passed_count += 1

        # 23. Router-on-a-Stick Physical Parent Interface UP
        elif vtype == "roas_parent_up":
            assert dev_el is not None
            parent_port = spec["parent_port"]
            vlan_ids = [int(v) for v in spec.get("vlan_ids", [])]
            ifaces, _ = _parse_ios_config(dev_el)
            parent_cfg = ifaces.get(parent_port, {"shutdown": True})
            parent_up = not parent_cfg.get("shutdown", True)
            subs_up = all(
                not ifaces.get(f"{parent_port}.{vid}", {"shutdown": True}).get("shutdown", True)
                for vid in vlan_ids
            )
            ok = parent_up and subs_up
            obs_str = (
                f"{dev_name} {parent_port}: {'UP (no shutdown)' if parent_up else 'Administratively DOWN (shutdown)'}"
            )
            items.append(
                CheckItemResult(
                    fault_id=fault.fault_id,
                    title=fault.title,
                    device=dev_name,
                    passed=ok,
                    observed_state=obs_str,
                    expected_state=fault.expected_state,
                    message=(
                        f"Fixed! {dev_name} {parent_port} and its 802.1Q subinterfaces are UP."
                        if ok
                        else f"Still faulty: {obs_str}."
                    ),
                )
            )
            if ok:
                passed_count += 1

        # 24. Layer 2 EtherChannel Protocol Match (LACP / PAgP / On)
        elif vtype == "etherchannel_lacp_valid":
            assert dev_el is not None
            member_ports = spec["member_ports"]
            peer_dev_name = spec["peer_device"]
            peer_ports = spec["peer_member_ports"]
            grp_num = int(spec.get("group_number", 1))
            peer_el = devs_by_name.get(peer_dev_name)
            ifaces_a, _ = _parse_ios_config(dev_el)
            ifaces_b, _ = _parse_ios_config(peer_el) if peer_el is not None else ({}, {})

            modes_a = [
                (ifaces_a.get(p, {}).get("channel_group") or (0, "none"))[1]
                for p in member_ports
            ]
            modes_b = [
                (ifaces_b.get(p, {}).get("channel_group") or (0, "none"))[1]
                for p in peer_ports
            ]

            def _ec_compatible(ma: str, mb: str) -> bool:
                if ma == "active" and mb in ("active", "passive"):
                    return True
                if mb == "active" and ma in ("active", "passive"):
                    return True
                if ma == "desirable" and mb in ("desirable", "auto"):
                    return True
                if mb == "desirable" and ma in ("desirable", "auto"):
                    return True
                if ma == "on" and mb == "on":
                    return True
                return False

            all_compat = (
                len(set(modes_a)) == 1
                and len(set(modes_b)) == 1
                and _ec_compatible(modes_a[0], modes_b[0])
            )
            po_name = f"Port-channel{grp_num}"
            po_a_trunk = ifaces_a.get(po_name, {}).get("trunk", False) or all(
                ifaces_a.get(p, {}).get("trunk", False) for p in member_ports
            )
            po_b_trunk = ifaces_b.get(po_name, {}).get("trunk", False) or all(
                ifaces_b.get(p, {}).get("trunk", False) for p in peer_ports
            )
            ok = all_compat and po_a_trunk and po_b_trunk
            obs_str = (
                f"{dev_name} ({','.join(member_ports)}) mode={modes_a[0]} | "
                f"{peer_dev_name} ({','.join(peer_ports)}) mode={modes_b[0]}"
            )
            items.append(
                CheckItemResult(
                    fault_id=fault.fault_id,
                    title=fault.title,
                    device=dev_name,
                    passed=ok,
                    observed_state=obs_str,
                    expected_state=fault.expected_state,
                    message=(
                        f"Fixed! EtherChannel {po_name} is bundled and trunking ({obs_str})."
                        if ok
                        else f"Still incompatible: {obs_str}."
                    ),
                )
            )
            if ok:
                passed_count += 1

        # ==================================================================
        # MODE 2 (BUILD NETWORK FROM SCRATCH) MULTI-ITEM COMMISSIONING GATES
        # ==================================================================
        # 25. All Expected Physical Links Connected
        elif vtype == "all_links_present":
            expected_links = spec.get("expected_links", [])
            missing: list[str] = []
            for exp in expected_links:
                da, pa, db, pb = exp["dev_a"], exp["port_a"], exp["dev_b"], exp["port_b"]
                found = any(
                    (la == da and lpa == pa and lb == db and lpb == pb)
                    or (la == db and lpa == pb and lb == da and lpb == pa)
                    for la, lpa, lb, lpb in links
                )
                if not found:
                    missing.append(f"{da} {pa} <-> {db} {pb}")
            ok = len(missing) == 0
            obs_str = (
                f"All {len(expected_links)} physical links connected"
                if ok
                else f"Missing {len(missing)}/{len(expected_links)} cable(s): {', '.join(missing[:3])}"
            )
            items.append(
                CheckItemResult(
                    fault_id=fault.fault_id,
                    title=fault.title,
                    device=dev_name,
                    passed=ok,
                    observed_state=obs_str,
                    expected_state=fault.expected_state,
                    message=(
                        f"Fixed! {obs_str}."
                        if ok
                        else f"Incomplete cabling: {obs_str}."
                    ),
                )
            )
            if ok:
                passed_count += 1

        # 26. Router-on-a-Stick All Subinterfaces & Parent Port Configured
        elif vtype == "roas_all_subinterfaces":
            assert dev_el is not None
            parent_port = spec["parent_port"]
            sub_specs = spec["subinterfaces"]  # list of {vlan_id, expected_ip, expected_mask}
            ifaces, _ = _parse_ios_config(dev_el)
            parent_up = not ifaces.get(parent_port, {"shutdown": True}).get("shutdown", True)
            bad_subs: list[str] = []
            if not parent_up:
                bad_subs.append(f"{parent_port} is shutdown")
            for s_item in sub_specs:
                vid = int(s_item["vlan_id"])
                exp_ip = s_item["expected_ip"]
                exp_mask = s_item["expected_mask"]
                sub_key = f"{parent_port}.{vid}"
                scfg = ifaces.get(sub_key, {})
                if (
                    scfg.get("dot1q_vlan") != vid
                    or scfg.get("ip") != exp_ip
                    or scfg.get("mask") != exp_mask
                    or scfg.get("shutdown", False)
                ):
                    bad_subs.append(f"{sub_key} (expected dot1Q {vid}, {exp_ip}/{exp_mask})")
            ok = len(bad_subs) == 0
            obs_str = "Parent UP & all 802.1Q subinterfaces configured" if ok else "; ".join(bad_subs)
            items.append(
                CheckItemResult(
                    fault_id=fault.fault_id,
                    title=fault.title,
                    device=dev_name,
                    passed=ok,
                    observed_state=obs_str,
                    expected_state=fault.expected_state,
                    message=(
                        f"Fixed! {dev_name} Router-on-a-Stick is fully operational."
                        if ok
                        else f"Still incomplete on {dev_name}: {obs_str}."
                    ),
                )
            )
            if ok:
                passed_count += 1

        # 27. Switch VLANs, Access Ports & Trunks Configured (Build Mode Level 2)
        elif vtype == "switch_vlans_and_ports":
            assert dev_el is not None
            req_vlans = {int(v) for v in spec.get("required_vlans", [])}
            access_map: dict[str, int] = {k: int(v) for k, v in spec.get("access_ports", {}).items()}
            trunk_ports: list[str] = list(spec.get("trunk_ports", []))
            sw_vlans = _extract_switch_vlans(dev_el)
            ifaces, _ = _parse_ios_config(dev_el)
            issues: list[str] = []
            missing_vlans = sorted(req_vlans - sw_vlans)
            if missing_vlans:
                issues.append(f"Missing VLANs in DB: {missing_vlans}")
            for p_name, exp_v in access_map.items():
                icfg = ifaces.get(p_name, {"access_vlan": 1, "trunk": False, "shutdown": False})
                if icfg.get("trunk") or icfg.get("access_vlan", 1) != exp_v or icfg.get("shutdown", False):
                    issues.append(f"{p_name}!=VLAN {exp_v}")
            for t_port in trunk_ports:
                icfg = ifaces.get(t_port, {"trunk": False, "shutdown": False})
                if not icfg.get("trunk") or icfg.get("shutdown", False):
                    issues.append(f"{t_port} not trunking")
            ok = len(issues) == 0
            obs_str = f"{dev_name}: All VLANs, access ports & trunks verified" if ok else f"{dev_name}: {', '.join(issues)}"
            items.append(
                CheckItemResult(
                    fault_id=fault.fault_id,
                    title=fault.title,
                    device=dev_name,
                    passed=ok,
                    observed_state=obs_str,
                    expected_state=fault.expected_state,
                    message=obs_str,
                )
            )
            if ok:
                passed_count += 1

        # 28. All Hosts IP / Mask / Gateway / DNS Configured (Build Mode)
        elif vtype == "all_hosts_ip_gw":
            host_specs = spec.get("hosts", [])
            bad_hosts: list[str] = []
            for h in host_specs:
                h_name = h["device"]
                h_el = devs_by_name.get(h_name)
                if h_el is None:
                    bad_hosts.append(f"{h_name} missing")
                    continue
                obs_ip = (h_el.findtext(".//PORT/IP") or "").strip()
                obs_mask = (h_el.findtext(".//PORT/SUBNET") or "").strip()
                obs_gw = (
                    (h_el.findtext("ENGINE/GATEWAY") or "").strip()
                    or (h_el.findtext(".//PORT/PORT_GATEWAY") or "").strip()
                )
                if (
                    obs_ip != h["expected_ip"]
                    or obs_mask != h["expected_mask"]
                    or obs_gw != h["expected_gateway"]
                ):
                    bad_hosts.append(f"{h_name} (IP={obs_ip or 'none'}, GW={obs_gw or 'none'})")
            ok = len(bad_hosts) == 0
            obs_str = (
                f"All {len(host_specs)} endpoints properly addressed"
                if ok
                else f"Misconfigured endpoints: {', '.join(bad_hosts)}"
            )
            items.append(
                CheckItemResult(
                    fault_id=fault.fault_id,
                    title=fault.title,
                    device=dev_name,
                    passed=ok,
                    observed_state=obs_str,
                    expected_state=fault.expected_state,
                    message=obs_str,
                )
            )
            if ok:
                passed_count += 1

    total = len(ticket.faults)
    return VerificationResult(
        inspected_path=path,
        all_passed=(passed_count == total and total > 0),
        passed_count=passed_count,
        total_count=total,
        items=items,
    )
