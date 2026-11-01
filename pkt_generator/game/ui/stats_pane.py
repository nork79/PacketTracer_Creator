"""Right-side Player Career & Statistics HUD Pane component."""

from __future__ import annotations

from collections.abc import Callable
import tkinter as tk

from pkt_generator.game.career import (
    MAX_CAREER_LEVEL,
    MILESTONE_TITLES,
    XPRewardBreakdown,
    next_milestone_for_level,
)
from pkt_generator.game.settings import GameSettings


def fmt_mmss(seconds: int) -> str:
    """Format seconds as `MM:SS`."""
    m, s = divmod(max(0, int(seconds)), 60)
    return f"{m:02d}:{s:02d}"


class PlayerStatsPane:
    """Right-side HUD displaying Career Level (1-50), XP, SLA Speed Timer, and Milestone Titles."""

    def __init__(
        self,
        parent: tk.Frame,
        settings: GameSettings,
        *,
        on_reset_career: Callable[[], None],
    ) -> None:
        stats_hdr = tk.Frame(parent, bg="#1e293b")
        stats_hdr.pack(fill="x", pady=(0, 6))

        tk.Label(
            stats_hdr,
            text="🏆 PLAYER CAREER & STATS",
            bg="#1e293b",
            fg="#38bdf8",
            font=("Segoe UI", 11, "bold"),
            anchor="w",
        ).pack(side="left")

        self.reset_career_btn = tk.Button(
            stats_hdr,
            text="⚠️ Reset Career",
            command=on_reset_career,
            bg="#dc2626",
            fg="#ffffff",
            activebackground="#b91c1c",
            activeforeground="#ffffff",
            relief="flat",
            padx=8,
            pady=2,
            font=("Segoe UI", 8, "bold"),
            cursor="hand2",
        )
        self.reset_career_btn.pack(side="right")

        # 1. Engineer Identity, Level & Rank Card
        rank_card = tk.Frame(
            parent,
            bg="#0f172a",
            padx=10,
            pady=8,
            highlightthickness=1,
            highlightbackground="#334155",
        )
        rank_card.pack(fill="x", pady=(0, 8))

        self.stat_player_lbl = tk.Label(
            rank_card,
            text=f"👤 {settings.player_name}  •  {settings.company_name}",
            bg="#0f172a",
            fg="#e2e8f0",
            font=("Segoe UI", 9, "bold"),
            anchor="w",
        )
        self.stat_player_lbl.pack(fill="x")

        self.stat_level_lbl = tk.Label(
            rank_card,
            text=f"LEVEL 1 / {MAX_CAREER_LEVEL}",
            bg="#0f172a",
            fg="#fbbf24",
            font=("Segoe UI", 16, "bold"),
            anchor="w",
        )
        self.stat_level_lbl.pack(fill="x", pady=(2, 0))

        self.stat_title_lbl = tk.Label(
            rank_card,
            text="🎖️ Rank: NOC Trainee",
            bg="#0f172a",
            fg="#38bdf8",
            font=("Segoe UI", 10, "bold"),
            anchor="w",
        )
        self.stat_title_lbl.pack(fill="x")

        self.stat_next_milestone_lbl = tk.Label(
            rank_card,
            text="Next Title (Lvl 5): Junior Helpdesk Technician",
            bg="#0f172a",
            fg="#94a3b8",
            font=("Segoe UI", 8),
            anchor="w",
        )
        self.stat_next_milestone_lbl.pack(fill="x", pady=(2, 0))

        # 2. Experience (XP) Progress Bar Card
        xp_card = tk.Frame(
            parent,
            bg="#0f172a",
            padx=10,
            pady=8,
            highlightthickness=1,
            highlightbackground="#334155",
        )
        xp_card.pack(fill="x", pady=(0, 8))

        self.stat_xp_lbl = tk.Label(
            xp_card,
            text="Level XP: 0 / 100 XP (0%)",
            bg="#0f172a",
            fg="#4ade80",
            font=("Segoe UI", 9, "bold"),
            anchor="w",
        )
        self.stat_xp_lbl.pack(fill="x", pady=(0, 4))

        self.xp_bar_canvas = tk.Canvas(
            xp_card,
            width=285,
            height=14,
            bg="#1e293b",
            highlightthickness=1,
            highlightbackground="#334155",
        )
        self.xp_bar_canvas.pack(fill="x", pady=(0, 4))

        self.stat_total_xp_lbl = tk.Label(
            xp_card,
            text="Total Career XP: 0 XP",
            bg="#0f172a",
            fg="#cbd5e1",
            font=("Consolas", 9),
            anchor="w",
        )
        self.stat_total_xp_lbl.pack(fill="x")

        # 3. Live SLA Speed Timer Card
        sla_card = tk.Frame(
            parent,
            bg="#0f172a",
            padx=10,
            pady=8,
            highlightthickness=1,
            highlightbackground="#334155",
        )
        sla_card.pack(fill="x", pady=(0, 8))

        self.stat_task_type_lbl = tk.Label(
            sla_card,
            text="ACTIVE TASK: 🔧 Fault Finding",
            bg="#0f172a",
            fg="#38bdf8",
            font=("Segoe UI", 9, "bold"),
            anchor="w",
        )
        self.stat_task_type_lbl.pack(fill="x")

        self.sla_time_lbl = tk.Label(
            sla_card,
            text="⏱️ Elapsed: 00:00  /  SLA Target: 03:00",
            bg="#0f172a",
            fg="#f8fafc",
            font=("Consolas", 9, "bold"),
            anchor="w",
        )
        self.sla_time_lbl.pack(fill="x", pady=(2, 2))

        self.sla_tier_lbl = tk.Label(
            sla_card,
            text="⚡ GOLD SLA SPEED BONUS (1.5x XP)",
            bg="#14532d",
            fg="#86efac",
            font=("Segoe UI", 8, "bold"),
            padx=6,
            pady=2,
            anchor="w",
        )
        self.sla_tier_lbl.pack(fill="x")

        # 4. Career Performance Stats Card
        metrics_card = tk.Frame(
            parent,
            bg="#0f172a",
            padx=10,
            pady=8,
            highlightthickness=1,
            highlightbackground="#334155",
        )
        metrics_card.pack(fill="x", pady=(0, 8))

        tk.Label(
            metrics_card,
            text="📊 CAREER RECORD",
            bg="#0f172a",
            fg="#38bdf8",
            font=("Segoe UI", 9, "bold"),
            anchor="w",
        ).pack(fill="x", pady=(0, 4))

        self.stat_tasks_lbl = tk.Label(
            metrics_card,
            text="Tasks Completed     : 0",
            bg="#0f172a",
            fg="#e2e8f0",
            font=("Consolas", 9),
            anchor="w",
        )
        self.stat_tasks_lbl.pack(fill="x")

        self.stat_breakdown_lbl = tk.Label(
            metrics_card,
            text="Faults / Setups     : 0 Fault  •  0 Setup",
            bg="#0f172a",
            fg="#cbd5e1",
            font=("Consolas", 9),
            anchor="w",
        )
        self.stat_breakdown_lbl.pack(fill="x")

        self.stat_streak_lbl = tk.Label(
            metrics_card,
            text="Current Win Streak  : 0 🔥 (Best: 0)",
            bg="#0f172a",
            fg="#fbbf24",
            font=("Consolas", 9),
            anchor="w",
        )
        self.stat_streak_lbl.pack(fill="x")

        self.stat_first_try_lbl = tk.Label(
            metrics_card,
            text="First-Try Solves    : 0 🎯",
            bg="#0f172a",
            fg="#4ade80",
            font=("Consolas", 9),
            anchor="w",
        )
        self.stat_first_try_lbl.pack(fill="x")

        self.stat_best_sla_lbl = tk.Label(
            metrics_card,
            text="Fastest Resolution  : --:--",
            bg="#0f172a",
            fg="#38bdf8",
            font=("Consolas", 9),
            anchor="w",
        )
        self.stat_best_sla_lbl.pack(fill="x")

        # 5. Last Ticket XP Award Summary
        reward_card = tk.Frame(
            parent,
            bg="#0f172a",
            padx=10,
            pady=6,
            highlightthickness=1,
            highlightbackground="#334155",
        )
        reward_card.pack(fill="x", pady=(0, 8))

        tk.Label(
            reward_card,
            text="✨ LAST TASK XP AWARD",
            bg="#0f172a",
            fg="#fbbf24",
            font=("Segoe UI", 8, "bold"),
            anchor="w",
        ).pack(fill="x")

        self.last_xp_summary_lbl = tk.Label(
            reward_card,
            text="Complete a task to earn Career XP & SLA Speed Bonuses!",
            bg="#0f172a",
            fg="#94a3b8",
            font=("Consolas", 8),
            justify="left",
            anchor="w",
            wraplength=285,
        )
        self.last_xp_summary_lbl.pack(fill="x", pady=(2, 0))

        # 6. Milestone Titles Roadmap (Lvl 1-50)
        milestone_card = tk.Frame(
            parent,
            bg="#0f172a",
            padx=8,
            pady=6,
            highlightthickness=1,
            highlightbackground="#334155",
        )
        milestone_card.pack(fill="both", expand=True)

        tk.Label(
            milestone_card,
            text="🎖️ MILESTONE TITLES (LVL 1–50)",
            bg="#0f172a",
            fg="#38bdf8",
            font=("Segoe UI", 8, "bold"),
            anchor="w",
        ).pack(fill="x", pady=(0, 4))

        self.milestone_list = tk.Listbox(
            milestone_card,
            bg="#0f172a",
            fg="#cbd5e1",
            selectbackground="#1e293b",
            selectforeground="#38bdf8",
            font=("Consolas", 8),
            relief="flat",
            highlightthickness=0,
            activestyle="none",
        )
        self.milestone_list.pack(fill="both", expand=True)

        self.refresh(settings)

    def refresh(
        self,
        settings: GameSettings,
        reward: XPRewardBreakdown | None = None,
    ) -> None:
        c = settings.career
        self.stat_player_lbl.configure(
            text=f"👤 {settings.player_name}  •  {settings.company_name}"
        )
        self.stat_level_lbl.configure(text=f"LEVEL {c.level} / {MAX_CAREER_LEVEL}")
        self.stat_title_lbl.configure(text=f"🎖️ {c.title}")

        nxt = next_milestone_for_level(c.level)
        if nxt is not None:
            self.stat_next_milestone_lbl.configure(
                text=f"Next Title (Lvl {nxt[0]}): {nxt[1]}"
            )
        else:
            self.stat_next_milestone_lbl.configure(
                text="🏆 Maximum Career Milestone Unlocked!"
            )

        needed = c.xp_needed
        if needed > 0:
            pct = min(100, int(round((c.xp / needed) * 100)))
            self.stat_xp_lbl.configure(
                text=f"Level XP: {c.xp:,} / {needed:,} XP ({pct}%)"
            )
            ratio = max(0.0, min(1.0, c.xp / needed))
        else:
            self.stat_xp_lbl.configure(text="Level XP: MAX LEVEL (50) REACHED")
            ratio = 1.0

        self.xp_bar_canvas.delete("all")
        bar_w = 285
        fill_w = int(round(bar_w * ratio))
        if fill_w > 0:
            self.xp_bar_canvas.create_rectangle(
                0, 0, fill_w, 16, fill="#0284c7", width=0
            )

        self.stat_total_xp_lbl.configure(text=f"Total Career XP: {c.total_xp:,} XP")
        self.stat_tasks_lbl.configure(text=f"Tasks Completed     : {c.tasks_completed}")
        self.stat_breakdown_lbl.configure(
            text=f"Faults / Setups     : {c.fault_tasks_completed} Fault  •  {c.setup_tasks_completed} Setup"
        )
        self.stat_streak_lbl.configure(
            text=f"Current Win Streak  : {c.current_streak} 🔥 (Best: {c.best_streak})"
        )
        self.stat_first_try_lbl.configure(
            text=f"First-Try Solves    : {c.first_try_solves} 🎯"
        )
        best_sla_str = (
            fmt_mmss(c.best_sla_seconds)
            if c.best_sla_seconds is not None
            else "--:--"
        )
        self.stat_best_sla_lbl.configure(text=f"Fastest Resolution  : {best_sla_str}")

        if reward is not None:
            if reward.solution_revealed:
                self.last_xp_summary_lbl.configure(
                    text="Solution Revealed -> 0 XP awarded (Streak reset).",
                    fg="#f87171",
                )
            else:
                lines = [
                    f"+{reward.total_xp_awarded} XP  ({reward.sla_tier})",
                    f"Base: {reward.base_xp} | Speed: +{reward.speed_bonus_xp} | 1st-Try: +{reward.first_try_bonus_xp}",
                    f"Streak: +{reward.streak_bonus_xp} | Hints: -{reward.hint_penalty_xp}",
                ]
                if reward.leveled_up:
                    lines.append(
                        f"🎉 LEVEL UP! Lvl {reward.old_level} -> Lvl {reward.new_level}!"
                    )
                self.last_xp_summary_lbl.configure(
                    text="\n".join(lines),
                    fg="#4ade80",
                )

        self.milestone_list.delete(0, "end")
        for req_lvl, m_title in MILESTONE_TITLES:
            unlocked = c.level >= req_lvl
            icon = "✅" if unlocked else "🔒"
            self.milestone_list.insert("end", f"{icon} Lvl {req_lvl:2d}: {m_title}")

    def update_sla_display(
        self,
        *,
        elapsed_seconds: int,
        target_sla_seconds: int,
        solution_revealed: bool,
    ) -> None:
        try:
            self.sla_time_lbl.configure(
                text=f"⏱️ Elapsed: {fmt_mmss(elapsed_seconds)}  /  SLA Target: {fmt_mmss(target_sla_seconds)}"
            )
            gold_cutoff = max(30, int(target_sla_seconds * 0.5))
            if solution_revealed:
                self.sla_tier_lbl.configure(
                    text="🔓 SOLUTION REVEALED (0 XP)",
                    bg="#7f1d1d",
                    fg="#fecaca",
                )
            elif elapsed_seconds <= gold_cutoff:
                self.sla_tier_lbl.configure(
                    text=f"⚡ GOLD SLA BONUS (1.5x XP) — Under {fmt_mmss(gold_cutoff)}",
                    bg="#14532d",
                    fg="#86efac",
                )
            elif elapsed_seconds <= target_sla_seconds:
                self.sla_tier_lbl.configure(
                    text=f"⏱️ SILVER SLA BONUS (1.2x XP) — Under {fmt_mmss(target_sla_seconds)}",
                    bg="#1e3a8a",
                    fg="#93c5fd",
                )
            else:
                self.sla_tier_lbl.configure(
                    text="🐢 STANDARD RESOLUTION (1.0x Base XP)",
                    bg="#334155",
                    fg="#cbd5e1",
                )
        except tk.TclError:
            pass

