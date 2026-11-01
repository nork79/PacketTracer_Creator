"""Command-line interface for generating and inspecting Cisco Packet Tracer (.pkt) files."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

from pkt_generator.network import SimpleNetwork, decode_bytes
from pkt_generator.presets import PRESETS, generate_preset


def cmd_preset(args: argparse.Namespace) -> int:
    report = generate_preset(args.name, args.output)
    print(f"Generated {args.output} using preset '{args.name}'")
    if report:
        print("Validation:", report.summary())
        if not report.ok:
            for f in report.link_findings:
                print("  Link issue:", f, file=sys.stderr)
            return 1
    return 0


def cmd_from_json(args: argparse.Namespace) -> int:
    net = SimpleNetwork.from_json(args.spec)
    report = net.save(args.output, validate=True)
    print(f"Generated {args.output} from {args.spec}")
    if report:
        print("Validation:", report.summary())
        if not report.ok:
            for f in report.link_findings:
                print("  Link issue:", f, file=sys.stderr)
            return 1
    return 0


def cmd_inspect(args: argparse.Namespace) -> int:
    import audit_links
    import check_layout
    import lab_api

    path = Path(args.file)
    raw = path.read_bytes()
    container = decode_bytes(raw, "pkt")
    root = ET.fromstring(container.xml)

    devs = {}
    print(f"=== {path.name} ({len(raw):,} bytes, XML: {len(container.xml):,} bytes) ===")
    print(f"Version : {root.findtext('VERSION') or 'unknown'}")
    print("\nDevices:")
    for d in root.findall(".//NETWORK/DEVICES/DEVICE"):
        sid = d.findtext("ENGINE/SAVE_REF_ID") or ""
        name = d.findtext("ENGINE/NAME") or "?"
        t_el = d.find("ENGINE/TYPE")
        model = (t_el.get("model") if t_el is not None else None) or (
            t_el.text if t_el is not None else "?"
        )
        x = d.findtext("WORKSPACE/LOGICAL/X") or "?"
        y = d.findtext("WORKSPACE/LOGICAL/Y") or "?"
        ip = d.findtext(".//PORT/IP") or ""
        gw = d.findtext("ENGINE/GATEWAY") or ""
        dhcp = d.findtext(".//PORT/PORT_DHCP_ENABLE") == "true"
        devs[sid] = name
        if dhcp:
            ip_info = " (DHCP)"
        elif ip:
            ip_info = f" (IP: {ip}, GW: {gw})"
        else:
            # Check RUNNINGCONFIG for IOS interface IPs
            cfg_map = audit_links.parse_config(d)
            ios_ips = []
            cur_if = None
            for line_el in d.findall("ENGINE/RUNNINGCONFIG/LINE"):
                txt = (line_el.text or "").strip()
                if txt.startswith("interface "):
                    cur_if = txt.split(None, 1)[1]
                elif txt.startswith("ip address ") and cur_if:
                    parts = txt.split()
                    if len(parts) >= 4:
                        ios_ips.append(f"{cur_if}={parts[2]}")
            ip_info = f" (IFs: {', '.join(ios_ips)})" if ios_ips else ""
        print(f"  - {name:<16} model={model:<16} pos=({x}, {y}){ip_info}")

    print("\nLinks:")
    for lk in root.findall(".//NETWORK/LINKS/LINK"):
        cab = lk.find("CABLE")
        if cab is None:
            continue
        frm = devs.get(cab.findtext("FROM") or "", "?")
        to = devs.get(cab.findtext("TO") or "", "?")
        ports = [p.text or "?" for p in cab.findall("PORT")]
        p_a = ports[0] if len(ports) > 0 else "?"
        p_b = ports[1] if len(ports) > 1 else "?"
        ltype = lk.findtext("TYPE") or "eCopper"
        print(f"  - {frm}:{p_a}  <--({ltype})-->  {to}:{p_b}")

    findings = audit_links.audit_xml(root)
    layout_rep = check_layout.analyse(
        lab_api.parse_devices(container.xml.decode("utf-8", "replace"))
    )
    overlaps = len(layout_rep.get("label_box_overlaps", []))
    off_page = len(layout_rep.get("off_page", []))
    print(
        f"\nAudit   : link_findings={len(findings)}, label_overlaps={overlaps}, off_page={off_page}"
    )
    return 0 if (not findings and overlaps == 0 and off_page == 0) else 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="pkt_generator",
        description="Generate and validate simple Cisco Packet Tracer (.pkt) network files.",
    )
    sub = p.add_subparsers(dest="command", required=True)

    p_preset = sub.add_parser("preset", help="Generate a ready-made network topology preset")
    p_preset.add_argument(
        "name",
        choices=sorted(PRESETS.keys()),
        help="Preset topology name",
    )
    p_preset.add_argument(
        "-o", "--output", required=True, help="Output .pkt file path"
    )
    p_preset.set_defaults(func=cmd_preset)

    p_json = sub.add_parser("from-json", help="Generate a .pkt network from a JSON topology spec")
    p_json.add_argument("spec", help="Path to JSON topology specification file")
    p_json.add_argument(
        "-o", "--output", required=True, help="Output .pkt file path"
    )
    p_json.set_defaults(func=cmd_from_json)

    p_insp = sub.add_parser("inspect", help="Inspect and validate an existing .pkt file")
    p_insp.add_argument("file", help="Path to .pkt file")
    p_insp.set_defaults(func=cmd_inspect)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
