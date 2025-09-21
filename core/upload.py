"""Upload orchestrator for generated Shorts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

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


def upload_manifest(manifest_path: str, settings_path: str) -> list[dict[str, str]]:
    """Upload all entries defined in the generation manifest."""

    manifest_file = Path(manifest_path)
    settings_file = Path(settings_path)

    items = _load_manifest(manifest_file)
    settings = _load_settings(settings_file)

    if not items:
        return []

    category_id = str(settings.get("categoryId", "24"))
    privacy_status = str(settings.get("privacyStatus", "private"))
    default_tags = settings.get("default_tags") or settings.get("shorts_hashtags") or []

    uploads: list[dict[str, str]] = []
    for entry in items:
        description = entry.get("description", "")
        tags = entry.get("tags") or default_tags
        response = upload_video(
            entry["video_path"],
            entry["title"],
            description,
            tags,
            category_id=category_id,
            privacy_status=privacy_status,
        )
        uploads.append(response)

    return uploads


__all__ = ["upload_manifest"]
