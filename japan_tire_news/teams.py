from __future__ import annotations

from datetime import datetime
from typing import Any
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from .models import ScoredNews


def build_message(items: list[ScoredNews]) -> str:
    now = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M")
    lines = [f"タイヤ市場ニュース {now}", ""]
    for index, scored in enumerate(items, start=1):
        item = scored.item
        lines.extend(
            [
                f"{index}. 【{_display_source(item.source)}】{item.title}",
                f"重要度スコア：{scored.importance} / {scored.score}",
                f"要約：{scored.summary}",
                f"リンク：{item.url}",
                "",
            ]
        )
    return "\n".join(lines).strip()


def post_to_teams(webhook_url: str, items: list[ScoredNews], timeout_seconds: int) -> None:
    if not webhook_url:
        raise ValueError("TEAMS_WEBHOOK_URL is not configured.")

    response = requests.post(
        webhook_url,
        json=_build_adaptive_card(items, timeout_seconds),
        timeout=timeout_seconds,
    )
    response.raise_for_status()


def _build_adaptive_card(items: list[ScoredNews], timeout_seconds: int) -> dict[str, Any]:
    now = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M")
    body: list[dict[str, Any]] = [
        {
            "type": "TextBlock",
            "text": f"タイヤ市場ニュース {now}",
            "weight": "Bolder",
            "size": "Medium",
            "wrap": True,
        }
    ]

    for index, scored in enumerate(items, start=1):
        item = scored.item
        thumbnail_url = _find_thumbnail_url(item.url, timeout_seconds)
        article_items: list[dict[str, Any]] = [
            _title_cell(f"{index}. 【{_display_source(item.source)}】{item.title}")
        ]

        if thumbnail_url:
            article_items.append(
                {
                    "type": "Image",
                    "url": thumbnail_url,
                    "size": "Stretch",
                    "altText": item.title,
                    "spacing": "Small",
                }
            )

        article_items.extend(
            [
                {
                    "type": "TextBlock",
                    "text": f"重要度スコア：{scored.importance} / {scored.score}",
                    "wrap": True,
                    "spacing": "Small",
                },
                {
                    "type": "TextBlock",
                    "text": f"要約：{scored.summary}",
                    "wrap": True,
                    "spacing": "Small",
                },
                {
                    "type": "ActionSet",
                    "actions": [
                        {
                            "type": "Action.OpenUrl",
                            "title": "リンク",
                            "url": item.url,
                        }
                    ],
                },
            ]
        )

        body.append(
            {
                "type": "Container",
                "separator": index > 1,
                "spacing": "Medium",
                "items": article_items,
            }
        )

    return {
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "type": "AdaptiveCard",
        "version": "1.4",
        "msteams": {
            "width": "Full",
        },
        "body": body,
    }


def _title_cell(title: str) -> dict[str, Any]:
    return {
        "type": "Container",
        "style": "emphasis",
        "bleed": False,
        "items": [
            {
                "type": "TextBlock",
                "text": title,
                "weight": "Bolder",
                "wrap": True,
            }
        ],
    }


def _display_source(source: str) -> str:
    source = source.strip()
    if source.startswith("Google News "):
        return source.replace("Google News ", "", 1).strip()
    return source


def _find_thumbnail_url(article_url: str, timeout_seconds: int) -> str | None:
    timeout = min(timeout_seconds, 6)
    try:
        response = requests.get(
            article_url,
            headers={"User-Agent": "JapanTireNews/0.1"},
            timeout=timeout,
        )
        response.raise_for_status()
    except requests.RequestException:
        return None

    soup = BeautifulSoup(response.text, "html.parser")
    selectors = [
        'meta[property="og:image"]',
        'meta[property="og:image:url"]',
        'meta[name="twitter:image"]',
        'meta[name="twitter:image:src"]',
    ]
    for selector in selectors:
        tag = soup.select_one(selector)
        if not tag:
            continue
        image_url = tag.get("content")
        if image_url:
            return urljoin(response.url, image_url)
    return None

