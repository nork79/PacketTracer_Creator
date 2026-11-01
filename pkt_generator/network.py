"""High-level API for building and validating Cisco Packet Tracer (.pkt) networks."""

from __future__ import annotations

from dataclasses import dataclass, field
import ipaddress
import json
from pathlib import Path
import sys
from typing import Any, Sequence
import xml.etree.ElementTree as ET

# Ensure bundled packet-tracer-pkt-format is importable without manual PYTHONPATH
_REPO_ROOT = Path(__file__).resolve().parent.parent
_PKT_FORMAT_ROOT = _REPO_ROOT / "packet-tracer-pkt-format"
for _p in (str(_PKT_FORMAT_ROOT / "src"), str(_PKT_FORMAT_ROOT / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from pkt_core import Lab, decode_bytes, encode  # noqa: E402
from pkt_generator.catalog import (  # noqa: E402
    ModelCapability,
    get_capability,
    resolve_model,
)


def parse_ipv4(ip_spec: str | Sequence[str]) -> tuple[str, str]:
    """Parse an IPv4 CIDR string ('192.168.1.10/24'), plain IP ('192.168.1.10' -> /24),
    or (ip, netmask) tuple into (ip_address, subnet_mask).
    """
    if isinstance(ip_spec, (tuple, list)):
        if len(ip_spec) >= 2:
            return str(ip_spec[0]).strip(), str(ip_spec[1]).strip()
        ip_spec = str(ip_spec[0])
    s = str(ip_spec).strip()
    if " " in s and "/" not in s:
        parts = s.split()
        return parts[0], parts[1]
    if "/" not in s:
        s = f"{s}/24"
    iface = ipaddress.IPv4Interface(s)
    return str(iface.ip), str(iface.netmask)


def parse_network_wildcard(net_spec: str | Sequence[str]) -> tuple[str, str, str]:
    """Parse a network spec ('192.168.1.0/24' or ('192.168.1.0', '255.255.255.0'))
    into (network_address, netmask, hostmask/wildcard).
    """
    if isinstance(net_spec, (tuple, list)):
        net = ipaddress.IPv4Network(f"{net_spec[0]}/{net_spec[1]}", strict=False)
    else:
        s = str(net_spec).strip()
        if " " in s and "/" not in s:
            parts = s.split()
            net = ipaddress.IPv4Network(f"{parts[0]}/{parts[1]}", strict=False)
        else:
            if "/" not in s:
                s = f"{s}/24"
            net = ipaddress.IPv4Network(s, strict=False)
    return str(net.network_address), str(net.netmask), str(net.hostmask)


@dataclass
class SubinterfaceSpec:
    parent_port: str
    vlan_id: int
    ip: str
    netmask: str
    native: bool = False
    description: str | None = None


@dataclass
class VlanSpec:
    vlan_id: int
    name: str
    svi_ip: str | None = None
    svi_netmask: str | None = None


@dataclass
class DhcpPoolSpec:
    pool_name: str
    network: str
    netmask: str
    default_router: str
    dns_server: str | None = None
    excluded_addresses: list[tuple[str, str | None]] = field(default_factory=list)


@dataclass
class OspfSpec:
    process_id: int = 1
    router_id: str | None = None
    # List of (network, wildcard, area)
    networks: list[tuple[str, str, int]] = field(default_factory=list)
    auto_advertise_connected: bool = True
    default_area: int = 0
    passive_interfaces: list[str] = field(default_factory=list)


@dataclass
class PortConfig:
    port: str
    ip: str | None = None
    netmask: str | None = None
    shutdown: bool = False
    routed: bool = False  # True -> emit 'no switchport' on L3 switches
    trunk: bool = False
    allowed_vlans: list[int] | None = None
    access_vlan: int | None = None
    clock_rate: int | None = None
    description: str | None = None


@dataclass
class DeviceSpec:
    name: str
    model: str
    capability: ModelCapability
    x: int | None = None
    y: int | None = None
    power: bool = True
    # End-device NIC config
    ip: str | None = None
    netmask: str | None = None
    gateway: str | None = None
    dns: str | None = None
    dhcp: bool = False
    # Wireless config
    ssid: str | None = None
    channel: int | None = None
    # Switch / Router specifics
    management_ip: str | None = None
    management_netmask: str | None = None
    default_gateway: str | None = None
    ip_routing: bool = False
    # Per-port configurations (keyed by port name)
    ports: dict[str, PortConfig] = field(default_factory=dict)
    used_ports: set[str] = field(default_factory=set)
    modules_to_install: list[str] = field(default_factory=list)
    vlans: dict[int, VlanSpec] = field(default_factory=dict)
    subinterfaces: list[SubinterfaceSpec] = field(default_factory=list)
    static_routes: list[tuple[str, str, str]] = field(default_factory=list)  # (net, mask, next_hop)
    dhcp_pools: list[DhcpPoolSpec] = field(default_factory=list)
    ospf: OspfSpec | None = None
    extra_ios_commands: list[str] = field(default_factory=list)
    raw_ios_override: list[str] | None = None


@dataclass
class LinkSpec:
    dev_a: str
    port_a: str
    dev_b: str
    port_b: str
    kind: str = "copper"  # "copper" or "serial"
    dce: str | None = None
    clock_rate: int = 2_000_000


@dataclass
class ValidationReport:
    ok: bool
    device_count: int
    link_count: int
    link_findings: list[dict[str, Any]]
    layout_report: dict[str, Any]
    roundtrip_exact: bool

    def summary(self) -> str:
        status = "PASSED" if self.ok else "FAILED"
        overlaps = len(self.layout_report.get("label_box_overlaps", []))
        off_page = len(self.layout_report.get("off_page", []))
        return (
            f"[{status}] {self.device_count} devices, {self.link_count} links | "
            f"link_findings={len(self.link_findings)}, label_overlaps={overlaps}, "
            f"off_page={off_page}, roundtrip_exact={self.roundtrip_exact}"
        )


# Service blocks in harvested templates that should be cleared unless authored
_TEMPLATE_SERVICE_TAGS = (
    "ACS_SERVER",
    "DHCP_SERVERS",
    "DNS_SERVER",
    "FTP_SERVER",
    "HTTP_SERVER",
    "HTTPS_SERVER",
    "NTP_SERVER",
    "SYSLOG_SERVER",
    "TFTP_SERVER",
    "EMAIL_SERVER",
)


class SimpleNetwork:
    """High-level builder for generating Cisco Packet Tracer (.pkt) files of simple networks.

    Example::

        net = SimpleNetwork()
        net.add_router("R1")
        net.add_switch("SW1")
        net.add_pc("PC1", ip="192.168.1.10/24", gateway="192.168.1.1")
        net.add_pc("PC2", ip="192.168.1.11/24", gateway="192.168.1.1")

        net.connect("R1", "SW1", ip_a="192.168.1.1/24")
        net.connect("SW1", "PC1")
        net.connect("SW1", "PC2")

        net.save("simple_lan.pkt")
    """

    def __init__(self) -> None:
        self.devices: dict[str, DeviceSpec] = {}
        self.links: list[LinkSpec] = []

    # ------------------------------------------------------------------
    # Device addition helpers
    # ------------------------------------------------------------------
    def add_device(
        self,
        name: str,
        role_or_model: str = "pc",
        *,
        x: int | None = None,
        y: int | None = None,
        power: bool = True,
        ip: str | Sequence[str] | None = None,
        gateway: str | None = None,
        dns: str | None = None,
        dhcp: bool = False,
        ssid: str | None = None,
        channel: int | None = None,
        management_ip: str | Sequence[str] | None = None,
        default_gateway: str | None = None,
        ip_routing: bool = False,
        ios_config: Sequence[str] | None = None,
    ) -> DeviceSpec:
        """Add any supported device by friendly role ('router', 'switch', 'pc', ...) or exact PT model."""
        if name in self.devices:
            raise ValueError(f"Device name {name!r} already exists in the network")

        model = resolve_model(role_or_model)
        cap = get_capability(model)

        parsed_ip = parsed_mask = None
        if ip is not None:
            if isinstance(ip, (tuple, list)) and len(ip) == 3 and gateway is None:
                parsed_ip, parsed_mask, gateway = str(ip[0]), str(ip[1]), str(ip[2])
            else:
                parsed_ip, parsed_mask = parse_ipv4(ip)

        mgmt_ip = mgmt_mask = None
        if management_ip is not None:
            mgmt_ip, mgmt_mask = parse_ipv4(management_ip)

        dev = DeviceSpec(
            name=name,
            model=model,
            capability=cap,
            x=x,
            y=y,
            power=power,
            ip=parsed_ip,
            netmask=parsed_mask,
            gateway=gateway,
            dns=dns,
            dhcp=dhcp,
            ssid=ssid,
            channel=channel,
            management_ip=mgmt_ip,
            management_netmask=mgmt_mask,
            default_gateway=default_gateway,
            ip_routing=ip_routing or (cap.category == "l3_switch"),
            raw_ios_override=list(ios_config) if ios_config is not None else None,
        )
        self.devices[name] = dev
        return dev

    def add_router(
        self,
        name: str,
        model: str = "2911",
        *,
        x: int | None = None,
        y: int | None = None,
        ios_config: Sequence[str] | None = None,
    ) -> DeviceSpec:
        """Add a Cisco router (default model: '2911')."""
        return self.add_device(name, model, x=x, y=y, ios_config=ios_config)

    def add_switch(
        self,
        name: str,
        model: str = "2960-24TT",
        *,
        x: int | None = None,
        y: int | None = None,
        management_ip: str | Sequence[str] | None = None,
        default_gateway: str | None = None,
        ios_config: Sequence[str] | None = None,
    ) -> DeviceSpec:
        """Add a Layer 2 switch (default model: '2960-24TT')."""
        return self.add_device(
            name,
            model,
            x=x,
            y=y,
            management_ip=management_ip,
            default_gateway=default_gateway,
            ios_config=ios_config,
        )

    def add_multilayer_switch(
        self,
        name: str,
        model: str = "3560-24PS",
        *,
        x: int | None = None,
        y: int | None = None,
        management_ip: str | Sequence[str] | None = None,
        ip_routing: bool = True,
        ios_config: Sequence[str] | None = None,
    ) -> DeviceSpec:
        """Add a Layer 3 multilayer switch (default model: '3560-24PS')."""
        return self.add_device(
            name,
            model,
            x=x,
            y=y,
            management_ip=management_ip,
            ip_routing=ip_routing,
            ios_config=ios_config,
        )

    def add_pc(
        self,
        name: str,
        ip: str | Sequence[str] | None = None,
        gateway: str | None = None,
        *,
        dns: str | None = None,
        dhcp: bool = False,
        model: str = "PC-PT",
        x: int | None = None,
        y: int | None = None,
    ) -> DeviceSpec:
        """Add a PC workstation (default model: 'PC-PT')."""
        return self.add_device(
            name, model, x=x, y=y, ip=ip, gateway=gateway, dns=dns, dhcp=dhcp
        )

    def add_server(
        self,
        name: str,
        ip: str | Sequence[str] | None = None,
        gateway: str | None = None,
        *,
        dns: str | None = None,
        dhcp: bool = False,
        model: str = "Server-PT",
        x: int | None = None,
        y: int | None = None,
    ) -> DeviceSpec:
        """Add a Server (default model: 'Server-PT')."""
        return self.add_device(
            name, model, x=x, y=y, ip=ip, gateway=gateway, dns=dns, dhcp=dhcp
        )

    def add_laptop(
        self,
        name: str,
        ip: str | Sequence[str] | None = None,
        gateway: str | None = None,
        *,
        dns: str | None = None,
        dhcp: bool = False,
        ssid: str | None = None,
        model: str = "Laptop-PT",
        x: int | None = None,
        y: int | None = None,
    ) -> DeviceSpec:
        """Add a Laptop (default model: 'Laptop-PT')."""
        return self.add_device(
            name,
            model,
            x=x,
            y=y,
            ip=ip,
            gateway=gateway,
            dns=dns,
            dhcp=dhcp,
            ssid=ssid,
        )

    def add_access_point(
        self,
        name: str,
        ssid: str = "OfficeWiFi",
        *,
        channel: int | None = None,
        model: str = "AccessPoint-PT",
        x: int | None = None,
        y: int | None = None,
    ) -> DeviceSpec:
        """Add a Wireless Access Point (default model: 'AccessPoint-PT')."""
        return self.add_device(name, model, x=x, y=y, ssid=ssid, channel=channel)

    def add_firewall(
        self,
        name: str,
        model: str = "5505",
        *,
        x: int | None = None,
        y: int | None = None,
        ios_config: Sequence[str] | None = None,
    ) -> DeviceSpec:
        """Add an ASA 5505 firewall."""
        return self.add_device(name, model, x=x, y=y, ios_config=ios_config)

    def add_cloud(
        self,
        name: str,
        model: str = "Cloud-PT",
        *,
        x: int | None = None,
        y: int | None = None,
    ) -> DeviceSpec:
        """Add a WAN Cloud device."""
        return self.add_device(name, model, x=x, y=y)

    # ------------------------------------------------------------------
    # Port allocation & Cabling
    # ------------------------------------------------------------------
    def _allocate_port(
        self, dev: DeviceSpec, peer: DeviceSpec, kind: str = "copper"
    ) -> str:
        cap = dev.capability
        if kind == "serial":
            for sp in cap.serial_ports:
                if sp not in dev.used_ports:
                    dev.used_ports.add(sp)
                    # Determine how many serial modules are required
                    idx = cap.serial_ports.index(sp)
                    needed_mods = (idx // max(1, cap.serial_ports_per_module)) + 1
                    if cap.serial_module:
                        while len(dev.modules_to_install) < needed_mods:
                            dev.modules_to_install.append(cap.serial_module)
                    return sp
            raise ValueError(
                f"Device {dev.name!r} ({dev.model}) has no available serial ports"
            )

        # Copper port selection:
        # If dev is a switch/l3_switch and peer is a router/switch/l3_switch/firewall/cloud,
        # prefer uplink ports first, then fall back to access ports.
        peer_is_infra = peer.capability.category in (
            "router",
            "switch",
            "l3_switch",
            "firewall",
            "cloud",
        )
        if cap.category in ("switch", "l3_switch") and peer_is_infra:
            candidates = list(cap.uplink_ports) + [
                p for p in cap.access_ports if p not in cap.uplink_ports
            ]
        elif cap.category in ("switch", "l3_switch"):
            candidates = list(cap.access_ports) + [
                p for p in cap.uplink_ports if p not in cap.access_ports
            ]
        else:
            candidates = list(cap.uplink_ports) + [
                p for p in cap.access_ports if p not in cap.uplink_ports
            ]

        for p in candidates:
            if p not in dev.used_ports:
                dev.used_ports.add(p)
                return p
        raise ValueError(
            f"Device {dev.name!r} ({dev.model}) has no free copper ports left "
            f"(used: {sorted(dev.used_ports)})"
        )

    def connect(
        self,
        dev_a: str | DeviceSpec,
        dev_b: str | DeviceSpec,
        *,
        port_a: str | None = None,
        port_b: str | None = None,
        ip_a: str | Sequence[str] | None = None,
        ip_b: str | Sequence[str] | None = None,
        kind: str = "copper",
        vlan: int | None = None,
        trunk: bool = False,
        allowed_vlans: Sequence[int] | None = None,
        dce: str | DeviceSpec | None = None,
        clock_rate: int = 2_000_000,
        description: str | None = None,
    ) -> LinkSpec:
        """Connect two devices with a copper or serial cable, automatically selecting
        valid free ports if port_a/port_b are omitted, and configuring interface IPs,
        VLANs, or 802.1Q trunking.
        """
        name_a = dev_a.name if isinstance(dev_a, DeviceSpec) else str(dev_a)
        name_b = dev_b.name if isinstance(dev_b, DeviceSpec) else str(dev_b)
        if name_a not in self.devices:
            raise KeyError(f"Unknown device {name_a!r}")
        if name_b not in self.devices:
            raise KeyError(f"Unknown device {name_b!r}")

        da = self.devices[name_a]
        db = self.devices[name_b]

        if kind not in ("copper", "serial"):
            raise ValueError(f"Unsupported link kind {kind!r}; expected 'copper' or 'serial'")

        if port_a is None:
            port_a = self._allocate_port(da, db, kind=kind)
        else:
            if port_a in da.used_ports:
                raise ValueError(f"Port {port_a!r} on {da.name!r} is already in use")
            da.used_ports.add(port_a)
            if kind == "serial" and da.capability.serial_module:
                if port_a in da.capability.serial_ports:
                    idx = da.capability.serial_ports.index(port_a)
                else:
                    idx = 0
                needed = (idx // max(1, da.capability.serial_ports_per_module)) + 1
                while len(da.modules_to_install) < needed:
                    da.modules_to_install.append(da.capability.serial_module)

        if port_b is None:
            port_b = self._allocate_port(db, da, kind=kind)
        else:
            if port_b in db.used_ports:
                raise ValueError(f"Port {port_b!r} on {db.name!r} is already in use")
            db.used_ports.add(port_b)
            if kind == "serial" and db.capability.serial_module:
                if port_b in db.capability.serial_ports:
                    idx = db.capability.serial_ports.index(port_b)
                else:
                    idx = 0
                needed = (idx // max(1, db.capability.serial_ports_per_module)) + 1
                while len(db.modules_to_install) < needed:
                    db.modules_to_install.append(db.capability.serial_module)

        dce_name: str | None = None
        if kind == "serial":
            if dce is not None:
                dce_name = dce.name if isinstance(dce, DeviceSpec) else str(dce)
            else:
                dce_name = da.name

        # Configure port state on device A and device B
        pa_cfg = da.ports.setdefault(port_a, PortConfig(port=port_a))
        pb_cfg = db.ports.setdefault(port_b, PortConfig(port=port_b))

        if description:
            pa_cfg.description = description
            pb_cfg.description = description

        parsed_ip_a = parsed_mask_a = None
        if ip_a is not None:
            parsed_ip_a, parsed_mask_a = parse_ipv4(ip_a)
            if da.capability.supports_ios:
                pa_cfg.ip = parsed_ip_a
                pa_cfg.netmask = parsed_mask_a
                if da.capability.category == "l3_switch":
                    pa_cfg.routed = True
            else:
                da.ip = parsed_ip_a
                da.netmask = parsed_mask_a

        parsed_ip_b = parsed_mask_b = None
        if ip_b is not None:
            parsed_ip_b, parsed_mask_b = parse_ipv4(ip_b)
            if db.capability.supports_ios:
                pb_cfg.ip = parsed_ip_b
                pb_cfg.netmask = parsed_mask_b
                if db.capability.category == "l3_switch":
                    pb_cfg.routed = True
            else:
                db.ip = parsed_ip_b
                db.netmask = parsed_mask_b

        # Auto-fill end-device gateway when directly connected to a router/L3 port with an IP
        if da.capability.category == "end_device" and not da.gateway and parsed_ip_b:
            da.gateway = parsed_ip_b
        if db.capability.category == "end_device" and not db.gateway and parsed_ip_a:
            db.gateway = parsed_ip_a

        if kind == "serial":
            if dce_name == da.name:
                pa_cfg.clock_rate = clock_rate
            elif dce_name == db.name:
                pb_cfg.clock_rate = clock_rate

        if trunk:
            if da.capability.category in ("switch", "l3_switch"):
                pa_cfg.trunk = True
                if allowed_vlans:
                    pa_cfg.allowed_vlans = list(allowed_vlans)
            if db.capability.category in ("switch", "l3_switch"):
                pb_cfg.trunk = True
                if allowed_vlans:
                    pb_cfg.allowed_vlans = list(allowed_vlans)
        elif vlan is not None:
            for d, pcfg in ((da, pa_cfg), (db, pb_cfg)):
                if d.capability.category in ("switch", "l3_switch") and not pcfg.routed:
                    pcfg.access_vlan = vlan
                    if vlan != 1 and vlan not in d.vlans:
                        d.vlans[vlan] = VlanSpec(vlan_id=vlan, name=f"VLAN{vlan}")

        link = LinkSpec(
            dev_a=da.name,
            port_a=port_a,
            dev_b=db.name,
            port_b=port_b,
            kind=kind,
            dce=dce_name,
            clock_rate=clock_rate,
        )
        self.links.append(link)
        return link

    # ------------------------------------------------------------------
    # Layer 2 & Layer 3 configuration helpers
    # ------------------------------------------------------------------
    def add_vlan(
        self,
        device: str | DeviceSpec,
        vlan_id: int,
        name: str | None = None,
        *,
        svi_ip: str | Sequence[str] | None = None,
    ) -> VlanSpec:
        """Define a VLAN on a switch or multilayer switch, with an optional SVI IP address."""
        dev_name = device.name if isinstance(device, DeviceSpec) else str(device)
        dev = self.devices[dev_name]
        ip_str = mask_str = None
        if svi_ip is not None:
            ip_str, mask_str = parse_ipv4(svi_ip)
        vspec = VlanSpec(
            vlan_id=int(vlan_id),
            name=name or f"VLAN{vlan_id}",
            svi_ip=ip_str,
            svi_netmask=mask_str,
        )
        dev.vlans[int(vlan_id)] = vspec
        return vspec

    def add_subinterface(
        self,
        router: str | DeviceSpec,
        parent_port: str,
        vlan_id: int,
        ip: str | Sequence[str],
        *,
        native: bool = False,
        description: str | None = None,
    ) -> SubinterfaceSpec:
        """Configure an 802.1Q router-on-a-stick subinterface (e.g. GigabitEthernet0/0.10)
        and ensure its parent physical interface is brought up ('no shutdown').
        """
        r_name = router.name if isinstance(router, DeviceSpec) else str(router)
        dev = self.devices[r_name]
        ip_str, mask_str = parse_ipv4(ip)
        # Ensure parent physical port exists in dev.ports and stays up (Rule 7)
        dev.ports.setdefault(parent_port, PortConfig(port=parent_port, shutdown=False))
        sub = SubinterfaceSpec(
            parent_port=parent_port,
            vlan_id=int(vlan_id),
            ip=ip_str,
            netmask=mask_str,
            native=native,
            description=description,
        )
        dev.subinterfaces.append(sub)

        # Also ensure if parent_port is connected to a switch, that switch port is set to trunk!
        for lk in self.links:
            if lk.dev_a == r_name and lk.port_a == parent_port:
                peer = self.devices[lk.dev_b]
                if peer.capability.category in ("switch", "l3_switch"):
                    peer.ports[lk.port_b].trunk = True
                    if int(vlan_id) != 1 and int(vlan_id) not in peer.vlans:
                        peer.vlans[int(vlan_id)] = VlanSpec(
                            vlan_id=int(vlan_id), name=f"VLAN{vlan_id}"
                        )
            elif lk.dev_b == r_name and lk.port_b == parent_port:
                peer = self.devices[lk.dev_a]
                if peer.capability.category in ("switch", "l3_switch"):
                    peer.ports[lk.port_a].trunk = True
                    if int(vlan_id) != 1 and int(vlan_id) not in peer.vlans:
                        peer.vlans[int(vlan_id)] = VlanSpec(
                            vlan_id=int(vlan_id), name=f"VLAN{vlan_id}"
                        )
        return sub

    def add_static_route(
        self,
        router: str | DeviceSpec,
        prefix: str | Sequence[str],
        next_hop: str,
    ) -> None:
        """Add an IPv4 static route ('ip route <network> <mask> <next_hop>') to a router or L3 switch."""
        r_name = router.name if isinstance(router, DeviceSpec) else str(router)
        dev = self.devices[r_name]
        net_addr, netmask, _ = parse_network_wildcard(prefix)
        dev.static_routes.append((net_addr, netmask, next_hop.strip()))

    def enable_ospf(
        self,
        router: str | DeviceSpec | None = None,
        *,
        process_id: int = 1,
        area: int = 0,
        networks: Sequence[str | Sequence[str]] | None = None,
        router_id: str | None = None,
        passive_interfaces: Sequence[str] | None = None,
    ) -> None:
        """Enable OSPF on a specific router/L3-switch, or on ALL routers if router is None.
        If `networks` is omitted, all directly connected IP interfaces on the router are
        advertised automatically in `area`.
        """
        targets: list[DeviceSpec]
        if router is None:
            targets = [
                d
                for d in self.devices.values()
                if d.capability.category == "router"
                or (d.capability.category == "l3_switch" and d.ip_routing)
            ]
        else:
            r_name = router.name if isinstance(router, DeviceSpec) else str(router)
            targets = [self.devices[r_name]]

        for dev in targets:
            spec = OspfSpec(
                process_id=process_id,
                router_id=router_id,
                auto_advertise_connected=(networks is None),
                default_area=area,
                passive_interfaces=list(passive_interfaces or []),
            )
            if networks is not None:
                for n in networks:
                    net_addr, _mask, wildcard = parse_network_wildcard(n)
                    spec.networks.append((net_addr, wildcard, area))
            dev.ospf = spec

    def add_dhcp_pool(
        self,
        router: str | DeviceSpec,
        pool_name: str,
        network: str | Sequence[str],
        default_router: str,
        *,
        dns_server: str | None = None,
        excluded_addresses: Sequence[str | tuple[str, str]] | None = None,
    ) -> DhcpPoolSpec:
        """Configure an IOS DHCP server pool on a router or multilayer switch."""
        r_name = router.name if isinstance(router, DeviceSpec) else str(router)
        dev = self.devices[r_name]
        net_addr, netmask, _ = parse_network_wildcard(network)
        excl: list[tuple[str, str | None]] = []
        if excluded_addresses:
            for item in excluded_addresses:
                if isinstance(item, (tuple, list)):
                    excl.append((str(item[0]), str(item[1]) if len(item) > 1 else None))
                else:
                    excl.append((str(item), None))
        pool = DhcpPoolSpec(
            pool_name=pool_name,
            network=net_addr,
            netmask=netmask,
            default_router=default_router,
            dns_server=dns_server,
            excluded_addresses=excl,
        )
        dev.dhcp_pools.append(pool)
        return pool

    def add_ios_commands(
        self, device: str | DeviceSpec, commands: Sequence[str]
    ) -> None:
        """Append raw global IOS CLI commands to a router or switch."""
        d_name = device.name if isinstance(device, DeviceSpec) else str(device)
        self.devices[d_name].extra_ios_commands.extend(commands)

    # ------------------------------------------------------------------
    # Auto-layout engine
    # ------------------------------------------------------------------
    def _compute_layout(self) -> dict[str, tuple[int, int]]:
        """Compute clean, collision-free (x, y) coordinates for all devices,
        preserving explicit coordinates when provided and organizing others into
        logical horizontal tiers with minimal cable crossings.
        """
        coords: dict[str, tuple[int, int]] = {}
        # Build adjacency map to group end-devices under their upstream switch/router
        neighbors: dict[str, list[str]] = {name: [] for name in self.devices}
        for lk in self.links:
            neighbors[lk.dev_a].append(lk.dev_b)
            neighbors[lk.dev_b].append(lk.dev_a)

        # Assign tiers:
        # Tier 0: routers, clouds
        # Tier 1: firewalls, l3_switches
        # Tier 2: switches, access points
        # Tier 3: end_devices (PCs, servers, laptops, phones)
        tiers: dict[int, list[DeviceSpec]] = {0: [], 1: [], 2: [], 3: []}
        for dev in self.devices.values():
            cat = dev.capability.category
            if cat in ("router", "cloud"):
                tiers[0].append(dev)
            elif cat in ("firewall", "l3_switch"):
                tiers[1].append(dev)
            elif cat in ("switch", "ap"):
                tiers[2].append(dev)
            else:
                tiers[3].append(dev)

        # Collapse empty tiers so vertical spacing stays compact
        active_tiers = [t for t in (0, 1, 2, 3) if tiers[t]]
        base_y = 180
        row_step = 180

        placed_boxes: list[tuple[int, int, int, int]] = []  # (cx, cy, w, h)

        def _box_size(dev: DeviceSpec) -> tuple[int, int]:
            w = max(80, 7 * max(len(dev.name), len(dev.model)) + 44)
            h = 110
            return w, h

        def _collides(cx: int, cy: int, w: int, h: int) -> bool:
            for px, py, pw, ph in placed_boxes:
                dx = abs(cx - px)
                dy = abs(cy - py)
                if dx * 2 < (w + pw) and dy * 2 < (h + ph):
                    return True
                if dx * dx + dy * dy < 85 * 85:
                    return True
            return False

        # Record explicitly positioned devices first
        for dev in self.devices.values():
            if dev.x is not None and dev.y is not None:
                w, h = _box_size(dev)
                coords[dev.name] = (int(dev.x), int(dev.y))
                placed_boxes.append((int(dev.x), int(dev.y), w, h))

        for tier_idx, t_key in enumerate(active_tiers):
            devs_in_tier = [
                d for d in tiers[t_key] if d.name not in coords
            ]
            if not devs_in_tier:
                continue

            # Sort devices in lower tiers by the average X coordinate of their already-placed neighbors
            def _sort_key(d: DeviceSpec) -> tuple[float, int]:
                placed_nbr_xs = [
                    coords[n][0] for n in neighbors.get(d.name, []) if n in coords
                ]
                avg_x = (
                    sum(placed_nbr_xs) / len(placed_nbr_xs)
                    if placed_nbr_xs
                    else 600.0
                )
                return (avg_x, list(self.devices.keys()).index(d.name))

            devs_in_tier.sort(key=_sort_key)

            # Split into rows of at most 14 devices per row
            max_per_row = 14
            for sub_row_idx in range(0, len(devs_in_tier), max_per_row):
                row_devs = devs_in_tier[sub_row_idx : sub_row_idx + max_per_row]
                cy = base_y + (tier_idx * row_step) + (sub_row_idx // max_per_row) * 160
                pitch = max(
                    180,
                    max(
                        (200 if len(d.name) <= 16 else 260 if len(d.name) <= 24 else 320)
                        for d in row_devs
                    ),
                )
                total_w = (len(row_devs) - 1) * pitch
                # Center around the mean X of already placed devices, or 560
                center_x = 560
                if coords:
                    center_x = int(
                        sum(x for x, _ in coords.values()) / len(coords)
                    )
                    center_x = max(400, min(1800, center_x))
                start_x = max(140, center_x - total_w // 2)

                for i, d in enumerate(row_devs):
                    w, h = _box_size(d)
                    cx = start_x + i * pitch
                    ry = cy
                    while _collides(cx, ry, w, h):
                        cx += 40
                        if cx > 3650:
                            cx = 140
                            ry += 160
                    coords[d.name] = (cx, ry)
                    placed_boxes.append((cx, ry, w, h))

        return coords

    # ------------------------------------------------------------------
    # IOS Configuration Synthesis
    # ------------------------------------------------------------------
    def _build_ios_config(self, dev: DeviceSpec) -> list[str] | None:
        if dev.raw_ios_override is not None:
            return list(dev.raw_ios_override)
        if not dev.capability.supports_ios:
            return None

        # Auto-infer inter-switch trunks if switches share VLANs > 1
        for lk in self.links:
            if lk.dev_a == dev.name or lk.dev_b == dev.name:
                my_port = lk.port_a if lk.dev_a == dev.name else lk.port_b
                peer_name = lk.dev_b if lk.dev_a == dev.name else lk.dev_a
                peer = self.devices[peer_name]
                pcfg = dev.ports.get(my_port)
                if (
                    pcfg
                    and dev.capability.category in ("switch", "l3_switch")
                    and peer.capability.category in ("switch", "l3_switch")
                    and not pcfg.routed
                    and pcfg.access_vlan is None
                ):
                    if any(v != 1 for v in dev.vlans) or any(
                        v != 1 for v in peer.vlans
                    ):
                        pcfg.trunk = True

        lines: list[str] = [
            "!",
            "version 15.1" if dev.capability.category == "router" else "version 12.2",
            "no service timestamps log datetime msec",
            "no service timestamps debug datetime msec",
            "no service password-encryption",
            "!",
            f"hostname {dev.name}",
            "!",
            "no ip domain-lookup",
        ]

        if dev.capability.category == "l3_switch" and dev.ip_routing:
            lines.append("ip routing")

        if dev.capability.category in ("switch", "l3_switch"):
            lines.append("spanning-tree mode pvst")

        lines.append("!")

        # DHCP Excluded addresses (global)
        for pool in dev.dhcp_pools:
            for low, high in pool.excluded_addresses:
                if high:
                    lines.append(f"ip dhcp excluded-address {low} {high}")
                else:
                    lines.append(f"ip dhcp excluded-address {low}")

        # DHCP Pools
        for pool in dev.dhcp_pools:
            lines.extend(
                [
                    f"ip dhcp pool {pool.pool_name}",
                    f" network {pool.network} {pool.netmask}",
                    f" default-router {pool.default_router}",
                ]
            )
            if pool.dns_server:
                lines.append(f" dns-server {pool.dns_server}")
            lines.append("!")

        # VLAN definitions on switches
        for vid in sorted(dev.vlans):
            if vid == 1:
                continue
            vspec = dev.vlans[vid]
            lines.extend([f"vlan {vid}", f" name {vspec.name}", "!"])

        # Physical interfaces (in deterministic order)
        for port_name in sorted(dev.ports):
            pcfg = dev.ports[port_name]
            lines.append(f"interface {port_name}")
            if pcfg.description:
                lines.append(f" description {pcfg.description}")
            if dev.capability.category == "l3_switch" and pcfg.routed:
                lines.append(" no switchport")
            if pcfg.ip and pcfg.netmask:
                lines.append(f" ip address {pcfg.ip} {pcfg.netmask}")
            if pcfg.clock_rate:
                lines.append(f" clock rate {pcfg.clock_rate}")
            if dev.capability.category in ("switch", "l3_switch") and not pcfg.routed:
                if pcfg.trunk:
                    if dev.capability.category == "l3_switch":
                        lines.append(" switchport trunk encapsulation dot1q")
                    lines.append(" switchport mode trunk")
                    if pcfg.allowed_vlans:
                        vlist = ",".join(str(v) for v in sorted(pcfg.allowed_vlans))
                        lines.append(f" switchport trunk allowed vlan {vlist}")
                else:
                    lines.append(" switchport mode access")
                    if pcfg.access_vlan and pcfg.access_vlan != 1:
                        lines.append(f" switchport access vlan {pcfg.access_vlan}")
            lines.append(" shutdown" if pcfg.shutdown else " no shutdown")
            lines.append("!")

        # Router-on-a-stick subinterfaces
        for sub in sorted(dev.subinterfaces, key=lambda s: (s.parent_port, s.vlan_id)):
            lines.append(f"interface {sub.parent_port}.{sub.vlan_id}")
            if sub.description:
                lines.append(f" description {sub.description}")
            native_kw = " native" if sub.native else ""
            lines.append(f" encapsulation dot1Q {sub.vlan_id}{native_kw}")
            lines.append(f" ip address {sub.ip} {sub.netmask}")
            lines.append(" no shutdown")
            lines.append("!")

        # Switch SVIs (Vlan1 management IP and any VLAN SVIs)
        if dev.management_ip and dev.management_netmask:
            lines.extend(
                [
                    "interface Vlan1",
                    f" ip address {dev.management_ip} {dev.management_netmask}",
                    " no shutdown",
                    "!",
                ]
            )
        for vid in sorted(dev.vlans):
            vspec = dev.vlans[vid]
            if vspec.svi_ip and vspec.svi_netmask:
                lines.extend(
                    [
                        f"interface Vlan{vid}",
                        f" ip address {vspec.svi_ip} {vspec.svi_netmask}",
                        " no shutdown",
                        "!",
                    ]
                )

        if dev.default_gateway and dev.capability.category == "switch":
            lines.append(f"ip default-gateway {dev.default_gateway}")
            lines.append("!")

        # OSPF routing
        if dev.ospf is not None:
            ospf = dev.ospf
            lines.append(f"router ospf {ospf.process_id}")
            if ospf.router_id:
                lines.append(f" router-id {ospf.router_id}")
            for p_iface in ospf.passive_interfaces:
                lines.append(f" passive-interface {p_iface}")

            net_entries: list[tuple[str, str, int]] = list(ospf.networks)
            if ospf.auto_advertise_connected:
                seen: set[tuple[str, str, int]] = set(net_entries)
                for pcfg in dev.ports.values():
                    if pcfg.ip and pcfg.netmask:
                        net_addr, _, wildcard = parse_network_wildcard(
                            (pcfg.ip, pcfg.netmask)
                        )
                        item = (net_addr, wildcard, ospf.default_area)
                        if item not in seen:
                            seen.add(item)
                            net_entries.append(item)
                for sub in dev.subinterfaces:
                    net_addr, _, wildcard = parse_network_wildcard(
                        (sub.ip, sub.netmask)
                    )
                    item = (net_addr, wildcard, ospf.default_area)
                    if item not in seen:
                        seen.add(item)
                        net_entries.append(item)
                for vspec in dev.vlans.values():
                    if vspec.svi_ip and vspec.svi_netmask:
                        net_addr, _, wildcard = parse_network_wildcard(
                            (vspec.svi_ip, vspec.svi_netmask)
                        )
                        item = (net_addr, wildcard, ospf.default_area)
                        if item not in seen:
                            seen.add(item)
                            net_entries.append(item)

            for net_addr, wildcard, area in net_entries:
                lines.append(f" network {net_addr} {wildcard} area {area}")
            lines.append("!")

        # Static routes
        for net_addr, netmask, next_hop in dev.static_routes:
            lines.append(f"ip route {net_addr} {netmask} {next_hop}")
        if dev.static_routes:
            lines.append("!")

        # Extra custom commands
        if dev.extra_ios_commands:
            lines.extend(dev.extra_ios_commands)
            lines.append("!")

        lines.extend(
            [
                "line con 0",
                " logging synchronous",
                "line vty 0 4",
                " login",
                "!",
                "end",
            ]
        )
        return lines

    # ------------------------------------------------------------------
    # Build & Save to .pkt
    # ------------------------------------------------------------------
    def build_lab(self) -> Lab:
        """Construct and return a `pkt_core.Lab` instance with all devices, modules,
        cables, IOS configs, and sanitized XML elements applied.
        """
        lab = Lab()
        lab.prune_seed_devices()

        coords = self._compute_layout()
        dev_sids: dict[str, str] = {}
        ios_configs: dict[str, list[str] | None] = {}

        for name, dev in self.devices.items():
            x, y = coords[name]
            ios_cfg = self._build_ios_config(dev)
            ios_configs[name] = ios_cfg

            pc_ip_tuple: tuple[str, str, str] | None = None
            if not dev.capability.supports_ios and dev.ip and dev.netmask:
                pc_ip_tuple = (dev.ip, dev.netmask, dev.gateway or "")

            sid = lab.add_device(
                dev.model,
                dev.name,
                x=x,
                y=y,
                power=dev.power,
                ios_config=ios_cfg,
                pc_ip=pc_ip_tuple,
            )
            dev_sids[name] = sid

            # Install any required expansion modules (e.g. HWIC-2T / NIM-2T for serial)
            for mod_name in dev.modules_to_install:
                lab.install_module(sid, mod_name)

            # Post-process the underlying XML element for end-devices, switches, and APs
            el = lab._els[sid]
            eng = el.find("ENGINE")

            # Strip un-authored template service blocks so `pkt audit` stays clean (Rule 4)
            if eng is not None:
                for svc_tag in _TEMPLATE_SERVICE_TAGS:
                    for svc_el in list(eng.findall(svc_tag)):
                        eng.remove(svc_el)

            # Clear leftover donor IP/SUBNET on IOS device ports (including installed modules like HWIC-2T)
            if dev.capability.supports_ios:
                for p_el in el.iter("PORT"):
                    for tag in ("IP", "SUBNET", "PORT_GATEWAY"):
                        e = p_el.find(tag)
                        if e is not None and e.text:
                            e.text = ""

            # Configure DHCP or DNS on end devices
            if dev.capability.category == "end_device":
                port_el = el.find(".//PORT")
                if dev.dhcp:
                    if port_el is not None:
                        for tag, val in (
                            ("IP", ""),
                            ("SUBNET", ""),
                            ("PORT_GATEWAY", ""),
                            ("PORT_DHCP_ENABLE", "true"),
                        ):
                            e = port_el.find(tag)
                            if e is None:
                                e = ET.SubElement(port_el, tag)
                            e.text = val
                    if eng is not None:
                        gate = eng.find("GATEWAY")
                        if gate is not None:
                            gate.text = ""
                elif not dev.ip and port_el is not None:
                    # Clear donor template default IP (e.g. 1.1.1.1 on PC-PT)
                    for tag in ("IP", "SUBNET", "PORT_GATEWAY"):
                        e = port_el.find(tag)
                        if e is not None:
                            e.text = ""
                    if eng is not None:
                        gate = eng.find("GATEWAY")
                        if gate is not None:
                            gate.text = ""

                if dev.dns and port_el is not None:
                    e = port_el.find("PORT_DNS")
                    if e is None:
                        e = ET.SubElement(port_el, "PORT_DNS")
                    e.text = dev.dns
                    if eng is not None:
                        dns_srv = eng.find("DNS_CLIENT/SERVER_IP")
                        if dns_srv is not None:
                            dns_srv.text = dev.dns

            # Wireless configuration (AccessPoint-PT, Laptop-PT, etc.)
            if dev.ssid is not None:
                lab.set_wireless(sid, ssid=dev.ssid, channel=dev.channel)

            # Populate switch <VLANS> table and <STARTUPCONFIG>
            if eng is not None and ios_cfg:
                sc = eng.find("STARTUPCONFIG")
                if sc is not None:
                    for child in list(sc):
                        sc.remove(child)
                    for line in ios_cfg:
                        ET.SubElement(sc, "LINE").text = line

                if dev.vlans:
                    vlans_el = eng.find("VLANS")
                    if vlans_el is None:
                        vlans_el = ET.SubElement(eng, "VLANS")
                    existing_vids = {
                        v.get("number") for v in vlans_el.findall("VLAN")
                    }
                    for vid, vspec in sorted(dev.vlans.items()):
                        if str(vid) not in existing_vids:
                            v_el = ET.Element(
                                "VLAN", number=str(vid), name=vspec.name
                            )
                            vlans_el.insert(1, v_el)

            # Ensure all ports on powered devices (especially AccessPoint-PT) have POWER=true (Rule 1)
            if dev.power:
                for p_el in el.iter("PORT"):
                    pw = p_el.find("POWER")
                    if pw is not None:
                        pw.text = "true"

        # Add all links
        for lk in self.links:
            sid_a = dev_sids[lk.dev_a]
            sid_b = dev_sids[lk.dev_b]
            if lk.kind == "serial":
                dce_sid = dev_sids[lk.dce] if lk.dce else sid_a
                dce_port = lk.port_a if lk.dce == lk.dev_a else lk.port_b
                lab.link(
                    sid_a,
                    lk.port_a,
                    sid_b,
                    lk.port_b,
                    kind="serial",
                    dce=dce_sid,
                    dce_port=dce_port,
                    clock=lk.clock_rate,
                )
                # Restore clean RUNNINGCONFIG on DCE router because lab.link() appends a duplicate
                # interface block at the bottom of RUNNINGCONFIG
                dce_dev_name = lk.dce or lk.dev_a
                clean_cfg = ios_configs.get(dce_dev_name)
                if clean_cfg:
                    eng = lab._els[dce_sid].find("ENGINE")
                    if eng is not None:
                        for rc in list(eng.findall("RUNNINGCONFIG")):
                            eng.remove(rc)
                        rc = ET.SubElement(eng, "RUNNINGCONFIG")
                        for line in clean_cfg:
                            ET.SubElement(rc, "LINE").text = line
            else:
                lab.link(sid_a, lk.port_a, sid_b, lk.port_b, kind="copper")

        return lab

    def to_xml_bytes(self) -> bytes:
        """Build the network and return its raw inner Packet Tracer XML bytes."""
        lab = self.build_lab()
        return ET.tostring(lab.base, encoding="unicode").encode("utf-8")

    def validate(self) -> ValidationReport:
        """Build the network in memory and run static verification gates:
        - `audit_links` (verifies every cabled port has a valid, non-shutdown interface config)
        - `check_layout` (verifies zero label/icon overlaps and all devices on page)
        """
        import audit_links
        import check_layout
        import lab_api

        xml_bytes = self.to_xml_bytes()
        root = ET.fromstring(xml_bytes)
        link_findings = audit_links.audit_xml(root)
        layout_rep = check_layout.analyse(
            lab_api.parse_devices(xml_bytes.decode("utf-8"))
        )
        layout_ok = not (
            layout_rep["label_box_overlaps"]
            or layout_rep["off_page"]
            or layout_rep["coincident"]
        )
        ok = (len(link_findings) == 0) and layout_ok
        return ValidationReport(
            ok=ok,
            device_count=len(self.devices),
            link_count=len(self.links),
            link_findings=link_findings,
            layout_report=layout_rep,
            roundtrip_exact=True,
        )

    def save(
        self, path: str | Path, *, validate: bool = True
    ) -> ValidationReport | None:
        """Save the network as an encrypted Cisco Packet Tracer `.pkt` file, and
        optionally validate links, layout, and byte-exact decode round-trip.
        """
        out_path = Path(path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        lab = self.build_lab()
        xml_bytes = ET.tostring(lab.base, encoding="unicode").encode("utf-8")
        lab.save(str(out_path))

        if not validate:
            return None

        import audit_links
        import check_layout
        import lab_api

        # Verify byte-exact decode round-trip from the written file
        decoded_xml = decode_bytes(out_path.read_bytes(), "pkt").xml
        roundtrip_ok = decoded_xml == xml_bytes

        root = ET.fromstring(decoded_xml)
        link_findings = audit_links.audit_xml(root)
        layout_rep = check_layout.analyse(
            lab_api.parse_devices(decoded_xml.decode("utf-8"))
        )
        layout_ok = not (
            layout_rep["label_box_overlaps"]
            or layout_rep["off_page"]
            or layout_rep["coincident"]
        )
        ok = (len(link_findings) == 0) and layout_ok and roundtrip_ok
        return ValidationReport(
            ok=ok,
            device_count=len(self.devices),
            link_count=len(self.links),
            link_findings=link_findings,
            layout_report=layout_rep,
            roundtrip_exact=roundtrip_ok,
        )

    # ------------------------------------------------------------------
    # Declarative JSON / Dict support
    # ------------------------------------------------------------------
    @classmethod
    def from_dict(cls, spec: dict[str, Any]) -> SimpleNetwork:
        """Create a `SimpleNetwork` from a declarative dictionary specification."""
        net = cls()
        for d in spec.get("devices", []):
            name = d["name"]
            role_or_model = d.get("model") or d.get("type") or d.get("role") or "pc"
            dev = net.add_device(
                name,
                role_or_model,
                x=d.get("x"),
                y=d.get("y"),
                power=d.get("power", True),
                ip=d.get("ip"),
                gateway=d.get("gateway"),
                dns=d.get("dns"),
                dhcp=d.get("dhcp", False),
                ssid=d.get("ssid"),
                channel=d.get("channel"),
                management_ip=d.get("management_ip"),
                default_gateway=d.get("default_gateway"),
                ip_routing=d.get("ip_routing", False),
                ios_config=d.get("ios_config"),
            )
            for v in d.get("vlans", []):
                if isinstance(v, int):
                    net.add_vlan(dev, v)
                else:
                    net.add_vlan(
                        dev,
                        v["id"],
                        v.get("name"),
                        svi_ip=v.get("svi_ip"),
                    )
            for sub in d.get("subinterfaces", []):
                net.add_subinterface(
                    dev,
                    sub["parent_port"],
                    sub["vlan"],
                    sub["ip"],
                    native=sub.get("native", False),
                    description=sub.get("description"),
                )
            for sr in d.get("static_routes", []):
                net.add_static_route(dev, sr["prefix"], sr["next_hop"])
            for pool in d.get("dhcp_pools", []):
                net.add_dhcp_pool(
                    dev,
                    pool["name"],
                    pool["network"],
                    pool["default_router"],
                    dns_server=pool.get("dns_server"),
                    excluded_addresses=pool.get("excluded_addresses"),
                )
            if d.get("ospf"):
                o = d["ospf"]
                if isinstance(o, bool):
                    net.enable_ospf(dev)
                else:
                    net.enable_ospf(
                        dev,
                        process_id=o.get("process_id", 1),
                        area=o.get("area", 0),
                        networks=o.get("networks"),
                        router_id=o.get("router_id"),
                        passive_interfaces=o.get("passive_interfaces"),
                    )
            if d.get("commands"):
                net.add_ios_commands(dev, d["commands"])

        for lk in spec.get("links", []):
            net.connect(
                lk["from"] if "from" in lk else lk["a"],
                lk["to"] if "to" in lk else lk["b"],
                port_a=lk.get("from_port") or lk.get("port_a") or lk.get("aport"),
                port_b=lk.get("to_port") or lk.get("port_b") or lk.get("bport"),
                ip_a=lk.get("ip_a") or lk.get("from_ip"),
                ip_b=lk.get("ip_b") or lk.get("to_ip"),
                kind=lk.get("kind", "copper"),
                vlan=lk.get("vlan"),
                trunk=lk.get("trunk", False),
                allowed_vlans=lk.get("allowed_vlans"),
                dce=lk.get("dce"),
                clock_rate=lk.get("clock_rate", 2_000_000),
                description=lk.get("description"),
            )

        # Subinterfaces defined after links can still auto-trunk their peer switch port
        for dev in net.devices.values():
            for sub in dev.subinterfaces:
                for lk in net.links:
                    if lk.dev_a == dev.name and lk.port_a == sub.parent_port:
                        peer = net.devices[lk.dev_b]
                        if peer.capability.category in ("switch", "l3_switch"):
                            peer.ports[lk.port_b].trunk = True
                    elif lk.dev_b == dev.name and lk.port_b == sub.parent_port:
                        peer = net.devices[lk.dev_a]
                        if peer.capability.category in ("switch", "l3_switch"):
                            peer.ports[lk.port_a].trunk = True

        if spec.get("ospf_all"):
            net.enable_ospf()

        return net

    @classmethod
    def from_json(cls, path: str | Path) -> SimpleNetwork:
        """Load a `SimpleNetwork` from a JSON topology file."""
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls.from_dict(data)

    def to_dict(self) -> dict[str, Any]:
        """Export the network definition as a JSON-serializable dictionary."""
        coords = self._compute_layout()
        devices_out = []
        for name, d in self.devices.items():
            x, y = coords[name]
            entry: dict[str, Any] = {
                "name": name,
                "model": d.model,
                "x": x,
                "y": y,
            }
            if d.ip and d.netmask:
                prefix_len = ipaddress.IPv4Network(f"0.0.0.0/{d.netmask}").prefixlen
                entry["ip"] = f"{d.ip}/{prefix_len}"
            if d.gateway:
                entry["gateway"] = d.gateway
            if d.dns:
                entry["dns"] = d.dns
            if d.dhcp:
                entry["dhcp"] = True
            if d.ssid:
                entry["ssid"] = d.ssid
            devices_out.append(entry)

        links_out = [
            {
                "from": lk.dev_a,
                "from_port": lk.port_a,
                "to": lk.dev_b,
                "to_port": lk.port_b,
                "kind": lk.kind,
            }
            for lk in self.links
        ]
        return {"devices": devices_out, "links": links_out}
