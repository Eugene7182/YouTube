"""CLI helper to trigger the /run/queue endpoint."""

from __future__ import annotations

import argparse
import logging
from typing import Any

import requests

from core.settings import get_settings

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

SETTINGS = get_settings()


def _invoke(payload: dict[str, Any]) -> dict[str, Any]:
    url = SETTINGS.service_base_url.rstrip("/") + "/run/queue"
    headers = {"Content-Type": "application/json"}
    if SETTINGS.admin_token:
        headers["Authorization"] = f"Bearer {SETTINGS.admin_token}"
    response = requests.post(url, json=payload, timeout=60)
    response.raise_for_status()
    return response.json()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Trigger Shorts generation queue")
    parser.add_argument("--topics", default="all", help="Идентификаторы тем или 'all'")
    parser.add_argument("--upload", action="store_true", help="Выполнить загрузку на YouTube")
    parser.add_argument("--dry-run", action="store_true", help="Не вызывать API, только показать payload")
    args = parser.parse_args(argv)

    payload: dict[str, Any]
    if args.topics.lower() == "all":
        payload = {"topics": "all", "upload": bool(args.upload)}
    else:
        payload = {"topics": [segment.strip() for segment in args.topics.split(",") if segment.strip()], "upload": bool(args.upload)}

    logger.info("payload=%s", payload)

    if args.dry_run:
        return

    try:
        result = _invoke(payload)
    except requests.RequestException as exc:  # pragma: no cover - network dependent
        logger.error("Не удалось запустить очередь: %s", exc)
        raise SystemExit(1) from exc

    logger.info("Статус: %s", result.get("status"))
    logger.info("Сгенерировано: %s", len(result.get("produced", [])))
    logger.info("Загружено: %s", result.get("uploaded"))


if __name__ == "__main__":  # pragma: no cover
    main()
