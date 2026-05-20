from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .classify import classify_item
from .collect import Collector
from .config import load_config, load_sources
from .quality import QualityFinding, find_low_quality_scored
from .runner import _is_too_old, _select_unique, _title_key
from .storage import Storage


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit selected news quality before posting.")
    parser.add_argument("--force", action="store_true", help="Reserved for parity with the main runner.")
    parser.add_argument("--limit", type=int, default=10, help="Maximum number of selected items to audit.")
    parser.add_argument("--respect-seen", action="store_true", help="Skip already-notified items.")
    parser.add_argument("--output", type=Path, help="Optional markdown report path.")
    args = parser.parse_args()

    config = load_config()
    sources = load_sources(config.sources_path)
    tz = ZoneInfo(config.timezone)
    storage = Storage(config.database_path, config.rejected_log_path)

    try:
        collector = Collector(config.http_timeout_seconds)
        scored_items = []
        for item in collector.collect(sources):
            if args.respect_seen and storage.has_seen(item):
                continue
            if _is_too_old(item.published_at, config.max_item_age_days, tz):
                continue

            scored, _ = classify_item(item)
            if scored is None:
                continue
            if args.respect_seen and storage.has_seen_key(_title_key(scored.item.title)):
                continue
            scored_items.append(scored)

        selected = _select_unique(scored_items, args.limit)
        findings = find_low_quality_scored(selected)
    finally:
        storage.close()

    report = _build_report(findings, len(selected))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report, encoding="utf-8")

    print(report)
    if findings:
        raise SystemExit(2)


def _build_report(findings: list[QualityFinding], selected_count: int) -> str:
    now = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %z")
    lines = [
        "# JapanTireNews quality audit",
        "",
        f"- Time: {now}",
        f"- Selected items checked: {selected_count}",
        f"- Findings: {len(findings)}",
        "",
    ]

    if not findings:
        lines.append("No low-quality selected news items were detected.")
        return "\n".join(lines)

    lines.extend(
        [
            "Low-quality news candidates were detected in the items that would be posted.",
            "These should be treated as a news-quality bug because the job may post category, product-list, or non-news pages.",
            "",
        ]
    )

    for index, finding in enumerate(findings, start=1):
        item = finding.item
        lines.extend(
            [
                f"## {index}. {item.title}",
                "",
                f"- Source: {item.source}",
                f"- URL: {item.url}",
                f"- Reason: {finding.reason}",
                "",
            ]
        )

    return "\n".join(lines).strip()


if __name__ == "__main__":
    main()
