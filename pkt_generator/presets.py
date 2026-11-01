"""Pre-built topology presets for common Cisco Packet Tracer simple networks."""

from __future__ import annotations

import ipaddress
from pathlib import Path

from pkt_generator.network import SimpleNetwork, ValidationReport


def build_single_lan(
    num_pcs: int = 3,
    include_server: bool = True,
    subnet: str = "192.168.1.0/24",
) -> SimpleNetwork:
    """Build a single-LAN topology:
        R1 (Gateway .1) --- SW1 --- PC1..PCn (.10+) & SRV1 (.100)
    """
    net_obj = ipaddress.IPv4Network(subnet, strict=False)
    prefix = net_obj.prefixlen
    hosts = list(net_obj.hosts())
    gw_ip = str(hosts[0])
    mgmt_ip = str(hosts[1])

    net = SimpleNetwork()
    net.add_router("R1")
    net.add_switch(
        "SW1",
        management_ip=f"{mgmt_ip}/{prefix}",
        default_gateway=gw_ip,
    )
    net.connect("R1", "SW1", ip_a=f"{gw_ip}/{prefix}")

    for i in range(1, num_pcs + 1):
        pc_ip = str(hosts[9 + i - 1])  # .10, .11, ...
        pc_name = f"PC{i}"
        net.add_pc(pc_name, ip=f"{pc_ip}/{prefix}", gateway=gw_ip)
        net.connect("SW1", pc_name)

    if include_server:
        srv_ip = str(hosts[min(99, len(hosts) - 1)])  # .100
        net.add_server("SRV1", ip=f"{srv_ip}/{prefix}", gateway=gw_ip)
        net.connect("SW1", "SRV1")

    return net


def build_dual_site_wan(routing: str = "ospf") -> SimpleNetwork:
    """Build a two-site routed WAN topology:
        [PC1, PC2] --- SW1 --- R1 ===(Serial WAN)=== R2 --- SW2 --- [PC3, SRV1]
    Supports `routing='ospf'` or `routing='static'`.
    """
    net = SimpleNetwork()

    net.add_router("R1", x=360, y=180)
    net.add_router("R2", x=760, y=180)
    net.add_switch("SW1", x=360, y=360, management_ip="192.168.1.2/24", default_gateway="192.168.1.1")
    net.add_switch("SW2", x=760, y=360, management_ip="192.168.2.2/24", default_gateway="192.168.2.1")

    net.add_pc("PC1", ip="192.168.1.10/24", gateway="192.168.1.1", x=240, y=540)
    net.add_pc("PC2", ip="192.168.1.11/24", gateway="192.168.1.1", x=460, y=540)
    net.add_pc("PC3", ip="192.168.2.10/24", gateway="192.168.2.1", x=660, y=540)
    net.add_server("SRV1", ip="192.168.2.100/24", gateway="192.168.2.1", x=880, y=540)

    # Serial WAN link between R1 (DCE) and R2
    net.connect(
        "R1",
        "R2",
        kind="serial",
        ip_a="10.0.0.1/30",
        ip_b="10.0.0.2/30",
        dce="R1",
        clock_rate=2_000_000,
    )

    # Site 1 LAN
    net.connect("R1", "SW1", ip_a="192.168.1.1/24")
    net.connect("SW1", "PC1")
    net.connect("SW1", "PC2")

    # Site 2 LAN
    net.connect("R2", "SW2", ip_a="192.168.2.1/24")
    net.connect("SW2", "PC3")
    net.connect("SW2", "SRV1")

    if routing.lower() == "ospf":
        net.enable_ospf()
    elif routing.lower() == "static":
        net.add_static_route("R1", "192.168.2.0/24", "10.0.0.2")
        net.add_static_route("R2", "192.168.1.0/24", "10.0.0.1")
    else:
        raise ValueError(f"Unsupported routing mode {routing!r}; use 'ospf' or 'static'")

    return net


def build_router_on_a_stick() -> SimpleNetwork:
    """Build an inter-VLAN routing ('Router-on-a-Stick') topology:
        R1 (Gi0/0.10 & Gi0/0.20) ---(802.1Q Trunk)--- SW1
            VLAN 10 (Sales, 192.168.10.0/24): PC-VLAN10-1, PC-VLAN10-2
            VLAN 20 (Engineering, 192.168.20.0/24): PC-VLAN20-1, SRV-VLAN20
    """
    net = SimpleNetwork()

    net.add_router("R1")
    net.add_switch("SW1")
    net.add_vlan("SW1", 10, "Sales")
    net.add_vlan("SW1", 20, "Engineering")

    # Trunk link between R1 and SW1
    link = net.connect("R1", "SW1", trunk=True, allowed_vlans=[10, 20])
    net.add_subinterface(
        "R1",
        link.port_a,
        vlan_id=10,
        ip="192.168.10.1/24",
        description="Sales VLAN 10 Gateway",
    )
    net.add_subinterface(
        "R1",
        link.port_a,
        vlan_id=20,
        ip="192.168.20.1/24",
        description="Engineering VLAN 20 Gateway",
    )

    # VLAN 10 endpoints
    net.add_pc("PC-SALES-1", ip="192.168.10.10/24", gateway="192.168.10.1")
    net.add_pc("PC-SALES-2", ip="192.168.10.11/24", gateway="192.168.10.1")
    net.connect("SW1", "PC-SALES-1", vlan=10)
    net.connect("SW1", "PC-SALES-2", vlan=10)

    # VLAN 20 endpoints
    net.add_pc("PC-ENG-1", ip="192.168.20.10/24", gateway="192.168.20.1")
    net.add_server("SRV-ENG-1", ip="192.168.20.100/24", gateway="192.168.20.1")
    net.connect("SW1", "PC-ENG-1", vlan=20)
    net.connect("SW1", "SRV-ENG-1", vlan=20)

    return net


def build_small_office_network() -> SimpleNetwork:
    """Build a small-office network with IOS DHCP Server, wired PCs, a static Server,
    and a Wireless Access Point with associated wireless Laptops.
    """
    net = SimpleNetwork()

    net.add_router("EDGE-RTR")
    net.add_dhcp_pool(
        "EDGE-RTR",
        pool_name="OFFICE-LAN",
        network="192.168.50.0/24",
        default_router="192.168.50.1",
        dns_server="192.168.50.10",
        excluded_addresses=[("192.168.50.1", "192.168.50.19")],
    )

    net.add_switch(
        "CORE-SW",
        management_ip="192.168.50.2/24",
        default_gateway="192.168.50.1",
    )
    net.connect("EDGE-RTR", "CORE-SW", ip_a="192.168.50.1/24")

    # Static internal DNS/Web server
    net.add_server(
        "OFFICE-SVR",
        ip="192.168.50.10/24",
        gateway="192.168.50.1",
        dns="192.168.50.10",
    )
    net.connect("CORE-SW", "OFFICE-SVR")

    # Wired DHCP workstations
    for i in (1, 2):
        pc_name = f"DESK-PC{i}"
        net.add_pc(pc_name, dhcp=True)
        net.connect("CORE-SW", pc_name)

    # Wireless Access Point + Laptops
    net.add_access_point("OFFICE-AP", ssid="SmallOfficeWiFi")
    net.connect("CORE-SW", "OFFICE-AP")

    net.add_laptop(
        "LAPTOP-1",
        ip="192.168.50.25/24",
        gateway="192.168.50.1",
        dns="192.168.50.10",
    )
    net.connect("CORE-SW", "LAPTOP-1")

    return net


PRESETS = {
    "single-lan": build_single_lan,
    "dual-site-wan": build_dual_site_wan,
    "router-on-a-stick": build_router_on_a_stick,
    "small-office": build_small_office_network,
}


def generate_preset(
    preset_name: str, out_path: str | Path, **kwargs: object
) -> ValidationReport | None:
    """Build and save a named preset topology to `out_path`."""
    key = preset_name.strip().lower().replace("_", "-")
    if key not in PRESETS:
        raise ValueError(
            f"Unknown preset {preset_name!r}. Available presets: {sorted(PRESETS)}"
        )
    net = PRESETS[key](**kwargs)  # type: ignore[operator]
    return net.save(out_path, validate=True)

