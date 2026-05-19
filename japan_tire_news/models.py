from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class NewsItem:
    title: str
    url: str
    source: str
    summary: str = ""
    published_at: datetime | None = None
    fetched_at: datetime | None = None
    raw_text: str = ""


@dataclass(frozen=True)
class ScoredNews:
    item: NewsItem
    score: int
    importance: str
    reason: str
    summary: str

