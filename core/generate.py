"""Video generation pipeline orchestrator."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, time, timedelta
from pathlib import Path
from typing import Any, Iterable, Sequence

import yaml
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from build_short import assemble_short, load_font
from core.settings import get_settings
from tts import synth_sync

SETTINGS = get_settings()
OUTPUT_ROOT = Path(os.getenv("OUTPUT_ROOT_DIR", "/tmp/shorts-output"))
AUDIO_ROOT = OUTPUT_ROOT / "audio"
VIDEO_ROOT = OUTPUT_ROOT / "video"
MANIFEST_PATH = OUTPUT_ROOT / "manifest.json"


def _slugify(value: str) -> str:
    """Produce a filesystem-safe slug from an arbitrary string."""

    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9\-]+", "-", value)
    value = re.sub(r"-+", "-", value)
    return value.strip("-") or "topic"


def _load_config(cfg_path: Path) -> dict[str, Any]:
    cfg: dict[str, Any] = {}
    if cfg_path.exists():
        with cfg_path.open("r", encoding="utf-8") as stream:
            loaded = yaml.safe_load(stream) or {}
            if isinstance(loaded, dict):
                cfg.update(loaded)

    default_tags_cfg: Sequence[str] = []
    if isinstance(cfg.get("default_tags"), (list, tuple)):
        default_tags_cfg = [str(tag).strip() for tag in cfg.get("default_tags", []) if str(tag).strip()]
    elif isinstance(cfg.get("shorts_hashtags"), (list, tuple)):
        default_tags_cfg = [
            str(tag).strip()
            for tag in cfg.get("shorts_hashtags", [])
            if str(tag).strip()
        ]

    env_default_tags = list(SETTINGS.channel_default_tags)

    merged_defaults: list[str] = []
    for tag in list(default_tags_cfg) + env_default_tags:
        if tag and tag not in merged_defaults:
            merged_defaults.append(tag)

    cfg["default_tags"] = merged_defaults
    cfg.setdefault("tts_lang", "ru")
    cfg.setdefault("tts_timeout", 30)
    cfg.setdefault("fps", 30)
    cfg.setdefault("resolution", [1080, 1920])
    cfg.setdefault("font", "DejaVuSans.ttf")
    cfg.setdefault("font_size", 64)

    uploader = cfg.get("uploader")
    if not isinstance(uploader, dict):
        uploader = {}
    uploader.setdefault("auto_schedule_if_missing", False)
    uploader.setdefault("time_local", "21:00")
    uploader.setdefault("timezone", SETTINGS.tz_target)
    cfg["uploader"] = uploader

    return cfg


def _load_topics(topics_path: Path) -> list[dict[str, Any]]:
    if not topics_path.exists():
        return []
    with topics_path.open("r", encoding="utf-8") as stream:
        data = yaml.safe_load(stream) or []
    if isinstance(data, dict):
        topics = data.get("topics", [])
    else:
        topics = data
    result: list[dict[str, Any]] = []
    for raw in topics:
        if isinstance(raw, dict):
            title = str(raw.get("title", "")).strip()
            if not title:
                continue
            lines = raw.get("lines") or []
            if isinstance(lines, str):
                prepared_lines = [segment.strip() for segment in lines.split("\n") if segment.strip()]
            else:
                prepared_lines = [str(segment).strip() for segment in lines if str(segment).strip()]
            result.append(
                {
                    "title": title,
                    "lines": prepared_lines,
                    "tags": [str(tag).strip() for tag in raw.get("tags", []) if str(tag).strip()],
                    "bg_video_path": raw.get("bg_video_path"),
                    "bg_image_path": raw.get("bg_image_path"),
                    "music_path": raw.get("music_path"),
                    "schedule": raw.get("schedule"),
                }
            )
    return result


def _ensure_directories() -> None:
    AUDIO_ROOT.mkdir(parents=True, exist_ok=True)
    VIDEO_ROOT.mkdir(parents=True, exist_ok=True)
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)


def _ensure_lines(lines: Iterable[str], title: str) -> list[str]:
    prepared = [line.strip() for line in lines if line.strip()]
    if prepared:
        return prepared
    return [segment.strip() for segment in re.split(r"[.!?]", title) if segment.strip()]


def _merge_tags(topic_tags: Iterable[str], default_tags: Iterable[str]) -> list[str]:
    merged: list[str] = []
    for source in (topic_tags, default_tags):
        for tag in source:
            normalized = str(tag).strip()
            if normalized and normalized not in merged:
                merged.append(normalized)
    return merged


def _parse_time_local(raw: str) -> time:
    try:
        hour_str, minute_str = raw.split(":", 1)
        hour = int(hour_str)
        minute = int(minute_str)
    except (ValueError, AttributeError) as exc:  # pragma: no cover - defensive
        raise RuntimeError(
            "uploader.time_local должен быть в формате HH:MM"
        ) from exc
    if not (0 <= hour < 24 and 0 <= minute < 60):
        raise RuntimeError("uploader.time_local должен быть валидным временем")
    return time(hour=hour, minute=minute)


def _load_timezone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError as exc:
        raise RuntimeError(f"Не найдена таймзона '{name}'") from exc


def _schedule_requires_timezone(value: str) -> bool:
    try:
        schedule_dt = datetime.fromisoformat(value)
    except ValueError:
        return True
    return schedule_dt.tzinfo is None


def _normalise_schedule(value: str, default_tz: ZoneInfo | None) -> str:
    try:
        schedule_dt = datetime.fromisoformat(value)
    except ValueError as exc:
        raise RuntimeError(f"Некорректный формат schedule: {value}") from exc
    if schedule_dt.tzinfo is None:
        if default_tz is None:
            raise RuntimeError("Для schedule без таймзоны необходимо настроить uploader.timezone")
        schedule_dt = schedule_dt.replace(tzinfo=default_tz)
    return schedule_dt.isoformat()


def _next_occurrence(desired_time: time, tz: ZoneInfo) -> datetime:
    now_local = datetime.now(tz)
    candidate = now_local.replace(
        hour=desired_time.hour,
        minute=desired_time.minute,
        second=0,
        microsecond=0,
    )
    if candidate <= now_local:
        candidate += timedelta(days=1)
    return candidate


def _select_topics(
    topics: Sequence[dict[str, Any]], selection: Sequence[int | str] | str
) -> list[dict[str, Any]]:
    if isinstance(selection, str):
        if selection == "all":
            return list(topics)
        normalized = selection.strip().lower()
        matched = [
            topic
            for topic in topics
            if str(topic.get("title", "")).strip().lower() == normalized
        ]
        if not matched:
            raise ValueError("No matching topics for provided title")
        return matched

    resolved: list[dict[str, Any]] = []
    for selector in selection:
        if isinstance(selector, int):
            if 0 <= selector < len(topics):
                candidate = topics[selector]
                if candidate not in resolved:
                    resolved.append(candidate)
        else:
            normalized = str(selector).strip().lower()
            match = next(
                (
                    topic
                    for topic in topics
                    if str(topic.get("title", "")).strip().lower() == normalized
                ),
                None,
            )
            if match and match not in resolved:
                resolved.append(match)
    if not resolved:
        raise ValueError("No matching topics found for the provided selection")
    return resolved


def build_all(
    settings_path: str,
    topics_path: str,
    selection: Sequence[int | str] | str = "all",
) -> list[dict[str, Any]]:
    """Render selected topics defined in ``topics_path`` using ``settings_path``.

    Returns:
        A list of produced artefacts containing ``path``, ``title``, ``tags`` and ``schedule``.

    Raises:
        TextToSpeechError: If narration synthesis fails for any topic.
        RuntimeError: For invalid configuration or processing errors.
    """

    cfg = _load_config(Path(settings_path))
    topics_all = _load_topics(Path(topics_path))

    if not topics_all:
        return []

    if isinstance(selection, str) and selection == "all":
        topics = topics_all
    else:
        selectors: Sequence[int | str]
        if isinstance(selection, str):
            selectors = [selection]
        elif isinstance(selection, Iterable):
            selectors = list(selection)
        else:
            selectors = []
        topics = _select_topics(topics_all, selectors)

    _ensure_directories()
    load_font(str(cfg.get("font")), int(cfg.get("font_size", 64)))

    resolution = cfg.get("resolution", [1080, 1920])
    if isinstance(resolution, (list, tuple)) and len(resolution) >= 2:
        width, height = int(resolution[0]), int(resolution[1])
    else:
        width, height = 1080, 1920

    produced: list[dict[str, Any]] = []
    manifest_items: list[dict[str, Any]] = []

    uploader_cfg = cfg.get("uploader", {})
    default_timezone_name = str(uploader_cfg.get("timezone", SETTINGS.tz_target))
    default_timezone: ZoneInfo | None = None
    auto_enabled = bool(uploader_cfg.get("auto_schedule_if_missing"))
    auto_time = _parse_time_local(str(uploader_cfg.get("time_local", "21:00"))) if auto_enabled else None
    if auto_enabled or any(
        isinstance(topic.get("schedule"), str)
        and _schedule_requires_timezone(str(topic.get("schedule")))
        for topic in topics
    ):
        default_timezone = _load_timezone(default_timezone_name)

    next_auto_slot = (
        _next_occurrence(auto_time, default_timezone)
        if auto_enabled and auto_time and default_timezone
        else None
    )
    auto_offset_days = 0

    for index, topic in enumerate(topics, start=1):
        title = topic["title"]
        lines = _ensure_lines(topic.get("lines", []), title)
        tags = _merge_tags(topic.get("tags", []), cfg.get("default_tags", []))
        schedule = topic.get("schedule")
        normalized_schedule: str | None
        if isinstance(schedule, str) and schedule.strip():
            normalized_schedule = _normalise_schedule(schedule.strip(), default_timezone)
        elif auto_enabled and next_auto_slot is not None:
            scheduled_dt = next_auto_slot + timedelta(days=auto_offset_days)
            auto_offset_days += 1
            normalized_schedule = scheduled_dt.isoformat()
        else:
            normalized_schedule = None
        script_text = "\n".join(lines)

        slug = _slugify(f"{index}-{title}")
        audio_path = AUDIO_ROOT / f"{slug}.mp3"
        video_path = VIDEO_ROOT / f"{slug}.mp4"

        synth_sync(
            script_text,
            audio_path,
            lang=str(cfg.get("tts_lang", "ru")),
            timeout=float(cfg.get("tts_timeout", 30)),
        )

        assemble_short(
            lines,
            audio_path.as_posix(),
            title,
            video_path.as_posix(),
            fps=int(cfg.get("fps", 30)),
            resolution=(width, height),
        )

        produced_item = {
            "path": video_path.as_posix(),
            "title": title,
            "tags": tags,
            "schedule": normalized_schedule,
        }
        produced.append(produced_item)

        manifest_items.append(
            {
                "title": title,
                "description": script_text,
                "tags": tags,
                "video_path": video_path.as_posix(),
                "audio_path": audio_path.as_posix(),
                "schedule": normalized_schedule,
            }
        )

    MANIFEST_PATH.write_text(
        json.dumps({"items": manifest_items}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return produced


__all__ = ["build_all", "MANIFEST_PATH"]
