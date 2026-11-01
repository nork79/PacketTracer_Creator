"""Career Mode progression engine (Levels 1-50, Milestone Titles, SLA Speed Bonus & XP)."""

from __future__ import annotations

from dataclasses import dataclass
import random
from typing import Any

MAX_CAREER_LEVEL = 50

MILESTONE_TITLES: list[tuple[int, str]] = [
    (1, "NOC Trainee"),
    (5, "Junior Helpdesk Technician"),
    (10, "NOC Tier-1 Operator"),
    (15, "Field Network Technician"),
    (20, "Associate Network Engineer (CCNA)"),
    (25, "NOC Tier-2 Escalation Engineer"),
    (30, "Network Infrastructure Specialist"),
    (35, "Senior Network Engineer"),
    (40, "Lead Campus Architect"),
    (45, "Principal Network Architect"),
    (50, "Distinguished Fellow of the NOC"),
]

ENTRY_LEVEL1_FAULTS: list[str] = [
    "device_powered_off",
    "missing_patch_cable",
    "host_nic_disabled",
    "router_port_shutdown",
    "switch_port_shutdown",
    "host_wrong_subnet_ip",
    "host_wrong_default_gateway",
    "host_dhcp_apipa",
    "host_wrong_dns",
]

SETUP_COMMISSIONING_FAULTS: list[str] = [
    "missing_patch_cable",
    "router_port_shutdown",
    "switch_port_shutdown",
    "switch_mgmt_fault",
    "host_dhcp_apipa",
    "server_ip_or_gateway_fault",
    "device_powered_off",
]

SINGLE_SWITCH_ARCHETYPES: list[str] = [
    "left_to_right_pipeline",
    "radial_star_office",
    "split_wing_east_west",
    "right_to_left_backoffice",
    "diagonal_corner_suite",
    "rooftop_diagonal_cascade",
]

MULTI_SWITCH_ARCHETYPES: list[str] = [
    "mdf_idf_two_closet",
    "multi_floor_riser",
    "three_switch_wings",
    "server_cage_and_user_pod",
    "linear_warehouse_bays",
    "u_shaped_courtyard",
]


def title_for_level(level: int) -> str:
    """Return the highest milestone title unlocked at `level`."""
    clamped = max(1, min(MAX_CAREER_LEVEL, level))
    current_title = MILESTONE_TITLES[0][1]
    for req_lvl, title in MILESTONE_TITLES:
        if clamped >= req_lvl:
            current_title = title
        else:
            break
    return current_title


def next_milestone_for_level(level: int) -> tuple[int, str] | None:
    """Return `(next_level, next_title)` for the next milestone, or `None` if at max milestone."""
    for req_lvl, title in MILESTONE_TITLES:
        if req_lvl > level:
            return req_lvl, title
    return None


def xp_for_next_level(level: int) -> int:
    """Return the XP required to advance from `level` to `level + 1`."""
    if level >= MAX_CAREER_LEVEL:
        return 0
    return int(round(100 * (max(1, level) ** 1.32)))


@dataclass
class CareerProfile:
    """Persistent player career progression state."""

    level: int = 1
    xp: int = 0
    total_xp: int = 0
    tasks_completed: int = 0
    fault_tasks_completed: int = 0
    setup_tasks_completed: int = 0
    current_streak: int = 0
    best_streak: int = 0
    first_try_solves: int = 0
    best_sla_seconds: int | None = None
    hints_used_total: int = 0
    solutions_revealed_total: int = 0

    @property
    def title(self) -> str:
        return title_for_level(self.level)

    @property
    def xp_needed(self) -> int:
        return xp_for_next_level(self.level)

    def to_dict(self) -> dict[str, Any]:
        return {
            "level": self.level,
            "xp": self.xp,
            "total_xp": self.total_xp,
            "tasks_completed": self.tasks_completed,
            "fault_tasks_completed": self.fault_tasks_completed,
            "setup_tasks_completed": self.setup_tasks_completed,
            "current_streak": self.current_streak,
            "best_streak": self.best_streak,
            "first_try_solves": self.first_try_solves,
            "best_sla_seconds": self.best_sla_seconds,
            "hints_used_total": self.hints_used_total,
            "solutions_revealed_total": self.solutions_revealed_total,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> CareerProfile:
        if not isinstance(raw, dict):
            return cls()
        lvl = max(1, min(MAX_CAREER_LEVEL, int(raw.get("level", 1))))
        best_sla = raw.get("best_sla_seconds")
        return cls(
            level=lvl,
            xp=max(0, int(raw.get("xp", 0))),
            total_xp=max(0, int(raw.get("total_xp", 0))),
            tasks_completed=max(0, int(raw.get("tasks_completed", 0))),
            fault_tasks_completed=max(0, int(raw.get("fault_tasks_completed", 0))),
            setup_tasks_completed=max(0, int(raw.get("setup_tasks_completed", 0))),
            current_streak=max(0, int(raw.get("current_streak", 0))),
            best_streak=max(0, int(raw.get("best_streak", 0))),
            first_try_solves=max(0, int(raw.get("first_try_solves", 0))),
            best_sla_seconds=int(best_sla) if isinstance(best_sla, (int, float)) else None,
            hints_used_total=max(0, int(raw.get("hints_used_total", 0))),
            solutions_revealed_total=max(0, int(raw.get("solutions_revealed_total", 0))),
        )


@dataclass
class CareerTaskSpec:
    """Parameters rolled by the Career Director for a new task."""

    task_kind: str  # "fault" or "setup"
    num_faults: int
    allowed_prefixes: list[int]
    allowed_archetypes: list[str]
    allowed_faults: list[str] | None
    target_sla_seconds: int
    tier_label: str


@dataclass
class XPRewardBreakdown:
    """Detailed XP breakdown returned when a player completes a task."""

    task_kind: str
    base_xp: int
    elapsed_seconds: int
    target_sla_seconds: int
    sla_tier: str
    speed_multiplier: float
    speed_bonus_xp: int
    first_try_bonus_xp: int
    streak_bonus_xp: int
    hint_penalty_xp: int
    solution_revealed: bool
    total_xp_awarded: int
    old_level: int
    new_level: int
    leveled_up: bool
    old_title: str
    new_title: str
    unlocked_new_title: bool


def roll_career_task(level: int, rng: random.Random | None = None) -> CareerTaskSpec:
    """Roll task type (Fault Finding vs. Network Setup) and difficulty scaled to `level` (1..50)."""
    r = rng if rng is not None else random.Random()
    lvl = max(1, min(MAX_CAREER_LEVEL, level))

    if lvl <= 4:
        setup_prob = 0.15
        num_faults = 1
        prefixes = [24]
        archetypes = list(SINGLE_SWITCH_ARCHETYPES)
        fault_pool: list[str] | None = list(ENTRY_LEVEL1_FAULTS)
        tier_label = "Tier 1 Trainee (Single-Switch /24 LAN, 1 Task Item)"
    elif lvl <= 9:
        setup_prob = 0.20
        num_faults = 1
        prefixes = [24, 25]
        archetypes = SINGLE_SWITCH_ARCHETYPES + ["mdf_idf_two_closet", "linear_warehouse_bays"]
        fault_pool = None  # All 16 Level 1 faults unlocked
        tier_label = "Tier 1 Junior Tech (1-2 Switches, /24-/25 CIDR, 1 Fault)"
    elif lvl <= 14:
        setup_prob = 0.20
        num_faults = 2 if r.random() < 0.65 else 1
        prefixes = [24, 25, 26]
        archetypes = SINGLE_SWITCH_ARCHETYPES + MULTI_SWITCH_ARCHETYPES[:4]
        fault_pool = None
        tier_label = f"Tier 1 Operator (Multi-Closet, /24-/26 CIDR, {num_faults} Faults)"
    elif lvl <= 19:
        setup_prob = 0.22
        num_faults = 2
        prefixes = [24, 25, 26, 27]
        archetypes = SINGLE_SWITCH_ARCHETYPES + MULTI_SWITCH_ARCHETYPES
        fault_pool = None
        tier_label = "Field Engineer (All Floorplans, /24-/27 CIDR, 2 Faults)"
    elif lvl <= 29:
        setup_prob = 0.25
        num_faults = 3 if r.random() < 0.6 else 2
        prefixes = [24, 25, 26, 27]
        archetypes = list(MULTI_SWITCH_ARCHETYPES) + SINGLE_SWITCH_ARCHETYPES[:2]
        fault_pool = None
        tier_label = f"CCNA Escalation Tier ({num_faults} Compound Faults / Setup)"
    elif lvl <= 39:
        setup_prob = 0.25
        num_faults = 3
        prefixes = [25, 26, 27]
        archetypes = list(MULTI_SWITCH_ARCHETYPES)
        fault_pool = None
        tier_label = "Senior NOC Tier (Multi-Switch /25-/27 Subnets, 3 Compound Items)"
    else:
        setup_prob = 0.30
        num_faults = 4 if r.random() < 0.55 else 3
        prefixes = [25, 26, 27]
        archetypes = list(MULTI_SWITCH_ARCHETYPES)
        fault_pool = None
        tier_label = f"Principal Architect Tier (Multi-Switch CIDR, {num_faults} Compound Items)"

    task_kind = "setup" if r.random() < setup_prob else "fault"
    if task_kind == "setup":
        fault_pool = list(SETUP_COMMISSIONING_FAULTS)

    # Target SLA window scales with fault count (3 min base + 90s per extra item)
    target_sla_seconds = 180 + (num_faults - 1) * 90

    return CareerTaskSpec(
        task_kind=task_kind,
        num_faults=num_faults,
        allowed_prefixes=prefixes,
        allowed_archetypes=archetypes,
        allowed_faults=fault_pool,
        target_sla_seconds=target_sla_seconds,
        tier_label=tier_label,
    )


def award_ticket_xp(
    profile: CareerProfile,
    *,
    task_kind: str,
    num_faults: int,
    num_switches: int,
    prefix_len: int,
    elapsed_seconds: int,
    target_sla_seconds: int,
    hints_used: int,
    failed_attempts: int,
    solution_revealed: bool,
) -> XPRewardBreakdown:
    """Calculate XP earned for a solved ticket and update `profile` in-place."""
    old_level = profile.level
    old_title = profile.title

    if task_kind == "setup":
        base_xp = 140 + 70 * max(1, num_faults) + 25 * max(0, num_switches - 1)
    else:
        base_xp = 100 * max(1, num_faults) + 25 * max(0, num_switches - 1)
    if prefix_len > 24:
        base_xp += 25

    elapsed = max(1, elapsed_seconds)
    gold_cutoff = max(30, int(target_sla_seconds * 0.5))
    if elapsed <= gold_cutoff:
        sla_tier = "⚡ GOLD SLA (1.5x)"
        speed_mult = 1.5
    elif elapsed <= target_sla_seconds:
        sla_tier = "⏱️ SILVER SLA (1.2x)"
        speed_mult = 1.2
    else:
        sla_tier = "🐢 STANDARD (1.0x)"
        speed_mult = 1.0

    if solution_revealed:
        profile.current_streak = 0
        profile.solutions_revealed_total += 1
        return XPRewardBreakdown(
            task_kind=task_kind,
            base_xp=base_xp,
            elapsed_seconds=elapsed,
            target_sla_seconds=target_sla_seconds,
            sla_tier="🔓 SOLUTION REVEALED (0 XP)",
            speed_multiplier=0.0,
            speed_bonus_xp=0,
            first_try_bonus_xp=0,
            streak_bonus_xp=0,
            hint_penalty_xp=0,
            solution_revealed=True,
            total_xp_awarded=0,
            old_level=old_level,
            new_level=profile.level,
            leveled_up=False,
            old_title=old_title,
            new_title=profile.title,
            unlocked_new_title=False,
        )

    speed_bonus_xp = int(round(base_xp * (speed_mult - 1.0)))
    first_try_bonus_xp = int(round(base_xp * 0.15)) if failed_attempts == 0 else 0
    streak_mult = min(0.25, profile.current_streak * 0.05)
    streak_bonus_xp = int(round(base_xp * streak_mult))
    hint_penalty_xp = int(round(base_xp * min(0.60, hints_used * 0.15)))

    total_xp = max(
        25,
        base_xp + speed_bonus_xp + first_try_bonus_xp + streak_bonus_xp - hint_penalty_xp,
    )

    # Update profile counters
    profile.tasks_completed += 1
    if task_kind == "setup":
        profile.setup_tasks_completed += 1
    else:
        profile.fault_tasks_completed += 1

    profile.current_streak += 1
    if profile.current_streak > profile.best_streak:
        profile.best_streak = profile.current_streak

    if failed_attempts == 0:
        profile.first_try_solves += 1

    if profile.best_sla_seconds is None or elapsed < profile.best_sla_seconds:
        profile.best_sla_seconds = elapsed

    profile.hints_used_total += hints_used
    profile.total_xp += total_xp
    profile.xp += total_xp

    # Process level ups (up to Level 50)
    while profile.level < MAX_CAREER_LEVEL:
        needed = xp_for_next_level(profile.level)
        if profile.xp >= needed:
            profile.xp -= needed
            profile.level += 1
        else:
            break

    if profile.level >= MAX_CAREER_LEVEL:
        profile.level = MAX_CAREER_LEVEL

    new_level = profile.level
    new_title = profile.title

    return XPRewardBreakdown(
        task_kind=task_kind,
        base_xp=base_xp,
        elapsed_seconds=elapsed,
        target_sla_seconds=target_sla_seconds,
        sla_tier=sla_tier,
        speed_multiplier=speed_mult,
        speed_bonus_xp=speed_bonus_xp,
        first_try_bonus_xp=first_try_bonus_xp,
        streak_bonus_xp=streak_bonus_xp,
        hint_penalty_xp=hint_penalty_xp,
        solution_revealed=False,
        total_xp_awarded=total_xp,
        old_level=old_level,
        new_level=new_level,
        leveled_up=(new_level > old_level),
        old_title=old_title,
        new_title=new_title,
        unlocked_new_title=(new_title != old_title),
    )

