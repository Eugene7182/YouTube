"""Metadata and media validators for Shorts automation."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

try:
    from moviepy import VideoFileClip
except ImportError:  # pragma: no cover - fallback for MoviePy<2.0
    from moviepy.editor import VideoFileClip

TITLE_LIMIT = 100
DESCRIPTION_LIMIT = 4900
MAX_TAGS = 3
MIN_TAGS = 1
ASPECT_RATIO = 9 / 16
ASPECT_TOLERANCE = 0.03
MAX_DURATION_SECONDS = 60.0


@dataclass(slots=True)
class MetadataPayload:
    """Normalized metadata ready for upload."""

    title: str
    description: str
    tags: list[str]
    hashtags: list[str]


@dataclass(slots=True)
class VideoInspection:
    """Information about a rendered video file."""

    duration: float
    width: int
    height: int

    @property
    def aspect_ratio(self) -> float:
        return 0.0 if self.height == 0 else self.width / self.height


def _normalize_title(title: str) -> str:
    normalized = " ".join(title.strip().split())
    if len(normalized) > TITLE_LIMIT:
        normalized = normalized[:TITLE_LIMIT].rstrip()
    if not normalized:
        raise ValueError("Title must not be empty")
    return normalized


def _normalize_description(description: str, hashtags: list[str]) -> str:
    normalized = description.strip()
    if hashtags:
        hashtags_block = " ".join(hashtags)
        if hashtags_block not in normalized:
            if normalized:
                normalized = f"{normalized}\n\n{hashtags_block}"
            else:
                normalized = hashtags_block
    if len(normalized) > DESCRIPTION_LIMIT:
        normalized = normalized[:DESCRIPTION_LIMIT].rstrip()
    return normalized


def _normalize_tag(raw: str) -> str | None:
    cleaned = re.sub(r"[^0-9a-zA-Z]+", "", raw).lower()
    if not cleaned:
        return None
    return cleaned


def normalize_metadata(title: str, description: str, tags: Iterable[str]) -> MetadataPayload:
    """Return sanitized metadata enforcing YouTube Shorts constraints."""

    normalized_tags: list[str] = []
    seen: set[str] = set()
    for tag in tags:
        normalized = _normalize_tag(str(tag))
        if not normalized:
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        normalized_tags.append(normalized)
        if len(normalized_tags) >= MAX_TAGS:
            break

    if len(normalized_tags) < MIN_TAGS:
        raise ValueError("At least one hashtag is required")

    hashtags = [f"#{tag}" for tag in normalized_tags]
    normalized_title = _normalize_title(title)
    normalized_description = _normalize_description(description, hashtags)

    return MetadataPayload(
        title=normalized_title,
        description=normalized_description,
        tags=normalized_tags,
        hashtags=hashtags,
    )


def inspect_video(path: str | Path) -> VideoInspection:
    """Collect duration and size information for a rendered video."""

    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"Video file not found: {file_path}")
    with VideoFileClip(file_path.as_posix()) as clip:
        duration = float(clip.duration or 0.0)
        width, height = clip.size
    return VideoInspection(duration=duration, width=int(width), height=int(height))


def validate_video(info: VideoInspection) -> None:
    """Validate Shorts-specific constraints for a video file."""

    if info.duration > MAX_DURATION_SECONDS + 0.25:
        raise ValueError("Длительность шорта должна быть <= 60 секунд")
    if info.height <= 0 or info.width <= 0:
        raise ValueError("Некорректное разрешение видео")
    if info.height <= info.width:
        raise ValueError("Шорт должен быть вертикальным (9:16)")
    if abs(info.aspect_ratio - ASPECT_RATIO) > ASPECT_TOLERANCE:
        raise ValueError("Соотношение сторон должно быть близко к 9:16")


__all__ = [
    "MetadataPayload",
    "VideoInspection",
    "normalize_metadata",
    "inspect_video",
    "validate_video",
]
