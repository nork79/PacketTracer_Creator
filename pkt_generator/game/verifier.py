"""Inspects an uploaded .pkt file against a ChallengeTicket to verify if faults are fixed."""

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


def _parse_ios_config(dev_el: ET.Element) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    """Parse <ENGINE><RUNNINGCONFIG> on a router/switch into:
      (interfaces_map, globals_map)
    """
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
        if raw == "!":
            cur_if = None
            continue
        if cur_if is None:
            continue

        interfaces[cur_if]["lines"].append(raw)
        if raw == "shutdown":
            interfaces[cur_if]["shutdown"] = True
        elif raw == "no shutdown":
            interfaces[cur_if]["shutdown"] = False
        elif raw.startswith("ip address "):
            parts = raw.split()
            if len(parts) >= 4:
                interfaces[cur_if]["ip"] = parts[2]
                interfaces[cur_if]["mask"] = parts[3]
        elif raw.startswith("speed "):
            interfaces[cur_if]["speed"] = raw.split(None, 1)[1].strip()
        elif raw.startswith("duplex "):
            interfaces[cur_if]["duplex"] = raw.split(None, 1)[1].strip()

    return interfaces, globals_map


def verify_pkt_file(
    pkt_path: str | Path, ticket: ChallengeTicket
) -> VerificationResult:
    """Decode `pkt_path` and verify whether every injected fault in `ticket` has been resolved."""
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

        if dev_el is None:
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

        # 1. End device IP + Mask + No duplicate IP
        if vtype == "end_device_ip":
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

        # 4. Router interface UP + Expected IP
        elif vtype == "router_port_up":
            iface_name = spec["interface"]
            exp_ip = spec["expected_ip"]
            ifaces, _ = _parse_ios_config(dev_el)
            icfg = ifaces.get(iface_name, {})
            is_shut = icfg.get("shutdown", True)
            obs_ip = icfg.get("ip", "")
            ok = (not is_shut) and (obs_ip == exp_ip)
            state_label = "Administratively DOWN (shutdown)" if is_shut else "UP (no shutdown)"
            obs_str = f"{dev_name} {iface_name}: {state_label}, IP={obs_ip or 'unassigned'}"
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

            # Valid if PC is set to Auto, OR PC matches 100/Full, OR Switch was reset to auto/auto and PC is Auto
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

        # 11. Switch Management SVI (Vlan1 IP + UP + ip default-gateway)
        elif vtype == "switch_mgmt_svi":
            exp_ip = spec["expected_ip"]
            exp_mask = spec["expected_mask"]
            exp_gw = spec["expected_gateway"]
            ifaces, globals_map = _parse_ios_config(dev_el)
            vlan1 = ifaces.get("Vlan1", {"ip": "", "mask": "", "shutdown": True})
            obs_ip = vlan1.get("ip", "")
            obs_mask = vlan1.get("mask", "")
            is_shut = vlan1.get("shutdown", True)
            obs_gw = globals_map.get("default_gateway", "")

            ok = (obs_ip == exp_ip) and (obs_mask == exp_mask) and (not is_shut) and (obs_gw == exp_gw)
            obs_str = (
                f"Vlan1 IP={obs_ip or 'none'}/{obs_mask or 'none'} "
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
                        f"Fixed! {dev_name} Vlan1 management SVI and default-gateway are properly configured."
                        if ok
                        else f"Still faulty on {dev_name}: {obs_str}."
                    ),
                )
            )
            if ok:
                passed_count += 1

        # 12. End device Static IPv4 (Not DHCP/APIPA)
        elif vtype == "end_device_static_not_dhcp":
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

        # 13. End device Full IP + Mask + Gateway (Server misconfig)
        elif vtype == "end_device_full_ip_gw":
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
            obs_str = f"IP={obs_ip}, Mask={obs_mask}, GW={obs_gw}"
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

    total = len(ticket.faults)
    return VerificationResult(
        inspected_path=path,
        all_passed=(passed_count == total and total > 0),
        passed_count=passed_count,
        total_count=total,
        items=items,
    )
