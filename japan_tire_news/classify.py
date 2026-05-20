from __future__ import annotations

import re

from .models import NewsItem, ScoredNews
from .quality import low_quality_reason


INCLUDE_TERMS = {
    "タイヤ新製品": ["新製品", "新商品", "発売", "発表", "新タイヤ", "ラインアップ"],
    "価格改定": [
        "価格改定",
        "値上げ",
        "値下げ",
        "価格を改定",
        "価格変更",
        "価格引き上げ",
        "価格引き下げ",
        "価格引上げ",
        "価格引下げ",
    ],
    "新車装着/OE採用": ["新車装着", "oe", "o.e.", "純正装着", "標準装着", "採用"],
    "トラック/バス": [
        "トラック",
        "バス",
        "商用車",
        "tbタイヤ",
        "小型トラック",
        "大型車",
        "トラック・バス用",
        "トラック・バス用タイヤ",
        "小型トラック・バス",
        "大型トラック・バス",
    ],
    "SUV/乗用車": ["suv", "乗用車", "passenger", "car tyre", "car tire"],
    "冬/オールシーズン": ["スタッドレス", "冬タイヤ", "オールシーズン", "all season", "snow"],
    "工場/供給": ["工場", "生産能力", "増産", "供給", "設備投資", "生産拠点"],
    "モータースポーツ": ["モータースポーツ", "レース", "ワンメイク", "super gt", "rally", "ラリー"],
    "EV": ["ev", "電気自動車", "電動車", "bev"],
    "新型車": ["新型車", "新型", "フルモデルチェンジ", "一部改良", "発売", "発表"]
}

EXCLUDE_TERMS = [
    "hankook",
    "ハンコック",
    "自転車",
    "ロードバイク",
    "クロスバイク",
    "マウンテンバイク",
    "原付",
    "二輪",
    "バイク",
    "モーターサイクル",
    "csr",
    "社会貢献",
    "サステナビリティ",
    "採用情報",
    "新卒採用",
    "中途採用",
    "求人",
    "決算",
    "ir情報",
    "irニュース",
    "株主",
    "スポーツ用品",
    "ゴルフ",
    "テニス",
    "市場規模",
    "分析レポート",
    "調査レポート",
    "市場調査",
    "レポートを発表"
]

HIGH_VALUE_TERMS = [
    "新製品",
    "価格改定",
    "値上げ",
    "値下げ",
    "新車装着",
    "純正装着",
    "標準装着",
    "トラック",
    "バス",
    "商用車",
    "価格引き上げ",
    "価格引き下げ",
    "国内市販用タイヤ",
    "市販用タイヤ",
    "トラック・バス用",
    "トラック・バス用タイヤ"
]

COMPETITOR_TERMS = [
    "ブリヂストン",
    "bridgestone",
    "ミシュラン",
    "michelin",
    "グッドイヤー",
    "goodyear",
    "toyo tire",
    "toyotires",
    "dunlop",
    "ダンロップ",
    "continental",
    "コンチネンタル",
    "pirelli",
    "ピレリ",
    "横浜ゴム",
    "横浜タイヤ",
    "yokohama"
]


def classify_item(item: NewsItem) -> tuple[ScoredNews | None, str | None]:
    quality_reason = low_quality_reason(item)
    if quality_reason:
        return None, f"品質除外: {quality_reason}"

    text = _normalize(" ".join([item.title, item.summary, item.raw_text, item.source]))

    excluded = [term for term in EXCLUDE_TERMS if term in text]
    if excluded:
        return None, f"除外語: {', '.join(excluded[:3])}"

    categories = _matched_categories(text)
    if not categories:
        return None, "対象カテゴリに一致しない"

    score = 10
    reasons: list[str] = []

    for category in categories:
        score += _category_score(category)
        reasons.append(category)

    if any(term in text for term in COMPETITOR_TERMS):
        score += 15
        reasons.append("競合メーカー")

    if any(term in text for term in HIGH_VALUE_TERMS):
        score += 15
        reasons.append("高優先度トピック")

    if "新型車" in categories and not any(term in text for term in ["タイヤ", "装着", "oe", "純正"]):
        score -= 10
        reasons.append("新型車一般ニュース")

    importance = "A" if score >= 55 else "B" if score >= 35 else "C"
    return ScoredNews(
        item=item,
        score=score,
        importance=importance,
        reason="、".join(dict.fromkeys(reasons)),
        summary=_summarize(item),
    ), None


def _normalize(text: str) -> str:
    text = text.lower()
    return re.sub(r"\s+", " ", text)


def _matched_categories(text: str) -> list[str]:
    categories = []
    for category, terms in INCLUDE_TERMS.items():
        if any(term.lower() in text for term in terms):
            categories.append(category)
    return categories


def _category_score(category: str) -> int:
    if category in {"価格改定", "新車装着/OE採用", "トラック/バス", "タイヤ新製品"}:
        return 20
    if category in {"EV", "冬/オールシーズン", "工場/供給"}:
        return 12
    if category in {"SUV/乗用車", "モータースポーツ"}:
        return 10
    return 8


def _summarize(item: NewsItem) -> str:
    text = item.summary or item.raw_text or item.title
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= 180:
        return text
    return text[:177].rstrip() + "..."
