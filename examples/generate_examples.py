"""Demonstrates generating Cisco Packet Tracer (.pkt) files using pkt_generator."""

from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pkt_generator import SimpleNetwork, generate_preset  # noqa: E402


def build_custom_network(out_file: Path) -> None:
    """Build a custom network using the Python API."""
    net = SimpleNetwork()

    # Add devices (no coordinates or port names required!)
    net.add_router("R1")
    net.add_switch("SW1", management_ip="192.168.10.2/24", default_gateway="192.168.10.1")
    net.add_pc("PC1", ip="192.168.10.10/24", gateway="192.168.10.1")
    net.add_pc("PC2", ip="192.168.10.11/24", gateway="192.168.10.1")
    net.add_server("WEB-SRV", ip="192.168.10.100/24", gateway="192.168.10.1")

    # Connect devices (ports and IOS interface configs are generated automatically)
    net.connect("R1", "SW1", ip_a="192.168.10.1/24")
    net.connect("SW1", "PC1")
    net.connect("SW1", "PC2")
    net.connect("SW1", "WEB-SRV")

    report = net.save(out_file)
    print(f"Custom API Lab   -> {out_file.name:<26} {report.summary() if report else ''}")


def main() -> None:
    out_dir = ROOT / "output"
    out_dir.mkdir(exist_ok=True)

    # 1. Custom Python API example
    build_custom_network(out_dir / "custom_simple_lan.pkt")

    # 2. All built-in presets
    for preset in ("single-lan", "dual-site-wan", "router-on-a-stick", "small-office"):
        pkt_path = out_dir / f"{preset.replace('-', '_')}.pkt"
        rep = generate_preset(preset, pkt_path)
        print(f"Preset ({preset:<17}) -> {pkt_path.name:<26} {rep.summary() if rep else ''}")

    # 3. Declarative JSON topology example
    json_spec = Path(__file__).resolve().parent / "topology.json"
    json_net = SimpleNetwork.from_json(json_spec)
    json_pkt = out_dir / "hq_branch_from_json.pkt"
    rep = json_net.save(json_pkt)
    print(f"JSON Spec Lab    -> {json_pkt.name:<26} {rep.summary() if rep else ''}")


if __name__ == "__main__":
    main()

