"""Fetch trending US Shorts and push them into the topics queue."""

from __future__ import annotations

import argparse
import logging
from typing import Any

import requests

from core.settings import get_settings

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

SETTINGS = get_settings()
YOUTUBE_API_URL = "https://www.googleapis.com/youtube/v3/videos"


def _parse_duration_iso8601(duration: str) -> int:
    if not duration or not duration.startswith("PT"):
        return 999
    total = 0
    value = ""
    for ch in duration[2:]:
        if ch.isdigit():
            value += ch
            continue
        if ch == "H":
            total += int(value or 0) * 3600
        elif ch == "M":
            total += int(value or 0) * 60
        elif ch == "S":
            total += int(value or 0)
        value = ""
    return total


def _fetch(api_key: str, region: str, max_results: int) -> list[dict[str, Any]]:
    params = {
        "part": "id,snippet,contentDetails,statistics",
        "chart": "mostPopular",
        "regionCode": region,
        "videoCategoryId": "",
        "maxResults": str(max_results),
        "key": api_key,
    }
    response = requests.get(YOUTUBE_API_URL, params=params, timeout=30)
    response.raise_for_status()
    payload = response.json()
    items = []
    for entry in payload.get("items", []):
        duration = _parse_duration_iso8601(entry.get("contentDetails", {}).get("duration", ""))
        if duration == 0 or duration > 60:
            continue
        snippet = entry.get("snippet", {})
        statistics = entry.get("statistics", {})
        title = snippet.get("title") or ""
        if not title:
            continue
        description = snippet.get("description", "")
        tags = snippet.get("tags", []) or SETTINGS.channel_default_tags[:3]
        lines = [
            snippet.get("title", ""),
            snippet.get("channelTitle", ""),
            f"Views: {statistics.get('viewCount', '0')}",
            (description.splitlines() or [""])[0],
        ]
        items.append({
            "title": title,
            "lines": [line for line in lines if line],
            "tags": tags[:3],
        })
    return items


def _post_topics(topics: list[dict[str, Any]]) -> None:
    if not topics:
        logger.info("Нечего отправлять")
        return
    url = SETTINGS.service_base_url.rstrip("/") + "/trends/generate"
    headers = {"Content-Type": "application/json"}
    if SETTINGS.admin_token:
        headers["Authorization"] = f"Bearer {SETTINGS.admin_token}"
    response = requests.post(url, json={"topics": topics}, timeout=30)
    response.raise_for_status()
    logger.info("Отправлено %s трендовых тем", response.json().get("count"))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Fetch trending Shorts ideas")
    parser.add_argument("--region", default="US", help="Регион поиска трендов")
    parser.add_argument("--max", type=int, default=15, help="Количество роликов")
    parser.add_argument("--dry-run", action="store_true", help="Только вывести темы")
    args = parser.parse_args(argv)

    if not SETTINGS.youtube_api_key:
        logger.error("YOUTUBE_API_KEY не задан")
        raise SystemExit(1)

    try:
        topics = _fetch(SETTINGS.youtube_api_key, args.region, args.max)
    except requests.HTTPError as exc:  # pragma: no cover - network dependent
        logger.error("YouTube API error: %s", exc.response.text if exc.response else exc)
        raise SystemExit(1) from exc
    except requests.RequestException as exc:  # pragma: no cover - network dependent
        logger.error("Ошибка при обращении к YouTube API: %s", exc)
        raise SystemExit(1) from exc

    if args.dry_run:
        logger.info("Dry-run: %s", topics)
        return

    try:
        _post_topics(topics)
    except requests.RequestException as exc:  # pragma: no cover - network dependent
        logger.error("Не удалось отправить темы: %s", exc)
        raise SystemExit(1) from exc


if __name__ == "__main__":  # pragma: no cover
    main()
