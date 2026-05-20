from __future__ import annotations

import re
from datetime import datetime
from email.utils import parsedate_to_datetime
from urllib.parse import urljoin

import feedparser
import requests
from bs4 import BeautifulSoup

from .models import NewsItem
from .quality import low_quality_reason


USER_AGENT = "JapanTireNews/0.1 (+https://github.com/GoriGinsan/JapanTireNews)"


class Collector:
    def __init__(self, timeout_seconds: int) -> None:
        self.timeout_seconds = timeout_seconds
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})

    def collect(self, sources: dict) -> list[NewsItem]:
        items: list[NewsItem] = []
        for feed in sources.get("rss_feeds", []):
            try:
                items.extend(self.collect_rss(feed["name"], feed["url"]))
            except Exception as exc:
                items.append(_error_item(feed["name"], feed["url"], exc))
        for page in sources.get("press_pages", []):
            try:
                items.extend(self.collect_press_page(page["name"], page["url"]))
            except Exception as exc:
                items.append(_error_item(page["name"], page["url"], exc))
        return _dedupe_in_memory(items)

    def collect_rss(self, source_name: str, url: str) -> list[NewsItem]:
        parsed = feedparser.parse(url)
        items = []
        fetched_at = datetime.now().astimezone()
        for entry in parsed.entries[:30]:
            title = _clean(getattr(entry, "title", ""))
            link = getattr(entry, "link", "")
            if not title or not link:
                continue
            summary = _clean(getattr(entry, "summary", ""))
            published_at = _parse_datetime(getattr(entry, "published", ""))
            items.append(
                NewsItem(
                    title=title,
                    url=link,
                    source=source_name,
                    summary=summary,
                    published_at=published_at,
                    fetched_at=fetched_at,
                    raw_text=summary,
                )
            )
        return items

    def collect_press_page(self, source_name: str, url: str) -> list[NewsItem]:
        response = self.session.get(url, timeout=self.timeout_seconds)
        response.raise_for_status()
        response.encoding = response.apparent_encoding or response.encoding
        soup = BeautifulSoup(response.text, "html.parser")
        fetched_at = datetime.now().astimezone()
        items = []

        for anchor in soup.select("a[href]"):
            title = _clean(anchor.get_text(" ", strip=True))
            href = anchor.get("href", "")
            if not title or len(title) < 8:
                continue
            if _looks_like_navigation(title):
                continue
            link = urljoin(url, href)
            if _looks_like_navigation_link(link):
                continue
            context = _clean(anchor.parent.get_text(" ", strip=True) if anchor.parent else title)
            item = NewsItem(
                title=title,
                url=link,
                source=source_name,
                summary=context,
                published_at=_extract_date(f"{context} {link}"),
                fetched_at=fetched_at,
                raw_text=context,
            )
            if low_quality_reason(item):
                continue
            items.append(item)

        return items[:60]


def _parse_datetime(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None


def _extract_date(value: str) -> datetime | None:
    match = re.search(r"(20\d{2})[./-](\d{1,2})[./-](\d{1,2})", value)
    if match:
        year, month, day = (int(part) for part in match.groups())
        return _date_or_none(year, month, day)

    japanese = re.search(r"(20\d{2})年\s*(\d{1,2})月\s*(\d{1,2})日", value)
    if japanese:
        year, month, day = (int(part) for part in japanese.groups())
        return _date_or_none(year, month, day)

    compact = re.search(r"(20\d{2})(\d{2})(\d{2})", value)
    if compact:
        year, month, day = (int(part) for part in compact.groups())
        return _date_or_none(year, month, day)

    year_slash_mmdd = re.search(r"(20\d{2})/(\d{2})(\d{2})", value)
    if year_slash_mmdd:
        year, month, day = (int(part) for part in year_slash_mmdd.groups())
        return _date_or_none(year, month, day)

    return None


def _date_or_none(year: int, month: int, day: int) -> datetime | None:
    try:
        return datetime(year, month, day).astimezone()
    except ValueError:
        return None


def _clean(value: str) -> str:
    value = value or ""
    if "<" not in value and ">" not in value:
        return " ".join(value.split())
    return " ".join(BeautifulSoup(value, "html.parser").get_text(" ").split())


def _looks_like_navigation(title: str) -> bool:
    navigation_terms = [
        "ホーム",
        "お問い合わせ",
        "サイトマップ",
        "検索",
        "一覧",
        "english",
        "global",
        "cookie",
        "privacy",
        "menu",
        "ページtop",
        "ページトップ",
        "プライバシーポリシー",
    ]
    lower = title.lower()
    return any(term in lower for term in navigation_terms)


def _looks_like_navigation_link(url: str) -> bool:
    lower = url.lower()
    navigation_paths = [
        "/products/",
        "/products/list",
        "/products/oe/",
        "/special/",
        "/catalogue/",
        "/strength/",
        "/knowledge/",
        "/dictionary/",
        "/corporate/",
        "/contact/",
        "/shop/",
        "/search/",
        "/privacy",
        "/policy/",
        "/cookie",
        "#pagetop",
        "instagram.com",
        "facebook.com",
        "x.com/",
        "youtube.com/",
    ]
    allowed_news_paths = [
        "/corporate/news/",
        "/press/",
        "/release/",
        "/news/",
        "/info/news/",
        "/newsroom/",
    ]
    if any(path in lower for path in allowed_news_paths):
        return False
    return any(path in lower for path in navigation_paths)


def _dedupe_in_memory(items: list[NewsItem]) -> list[NewsItem]:
    seen: set[str] = set()
    unique = []
    for item in items:
        key = item.url.strip() or item.title.strip()
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def _error_item(source_name: str, url: str, exc: Exception) -> NewsItem:
    return NewsItem(
        title=f"取得失敗: {source_name}",
        url=url,
        source="system",
        summary=str(exc),
        fetched_at=datetime.now().astimezone(),
        raw_text="",
    )
