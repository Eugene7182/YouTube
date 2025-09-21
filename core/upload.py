"""Upload orchestrator for generated Shorts with validation."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

import yaml
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from core.metadata import inspect_video, normalize_metadata, validate_video
from core.settings import get_settings
from upload_youtube import upload_video

logger = logging.getLogger(__name__)
SETTINGS = get_settings()


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
    tz_name = str(uploader_cfg.get("timezone") or SETTINGS.tz_target)
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
    return _merge_tags(defaults, SETTINGS.channel_default_tags)


def _ensure_future_publish_at(publish_at: datetime | None, *, min_delta_minutes: int = 60) -> datetime | None:
    if publish_at is None:
        return None
    now = datetime.now(timezone.utc)
    minimum = now + timedelta(minutes=min_delta_minutes)
    if publish_at < minimum:
        logger.info(
            "Adjusting publishAt to respect 60-minute safety window",
            extra={"original": publish_at.isoformat(), "adjusted": minimum.isoformat()},
        )
        return minimum
    return publish_at


def _cleanup_artifacts(entry: dict[str, Any]) -> None:
    for key in ("video_path", "audio_path"):
        value = entry.get(key)
        if not value:
            continue
        path = Path(value)
        try:
            path.unlink(missing_ok=True)
        except Exception:  # pragma: no cover - best effort cleanup
            logger.warning("Failed to remove artefact", extra={"path": path.as_posix()})


def upload_manifest(manifest_path: str, settings_path: str) -> list[dict[str, str]]:
    """Upload all entries defined in the generation manifest."""

    manifest_file = Path(manifest_path)
    settings_file = Path(settings_path)

    items = _load_manifest(manifest_file)
    settings = _load_settings(settings_file)

    if not items:
        return []

    category_id = str(settings.get("categoryId", SETTINGS.default_category_id))
    privacy_status_default = str(settings.get("privacyStatus", SETTINGS.default_privacy))
    default_tags = _default_tags_from_settings(settings)

    results: list[dict[str, str]] = []
    for entry in items:
        video_path = Path(entry["video_path"])
        try:
            combined_tags = _merge_tags(entry.get("tags", []), default_tags)
            metadata = normalize_metadata(entry["title"], entry.get("description", ""), combined_tags)
            video_info = inspect_video(video_path)
            validate_video(video_info)
            schedule_utc = _parse_schedule(entry.get("schedule"), settings)
            publish_at = _ensure_future_publish_at(schedule_utc)
            logger.info(
                "Prepared upload entry",
                extra={
                    "title": metadata.title,
                    "publishAt": publish_at.isoformat() if publish_at else None,
                },
            )
            privacy_status = privacy_status_default
            if publish_at is not None:
                privacy_status = "private"
            response = upload_video(
                video_path,
                metadata.title,
                metadata.description,
                metadata.tags,
                category_id=category_id,
                privacy_status=privacy_status,
                publish_at=publish_at,
            )
            response.setdefault("title", metadata.title)
            results.append(response)
        except Exception as exc:
            logger.error(
                "Upload skipped due to validation error",
                extra={"title": entry.get("title"), "error": str(exc)},
            )
            results.append({
                "title": str(entry.get("title", "")),
                "status": "failed",
                "reason": str(exc),
            })
        finally:
            _cleanup_artifacts(entry)

    return results


__all__ = ["upload_manifest"]
