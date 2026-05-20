from __future__ import annotations

from datetime import datetime
from typing import Any

import requests

from .models import ScoredNews


def build_message(items: list[ScoredNews]) -> str:
    now = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M")
    lines = [f"タイヤ市場ニュース {now}", ""]
    for index, scored in enumerate(items, start=1):
        item = scored.item
        lines.extend(
            [
                f"{index}. 【{item.source}】{item.title}",
                f"重要度スコア：{scored.importance} / {scored.score}",
                f"要約：{scored.summary}",
                f"URL：{item.url}",
                "",
            ]
        )
    return "\n".join(lines).strip()


def post_to_teams(webhook_url: str, message: str, timeout_seconds: int) -> None:
    if not webhook_url:
        raise ValueError("TEAMS_WEBHOOK_URL is not configured.")

    response = requests.post(
        webhook_url,
        json=_build_adaptive_card(message),
        timeout=timeout_seconds,
    )
    response.raise_for_status()


def _build_adaptive_card(message: str) -> dict[str, Any]:
    lines = message.splitlines()
    title = lines[0] if lines else "JapanTireNews"
    body_text = "\n".join(lines[1:]).strip() if len(lines) > 1 else message

    return {
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "type": "AdaptiveCard",
        "version": "1.4",
        "msteams": {
            "width": "Full",
        },
        "body": [
            {
                "type": "TextBlock",
                "text": title,
                "weight": "Bolder",
                "size": "Medium",
                "wrap": True,
            },
            {
                "type": "TextBlock",
                "text": body_text,
                "wrap": True,
            },
        ],
    }

