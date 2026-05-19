from __future__ import annotations

from datetime import datetime

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
        json={"text": message},
        timeout=timeout_seconds,
    )
    response.raise_for_status()

