"""Device catalog, friendly aliases, and verified port definitions for Packet Tracer models."""

from __future__ import annotations

from dataclasses import dataclass, field


# Friendly role/type aliases -> default Packet Tracer model name
MODEL_ALIASES: dict[str, str] = {
    # Routers
    "router": "2911",
    "rtr": "2911",
    "2911": "2911",
    "1941": "1941",
    "2901": "2901",
    "2811": "2811",
    "1841": "1841",
    "isr4321": "ISR4321",
    "isr4331": "ISR4331",
    "router-pt": "Router-PT",
    "generic-router": "Router-PT",
    "home-router": "HomeRouter-PT-AC",
    # Switches
    "switch": "2960-24TT",
    "sw": "2960-24TT",
    "2960": "2960-24TT",
    "2960-24tt": "2960-24TT",
    "2950": "2950-24",
    "2950-24": "2950-24",
    "2950t-24": "2950T-24",
    "switch-pt": "Switch-PT",
    "generic-switch": "Switch-PT",
    # Multilayer / L3 Switches
    "multilayer-switch": "3560-24PS",
    "multilayer_switch": "3560-24PS",
    "l3-switch": "3560-24PS",
    "l3_switch": "3560-24PS",
    "mls": "3560-24PS",
    "3560": "3560-24PS",
    "3560-24ps": "3560-24PS",
    "3650": "3650-24PS",
    "3650-24ps": "3650-24PS",
    # End devices
    "pc": "PC-PT",
    "pc-pt": "PC-PT",
    "host": "PC-PT",
    "workstation": "PC-PT",
    "server": "Server-PT",
    "srv": "Server-PT",
    "server-pt": "Server-PT",
    "laptop": "Laptop-PT",
    "laptop-pt": "Laptop-PT",
    "tablet": "TabletPC-PT",
    "tabletpc-pt": "TabletPC-PT",
    "phone": "7960",
    "ip-phone": "7960",
    "7960": "7960",
    # Wireless / Security / WAN
    "ap": "AccessPoint-PT",
    "access-point": "AccessPoint-PT",
    "access_point": "AccessPoint-PT",
    "accesspoint-pt": "AccessPoint-PT",
    "firewall": "5505",
    "asa": "5505",
    "5505": "5505",
    "cloud": "Cloud-PT",
    "cloud-pt": "Cloud-PT",
}


@dataclass(frozen=True)
class ModelCapability:
    """Verified capabilities and port names for a Packet Tracer device model."""

    model: str
    category: str  # "router", "switch", "l3_switch", "end_device", "ap", "firewall", "cloud"
    uplink_ports: list[str] = field(default_factory=list)
    access_ports: list[str] = field(default_factory=list)
    serial_ports: list[str] = field(default_factory=list)
    serial_module: str | None = None
    serial_ports_per_module: int = 2
    supports_ios: bool = False


def _fa_range(n: int = 24) -> list[str]:
    return [f"FastEthernet0/{i}" for i in range(1, n + 1)]


def _gi_stack_range(n: int = 24) -> list[str]:
    return [f"GigabitEthernet1/0/{i}" for i in range(1, n + 1)]


# Verified port catalog matching Packet Tracer 9.0.1 & pkt_core templates
MODEL_CATALOG: dict[str, ModelCapability] = {
    # --- Routers ---
    "2911": ModelCapability(
        model="2911",
        category="router",
        uplink_ports=["GigabitEthernet0/0", "GigabitEthernet0/1", "GigabitEthernet0/2"],
        access_ports=["GigabitEthernet0/0", "GigabitEthernet0/1", "GigabitEthernet0/2"],
        serial_ports=["Serial0/0/0", "Serial0/0/1", "Serial0/1/0", "Serial0/1/1"],
        serial_module="HWIC-2T",
        serial_ports_per_module=2,
        supports_ios=True,
    ),
    "1941": ModelCapability(
        model="1941",
        category="router",
        uplink_ports=["GigabitEthernet0/0", "GigabitEthernet0/1"],
        access_ports=["GigabitEthernet0/0", "GigabitEthernet0/1"],
        serial_ports=["Serial0/0/0", "Serial0/0/1", "Serial0/1/0", "Serial0/1/1"],
        serial_module="HWIC-2T",
        serial_ports_per_module=2,
        supports_ios=True,
    ),
    "2901": ModelCapability(
        model="2901",
        category="router",
        uplink_ports=["GigabitEthernet0/0", "GigabitEthernet0/1"],
        access_ports=["GigabitEthernet0/0", "GigabitEthernet0/1"],
        serial_ports=["Serial0/0/0", "Serial0/0/1", "Serial0/1/0", "Serial0/1/1"],
        serial_module="HWIC-2T",
        serial_ports_per_module=2,
        supports_ios=True,
    ),
    "2811": ModelCapability(
        model="2811",
        category="router",
        uplink_ports=["FastEthernet0/0", "FastEthernet0/1"],
        access_ports=["FastEthernet0/0", "FastEthernet0/1"],
        serial_ports=["Serial0/0/0", "Serial0/0/1", "Serial0/1/0", "Serial0/1/1"],
        serial_module="HWIC-2T",
        serial_ports_per_module=2,
        supports_ios=True,
    ),
    "1841": ModelCapability(
        model="1841",
        category="router",
        uplink_ports=["FastEthernet0/0", "FastEthernet0/1"],
        access_ports=["FastEthernet0/0", "FastEthernet0/1"],
        serial_ports=["Serial0/0/0", "Serial0/0/1", "Serial0/1/0", "Serial0/1/1"],
        serial_module="HWIC-2T",
        serial_ports_per_module=2,
        supports_ios=True,
    ),
    "ISR4321": ModelCapability(
        model="ISR4321",
        category="router",
        uplink_ports=["GigabitEthernet0/0/0", "GigabitEthernet0/0/1"],
        access_ports=["GigabitEthernet0/0/0", "GigabitEthernet0/0/1"],
        serial_ports=["Serial0/1/0", "Serial0/1/1"],
        serial_module="NIM-2T",
        serial_ports_per_module=2,
        supports_ios=True,
    ),
    "ISR4331": ModelCapability(
        model="ISR4331",
        category="router",
        uplink_ports=["GigabitEthernet0/0/0", "GigabitEthernet0/0/1", "GigabitEthernet0/0/2"],
        access_ports=["GigabitEthernet0/0/0", "GigabitEthernet0/0/1", "GigabitEthernet0/0/2"],
        serial_ports=["Serial0/1/0", "Serial0/1/1"],
        serial_module="NIM-2T",
        serial_ports_per_module=2,
        supports_ios=True,
    ),
    "Router-PT": ModelCapability(
        model="Router-PT",
        category="router",
        uplink_ports=["FastEthernet0/0", "FastEthernet1/0"],
        access_ports=["FastEthernet0/0", "FastEthernet1/0"],
        serial_ports=["Serial2/0", "Serial3/0"],
        serial_module=None,
        supports_ios=True,
    ),
    # --- Switches ---
    "2960-24TT": ModelCapability(
        model="2960-24TT",
        category="switch",
        uplink_ports=["GigabitEthernet0/1", "GigabitEthernet0/2"],
        access_ports=_fa_range(24),
        supports_ios=True,
    ),
    "2950-24": ModelCapability(
        model="2950-24",
        category="switch",
        uplink_ports=["FastEthernet0/24", "FastEthernet0/23"],
        access_ports=_fa_range(22),
        supports_ios=True,
    ),
    "2950T-24": ModelCapability(
        model="2950T-24",
        category="switch",
        uplink_ports=["GigabitEthernet0/1", "GigabitEthernet0/2"],
        access_ports=_fa_range(24),
        supports_ios=True,
    ),
    "Switch-PT": ModelCapability(
        model="Switch-PT",
        category="switch",
        uplink_ports=["FastEthernet0/1", "FastEthernet1/1"],
        access_ports=["FastEthernet2/1", "FastEthernet3/1"],
        supports_ios=True,
    ),
    # --- Multilayer Switches ---
    "3560-24PS": ModelCapability(
        model="3560-24PS",
        category="l3_switch",
        uplink_ports=["GigabitEthernet0/1", "GigabitEthernet0/2"],
        access_ports=_fa_range(24),
        supports_ios=True,
    ),
    "3650-24PS": ModelCapability(
        model="3650-24PS",
        category="l3_switch",
        uplink_ports=[
            "GigabitEthernet1/1/1",
            "GigabitEthernet1/1/2",
            "GigabitEthernet1/1/3",
            "GigabitEthernet1/1/4",
        ],
        access_ports=_gi_stack_range(24),
        supports_ios=True,
    ),
    # --- End Devices ---
    "PC-PT": ModelCapability(
        model="PC-PT",
        category="end_device",
        uplink_ports=["FastEthernet0"],
        access_ports=["FastEthernet0"],
        supports_ios=False,
    ),
    "Server-PT": ModelCapability(
        model="Server-PT",
        category="end_device",
        uplink_ports=["FastEthernet0"],
        access_ports=["FastEthernet0"],
        supports_ios=False,
    ),
    "Laptop-PT": ModelCapability(
        model="Laptop-PT",
        category="end_device",
        uplink_ports=["FastEthernet0"],
        access_ports=["FastEthernet0"],
        supports_ios=False,
    ),
    "TabletPC-PT": ModelCapability(
        model="TabletPC-PT",
        category="end_device",
        uplink_ports=[],
        access_ports=[],
        supports_ios=False,
    ),
    "7960": ModelCapability(
        model="7960",
        category="end_device",
        uplink_ports=["Switch"],
        access_ports=["PC"],
        supports_ios=False,
    ),
    # --- Wireless / Security / WAN ---
    "AccessPoint-PT": ModelCapability(
        model="AccessPoint-PT",
        category="ap",
        uplink_ports=["Port 0"],
        access_ports=["Port 0"],
        supports_ios=False,
    ),
    "HomeRouter-PT-AC": ModelCapability(
        model="HomeRouter-PT-AC",
        category="router",
        uplink_ports=["GigabitEthernet1"],
        access_ports=["Ethernet1", "Ethernet2", "Ethernet3", "Ethernet4"],
        supports_ios=False,
    ),
    "5505": ModelCapability(
        model="5505",
        category="firewall",
        uplink_ports=["Ethernet0/0", "Ethernet0/1"],
        access_ports=[f"Ethernet0/{i}" for i in range(2, 8)],
        supports_ios=True,
    ),
    "Cloud-PT": ModelCapability(
        model="Cloud-PT",
        category="cloud",
        uplink_ports=["Port 0"],
        access_ports=["Port 0"],
        supports_ios=False,
    ),
}


def resolve_model(role_or_model: str, available_models: set[str] | None = None) -> str:
    """Resolve a friendly alias (e.g. 'router', 'switch', 'pc') or exact model name."""
    key = role_or_model.strip()
    lower = key.lower()
    if lower in MODEL_ALIASES:
        return MODEL_ALIASES[lower]
    if available_models and key in available_models:
        return key
    if available_models:
        for m in available_models:
            if m.lower() == lower:
                return m
    return key


def get_capability(model: str) -> ModelCapability:
    """Return ModelCapability for a model, or a sensible default if not in the static catalog."""
    if model in MODEL_CATALOG:
        return MODEL_CATALOG[model]
    lower = model.lower()
    if any(k in lower for k in ("router", "isr", "29", "19", "28", "18")):
        return ModelCapability(
            model=model,
            category="router",
            uplink_ports=["GigabitEthernet0/0", "GigabitEthernet0/1"],
            access_ports=["GigabitEthernet0/0", "GigabitEthernet0/1"],
            supports_ios=True,
        )
    if any(k in lower for k in ("3560", "3650")):
        return ModelCapability(
            model=model,
            category="l3_switch",
            uplink_ports=["GigabitEthernet0/1", "GigabitEthernet0/2"],
            access_ports=_fa_range(24),
            supports_ios=True,
        )
    if "switch" in lower or "2960" in lower or "2950" in lower:
        return ModelCapability(
            model=model,
            category="switch",
            uplink_ports=["GigabitEthernet0/1", "GigabitEthernet0/2"],
            access_ports=_fa_range(24),
            supports_ios=True,
        )
    return ModelCapability(
        model=model,
        category="end_device",
        uplink_ports=["FastEthernet0"],
        access_ports=["FastEthernet0"],
        supports_ios=False,
    )

