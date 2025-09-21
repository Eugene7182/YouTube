"""Video generation pipeline orchestrator."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Iterable

import yaml

from build_short import assemble_short, load_font
from tts import synth_sync

OUTPUT_ROOT = Path("data/output")
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
    # Environment overrides
    default_tags_env = os.getenv("DEFAULT_TAGS", "").strip()
    if default_tags_env:
        cfg["default_tags"] = [tag.strip() for tag in default_tags_env.split(",") if tag.strip()]
    cfg.setdefault("default_tags", [])
    cfg.setdefault("tts_lang", "ru")
    cfg.setdefault("tts_timeout", 30)
    cfg.setdefault("fps", 30)
    cfg.setdefault("resolution", [1080, 1920])
    cfg.setdefault("font", "DejaVuSans.ttf")
    cfg.setdefault("font_size", 64)
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


def build_all(cfg_path: str, topics_path: str) -> list[dict[str, Any]]:
    """Render all topics defined in ``topics_path`` using configuration from ``cfg_path``.

    Returns:
        A list of produced artefacts containing ``path``, ``title``, ``tags`` and ``schedule``.

    Raises:
        TextToSpeechError: If narration synthesis fails for any topic.
        RuntimeError: For invalid configuration or processing errors.
    """

    cfg = _load_config(Path(cfg_path))
    topics = _load_topics(Path(topics_path))

    if not topics:
        return []

    _ensure_directories()
    load_font(str(cfg.get("font")), int(cfg.get("font_size", 64)))

    resolution = cfg.get("resolution", [1080, 1920])
    if isinstance(resolution, (list, tuple)) and len(resolution) >= 2:
        width, height = int(resolution[0]), int(resolution[1])
    else:
        width, height = 1080, 1920

    produced: list[dict[str, Any]] = []
    manifest_items: list[dict[str, Any]] = []

    for index, topic in enumerate(topics, start=1):
        title = topic["title"]
        lines = _ensure_lines(topic.get("lines", []), title)
        tags = topic.get("tags") or cfg.get("default_tags", [])
        schedule = topic.get("schedule")
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
            "schedule": schedule,
        }
        produced.append(produced_item)

        manifest_items.append(
            {
                "title": title,
                "description": script_text,
                "tags": tags,
                "video_path": video_path.as_posix(),
                "audio_path": audio_path.as_posix(),
                "schedule": schedule,
            }
        )

    MANIFEST_PATH.write_text(
        json.dumps({"items": manifest_items}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return produced


__all__ = ["build_all", "MANIFEST_PATH"]
