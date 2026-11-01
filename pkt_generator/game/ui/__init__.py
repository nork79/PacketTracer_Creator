"""Modular Tkinter UI components for NetDoctor NOC."""

from __future__ import annotations

from pkt_generator.game.ui.constants import (
    ADDRESSING_HELP_OPTIONS,
    BUILD_LEVEL_OPTIONS,
    CABLING_MODE_OPTIONS,
    FAULT_FILTER_OPTIONS,
    LEVEL2_FAULT_FILTER_OPTIONS,
    MISSION_MODES,
    TROUBLESHOOT_LEVEL_OPTIONS,
    configure_ttk_styles,
)
from pkt_generator.game.ui.diagnostic_popup import DiagnosticConsolePopup
from pkt_generator.game.ui.stats_pane import PlayerStatsPane, fmt_mmss
from pkt_generator.game.ui.topology_canvas import TopologyDiagramView

__all__ = [
    "ADDRESSING_HELP_OPTIONS",
    "BUILD_LEVEL_OPTIONS",
    "CABLING_MODE_OPTIONS",
    "DiagnosticConsolePopup",
    "FAULT_FILTER_OPTIONS",
    "LEVEL2_FAULT_FILTER_OPTIONS",
    "MISSION_MODES",
    "PlayerStatsPane",
    "TROUBLESHOOT_LEVEL_OPTIONS",
    "TopologyDiagramView",
    "configure_ttk_styles",
    "fmt_mmss",
]

