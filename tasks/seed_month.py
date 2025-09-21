"""Seed upcoming month of Shorts topics via the API."""

from __future__ import annotations

import argparse
import logging
from datetime import datetime, timedelta
from typing import Any

import requests

from core.schedule import ScheduleParseError, to_utc_iso
from core.settings import get_settings

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

SETTINGS = get_settings()


def _build_topics(start: str, days: int, slot: str) -> list[dict[str, Any]]:
    try:
        base_date = datetime.strptime(start, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError("--start должен быть в формате YYYY-MM-DD") from exc

    topics: list[dict[str, Any]] = []
    default_tags = SETTINGS.channel_default_tags[:3] or ["shorts"]
    for offset in range(days):
        current_date = base_date + timedelta(days=offset)
        schedule_iso = to_utc_iso(current_date.isoformat(), slot, SETTINGS.tz_target)
        topics.append(
            {
                "title": f"Scheduled Shorts for {current_date.isoformat()}",
                "lines": [
                    "Hook: 3 факта из трендов.",
                    "Body: Добавь юмор и динамику.",
                    "CTA: Подписывайся на ежедневные шорты.",
                ],
                "tags": default_tags,
                "schedule": schedule_iso,
            }
        )
    return topics


def _post_topics(topics: list[dict[str, Any]]) -> None:
    if not topics:
        logger.info("Нет тем для отправки")
        return
    url = SETTINGS.service_base_url.rstrip("/") + "/trends/generate"
    headers = {"Content-Type": "application/json"}
    if SETTINGS.admin_token:
        headers["Authorization"] = f"Bearer {SETTINGS.admin_token}"
    response = requests.post(url, json={"topics": topics}, timeout=30)
    response.raise_for_status()
    logger.info("Отправлено %s тем", response.json().get("count"))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Seed a month of scheduled shorts")
    parser.add_argument("--start", required=True, help="Дата начала YYYY-MM-DD")
    parser.add_argument("--days", type=int, default=30, help="Количество дней для планирования")
    parser.add_argument("--slot", default="09:00 ET", help="Временной слот, например '09:00 ET'")
    parser.add_argument("--dry-run", action="store_true", help="Только вывести payload без отправки")
    args = parser.parse_args(argv)

    try:
        topics = _build_topics(args.start, args.days, args.slot)
    except (ValueError, ScheduleParseError) as exc:
        logger.error("Ошибка подготовки тем: %s", exc)
        raise SystemExit(1) from exc

    if args.dry_run:
        logger.info("Dry-run: %s", topics)
        return

    try:
        _post_topics(topics)
    except requests.HTTPError as exc:  # pragma: no cover - network dependent
        logger.error("API вернул ошибку: %s", exc.response.text if exc.response else exc)
        raise SystemExit(1) from exc
    except requests.RequestException as exc:  # pragma: no cover - network dependent
        logger.error("Не удалось отправить темы: %s", exc)
        raise SystemExit(1) from exc


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    main()
