"""Upload orchestrator for generated Shorts."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

import yaml
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from upload_youtube import upload_video


def _load_manifest(manifest_path: Path) -> list[dict[str, Any]]:
    if not manifest_path.exists():
        return []
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    items = data.get("items") if isinstance(data, dict) else data
    if not isinstance(items, list):
        return []
    result: list[dict[str, Any]] = []
    for entry in items:
        if isinstance(entry, dict) and entry.get("video_path") and entry.get("title"):
            result.append(entry)
    return result


def _load_settings(settings_path: Path) -> dict[str, Any]:
    if not settings_path.exists():
        return {}
    with settings_path.open("r", encoding="utf-8") as stream:
        data = yaml.safe_load(stream) or {}
    if not isinstance(data, dict):
        return {}
    return data


def _merge_tags(*tag_sources: Iterable[str]) -> list[str]:
    merged: list[str] = []
    for source in tag_sources:
        for tag in source:
            normalized = str(tag).strip()
            if normalized and normalized not in merged:
                merged.append(normalized)
    return merged


def _load_timezone_from_settings(settings: dict[str, Any]) -> ZoneInfo:
    uploader_cfg = settings.get("uploader") if isinstance(settings.get("uploader"), dict) else {}
    tz_name = str(uploader_cfg.get("timezone") or os.getenv("TZ", "Asia/Almaty"))
    try:
        return ZoneInfo(tz_name)
    except ZoneInfoNotFoundError as exc:
        raise RuntimeError(f"Не найдена таймзона '{tz_name}' для uploader") from exc


def _parse_schedule(schedule: str | None, settings: dict[str, Any]) -> datetime | None:
    if not schedule:
        return None
    try:
        parsed = datetime.fromisoformat(schedule)
    except ValueError as exc:
        raise RuntimeError(f"Некорректный формат schedule в манифесте: {schedule}") from exc
    if parsed.tzinfo is None:
        tz = _load_timezone_from_settings(settings)
        parsed = parsed.replace(tzinfo=tz)
    return parsed.astimezone(timezone.utc)


def _default_tags_from_settings(settings: dict[str, Any]) -> list[str]:
    defaults: Sequence[str] = []
    if isinstance(settings.get("default_tags"), (list, tuple)):
        defaults = [str(tag).strip() for tag in settings.get("default_tags", []) if str(tag).strip()]
    elif isinstance(settings.get("shorts_hashtags"), (list, tuple)):
        defaults = [
            str(tag).strip()
            for tag in settings.get("shorts_hashtags", [])
            if str(tag).strip()
        ]

    env_tags = [
        segment.strip()
        for segment in os.getenv("DEFAULT_TAGS", "").split(",")
        if segment.strip()
    ]
    return _merge_tags(defaults, env_tags)


def upload_manifest(manifest_path: str, settings_path: str) -> list[dict[str, str]]:
    """Upload all entries defined in the generation manifest."""

    manifest_file = Path(manifest_path)
    settings_file = Path(settings_path)

    items = _load_manifest(manifest_file)
    settings = _load_settings(settings_file)

    if not items:
        return []

    category_id = str(settings.get("categoryId", "24"))
    privacy_status_default = str(settings.get("privacyStatus", "private"))
    default_tags = _default_tags_from_settings(settings)

    uploads: list[dict[str, str]] = []
    for entry in items:
        description = entry.get("description", "")
        tags = _merge_tags(entry.get("tags", []), default_tags)
        schedule_utc = _parse_schedule(entry.get("schedule"), settings)
        privacy_status = privacy_status_default
        publish_at = None
        if schedule_utc is not None:
            publish_at = schedule_utc
            privacy_status = "private"
        response = upload_video(
            entry["video_path"],
            entry["title"],
            description,
            tags,
            category_id=category_id,
            privacy_status=privacy_status,
            publish_at=publish_at,
        )
        uploads.append(response)

    return uploads


__all__ = ["upload_manifest"]
