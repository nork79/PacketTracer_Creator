"""Player, Company, and Department settings loader for NetDoctor NOC."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
import re
from typing import Any

from pkt_generator.game.career import CareerProfile

DEFAULT_SETTINGS_PATH = Path(__file__).resolve().parent.parent.parent / "game_settings.json"

DEFAULT_DEPARTMENTS: list[tuple[str, str]] = [
    ("FIN", "Finance & Accounting"),
    ("ENG", "Engineering & R&D"),
    ("HR", "Human Resources"),
    ("OPS", "Operations & Logistics"),
    ("SLS", "Sales & Marketing"),
    ("SEC", "Security Operations (SOC)"),
    ("IT", "Corporate IT Services"),
    ("EXEC", "Executive Suite"),
]


def _derive_code(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]", "", name.upper())
    return (cleaned[:4] or "DEPT")


@dataclass
class GameSettings:
    """Configurable player identity, company name, internal departments, and career stats."""

    player_name: str = "Nork"
    company_name: str = "Apex Global Systems"
    departments: list[tuple[str, str]] = field(
        default_factory=lambda: list(DEFAULT_DEPARTMENTS)
    )
    career: CareerProfile = field(default_factory=CareerProfile)
    settings_path: Path = DEFAULT_SETTINGS_PATH

    @classmethod
    def load(cls, path: str | Path | None = None) -> GameSettings:
        """Load settings from `game_settings.json` (creating it with defaults if missing)."""
        target = Path(path) if path is not None else DEFAULT_SETTINGS_PATH
        if not target.is_file():
            default_obj = cls(settings_path=target)
            try:
                default_obj.save(target)
            except OSError:
                pass
            return default_obj

        try:
            raw: dict[str, Any] = json.loads(target.read_text(encoding="utf-8"))
        except Exception:
            return cls(settings_path=target)

        player_name = str(raw.get("player_name") or "Nork").strip() or "Nork"
        company_name = (
            str(raw.get("company_name") or "Apex Global Systems").strip()
            or "Apex Global Systems"
        )

        parsed_depts: list[tuple[str, str]] = []
        raw_depts = raw.get("departments")
        if isinstance(raw_depts, list):
            for entry in raw_depts:
                if isinstance(entry, dict):
                    d_name = str(entry.get("name") or "").strip()
                    d_code = str(entry.get("code") or "").strip().upper()
                    if d_name:
                        parsed_depts.append((d_code or _derive_code(d_name), d_name))
                elif isinstance(entry, str) and entry.strip():
                    d_name = entry.strip()
                    parsed_depts.append((_derive_code(d_name), d_name))

        if not parsed_depts:
            parsed_depts = list(DEFAULT_DEPARTMENTS)

        career = CareerProfile.from_dict(raw.get("career"))

        return cls(
            player_name=player_name,
            company_name=company_name,
            departments=parsed_depts,
            career=career,
            settings_path=target,
        )

    def save(self, path: str | Path | None = None) -> Path:
        """Write current settings to `game_settings.json`."""
        target = Path(path) if path is not None else self.settings_path
        payload = {
            "player_name": self.player_name,
            "company_name": self.company_name,
            "departments": [
                {"code": code, "name": name} for code, name in self.departments
            ],
            "career": self.career.to_dict(),
        }
        target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        return target

