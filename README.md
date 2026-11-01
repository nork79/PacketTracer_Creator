# PacketTracer_Creator & NetDoctor NOC (`pkt_generator` v1.2)

Generate valid, pre-configured Cisco Packet Tracer (`.pkt`) network files offline from Python or JSON—and practice **CCNA (200-301 v2.0)** troubleshooting and network engineering in the **NetDoctor NOC** desktop game (`tkinter`).

---

## 🚀 What's New in Version 1.2
- **✅ Level 2 Troubleshooting — Fully Implemented (12 CCNA v2.0 Faults)**:
  - Multi-switch (MDF/IDF, 2–3 switches) dual-VLAN campus topologies routed via **Router-on-a-Stick (802.1Q)**, with 1–4 simultaneous faults:
    - **VLANs:** access port in wrong VLAN, VLAN missing from switch database, Voice/Data VLAN misconfiguration.
    - **802.1Q Trunks & DTP:** uplink left in access mode, allowed-VLAN list pruning, native VLAN mismatch, DTP `dynamic auto` / `dynamic auto` failure.
    - **Router-on-a-Stick:** wrong `encapsulation dot1Q` tag, wrong subinterface IP, parent interface shutdown, switch uplink not trunking.
    - **EtherChannel:** LACP `active` vs PAgP `desirable` mismatch on `Port-channel1`.
- **✅ Mode 2: Build Network from Scratch — Fully Implemented (Level 1 & Level 2)**:
  - **Level 1 — Branch LAN Bring-Up:** cabling → router gateway → switch `Vlan1` SVI + default-gateway → endpoint addressing.
  - **Level 2 — Dual-Subnet VLANs & 802.1Q RoaS:** cabling → RoaS subinterfaces → MDF/IDF switch VLANs, access ports & trunks → multi-VLAN host addressing.
  - Choose **📘 Guided** (exact IPs) or **🧮 Subnetting Challenge** (rules only), and **🔌 Uncabled** or **🔗 Pre-Cabled** hardware. Each stage is verified independently.
- **🖥️ Split-Screen NOC Workspace**:
  - The **Intended Network Specification** (Addressing, Cabling & Ports, Visual Topology) now fills the **right-hand side** of the screen, with ticket details, symptoms and actions in a narrower left column. Drag the divider to resize; tables have scrollbars.
- **🧹 Removed / Replaced**:
  - **Removed:** Career Mode and the right-side Player Stats / XP HUD (including the Reset Career button) are no longer part of the interface.
  - **Removed:** Unimplemented Mode 2 Levels 3–5 placeholders from the difficulty dropdown.
  - **Replaced:** "Backend implementation pending" placeholders for Level 2 and Mode 2 are replaced by working generators and verifiers.
  - **Changed:** Fault Count now supports 1–4 simultaneous faults (was 1–2).
- **🏢 Customizable Player, Company & Department Settings (`game_settings.json`)**:
  - Configure `player_name`, `company_name`, and internal `departments` (with prefix codes like `FIN-R1`, `ENG-SW1`, `SEC-SRV1`) in [`game_settings.json`](game_settings.json); changes reload live on every new task.
- **🗺️ 12 Real-World Physical Floorplan Archetypes (1, 2 & 3 Switches)**:
  - Includes `left_to_right_pipeline`, `mdf_idf_two_closet`, `radial_star_office`, `split_wing_east_west`, `right_to_left_backoffice`, `diagonal_corner_suite`, `multi_floor_riser`, `three_switch_wings`, `server_cage_and_user_pod`, `linear_warehouse_bays`, `u_shaped_courtyard`, and `rooftop_diagonal_cascade`.
- **🔍 Interactive Scrollable & Zoomable Topology Diagram + Popup Diagnostic Console**:
  - Mouse-wheel zoom (`Zoom In` / `Zoom Out` / `Reset 100%`), left-click drag panning, and scrollbars on the Visual Topology Diagram.
  - Popup window (`💡 Diagnostic Console & Solution Reveal`) with progressive hints and full solution reveal.
- **🧱 Modular Package Architecture**:
  - `pkt_generator/game/`: `generator.py` (Level 1), `generator_level2.py` (Level 2 + Mode 2 builds), `faults_level1.py`, `faults_level2.py`, `layouts.py`, `settings.py`, `verifier.py`, and `ui/` (`constants.py`, `topology_canvas.py`, `diagnostic_popup.py`).
  - `SimpleNetwork` now supports voice VLANs, native VLANs, explicit switchport modes (incl. DTP), EtherChannel `channel-group`, custom `dot1Q` tags and shutdown subinterfaces.

---

## 🎮 NetDoctor NOC — Educational Troubleshooting & Network Engineering Game

Launch the desktop NOC console (100% Python standard library + `tkinter`):

```powershell
python play_game.py
```

### Game Modes
1. **🔧 Mode 1: Break/Fix Troubleshooting**:
   - **Level 1 — Tier 1 Helpdesk (Single LAN):** filter for any of the **16 Level 1 CCNA v2.0 faults** (or random combinations) across Layer 1 (physical power, missing patch cables, disabled NICs, speed/duplex mismatches, wrong router uplink port), Layer 2 (administratively down ports, broken switch `Vlan1` management SVI), Layer 3 (wrong subnet IP, wrong default gateway, restrictive subnet mask, duplicate IP conflicts, router/server IP typos), and Network Services (DHCP/APIPA `169.254.x.x` fallback, wrong DNS server).
   - **Level 2 — Switching, VLANs, 802.1Q Trunks & RoaS:** filter for any of the **12 Level 2 CCNA v2.0 faults** (VLANs, trunks, DTP, Router-on-a-Stick, EtherChannel) on multi-switch dual-VLAN topologies.
2. **🏗️ Mode 2: Build Network from Scratch**:
   - **Level 1 — Branch LAN Bring-Up** and **Level 2 — Dual-Subnet VLANs & 802.1Q RoaS** greenfield work orders, with configurable Addressing Help and Hardware Cabling states and staged commissioning checks.

### Workflow
1. Click **⚡ Generate New .pkt Challenge** and open the file with **🚀 Open .pkt in Packet Tracer**.
2. Compare Packet Tracer against the **Intended Network Specification** on the right.
3. Fix or build the network, save in Packet Tracer (`Ctrl+S`), then click **🔄 Quick-Check Current .pkt** or **📤 Upload & Inspect .pkt File...**.
4. Stuck? Open **💡 Diagnostic Console & Solution Reveal** for progressive hints.

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
