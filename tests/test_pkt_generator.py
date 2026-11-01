"""Automated tests for pkt_generator API, presets, CLI, and .pkt verification."""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pkt_generator import (  # noqa: E402
    PRESETS,
    SimpleNetwork,
    decode_bytes,
    generate_preset,
    parse_ipv4,
)
from pkt_generator.cli import main as cli_main  # noqa: E402


class TestPktGenerator(unittest.TestCase):
    def test_parse_ipv4(self) -> None:
        self.assertEqual(parse_ipv4("192.168.1.10/24"), ("192.168.1.10", "255.255.255.0"))
        self.assertEqual(parse_ipv4("10.0.0.1/30"), ("10.0.0.1", "255.255.255.252"))
        self.assertEqual(parse_ipv4("172.16.5.4"), ("172.16.5.4", "255.255.255.0"))
        self.assertEqual(
            parse_ipv4(("10.1.1.1", "255.255.0.0")), ("10.1.1.1", "255.255.0.0")
        )

    def test_simple_lan_builder_and_roundtrip(self) -> None:
        net = SimpleNetwork()
        net.add_router("R1")
        net.add_switch("SW1", management_ip="192.168.1.2/24", default_gateway="192.168.1.1")
        net.add_pc("PC1", ip="192.168.1.10/24")
        net.add_pc("PC2", dhcp=True)

        l1 = net.connect("R1", "SW1", ip_a="192.168.1.1/24")
        l2 = net.connect("SW1", "PC1")
        l3 = net.connect("SW1", "PC2")

        # Verify automatic port allocation picked uplink Gi0/1 on switch -> router, and Fa0/1..2 -> PCs
        self.assertEqual(l1.port_a, "GigabitEthernet0/0")
        self.assertEqual(l1.port_b, "GigabitEthernet0/1")
        self.assertEqual(l2.port_a, "FastEthernet0/1")
        self.assertEqual(l2.port_b, "FastEthernet0")
        self.assertEqual(l3.port_a, "FastEthernet0/2")
        self.assertEqual(l3.port_b, "FastEthernet0")

        with tempfile.TemporaryDirectory() as tmp:
            out_pkt = Path(tmp) / "test_lan.pkt"
            rep = net.save(out_pkt, validate=True)
            self.assertIsNotNone(rep)
            assert rep is not None
            self.assertTrue(rep.ok, rep.summary())
            self.assertEqual(rep.device_count, 4)
            self.assertEqual(rep.link_count, 3)
            self.assertTrue(rep.roundtrip_exact)

            # Verify decoded XML contents
            xml_bytes = decode_bytes(out_pkt.read_bytes(), "pkt").xml
            root = ET.fromstring(xml_bytes)
            names = [
                d.findtext("ENGINE/NAME")
                for d in root.findall(".//NETWORK/DEVICES/DEVICE")
            ]
            self.assertEqual(names, ["R1", "SW1", "PC1", "PC2"])

    def test_multilayer_switch_and_ospf(self) -> None:
        net = SimpleNetwork()
        net.add_router("R-CORE", model="ISR4331")
        net.add_multilayer_switch("MLS1", model="3560-24PS")
        net.add_vlan("MLS1", 10, "Users", svi_ip="10.10.10.1/24")
        net.add_pc("PC-USER", ip="10.10.10.10/24", gateway="10.10.10.1")

        net.connect("R-CORE", "MLS1", ip_a="10.0.0.1/30", ip_b="10.0.0.2/30")
        net.connect("MLS1", "PC-USER", vlan=10)
        net.enable_ospf()

        rep = net.validate()
        self.assertTrue(rep.ok, rep.summary())

    def test_all_presets_validate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            for name in PRESETS:
                out_file = Path(tmp) / f"{name}.pkt"
                rep = generate_preset(name, out_file)
                self.assertIsNotNone(rep)
                assert rep is not None
                self.assertTrue(rep.ok, f"Preset {name} failed: {rep.summary()}")

    def test_json_spec_and_cli(self) -> None:
        spec_path = ROOT / "examples" / "topology.json"
        with tempfile.TemporaryDirectory() as tmp:
            out_pkt = Path(tmp) / "from_json.pkt"
            rc = cli_main(["from-json", str(spec_path), "-o", str(out_pkt)])
            self.assertEqual(rc, 0)
            self.assertTrue(out_pkt.is_file())

            rc_insp = cli_main(["inspect", str(out_pkt)])
            self.assertEqual(rc_insp, 0)


if __name__ == "__main__":
    unittest.main()

