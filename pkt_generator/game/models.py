"""Data models for the NetDoctor NOC Packet Tracer troubleshooting game."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class BlueprintDeviceRow:
    """One row of the intended (golden) IPv4 addressing blueprint."""

    device: str
    model: str
    role: str
    interface: str
    expected_ip: str
    expected_mask: str
    expected_gateway: str = "-"
    expected_dns: str = "-"
    notes: str = ""


@dataclass
class BlueprintLinkRow:
    """One row of the intended (golden) cabling blueprint."""

    dev_a: str
    port_a: str
    dev_b: str
    port_b: str
    cable_type: str = "Copper Straight-Through"
    mode_or_vlan: str = "Access (VLAN 1)"


@dataclass
class FaultRecord:
    """Describes a single fault injected into the .pkt file and how to verify/fix it."""

    fault_id: str
    title: str
    category: str  # e.g. "Layer 3 (IPv4 Addressing)", "Layer 1 (Physical / Interface)"
    device: str
    interface: str
    symptom: str
    expected_state: str
    faulty_state: str
    hints: list[str]
    explanation: str
    fix_steps: list[str]
    # Machine-readable verification criteria used by verifier.py when inspecting an uploaded .pkt
    verify_spec: dict[str, Any] = field(default_factory=dict)


@dataclass
class CheckItemResult:
    """Result of inspecting one fault condition in an uploaded .pkt file."""

    fault_id: str
    title: str
    device: str
    passed: bool
    observed_state: str
    expected_state: str
    message: str


@dataclass
class VerificationResult:
    """Overall result of inspecting a student's uploaded .pkt file."""

    inspected_path: Path
    all_passed: bool
    passed_count: int
    total_count: int
    items: list[CheckItemResult] = field(default_factory=list)
    general_errors: list[str] = field(default_factory=list)


@dataclass
class ChallengeTicket:
    """Complete state for a generated troubleshooting challenge."""

    ticket_id: str
    level: int
    level_name: str
    scenario_title: str
    symptom_summary: str
    pkt_path: Path
    subnet_cidr: str
    device_rows: list[BlueprintDeviceRow]
    link_rows: list[BlueprintLinkRow]
    service_notes: list[str]
    faults: list[FaultRecord]
    # Visual layout coordinates for the built-in Tkinter topology preview canvas
    canvas_nodes: list[dict[str, Any]] = field(default_factory=list)
    canvas_edges: list[tuple[str, str, str, str]] = field(default_factory=list)

