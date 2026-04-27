"""新聞 RSS 抓取"""
from __future__ import annotations

import logging
from typing import Any

import feedparser

from config import NEWS_FEEDS

logger = logging.getLogger(__name__)

MAX_PER_FEED = 8


def fetch_feed(url: str, source_name: str) -> list[dict[str, Any]]:
    try:
        parsed = feedparser.parse(url)
        items = []
        for entry in parsed.entries[:MAX_PER_FEED]:
            items.append({
                "source": source_name,
                "title": entry.get("title", ""),
                "summary": (entry.get("summary", "") or "").strip()[:300],
                "link": entry.get("link", ""),
                "published": entry.get("published", ""),
            })
        return items
    except Exception as e:
        logger.exception("feed %s failed", url)
        return []


def fetch_all_news() -> list[dict[str, Any]]:
    out = []
    for feed in NEWS_FEEDS:
        out.extend(fetch_feed(feed["url"], feed["name"]))
    return out


if __name__ == "__main__":
    import json
    logging.basicConfig(level=logging.INFO)
    news = fetch_all_news()
    print(f"共 {len(news)} 則")
    print(json.dumps(news[:5], ensure_ascii=False, indent=2))
