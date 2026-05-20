from __future__ import annotations

import argparse
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import holidays

from .classify import classify_item
from .collect import Collector
from .config import load_config, load_sources
from .models import ScoredNews
from .storage import Storage
from .teams import build_message, post_to_teams


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect tire market news and notify Microsoft Teams.")
    parser.add_argument("--dry-run", action="store_true", help="Collect and print results without posting to Teams.")
    parser.add_argument("--force", action="store_true", help="Run outside the time, weekend, and holiday checks.")
    parser.add_argument("--limit", type=int, default=10, help="Maximum number of items to notify.")
    args = parser.parse_args()

    config = load_config()
    tz = ZoneInfo(config.timezone)

    if not args.force and not _should_run_now(tz):
        print("Outside collection calendar. No action.")
        return

    sources = load_sources(config.sources_path)
    storage = Storage(config.database_path, config.rejected_log_path)
    try:
        collector = Collector(config.http_timeout_seconds)
        raw_items = collector.collect(sources)
        scored_items: list[ScoredNews] = []

        for item in raw_items:
            if storage.has_seen(item):
                continue
            if _is_too_old(item.published_at, config.max_item_age_days, tz):
                storage.log_rejected(item, f"{config.max_item_age_days}日より古い")
                continue

            scored, reject_reason = classify_item(item)
            if scored is None:
                storage.log_rejected(item, reject_reason or "不明")
                continue
            if storage.has_seen_key(_title_key(scored.item.title)):
                continue

            scored_items.append(scored)

        if not scored_items:
            storage.prune(days=180)
            print("No relevant news.")
            return

        selected = _select_unique(scored_items, args.limit)
        message = build_message(selected)

        if args.dry_run:
            print(message)
        else:
            post_to_teams(config.teams_webhook_url, selected, config.http_timeout_seconds)
            for scored in selected:
                storage.save_notified(scored, _title_key(scored.item.title))

        storage.prune(days=180)
    finally:
        storage.close()


def _should_run_now(tz: ZoneInfo) -> bool:
    now = datetime.now(tz)
    if not _within_business_hours(now):
        return False
    if _is_weekend_or_japanese_holiday(now):
        return False
    return True


def _within_business_hours(now: datetime) -> bool:
    return 9 <= now.hour <= 18


def _is_weekend_or_japanese_holiday(now: datetime) -> bool:
    if now.weekday() >= 5:
        return True
    japan_holidays = holidays.country_holidays("JP", years=[now.year])
    return now.date() in japan_holidays


def _is_too_old(published_at: datetime | None, max_item_age_days: int, tz: ZoneInfo) -> bool:
    if published_at is None:
        return False
    threshold = datetime.now(tz) - timedelta(days=max_item_age_days)
    return published_at.astimezone(tz) < threshold


def _select_unique(items: list[ScoredNews], limit: int) -> list[ScoredNews]:
    selected = []
    seen_titles: set[str] = set()
    for scored in sorted(items, key=lambda item: item.score, reverse=True):
        key = _title_key(scored.item.title)
        if key in seen_titles:
            continue
        seen_titles.add(key)
        selected.append(scored)
        if len(selected) >= limit:
            break
    return selected


def _title_key(title: str) -> str:
    topic_key = _topic_key(title)
    if topic_key:
        return topic_key
    product_key = _product_key(title)
    if product_key:
        return product_key
    title = re.sub(r"（.*?）|\(.*?\)", "", title)
    title = re.sub(r"\s+-\s+.*$", "", title)
    title = re.sub(r"[\s　「」『』【】\[\]・、。！？!?\"']", "", title.lower())
    return title[:45]


def _topic_key(title: str) -> str | None:
    compact = re.sub(r"[\s　「」『』【】\[\]・、。！？!?\"'－\-+＋]", "", title.lower())
    topic_patterns = [
        ("topic:toyo-m635", ["トーヨー", "小型トラック", "オールウェザー"]),
        ("topic:toyo-m635", ["小型トラック", "オールウェザー", "m635"]),
        ("topic:xice-snow-plus", ["ミシュラン", "スタッドレス", "xice"]),
        ("topic:xice-snow-plus", ["ミシュラン", "スタッドレス", "xアイス"]),
    ]
    for key, terms in topic_patterns:
        if all(term in compact for term in terms):
            return key
    return None


def _product_key(title: str) -> str | None:
    quoted = re.findall(r"[「『\"]([^」』\"]{2,40})[」』\"]", title)
    for value in quoted:
        model_fragment = _model_fragment(value)
        if model_fragment:
            return f"product:{model_fragment}"
        normalized = _normalize_product(value)
        if _looks_like_product_name(normalized):
            return f"product:{normalized}"

    model = re.search(r"\b([A-Z]{1,8}[- ]?[A-Z0-9]{2,12}\+?)\b", title, re.IGNORECASE)
    if model:
        normalized = _normalize_product(model.group(1))
        if _looks_like_product_name(normalized):
            return f"product:{normalized}"
    return None


def _model_fragment(value: str) -> str | None:
    match = re.search(r"\b([A-Z]{0,8}[- ]?\d{2,}[A-Z0-9+]*)\b", value, re.IGNORECASE)
    if not match:
        return None
    return _normalize_product(match.group(1))


def _normalize_product(value: str) -> str:
    value = value.lower()
    replacements = {
        "ｘ": "x",
        "＋": "+",
        "アイス": "ice",
        "スノー": "snow",
        "プライマシー": "primacy",
        "パイロットスポーツ": "pilotsport",
    }
    for source, replacement in replacements.items():
        value = value.replace(source, replacement)

    normalized = re.sub(r"[^a-z0-9+]", "", value)
    for brand in ["michelin", "dunlop", "goodyear", "bridgestone", "pirelli", "continental", "yokohama"]:
        normalized = normalized.replace(brand, "")
    return normalized


def _looks_like_product_name(value: str) -> bool:
    if len(value) < 3:
        return False
    return any(char.isdigit() for char in value) or any(token in value for token in ["xice", "delvex", "sp", "snow", "primacy"])
