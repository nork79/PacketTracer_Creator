"""Physical floorplan layout archetypes and Packet Tracer-to-Canvas coordinate mapping."""

from __future__ import annotations

TOPOLOGY_ARCHETYPES: list[str] = [
    "left_to_right_pipeline",
    "mdf_idf_two_closet",
    "radial_star_office",
    "split_wing_east_west",
    "right_to_left_backoffice",
    "diagonal_corner_suite",
    "multi_floor_riser",
    "three_switch_wings",
    "server_cage_and_user_pod",
    "linear_warehouse_bays",
    "u_shaped_courtyard",
    "rooftop_diagonal_cascade",
]


def pt_to_canvas(pt_x: int, pt_y: int) -> tuple[int, int]:
    """Map Packet Tracer logical workspace coordinates (x in 180..830, y in 130..530)
    proportionally onto the NetDoctor Tkinter Topology Canvas (760 x 350).
    """
    cx = int(85 + (pt_x - 180) * 0.90)
    cy = int(42 + (pt_y - 130) * 0.67)
    return max(75, min(685, cx)), max(34, min(318, cy))


def build_layout_positions(
    archetype: str, num_clients: int
) -> tuple[str, int, list[int], dict[str, tuple[int, int]]]:
    """Return `(archetype_label, num_switches, client_switch_indices, positions_map)`
    in Packet Tracer logical workspace coordinates.
    """
    pos: dict[str, tuple[int, int]] = {}

    if archetype == "left_to_right_pipeline":
        label = "Left-to-Right Enterprise Demarc Flow"
        num_sw = 1
        client_sw = [1] * num_clients
        pos["rtr"] = (190, 330)
        pos["sw1"] = (430, 330)
        pos["srv"] = (430, 140)
        y_slots = (
            [220, 440]
            if num_clients == 2
            else [160, 330, 500]
            if num_clients == 3
            else [135, 265, 395, 525]
        )
        for i in range(num_clients):
            pos[f"c{i}"] = (740 + (45 if i % 2 == 1 else 0), y_slots[i])

    elif archetype == "mdf_idf_two_closet":
        label = "Two-Closet MDF + IDF Floorplan (2 Switches)"
        num_sw = 2
        client_sw = [1] + [2] * (num_clients - 1)
        pos["rtr"] = (200, 150)
        pos["sw1"] = (350, 310)
        pos["srv"] = (190, 480)
        pos["c0"] = (370, 510)
        pos["sw2"] = (590, 310)
        idf_slots = [(620, 140), (810, 260), (790, 480)]
        for i in range(1, num_clients):
            pos[f"c{i}"] = idf_slots[i - 1]

    elif archetype == "radial_star_office":
        label = "Central Wiring Closet Radial Star"
        num_sw = 1
        client_sw = [1] * num_clients
        pos["sw1"] = (500, 320)
        pos["rtr"] = (240, 150)
        pos["srv"] = (760, 150)
        radial_slots = [
            (200, 350),
            (340, 515),
            (660, 515),
            (800, 350),
        ]
        for i in range(num_clients):
            pos[f"c{i}"] = radial_slots[i]

    elif archetype == "split_wing_east_west":
        label = "Bottom Fiber Demarc + East/West Split Wings"
        num_sw = 1
        client_sw = [1] * num_clients
        pos["rtr"] = (500, 520)
        pos["sw1"] = (500, 330)
        pos["srv"] = (500, 140)
        wing_slots = [
            (210, 220),
            (790, 220),
            (210, 430),
            (790, 430),
        ]
        for i in range(num_clients):
            pos[f"c{i}"] = wing_slots[i]

    elif archetype == "right_to_left_backoffice":
        label = "Right-to-Left Back-Office Rack & Desk Pods"
        num_sw = 1
        client_sw = [1] * num_clients
        pos["rtr"] = (800, 175)
        pos["srv"] = (800, 485)
        pos["sw1"] = (580, 330)
        pod_slots = [
            (350, 155),
            (195, 255),
            (195, 415),
            (350, 515),
        ]
        for i in range(num_clients):
            pos[f"c{i}"] = pod_slots[i]

    elif archetype == "diagonal_corner_suite":
        label = "L-Shaped Corner Suite Floorplan"
        num_sw = 1
        client_sw = [1] * num_clients
        pos["rtr"] = (220, 510)
        pos["sw1"] = (430, 330)
        pos["srv"] = (205, 190)
        l_slots = [
            (460, 140),
            (710, 165),
            (780, 340),
            (700, 510),
        ]
        for i in range(num_clients):
            pos[f"c{i}"] = l_slots[i]

    elif archetype == "multi_floor_riser":
        label = "Multi-Story Building Vertical Riser (Ground MDF + 2nd Floor IDF)"
        num_sw = 2
        client_sw = [1] + [2] * (num_clients - 1)
        pos["rtr"] = (200, 495)
        pos["sw1"] = (470, 475)
        pos["srv"] = (760, 500)
        pos["c0"] = (240, 340)
        pos["sw2"] = (470, 235)
        upper_slots = [(210, 145), (700, 145), (790, 285)]
        for i in range(1, num_clients):
            pos[f"c{i}"] = upper_slots[i - 1]

    elif archetype == "three_switch_wings":
        label = "Two-Tier Collapsed Core + West/East IDF Wings (3 Switches)"
        num_sw = 3
        client_sw = [2 if i % 2 == 0 else 3 for i in range(num_clients)]
        pos["rtr"] = (355, 140)
        pos["srv"] = (645, 140)
        pos["sw1"] = (500, 255)
        pos["sw2"] = (265, 355)
        pos["sw3"] = (735, 355)
        wing_slots_3sw = [
            (190, 515),
            (810, 515),
            (370, 515),
            (630, 515),
        ]
        for i in range(num_clients):
            pos[f"c{i}"] = wing_slots_3sw[i]

    elif archetype == "server_cage_and_user_pod":
        label = "Dedicated Server Cage + Open-Office User Pod (2 Switches)"
        num_sw = 2
        client_sw = [2] * num_clients
        pos["rtr"] = (195, 145)
        pos["srv"] = (435, 145)
        pos["sw1"] = (315, 265)
        pos["sw2"] = (565, 355)
        cubicle_slots = [
            (790, 195),
            (795, 355),
            (755, 515),
            (485, 515),
        ]
        for i in range(num_clients):
            pos[f"c{i}"] = cubicle_slots[i]

    elif archetype == "linear_warehouse_bays":
        label = "Linear Warehouse Assembly-Line Bays (2 Switches)"
        num_sw = 2
        client_sw = [1] + [2] * (num_clients - 1)
        pos["rtr"] = (190, 325)
        pos["sw1"] = (425, 325)
        pos["sw2"] = (675, 325)
        pos["srv"] = (355, 145)
        pos["c0"] = (425, 510)
        bay_b_slots = [
            (615, 145),
            (675, 510),
            (810, 220),
        ]
        for i in range(1, num_clients):
            pos[f"c{i}"] = bay_b_slots[i - 1]

    elif archetype == "u_shaped_courtyard":
        label = "U-Shaped Courtyard Perimeter (2 Switches)"
        num_sw = 2
        client_sw = [1] + [2] * (num_clients - 1)
        pos["rtr"] = (205, 150)
        pos["srv"] = (205, 320)
        pos["sw1"] = (285, 485)
        pos["c0"] = (485, 520)
        pos["sw2"] = (695, 485)
        east_u_slots = [
            (795, 335),
            (795, 160),
            (565, 145),
        ]
        for i in range(1, num_clients):
            pos[f"c{i}"] = east_u_slots[i - 1]

    else:  # rooftop_diagonal_cascade
        label = "Rooftop WISP Demarc Diagonal Cascade"
        num_sw = 1
        client_sw = [1] * num_clients
        pos["rtr"] = (790, 145)
        pos["sw1"] = (540, 280)
        pos["srv"] = (780, 385)
        diag_slots = [
            (300, 160),
            (205, 330),
            (285, 505),
            (540, 505),
        ]
        for i in range(num_clients):
            pos[f"c{i}"] = diag_slots[i]

    return label, num_sw, client_sw, pos

