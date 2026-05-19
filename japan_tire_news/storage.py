from __future__ import annotations

import csv
import hashlib
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from .models import NewsItem, ScoredNews


class Storage:
    def __init__(self, database_path: Path, rejected_log_path: Path) -> None:
        self.database_path = database_path
        self.rejected_log_path = rejected_log_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.rejected_log_path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.database_path)
        self.connection.row_factory = sqlite3.Row
        self._init_schema()

    def close(self) -> None:
        self.connection.close()

    def has_seen(self, item: NewsItem) -> bool:
        digest = item_digest(item)
        row = self.connection.execute(
            "select 1 from news_items where digest = ? limit 1",
            (digest,),
        ).fetchone()
        return row is not None

    def save_notified(self, scored: ScoredNews) -> None:
        item = scored.item
        self.connection.execute(
            """
            insert or ignore into news_items
            (digest, title, url, source, summary, score, importance, reason, published_at, fetched_at, notified_at)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item_digest(item),
                item.title,
                item.url,
                item.source,
                scored.summary,
                scored.score,
                scored.importance,
                scored.reason,
                _iso(item.published_at),
                _iso(item.fetched_at),
                datetime.now().astimezone().isoformat(),
            ),
        )
        self.connection.commit()

    def log_rejected(self, item: NewsItem, reason: str) -> None:
        exists = self.rejected_log_path.exists()
        with self.rejected_log_path.open("a", newline="", encoding="utf-8-sig") as file:
            writer = csv.writer(file)
            if not exists:
                writer.writerow(["logged_at", "reason", "source", "title", "url"])
            writer.writerow([datetime.now().astimezone().isoformat(), reason, item.source, item.title, item.url])

    def prune(self, days: int = 180) -> None:
        threshold = datetime.now().astimezone() - timedelta(days=days)
        self.connection.execute(
            "delete from news_items where notified_at < ?",
            (threshold.isoformat(),),
        )
        self.connection.commit()

    def _init_schema(self) -> None:
        self.connection.execute(
            """
            create table if not exists news_items (
                digest text primary key,
                title text not null,
                url text not null,
                source text not null,
                summary text,
                score integer not null,
                importance text not null,
                reason text,
                published_at text,
                fetched_at text,
                notified_at text not null
            )
            """
        )
        self.connection.commit()


def item_digest(item: NewsItem) -> str:
    basis = (item.url or item.title).strip().lower()
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()

