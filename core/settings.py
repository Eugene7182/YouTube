"""Runtime settings helpers for Shorts automation."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

logger = logging.getLogger(__name__)


def _split_csv(raw: str | None) -> list[str]:
    if not raw:
        return []
    items: list[str] = []
    for segment in raw.split(","):
        value = segment.strip()
        if not value:
            continue
        items.append(value)
    return items


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_json(name: str) -> dict[str, Any] | None:
    raw = os.getenv(name, "").strip()
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.error("%s содержит некорректный JSON: %s", name, exc)
        raise


@dataclass(slots=True)
class EnvironmentSettings:
    """Aggregated environment configuration."""

    channel_default_tags: list[str]
    default_category_id: str
    default_privacy: str
    tz_target: str
    tz_local: str
    render_deploy: bool
    youtube_api_key: str
    youtube_region: str
    ideas_per_refresh: int
    search_queries: list[str]
    admin_token: str
    dry_run: bool
    service_base_url: str


@lru_cache(maxsize=1)
def get_settings() -> EnvironmentSettings:
    channel_tags = _split_csv(os.getenv("CHANNEL_DEFAULT_TAGS", "shorts,cartoon,comedy"))
    default_privacy = os.getenv("DEFAULT_PRIVACY", "private") or "private"
    default_category_id = os.getenv("DEFAULT_CATEGORY_ID", "1") or "1"
    tz_target = os.getenv("TZ_TARGET", "America/New_York") or "America/New_York"
    tz_local = os.getenv("TZ_LOCAL", "Asia/Almaty") or "Asia/Almaty"
    youtube_api_key = os.getenv("YOUTUBE_API_KEY", "").strip()
    youtube_region = os.getenv("YOUTUBE_REGION", "US").strip() or "US"
    ideas_raw = os.getenv("IDEAS_PER_REFRESH", "50").strip()
    try:
        ideas_per_refresh = max(1, min(100, int(ideas_raw)))
    except ValueError:
        ideas_per_refresh = 50
    search_queries = _split_csv(os.getenv("YT_SEARCH_QUERIES", ""))
    admin_token = os.getenv("ADMIN_TOKEN", "").strip()
    dry_run = _env_bool("YOUTUBE_DRY_RUN", False)
    service_base_url = os.getenv("SERVICE_BASE_URL", "http://localhost:10000").strip() or "http://localhost:10000"

    return EnvironmentSettings(
        channel_default_tags=channel_tags,
        default_category_id=str(default_category_id),
        default_privacy=default_privacy,
        tz_target=tz_target,
        tz_local=tz_local,
        render_deploy=_env_bool("RENDER_DEPLOY", False),
        youtube_api_key=youtube_api_key,
        youtube_region=youtube_region,
        ideas_per_refresh=ideas_per_refresh,
        search_queries=search_queries,
        admin_token=admin_token,
        dry_run=dry_run,
        service_base_url=service_base_url,
    )


__all__ = ["EnvironmentSettings", "get_settings", "_env_json"]
