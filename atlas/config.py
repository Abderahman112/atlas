"""Settings loaded from the environment (.env in development)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


def _list(name: str) -> list[str]:
    return [v.strip() for v in os.getenv(name, "").split(",") if v.strip()]


@dataclass(frozen=True)
class Settings:
    telegram_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    # Only this Telegram user may talk to the bot. Leave empty on first run; /start prints your id.
    owner_id: int = int(os.getenv("TELEGRAM_OWNER_ID", "0") or 0)

    model: str = os.getenv("ATLAS_MODEL", "claude-opus-5")
    orchestrator_effort: str = os.getenv("ATLAS_ORCHESTRATOR_EFFORT", "medium")
    specialist_effort: str = os.getenv("ATLAS_SPECIALIST_EFFORT", "low")

    tz: ZoneInfo = ZoneInfo(os.getenv("ATLAS_TIMEZONE", "America/Toronto"))
    db_path: Path = Path(os.getenv("ATLAS_DB", ROOT / "data" / "atlas.db"))

    # Google (Gmail + Calendar). token.json is created by `python -m atlas.setup_google`.
    google_client_secret: Path = Path(os.getenv("GOOGLE_CLIENT_SECRET", ROOT / "secrets" / "client_secret.json"))
    google_token: Path = Path(os.getenv("GOOGLE_TOKEN", ROOT / "secrets" / "token.json"))

    # Read-only ICS feeds: "label|url" pairs, comma-separated.
    # e.g. Avenue to Learn, school Outlook (published calendar), iCloud (public calendar).
    ics_feeds: list[str] = field(default_factory=lambda: _list("ICS_FEEDS"))

    coop_tracker: Path = Path(os.getenv("COOP_TRACKER", ROOT / "data" / "Co-op Tracker.xlsx"))
    timetable: Path = ROOT / "data" / "timetable.json"          # personal, git-ignored
    profile: Path = ROOT / "data" / "profile.md"               # personal, git-ignored
    challenge: Path = ROOT / "data" / "challenge.json"

    # Atlas Town web UI. Keep the host on 127.0.0.1 and reach it through Tailscale or an SSH tunnel.
    ui_host: str = os.getenv("ATLAS_UI_HOST", "127.0.0.1")
    ui_port: int = int(os.getenv("ATLAS_UI_PORT", "8787"))
    ui_token: str = os.getenv("ATLAS_UI_TOKEN", "")  # empty: one is generated and printed at startup

    quiet_start: int = int(os.getenv("QUIET_START_HOUR", "23"))
    quiet_end: int = int(os.getenv("QUIET_END_HOUR", "7"))


settings = Settings()
