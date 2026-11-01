"""pkt_generator — Simple Network Generator API for Cisco Packet Tracer (.pkt) files.

Built on top of `aacanadaa/packet-tracer-pkt-format` (`pkt_core`), this package
provides a high-level Python API (`SimpleNetwork`), automatic port selection,
automatic IOS configuration synthesis, collision-free tier layout, declarative
JSON loading, and pre-built network presets.
"""

from __future__ import annotations

from pkt_generator.catalog import (
    MODEL_ALIASES,
    MODEL_CATALOG,
    ModelCapability,
    get_capability,
    resolve_model,
)
from pkt_generator.network import (
    DeviceSpec,
    DhcpPoolSpec,
     Lab,
    LinkSpec,
    OspfSpec,
    PortConfig,
    SimpleNetwork,
    SubinterfaceSpec,
    ValidationReport,
    VlanSpec,
    decode_bytes,
    parse_ipv4,
    parse_network_wildcard,
)
from pkt_generator.presets import (
    PRESETS,
    build_dual_site_wan,
    build_router_on_a_stick,
    build_single_lan,
    build_small_office_network,
    generate_preset,
)

__all__ = [
    "SimpleNetwork",
    "DeviceSpec",
    "LinkSpec",
    "PortConfig",
    "VlanSpec",
    "SubinterfaceSpec",
    "DhcpPoolSpec",
    "OspfSpec",
    "ValidationReport",
    "ModelCapability",
    "MODEL_ALIASES",
    "MODEL_CATALOG",
    "resolve_model",
    "get_capability",
    "parse_ipv4",
    "parse_network_wildcard",
    "PRESETS",
    "build_single_lan",
    "build_dual_site_wan",
    "build_router_on_a_stick",
    "build_small_office_network",
    "generate_preset",
    "Lab",
    "decode_bytes",
]

