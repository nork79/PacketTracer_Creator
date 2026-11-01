"""Scrollable, zoomable, and pannable Visual Topology Diagram Canvas component."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from pkt_generator.game.models import ChallengeTicket


class TopologyDiagramView:
    """Encapsulates the Visual Topology Diagram tab with zoom and pan controls."""

    def __init__(self, parent: tk.Widget) -> None:
        self.zoom: float = 1.0
        self.current_ticket: ChallengeTicket | None = None

        canvas_toolbar = tk.Frame(parent, bg="#1e293b", padx=8, pady=4)
        canvas_toolbar.pack(fill="x", padx=4, pady=(4, 0))

        tk.Button(
            canvas_toolbar,
            text="➕ Zoom In",
            command=lambda: self.zoom_by(1.15),
            bg="#334155",
            fg="#f8fafc",
            activebackground="#475569",
            activeforeground="#ffffff",
            relief="flat",
            padx=8,
            pady=2,
            font=("Segoe UI", 8, "bold"),
            cursor="hand2",
        ).pack(side="left", padx=(0, 4))

        tk.Button(
            canvas_toolbar,
            text="➖ Zoom Out",
            command=lambda: self.zoom_by(1 / 1.15),
            bg="#334155",
            fg="#f8fafc",
            activebackground="#475569",
            activeforeground="#ffffff",
            relief="flat",
            padx=8,
            pady=2,
            font=("Segoe UI", 8, "bold"),
            cursor="hand2",
        ).pack(side="left", padx=(0, 4))

        tk.Button(
            canvas_toolbar,
            text="🔄 Reset 100%",
            command=self.reset_zoom,
            bg="#334155",
            fg="#f8fafc",
            activebackground="#475569",
            activeforeground="#ffffff",
            relief="flat",
            padx=8,
            pady=2,
            font=("Segoe UI", 8),
            cursor="hand2",
        ).pack(side="left", padx=(0, 10))

        self.zoom_status_lbl = tk.Label(
            canvas_toolbar,
            text="Zoom: 100%  |  🖱️ Mouse Wheel: Zoom In/Out  •  Left-Click Drag: Pan",
            bg="#1e293b",
            fg="#94a3b8",
            font=("Segoe UI", 8),
        )
        self.zoom_status_lbl.pack(side="left")

        canvas_grid = tk.Frame(parent, bg="#0f172a")
        canvas_grid.pack(fill="both", expand=True, padx=4, pady=4)
        canvas_grid.rowconfigure(0, weight=1)
        canvas_grid.columnconfigure(0, weight=1)

        self.vscroll = ttk.Scrollbar(canvas_grid, orient="vertical")
        self.hscroll = ttk.Scrollbar(canvas_grid, orient="horizontal")

        self.canvas = tk.Canvas(
            canvas_grid,
            bg="#0f172a",
            highlightthickness=0,
            yscrollcommand=self.vscroll.set,
            xscrollcommand=self.hscroll.set,
            scrollregion=(0, 0, 900, 460),
        )
        self.vscroll.configure(command=self.canvas.yview)
        self.hscroll.configure(command=self.canvas.xview)

        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.vscroll.grid(row=0, column=1, sticky="ns")
        self.hscroll.grid(row=1, column=0, sticky="ew")

        self.canvas.bind("<MouseWheel>", self._on_mousewheel)
        self.canvas.bind("<Button-4>", lambda e: self.zoom_by(1.15, e))
        self.canvas.bind("<Button-5>", lambda e: self.zoom_by(1 / 1.15, e))
        self.canvas.bind("<ButtonPress-1>", self._on_pan_start)
        self.canvas.bind("<B1-Motion>", self._on_pan_move)

    def _on_pan_start(self, event: tk.Event) -> None:  # type: ignore[type-arg]
        self.canvas.scan_mark(event.x, event.y)

    def _on_pan_move(self, event: tk.Event) -> None:  # type: ignore[type-arg]
        self.canvas.scan_dragto(event.x, event.y, gain=1)

    def _on_mousewheel(self, event: tk.Event) -> None:  # type: ignore[type-arg]
        factor = 1.15 if event.delta > 0 else (1 / 1.15)
        self.zoom_by(factor, event)

    def zoom_by(self, factor: float, _event: object = None) -> None:
        new_zoom = max(0.45, min(2.6, self.zoom * factor))
        if abs(new_zoom - self.zoom) < 1e-3:
            return
        self.zoom = new_zoom
        self.zoom_status_lbl.configure(
            text=f"Zoom: {int(round(self.zoom * 100))}%  |  🖱️ Mouse Wheel: Zoom In/Out  •  Left-Click Drag: Pan"
        )
        if self.current_ticket is not None:
            self.draw(self.current_ticket)

    def reset_zoom(self) -> None:
        self.zoom = 1.0
        self.zoom_status_lbl.configure(
            text="Zoom: 100%  |  🖱️ Mouse Wheel: Zoom In/Out  •  Left-Click Drag: Pan"
        )
        if self.current_ticket is not None:
            self.draw(self.current_ticket)
        self.canvas.xview_moveto(0.0)
        self.canvas.yview_moveto(0.0)

    def draw(self, ticket: ChallengeTicket) -> None:
        self.current_ticket = ticket
        c = self.canvas
        c.delete("all")
        z = self.zoom

        node_pos = {n["name"]: (n["x"] * z, n["y"] * z) for n in ticket.canvas_nodes}
        title_fs = max(7, min(18, int(round(9 * z))))
        sub_fs = max(6, min(15, int(round(8 * z))))
        line_w = max(1, int(round(2 * z)))

        for da, db, pa, pb in ticket.canvas_edges:
            if da in node_pos and db in node_pos:
                x1, y1 = node_pos[da]
                x2, y2 = node_pos[db]
                c.create_line(x1, y1, x2, y2, fill="#475569", width=line_w)
                mx, my = (x1 + x2) / 2, (y1 + y2) / 2
                c.create_text(
                    mx,
                    my - 8 * z,
                    text=f"{pa} ↔ {pb}",
                    fill="#94a3b8",
                    font=("Consolas", sub_fs),
                )

        role_colors = {
            "router": ("#0284c7", "#e0f2fe"),
            "switch": ("#4f46e5", "#e0e7ff"),
            "pc": ("#0f766e", "#ccfbf1"),
            "server": ("#b45309", "#fef3c7"),
        }
        hw = 68 * z
        hh = 26 * z
        for n in ticket.canvas_nodes:
            x, y = n["x"] * z, n["y"] * z
            bg_col, fg_col = role_colors.get(n["role"], ("#334155", "#f8fafc"))
            c.create_rectangle(
                x - hw,
                y - hh,
                x + hw,
                y + hh,
                fill=bg_col,
                outline="#94a3b8",
                width=max(1, int(round(z))),
            )
            c.create_text(
                x,
                y - 10 * z,
                text=n["name"],
                fill="#ffffff",
                font=("Segoe UI", title_fs, "bold"),
            )
            c.create_text(
                x,
                y + 9 * z,
                text=n["sub"],
                fill=fg_col,
                font=("Consolas", sub_fs),
                justify="center",
            )

        bbox = c.bbox("all")
        if bbox:
            pad = int(80 * z)
            c.configure(
                scrollregion=(
                    bbox[0] - pad,
                    bbox[1] - pad,
                    bbox[2] + pad,
                    bbox[3] + pad,
                )
            )

