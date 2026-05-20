from __future__ import annotations

import re
from datetime import datetime
from typing import Any
from urllib.parse import parse_qs, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from .models import ScoredNews

try:
    import googlenewsdecoder
except ImportError:  # pragma: no cover - handled by requirements in normal installs.
    googlenewsdecoder = None

NO_IMAGE_URL = (
    "https://raw.githubusercontent.com/GoriGinsan/JapanTireNews/main/assets/no-image.png"
)
USER_AGENT = "JapanTireNews/0.1"


def build_message(items: list[ScoredNews]) -> str:
    now = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M")
    lines = [f"タイヤ市場ニュース {now}", ""]
    for index, scored in enumerate(items, start=1):
        item = scored.item
        lines.extend(
            [
                f"{index:02d}｜【{_display_source(item.source)}】{item.title}",
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
        article_url = _resolve_article_url(item.url)
        thumbnail_url = _find_thumbnail_url(article_url, timeout_seconds) or NO_IMAGE_URL
        article_items: list[dict[str, Any]] = [
            _title_cell(f"{index:02d}｜【{_display_source(item.source)}】{item.title}")
        ]

        article_items.append(
            {
                "type": "Image",
                "url": thumbnail_url,
                "width": "200px",
                "altText": item.title,
                "horizontalAlignment": "Left",
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
                            "url": article_url,
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


def _resolve_article_url(article_url: str) -> str:
    parsed = urlparse(article_url)
    if parsed.netloc.lower() != "news.google.com":
        return article_url
    if googlenewsdecoder is None:
        return article_url

    try:
        decoded = googlenewsdecoder.gnewsdecoder(article_url)
    except Exception:
        return article_url

    if not decoded.get("status"):
        return article_url

    decoded_url = decoded.get("decoded_url")
    if not isinstance(decoded_url, str) or not decoded_url.startswith(("http://", "https://")):
        return article_url
    return decoded_url


def _find_thumbnail_url(article_url: str, timeout_seconds: int) -> str | None:
    timeout = min(timeout_seconds, 6)
    try:
        response = requests.get(
            article_url,
            headers={"User-Agent": USER_AGENT},
            timeout=timeout,
        )
        response.raise_for_status()
    except requests.RequestException:
        return None

    soup = BeautifulSoup(response.text, "html.parser")
    for image_url in _candidate_image_urls(soup, response.url):
        thumbnail_url = urljoin(response.url, image_url)
        if _looks_like_generic_thumbnail(response.url, thumbnail_url):
            continue
        return thumbnail_url
    return None


def _candidate_image_urls(soup: BeautifulSoup, page_url: str) -> list[str]:
    candidates: list[tuple[int, str]] = []

    meta_selectors = [
        'meta[property="og:image"]',
        'meta[property="og:image:url"]',
        'meta[name="twitter:image"]',
        'meta[name="twitter:image:src"]',
        'meta[itemprop="image"]',
        'link[rel="image_src"]',
    ]
    for selector in meta_selectors:
        tag = soup.select_one(selector)
        if not tag:
            continue
        image_url = tag.get("content") or tag.get("href")
        if image_url:
            candidates.append((80, image_url))

    for video in soup.select("video[poster]"):
        poster = video.get("poster")
        if poster:
            candidates.append((115, poster))

    for iframe in soup.select("iframe[src]"):
        thumbnail = _video_thumbnail_from_iframe(iframe.get("src", ""))
        if thumbnail:
            candidates.append((110, thumbnail))

    for image in soup.select("main img, article img, [role='main'] img, .article img, .news img, .entry img, img"):
        image_url = _image_url_from_tag(image)
        if not image_url:
            continue
        score = 105
        width = _int_or_none(image.get("width"))
        height = _int_or_none(image.get("height"))
        if width and height:
            if width < 120 or height < 90:
                continue
            score += min((width * height) // 60000, 20)
        alt_text = " ".join([image.get("alt", ""), image.get("title", "")]).lower()
        if any(term in alt_text for term in ["logo", "ロゴ", "icon", "アイコン"]):
            continue
        candidates.append((score, image_url))

    seen: set[str] = set()
    ordered = []
    for _, image_url in sorted(candidates, key=lambda item: item[0], reverse=True):
        absolute = urljoin(page_url, image_url)
        if absolute in seen:
            continue
        seen.add(absolute)
        ordered.append(absolute)
    return ordered


def _image_url_from_tag(image: Any) -> str | None:
    srcset = image.get("srcset") or image.get("data-srcset")
    if srcset:
        return _largest_srcset_url(srcset)

    for attr in [
        "data-src",
        "data-original",
        "data-original-src",
        "data-lazy-src",
        "data-lazy",
        "data-large",
        "src",
    ]:
        value = image.get(attr)
        if value and not str(value).startswith("data:"):
            return value

    return None


def _largest_srcset_url(srcset: str) -> str | None:
    best_url = None
    best_score = -1
    for part in srcset.split(","):
        tokens = part.strip().split()
        if not tokens:
            continue
        image_url = tokens[0]
        score = 0
        if len(tokens) > 1:
            match = re.match(r"(\d+)(w|x)", tokens[1])
            if match:
                score = int(match.group(1))
        if score >= best_score:
            best_url = image_url
            best_score = score
    return best_url


def _video_thumbnail_from_iframe(src: str) -> str | None:
    parsed = urlparse(src)
    hostname = parsed.netloc.lower()
    if "youtube.com" in hostname:
        if "/embed/" in parsed.path:
            video_id = parsed.path.rsplit("/", 1)[-1]
        else:
            video_id = parse_qs(parsed.query).get("v", [""])[0]
        if video_id:
            return f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg"
    if "youtu.be" in hostname:
        video_id = parsed.path.strip("/")
        if video_id:
            return f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg"
    return None


def _int_or_none(value: Any) -> int | None:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _looks_like_generic_thumbnail(page_url: str, image_url: str) -> bool:
    normalized_page = page_url.lower()
    normalized_image = image_url.lower()
    generic_markers = [
        "google_news",
        "googlenews",
        "google-news",
        "news.google.com",
        "gstatic.com/news",
        "gstatic.com/images/branding",
        "googlelogo",
        "google_logo",
        "favicon",
        "apple-touch-icon",
        "/logo",
        "logo.",
        "logo-",
        "logo_",
        "_logo",
        "rn-logo",
        "/icon",
        "icon_",
        "rn-icon",
        "share.png",
        "/share",
        "common/images/common",
        "products_bnr",
        "special_bnr",
        "catalogue_bnr",
        "/menu_",
        "noimage",
        "no-image",
        "placeholder",
        "spacer",
        "blank.",
        ".svg",
    ]
    if any(marker in normalized_image for marker in generic_markers):
        return True

    if "news.google.com" in normalized_page:
        return True

    return False

