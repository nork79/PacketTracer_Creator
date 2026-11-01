"""Unit tests for all 16 Level 1 CCNA v2.0 NOC Game faults, .pkt verifier, and Tkinter GUI."""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import tkinter as tk
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pkt_generator.game import generate_level1_challenge, verify_pkt_file  # noqa: E402
from pkt_generator.game.generator import ALL_LEVEL1_FAULT_TYPES, TOPOLOGY_ARCHETYPES  # noqa: E402
from pkt_generator.game.gui import NetDoctorApp  # noqa: E402
from pkt_generator.network import decode_bytes, encode  # noqa: E402


class TestLevel1Game(unittest.TestCase):
    def test_all_16_level1_fault_types_detect_and_verify_when_fixed(self) -> None:
        self.assertEqual(len(ALL_LEVEL1_FAULT_TYPES), 16)
        with tempfile.TemporaryDirectory() as tmp:
            for fcode in ALL_LEVEL1_FAULT_TYPES:
                with self.subTest(fault_type=fcode):
                    ticket = generate_level1_challenge(
                        tmp, num_faults=1, seed=42, fault_types=[fcode]
                    )
                    self.assertTrue(ticket.pkt_path.is_file())
                    self.assertEqual(len(ticket.faults), 1)

                    # 1. Verify the freshly generated faulty .pkt fails verification
                    res_broken = verify_pkt_file(ticket.pkt_path, ticket)
                    self.assertFalse(
                        res_broken.all_passed,
                        f"Expected broken .pkt for {fcode} to fail verification",
                    )
                    self.assertEqual(res_broken.passed_count, 0)

                    # 2. Repair the fault in the .pkt XML, re-encode, and verify it passes!
                    raw = ticket.pkt_path.read_bytes()
                    root = ET.fromstring(decode_bytes(raw, "pkt").xml)
                    spec = ticket.faults[0].verify_spec

                    devs_by_name = {
                        (d.findtext("ENGINE/NAME") or "").strip(): d
                        for d in root.findall(".//NETWORK/DEVICES/DEVICE")
                    }
                    d = devs_by_name[spec["device"]]

                    if fcode in ("host_wrong_subnet_ip", "duplicate_ip_conflict"):
                        d.find(".//PORT/IP").text = spec["expected_ip"]  # type: ignore[union-attr]
                        d.find(".//PORT/SUBNET").text = spec["expected_mask"]  # type: ignore[union-attr]
                    elif fcode == "host_wrong_default_gateway":
                        d.find("ENGINE/GATEWAY").text = spec["expected_gateway"]  # type: ignore[union-attr]
                        d.find(".//PORT/PORT_GATEWAY").text = spec["expected_gateway"]  # type: ignore[union-attr]
                    elif fcode == "host_wrong_subnet_mask":
                        d.find(".//PORT/SUBNET").text = spec["expected_mask"]  # type: ignore[union-attr]
                    elif fcode in ("router_port_shutdown", "switch_port_shutdown"):
                        for line_el in d.findall("ENGINE/RUNNINGCONFIG/LINE"):
                            if (line_el.text or "").strip() == "shutdown":
                                line_el.text = " no shutdown"
                    elif fcode == "wrong_router_port_cabled":
                        for p_el in root.findall(".//NETWORK/LINKS/LINK/CABLE/PORT"):
                            if (p_el.text or "").strip() == "GigabitEthernet0/1":
                                p_el.text = "GigabitEthernet0/0"
                    elif fcode == "device_powered_on" or fcode == "device_powered_off":
                        d.find("ENGINE/POWER").text = "true"  # type: ignore[union-attr]
                    elif fcode == "missing_patch_cable":
                        sw_el = devs_by_name[spec["peer_device"]]
                        dev_sid = d.findtext("ENGINE/SAVE_REF_ID") or ""
                        sw_sid = sw_el.findtext("ENGINE/SAVE_REF_ID") or ""
                        links_el = root.find(".//NETWORK/LINKS")
                        assert links_el is not None
                        lk = ET.SubElement(links_el, "LINK")
                        ET.SubElement(lk, "TYPE").text = "eCopper"
                        cab = ET.SubElement(lk, "CABLE")
                        for t, v in (
                            ("LENGTH", "1"),
                            ("FUNCTIONAL", "true"),
                            ("FROM", sw_sid),
                            ("PORT", spec["expected_peer_port"]),
                            ("TO", dev_sid),
                            ("PORT", spec["device_port"]),
                            ("TYPE", "eStraightThrough"),
                        ):
                            ET.SubElement(cab, t).text = v
                    elif fcode == "host_nic_disabled":
                        d.find(".//PORT/POWER").text = "true"  # type: ignore[union-attr]
                    elif fcode == "speed_duplex_mismatch":
                        d.find(".//PORT/AUTONEGOTIATEBANDWIDTH").text = "true"  # type: ignore[union-attr]
                        d.find(".//PORT/AUTONEGOTIATEDUPLEX").text = "true"  # type: ignore[union-attr]
                    elif fcode == "switch_mgmt_fault":
                        rc = d.find("ENGINE/RUNNINGCONFIG")
                        assert rc is not None
                        for line_el in list(rc.findall("LINE")):
                            txt = (line_el.text or "").strip()
                            if txt == "shutdown":
                                line_el.text = " no shutdown"
                            elif txt.startswith("ip address "):
                                line_el.text = f" ip address {spec['expected_ip']} {spec['expected_mask']}"
                            elif txt.startswith("ip default-gateway "):
                                line_el.text = f"ip default-gateway {spec['expected_gateway']}"
                    elif fcode == "host_dhcp_apipa":
                        d.find(".//PORT/PORT_DHCP_ENABLE").text = "false"  # type: ignore[union-attr]
                        d.find(".//PORT/IP").text = spec["expected_ip"]  # type: ignore[union-attr]
                        d.find(".//PORT/SUBNET").text = spec["expected_mask"]  # type: ignore[union-attr]
                        d.find("ENGINE/GATEWAY").text = spec["expected_gateway"]  # type: ignore[union-attr]
                    elif fcode == "router_wrong_ip_or_mask":
                        for line_el in d.findall("ENGINE/RUNNINGCONFIG/LINE"):
                            if (line_el.text or "").strip().startswith("ip address "):
                                line_el.text = f" ip address {spec['expected_ip']} 255.255.255.0"
                    elif fcode == "server_ip_or_gateway_fault":
                        d.find(".//PORT/IP").text = spec["expected_ip"]  # type: ignore[union-attr]
                        d.find(".//PORT/SUBNET").text = spec["expected_mask"]  # type: ignore[union-attr]
                        d.find("ENGINE/GATEWAY").text = spec["expected_gateway"]  # type: ignore[union-attr]
                    elif fcode == "host_wrong_dns":
                        d.find(".//PORT/PORT_DNS").text = spec["expected_dns"]  # type: ignore[union-attr]

                    fixed_pkt = Path(tmp) / f"fixed_{fcode}.pkt"
                    encode(
                        str(fixed_pkt),
                        ET.tostring(root, encoding="unicode").encode("utf-8"),
                        "pkt",
                    )

                    res_fixed = verify_pkt_file(fixed_pkt, ticket)
                    self.assertTrue(
                        res_fixed.all_passed,
                        f"Expected fixed .pkt for {fcode} to pass: {res_fixed.items}",
                    )

    def test_level1_topology_and_subnet_variety_and_multi_faults(self) -> None:
        seen_prefixes: set[str] = set()
        seen_client_counts: set[int] = set()
        seen_layouts: set[str] = set()
        seen_laptop = False
        seen_two_switches = False

        with tempfile.TemporaryDirectory() as tmp:
            for seed in range(1, 30):
                ticket = generate_level1_challenge(tmp, num_faults=2, seed=seed)
                self.assertEqual(len(ticket.faults), 2)
                self.assertNotEqual(ticket.faults[0].fault_id, ticket.faults[1].fault_id)
                prefix = "/" + ticket.subnet_cidr.split("/")[1]
                seen_prefixes.add(prefix)
                seen_layouts.add(ticket.service_notes[0])
                client_rows = [r for r in ticket.device_rows if r.model in ("PC-PT", "Laptop-PT")]
                seen_client_counts.add(len(client_rows))
                if any(r.model == "Laptop-PT" for r in client_rows):
                    seen_laptop = True
                if sum(1 for r in ticket.device_rows if r.model == "2960-24TT") == 2:
                    seen_two_switches = True

                res = verify_pkt_file(ticket.pkt_path, ticket)
                self.assertFalse(res.all_passed)
                self.assertEqual(res.total_count, 2)

        self.assertEqual(seen_prefixes, {"/24", "/25", "/26", "/27"})
        self.assertEqual(seen_client_counts, {2, 3, 4})
        self.assertEqual(len(seen_layouts), len(TOPOLOGY_ARCHETYPES))
        self.assertTrue(seen_laptop)
        self.assertTrue(seen_two_switches)

    def test_tkinter_gui_initialization_and_actions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = tk.Tk()
            root.withdraw()
            try:
                app = NetDoctorApp(root, challenges_dir=tmp)
                self.assertIsNotNone(app.current_ticket)
                assert app.current_ticket is not None
                self.assertTrue(app.current_ticket.pkt_path.is_file())

                app.quick_check_current_pkt()
                app.show_next_hint()
                app.show_next_hint()
                app.reveal_what_was_wrong()
            finally:
                root.destroy()


if __name__ == "__main__":
    unittest.main()
