from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

from .models import NewsItem, ScoredNews


@dataclass(frozen=True)
class QualityFinding:
    item: NewsItem
    reason: str


LOW_QUALITY_TITLE_TERMS = [
    "タイヤサイト",
    "ニュースリリース",
    "モータースポーツ",
    "サステナビリティ",
    "ソリューション",
    "テクノロジー",
    "イノベーション",
    "投資家情報",
    "株主",
    "レポートライブラリ",
    "ご利用にあたって",
    "オンラインショップ",
    "タイヤパンク応急処理キット",
]

LOW_QUALITY_PATH_TERMS = [
    "/csr/",
    "/solution/",
    "/technology_innovation/",
    "/ir/",
    "/terms_of_use/",
    "/motorsport/",
    "/ec",
    "/ims",
    "/products/",
    "/tire_wheel/",
    "/wheels/",
    "/wheel/",
]

LISTING_PATH_ENDINGS = [
    "/corporate/news/index.html",
    "/corporate/news/search/",
    "/corporate/news/search",
    "/info/news/",
    "/news/",
    "/newsroom/",
    "/press/",
]


def find_low_quality_scored(items: list[ScoredNews]) -> list[QualityFinding]:
    findings = []
    for scored in items:
        finding = low_quality_reason(scored.item)
        if finding:
            findings.append(QualityFinding(scored.item, finding))
    return findings


def low_quality_reason(item: NewsItem) -> str | None:
    title = item.title.strip().lower()
    url = item.url.strip()
    parsed = urlparse(url)
    path = parsed.path.lower()

    matched_title_terms = [term for term in LOW_QUALITY_TITLE_TERMS if term.lower() in title]
    if matched_title_terms:
        return f"ニュース本文ではない可能性が高いタイトル: {', '.join(matched_title_terms[:3])}"

    if any(term in path for term in LOW_QUALITY_PATH_TERMS):
        return "商品・カテゴリ・企業情報などの一覧/案内ページURL"

    if any(path.endswith(ending) for ending in LISTING_PATH_ENDINGS):
        return "ニュース一覧ページURL"

    if parsed.netloc == "tire.bridgestone.co.jp" and path in {"", "/"}:
        return "ブリヂストンのタイヤサイトトップページ"

    if parsed.netloc == "ms.bridgestone.co.jp" and path in {"", "/"}:
        return "ブリヂストンのモータースポーツ一覧ページ"

    return None
