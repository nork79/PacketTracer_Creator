# PacketTracer_Creator & NetDoctor NOC (`pkt_generator`)

Generate valid, pre-configured Cisco Packet Tracer (`.pkt`) network files offline from Python or JSON—and practice **CCNA (200-301 v2.0)** troubleshooting and network engineering in the **NetDoctor NOC** desktop game (`tkinter`).

---

## 🎮 NetDoctor NOC — Educational Troubleshooting & Network Engineering Game

Launch the desktop NOC console (100% Python standard library + `tkinter`):

```powershell
python play_game.py
```

### Key Features
- **Mission Mode 1: Break/Fix Troubleshooting**:
  - Generates randomized `.pkt` challenge files with realistic **CCNA v2.0 (200-301)** faults across Layer 1 (physical power, missing patch cables, disabled NICs, speed/duplex mismatches, wrong router uplink port), Layer 2 (administratively down ports, broken switch `Vlan1` management SVI), Layer 3 (wrong subnet IP, wrong default gateway, restrictive subnet mask, duplicate IP conflicts, router/server IP typos), and Network Services (DHCP/APIPA `169.254.x.x` fallback, wrong DNS server).
  - **6 Real-World Floorplan & Topology Archetypes**: Left-to-Right Enterprise Demarc Flow, Two-Closet MDF + IDF Floorplan (2 Switches), Central Wiring Closet Radial Star, Bottom Fiber Demarc + East/West Split Wings, Right-to-Left Back-Office & Desk Pods, and L-Shaped Corner Suite Floorplan.
  - **Randomized Subnets & Hardware**: Supports `/24`, `/25`, `/26`, and `/27` subnets across `10.x.y.z`, `172.16–31.y.z`, and `192.168.y.z`, alternating between first-usable and last-usable gateway conventions, variable host counts (`PC-PT` + `Laptop-PT`), and multiple router models (`2911`, `1941`, `2901`).
  - **Offline `.pkt` Inspector & Verifier**: Save your fixed `.pkt` in Cisco Packet Tracer (`Ctrl+S`) and click **Upload & Inspect .pkt** (or **Quick-Check Current Challenge .pkt**) to grade your fix, get 3-step progressive hints, or click **Reveal What Was Wrong** for exact IOS CLI / GUI remediation steps.
- **Mission Mode 2: Build Network from Scratch** *(UI setup ready)*:
  - Designed for greenfield network deployment work orders with configurable Subnet Assistance (`Guided`, `Standard FLSM`, `Hard VLSM`) and Starter `.pkt` templates (`Pre-Placed Unconfigured Devices` or `Blank Canvas`).

---

## Architecture

This project combines:
1. **[`aacanadaa/packet-tracer-pkt-format`](https://github.com/aacanadaa/packet-tracer-pkt-format) (`pkt_core`)**: Reverse-engineered byte-exact Twofish-EAX / `qCompress` container codec, 137 harvested Packet Tracer device templates, and static verification gates (`audit_links`, `check_layout`).
2. **`pkt_generator` (`SimpleNetwork` API & CLI)**: A high-level Python API and CLI built on top of `pkt_core` that automates:
   - **Port allocation**: Automatically selects valid free ports per model (e.g., `GigabitEthernet0/1` switch uplinks to routers, `FastEthernet0/1..24` access ports to PCs, and auto-installs `HWIC-2T` / `NIM-2T` expansion cards when serial WAN links are requested).
   - **IOS configuration synthesis**: Automatically generates `hostname`, `interface`, `ip address`, `no shutdown`, `clock rate`, VLAN definitions (`vlan.dat` + IOS), 802.1Q trunks, Router-on-a-Stick subinterfaces, OSPF routing, static routes, and IOS DHCP Server pools.
   - **Collision-free tiered layout**: Automatically places routers, switches, and end devices in horizontal tiers with zero icon/label overlap.
   - **Built-in validation**: Every `.pkt` saved is automatically verified for byte-exact round-trip decoding, active link states (`audit_links`), and label-box geometry (`check_layout`).

---

## Quickstart

### 1. Python API (`SimpleNetwork`)

```python
from pkt_generator import SimpleNetwork

net = SimpleNetwork()

# Add devices (coordinates and port names are optional)
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

# Save and validate .pkt
report = net.save("output/my_network.pkt")
print(report.summary())
```

### 2. Command-Line Interface

Generate ready-made topologies, build from a JSON file, or inspect existing `.pkt` files:

```powershell
# Generate built-in network presets
python -m pkt_generator preset single-lan -o output/single_lan.pkt
python -m pkt_generator preset dual-site-wan -o output/dual_site_wan.pkt
python -m pkt_generator preset router-on-a-stick -o output/router_on_a_stick.pkt
python -m pkt_generator preset small-office -o output/small_office.pkt

# Generate a .pkt from a declarative JSON topology file
python -m pkt_generator from-json examples/topology.json -o output/hq_branch.pkt

# Inspect devices, IPs, links, and run audits on any .pkt file
python -m pkt_generator inspect output/dual_site_wan.pkt
```

---

## Advanced Features

### Routed WAN + Serial Links + Automatic OSPF
```python
from pkt_generator import SimpleNetwork

net = SimpleNetwork()
net.add_router("R1")
net.add_router("R2")
net.add_switch("SW1")
net.add_switch("SW2")
net.add_pc("PC1", ip="192.168.1.10/24", gateway="192.168.1.1")
net.add_pc("PC2", ip="192.168.2.10/24", gateway="192.168.2.1")

# Automatically installs HWIC-2T modules and sets clock rate on R1 (DCE)
net.connect("R1", "R2", kind="serial", ip_a="10.0.0.1/30", ip_b="10.0.0.2/30", dce="R1")
net.connect("R1", "SW1", ip_a="192.168.1.1/24")
net.connect("SW1", "PC1")
net.connect("R2", "SW2", ip_a="192.168.2.1/24")
net.connect("SW2", "PC2")

# Advertise all connected router subnets in OSPF process 1 area 0
net.enable_ospf()
net.save("output/wan_ospf.pkt")
```

### VLANs & Router-on-a-Stick (802.1Q)
```python
from pkt_generator import SimpleNetwork

net = SimpleNetwork()
net.add_router("R1")
net.add_switch("SW1")
net.add_vlan("SW1", 10, "Sales")
net.add_vlan("SW1", 20, "Engineering")

link = net.connect("R1", "SW1", trunk=True, allowed_vlans=[10, 20])
net.add_subinterface("R1", link.port_a, vlan_id=10, ip="192.168.10.1/24")
net.add_subinterface("R1", link.port_a, vlan_id=20, ip="192.168.20.1/24")

net.add_pc("PC-SALES", ip="192.168.10.10/24", gateway="192.168.10.1")
net.add_pc("PC-ENG", ip="192.168.20.10/24", gateway="192.168.20.1")
net.connect("SW1", "PC-SALES", vlan=10)
net.connect("SW1", "PC-ENG", vlan=20)

net.save("output/intervlan.pkt")
```

---

## Supported Device Roles & Default Models

| Role Alias | Default Model | Additional Supported Models |
| :--- | :--- | :--- |
| `"router"` | `2911` | `1941`, `2901`, `2811`, `1841`, `ISR4321`, `ISR4331`, `Router-PT`, `HomeRouter-PT-AC` |
| `"switch"` | `2960-24TT` | `2950-24`, `2950T-24`, `Switch-PT` |
| `"l3_switch"` | `3560-24PS` | `3650-24PS` |
| `"pc"` | `PC-PT` | — |
| `"server"` | `Server-PT` | — |
| `"laptop"` | `Laptop-PT` | `TabletPC-PT` |
| `"ap"` | `AccessPoint-PT` | — |
| `"firewall"` | `5505` | — |
| `"cloud"` | `Cloud-PT` | — |
| `"phone"` | `7960` | — |

