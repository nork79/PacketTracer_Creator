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

from pkt_generator.game import (  # noqa: E402
    ALL_LEVEL1_FAULT_TYPES,
    ALL_LEVEL2_FAULT_TYPES,
    GameSettings,
    generate_build_mission,
    generate_level1_challenge,
    generate_level2_challenge,
    verify_pkt_file,
)
from pkt_generator.game.career import (  # noqa: E402
    CareerProfile,
    award_ticket_xp,
    roll_career_task,
    title_for_level,
)
from pkt_generator.game.generator import TOPOLOGY_ARCHETYPES  # noqa: E402
from pkt_generator.game.gui import NetDoctorApp  # noqa: E402
from pkt_generator.game.ui import BUILD_LEVEL_OPTIONS, MISSION_MODES, TROUBLESHOOT_LEVEL_OPTIONS  # noqa: E402
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
        seen_switch_counts: set[int] = set()
        seen_laptop = False

        with tempfile.TemporaryDirectory() as tmp:
            for idx, arch in enumerate(TOPOLOGY_ARCHETYPES):
                ticket = generate_level1_challenge(
                    tmp, num_faults=2, seed=idx + 1, archetype=arch
                )
                self.assertEqual(len(ticket.faults), 2)
                self.assertNotEqual(ticket.faults[0].fault_id, ticket.faults[1].fault_id)
                prefix = "/" + ticket.subnet_cidr.split("/")[1]
                seen_prefixes.add(prefix)
                seen_layouts.add(ticket.service_notes[0])
                client_rows = [r for r in ticket.device_rows if r.model in ("PC-PT", "Laptop-PT")]
                seen_client_counts.add(len(client_rows))
                if any(r.model == "Laptop-PT" for r in client_rows):
                    seen_laptop = True
                seen_switch_counts.add(
                    sum(1 for r in ticket.device_rows if r.model == "2960-24TT")
                )

                res = verify_pkt_file(ticket.pkt_path, ticket)
                self.assertFalse(res.all_passed)
                self.assertEqual(res.total_count, 2)

            # A few extra seeds to guarantee all 4 prefix lengths and laptop appear
            for seed in range(13, 25):
                ticket = generate_level1_challenge(tmp, num_faults=2, seed=seed)
                seen_prefixes.add("/" + ticket.subnet_cidr.split("/")[1])
                client_rows = [r for r in ticket.device_rows if r.model in ("PC-PT", "Laptop-PT")]
                seen_client_counts.add(len(client_rows))
                if any(r.model == "Laptop-PT" for r in client_rows):
                    seen_laptop = True

        self.assertEqual(len(TOPOLOGY_ARCHETYPES), 12)
        self.assertEqual(len(seen_layouts), 12)
        self.assertEqual(seen_switch_counts, {1, 2, 3})
        self.assertEqual(seen_prefixes, {"/24", "/25", "/26", "/27"})
        self.assertEqual(seen_client_counts, {2, 3, 4})
        self.assertTrue(seen_laptop)

    def test_tkinter_gui_initialization_and_actions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings_file = Path(tmp) / "test_settings.json"
            root = tk.Tk()
            root.withdraw()
            try:
                app = NetDoctorApp(root, challenges_dir=tmp, settings_path=settings_file)
                self.assertIsNotNone(app.current_ticket)
                assert app.current_ticket is not None
                self.assertTrue(app.current_ticket.pkt_path.is_file())

                app.quick_check_current_pkt()
                app.open_diagnostic_popup()
                app.show_next_hint()
                app.show_next_hint()
                app.reveal_what_was_wrong()
                app._zoom_topology(1.15)
                app._zoom_topology(1 / 1.15)
                app._reset_topology_zoom()

                # Switch to Level 2 Troubleshooting in GUI and generate challenge
                app.level_var.set(TROUBLESHOOT_LEVEL_OPTIONS[1])
                app._on_troubleshoot_level_changed()
                app.generate_new_challenge()
                assert app.current_ticket is not None
                self.assertEqual(app.current_ticket.level, 2)
                self.assertTrue(app.current_ticket.pkt_path.is_file())
                app.quick_check_current_pkt()

                # Switch to Mode 2 (Build Network from Scratch) Level 1 & Level 2
                app.mission_mode_var.set(MISSION_MODES[1])
                app.build_level_var.set(BUILD_LEVEL_OPTIONS[0])
                app.generate_new_challenge()
                assert app.current_ticket is not None
                self.assertEqual(app.current_ticket.level, 1)
                self.assertIn("[BUILD LVL 1]", app.current_ticket.scenario_title)
                app.quick_check_current_pkt()

                app.build_level_var.set(BUILD_LEVEL_OPTIONS[1])
                app.generate_new_challenge()
                assert app.current_ticket is not None
                self.assertEqual(app.current_ticket.level, 2)
                self.assertIn("[BUILD LVL 2]", app.current_ticket.scenario_title)
                app.quick_check_current_pkt()
            finally:
                root.destroy()

    def test_all_12_level2_fault_types_detect_and_verify_when_fixed(self) -> None:
        self.assertEqual(len(ALL_LEVEL2_FAULT_TYPES), 12)
        with tempfile.TemporaryDirectory() as tmp:
            for fcode in ALL_LEVEL2_FAULT_TYPES:
                with self.subTest(level2_fault=fcode):
                    ticket = generate_level2_challenge(
                        tmp, num_faults=1, seed=42, fault_types=[fcode]
                    )
                    self.assertTrue(ticket.pkt_path.is_file())
                    self.assertEqual(ticket.level, 2)
                    self.assertEqual(len(ticket.faults), 1)

                    # 1. Verify freshly generated faulty Level 2 .pkt fails verification
                    res_broken = verify_pkt_file(ticket.pkt_path, ticket)
                    self.assertFalse(
                        res_broken.all_passed,
                        f"Expected broken Level 2 .pkt for {fcode} to fail verification",
                    )
                    self.assertEqual(res_broken.passed_count, 0)

                    # 2. Repair the Level 2 fault in .pkt XML, re-encode, and verify it passes!
                    raw = ticket.pkt_path.read_bytes()
                    root = ET.fromstring(decode_bytes(raw, "pkt").xml)
                    spec = ticket.faults[0].verify_spec
                    devs_by_name = {
                        (d.findtext("ENGINE/NAME") or "").strip(): d
                        for d in root.findall(".//NETWORK/DEVICES/DEVICE")
                    }
                    d = devs_by_name[spec["device"]]
                    rc = d.find("ENGINE/RUNNINGCONFIG")
                    assert rc is not None

                    if fcode == "access_port_wrong_vlan":
                        cur_if = ""
                        for line_el in rc.findall("LINE"):
                            txt = (line_el.text or "").strip()
                            if txt.startswith("interface "):
                                cur_if = txt.split(None, 1)[1]
                            elif cur_if == spec["interface"] and txt.startswith("switchport access vlan "):
                                line_el.text = f" switchport access vlan {spec['expected_vlan']}"
                    elif fcode == "vlan_missing_from_db":
                        vlans_el = d.find("ENGINE/VLANS")
                        assert vlans_el is not None
                        ET.SubElement(vlans_el, "VLAN", number=str(spec["expected_vlan"]), name="RESTORED")
                    elif fcode == "voice_vlan_mismatch":
                        cur_if = ""
                        for line_el in rc.findall("LINE"):
                            txt = (line_el.text or "").strip()
                            if txt.startswith("interface "):
                                cur_if = txt.split(None, 1)[1]
                            elif cur_if == spec["interface"] and txt.startswith("switchport access vlan "):
                                line_el.text = f" switchport access vlan {spec['expected_data_vlan']}"
                        # Append voice vlan command inside the interface stanza
                        lines = list(rc.findall("LINE"))
                        for i, line_el in enumerate(lines):
                            if (line_el.text or "").strip() == f"interface {spec['interface']}":
                                new_el = ET.Element("LINE")
                                new_el.text = f" switchport voice vlan {spec['expected_voice_vlan']}"
                                rc.insert(i + 2, new_el)
                                break
                    elif fcode in ("trunk_left_as_access", "roas_switch_uplink_not_trunk"):
                        cur_if = ""
                        for line_el in rc.findall("LINE"):
                            txt = (line_el.text or "").strip()
                            if txt.startswith("interface "):
                                cur_if = txt.split(None, 1)[1]
                            elif cur_if == spec["interface"] and txt.startswith("switchport mode "):
                                line_el.text = " switchport mode trunk"
                    elif fcode == "trunk_allowed_vlan_missing":
                        cur_if = ""
                        vlist = ",".join(str(v) for v in spec["required_vlans"])
                        for line_el in rc.findall("LINE"):
                            txt = (line_el.text or "").strip()
                            if txt.startswith("interface "):
                                cur_if = txt.split(None, 1)[1]
                            elif cur_if == spec["interface"] and txt.startswith("switchport trunk allowed vlan "):
                                line_el.text = f" switchport trunk allowed vlan {vlist}"
                    elif fcode == "trunk_native_vlan_mismatch":
                        cur_if = ""
                        for line_el in rc.findall("LINE"):
                            txt = (line_el.text or "").strip()
                            if txt.startswith("interface "):
                                cur_if = txt.split(None, 1)[1]
                            elif cur_if == spec["interface"] and txt.startswith("switchport trunk native vlan "):
                                line_el.text = " no switchport trunk native vlan"
                    elif fcode == "dtp_mode_mismatch":
                        for line_el in rc.findall("LINE"):
                            if (line_el.text or "").strip() == "switchport mode dynamic auto":
                                line_el.text = " switchport mode trunk"
                    elif fcode == "roas_wrong_dot1q_tag":
                        sub_if = f"{spec['parent_port']}.{spec['vlan_id']}"
                        cur_if = ""
                        for line_el in rc.findall("LINE"):
                            txt = (line_el.text or "").strip()
                            if txt.startswith("interface "):
                                cur_if = txt.split(None, 1)[1]
                            elif cur_if == sub_if and txt.startswith("encapsulation dot1Q "):
                                line_el.text = f" encapsulation dot1Q {spec['vlan_id']}"
                    elif fcode == "roas_subif_wrong_ip":
                        sub_if = f"{spec['parent_port']}.{spec['vlan_id']}"
                        cur_if = ""
                        for line_el in rc.findall("LINE"):
                            txt = (line_el.text or "").strip()
                            if txt.startswith("interface "):
                                cur_if = txt.split(None, 1)[1]
                            elif cur_if == sub_if and txt.startswith("ip address "):
                                line_el.text = f" ip address {spec['expected_ip']} {spec['expected_mask']}"
                    elif fcode == "roas_parent_port_shutdown":
                        cur_if = ""
                        for line_el in rc.findall("LINE"):
                            txt = (line_el.text or "").strip()
                            if txt.startswith("interface "):
                                cur_if = txt.split(None, 1)[1]
                            elif cur_if == spec["parent_port"] and txt == "shutdown":
                                line_el.text = " no shutdown"
                    elif fcode == "etherchannel_mode_mismatch":
                        for line_el in rc.findall("LINE"):
                            if (line_el.text or "").strip().startswith("channel-group 1 mode "):
                                line_el.text = " channel-group 1 mode active"

                    fixed_pkt = Path(tmp) / f"fixed_l2_{fcode}.pkt"
                    encode(
                        str(fixed_pkt),
                        ET.tostring(root, encoding="unicode").encode("utf-8"),
                        "pkt",
                    )

                    res_fixed = verify_pkt_file(fixed_pkt, ticket)
                    self.assertTrue(
                        res_fixed.all_passed,
                        f"Expected fixed Level 2 .pkt for {fcode} to pass: {res_fixed.items}",
                    )

    def test_mode2_build_missions_level1_and_level2(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            # Level 1 Build Mission (Uncabled + Subnetting Challenge)
            b1 = generate_build_mission(
                tmp,
                level=1,
                addressing_help="🧮 Subnetting Challenge (CIDR Block & Rules Only)",
                cabling_mode="🔌 Uncabled Hardware (Wire from Scratch)",
                seed=11,
            )
            self.assertEqual(b1.level, 1)
            self.assertEqual(len(b1.faults), 4)
            res_b1 = verify_pkt_file(b1.pkt_path, b1)
            self.assertFalse(res_b1.all_passed)
            self.assertEqual(res_b1.passed_count, 0)

            # Level 2 Build Mission (Pre-Cabled + Guided)
            b2 = generate_build_mission(
                tmp,
                level=2,
                addressing_help="📘 Guided (Full IPv4 Table Provided)",
                cabling_mode="🔗 Pre-Cabled Hardware (Focus on CLI / IPs)",
                seed=22,
            )
            self.assertEqual(b2.level, 2)
            self.assertEqual(len(b2.faults), 4)
            res_b2 = verify_pkt_file(b2.pkt_path, b2)
            self.assertFalse(res_b2.all_passed)
            self.assertEqual(res_b2.passed_count, 0)

    def test_career_mode_progression_and_stats_pane(self) -> None:
        profile = CareerProfile()
        self.assertEqual(profile.level, 1)
        self.assertEqual(profile.title, "NOC Trainee")

        # Level 1 Gold SLA first-try solve should award >100 XP and level up to Level 2
        reward1 = award_ticket_xp(
            profile,
            task_kind="fault",
            num_faults=1,
            num_switches=1,
            prefix_len=24,
            elapsed_seconds=45,
            target_sla_seconds=180,
            hints_used=0,
            failed_attempts=0,
            solution_revealed=False,
        )
        self.assertTrue(reward1.leveled_up)
        self.assertEqual(profile.level, 2)
        self.assertEqual(profile.tasks_completed, 1)
        self.assertEqual(profile.fault_tasks_completed, 1)
        self.assertEqual(profile.first_try_solves, 1)
        self.assertEqual(profile.best_sla_seconds, 45)
        self.assertEqual(reward1.speed_multiplier, 1.5)

        # Verify setup task award and milestone title at Level 5 and Level 50
        self.assertEqual(title_for_level(5), "Junior Helpdesk Technician")
        self.assertEqual(title_for_level(20), "Associate Network Engineer (CCNA)")
        self.assertEqual(title_for_level(50), "Distinguished Fellow of the NOC")

        # Verify task director rolls both fault and setup tasks across levels 1..50
        spec_low = roll_career_task(1)
        spec_high = roll_career_task(45)
        self.assertEqual(spec_low.num_faults, 1)
        self.assertGreaterEqual(spec_high.num_faults, 3)

        with tempfile.TemporaryDirectory() as tmp:
            setup_ticket = generate_level1_challenge(
                tmp,
                num_faults=3,
                seed=99,
                task_kind="setup",
            )
            self.assertIn("[NETWORK SETUP]", setup_ticket.scenario_title)
            self.assertEqual(len(setup_ticket.faults), 3)
            res = verify_pkt_file(setup_ticket.pkt_path, setup_ticket)
            self.assertFalse(res.all_passed)
            self.assertEqual(res.total_count, 3)

    def test_custom_game_settings_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings_file = Path(tmp) / "custom_settings.json"
            custom = GameSettings(
                player_name="Alice",
                company_name="CyberDyne Corp",
                departments=[("RND", "Robotics Research")],
                settings_path=settings_file,
            )
            custom.save(settings_file)

            loaded = GameSettings.load(settings_file)
            self.assertEqual(loaded.player_name, "Alice")
            self.assertEqual(loaded.company_name, "CyberDyne Corp")
            self.assertEqual(loaded.departments, [("RND", "Robotics Research")])

            ticket = generate_level1_challenge(tmp, seed=7, settings=loaded)
            self.assertIn("CyberDyne Corp", ticket.scenario_title)
            self.assertIn("Robotics Research", ticket.scenario_title)
            self.assertTrue(any("Alice" in n for n in ticket.service_notes))
            self.assertEqual(ticket.device_rows[0].device, "RND-R1")


if __name__ == "__main__":
    unittest.main()
