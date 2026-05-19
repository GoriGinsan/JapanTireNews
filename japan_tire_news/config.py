from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class AppConfig:
    teams_webhook_url: str
    timezone: str
    database_path: Path
    rejected_log_path: Path
    http_timeout_seconds: int
    max_item_age_days: int
    sources_path: Path


def load_config() -> AppConfig:
    load_dotenv(PROJECT_ROOT / ".env")
    database_path = Path(os.getenv("DATABASE_PATH", "data/news.sqlite3"))
    rejected_log_path = Path(os.getenv("REJECTED_LOG_PATH", "logs/rejected_news.csv"))
    sources_path = Path(os.getenv("SOURCES_PATH", "config/sources.json"))

    return AppConfig(
        teams_webhook_url=os.getenv("TEAMS_WEBHOOK_URL", "").strip(),
        timezone=os.getenv("TIMEZONE", "Asia/Tokyo").strip(),
        database_path=_resolve_path(database_path),
        rejected_log_path=_resolve_path(rejected_log_path),
        http_timeout_seconds=int(os.getenv("HTTP_TIMEOUT_SECONDS", "20")),
        max_item_age_days=int(os.getenv("MAX_ITEM_AGE_DAYS", "21")),
        sources_path=_resolve_path(sources_path),
    )


def load_sources(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def _resolve_path(path: Path) -> Path:
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path
