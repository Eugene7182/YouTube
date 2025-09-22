"""Scheduler utilities for monthly Shorts automation."""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, time, timedelta, timezone
from itertools import cycle, islice
from pathlib import Path
from typing import Any, Callable, Iterable, List

import yaml
from zoneinfo import ZoneInfo

from core.generate import MANIFEST_PATH, build_all
from core.upload import upload_manifest

logger = logging.getLogger(__name__)

ALMATY_TZ = "Asia/Almaty"
DEFAULT_SLOTS = ["09:00", "15:00", "21:00"]
DEFAULT_LINES = ["Hook", "Setup", "Twist"]
DEFAULT_TAGS = ["#shorts", "#cartoon", "#comedy", "#viral"]
VALID_STATUSES = {"queued", "rendered", "uploaded", "failed"}
DEFAULT_DAYS = 30

SCHEDULE_FILE = Path("data/schedule.json")
TEMP_TOPICS_PATH = Path("data/scheduler_topic.yaml")
DEFAULT_CONFIG_PATH = Path("config.yaml")


def _topic_model_cls():
    """Import TopicModel lazily to avoid circular import with ``server``."""

    from server import TopicModel  # local import to prevent circular dependency

    return TopicModel


def _parse_slot(slot: str) -> time:
    try:
        hour_str, minute_str = slot.split(":", 1)
        hour = int(hour_str)
        minute = int(minute_str)
    except (ValueError, AttributeError) as exc:
        raise ValueError(f"Invalid slot format: {slot}") from exc
    if not (0 <= hour < 24 and 0 <= minute < 60):
        raise ValueError(f"Slot must be HH:MM within 24h: {slot}")
    return time(hour=hour, minute=minute)


def _ensure_iterable(items: Iterable[str], total: int, fill: str) -> List[str]:
    buffer = [str(item).strip() for item in items if str(item).strip()]
    if not buffer:
        buffer = [fill.format(index=i) for i in range(1, total + 1)]
    if len(buffer) >= total:
        return buffer[:total]
    return list(islice(cycle(buffer), total))


def _default_topics(total: int) -> List[str]:
    return [f"Crazy Cat Fails #{index}" for index in range(1, total + 1)]


def _format_schedule(dt_local: datetime) -> str:
    dt_utc = dt_local.astimezone(timezone.utc).replace(microsecond=0)
    return dt_utc.isoformat().replace("+00:00", "Z")


def make_month_plan(
    start_date_local: date,
    topics_seed: list[str],
    slots_local: list[str] | None = None,
) -> list["TopicModel"]:
    """Generate a 30-day plan with three daily slots by default."""

    slots = slots_local or list(DEFAULT_SLOTS)
    if not slots:
        slots = list(DEFAULT_SLOTS)
    tz_local = ZoneInfo(ALMATY_TZ)
    total_slots = len(slots) * DEFAULT_DAYS

    topics_input = [str(topic).strip() for topic in topics_seed if str(topic).strip()]
    if not topics_input:
        topics_input = _default_topics(total_slots)
    else:
        topics_input = _ensure_iterable(topics_input, total_slots, "Topic #{index}")

    TopicModel = _topic_model_cls()
    plan: list[TopicModel] = []

    topic_iter = iter(topics_input)
    for day_offset in range(DEFAULT_DAYS):
        day_local = start_date_local + timedelta(days=day_offset)
        for slot in slots:
            slot_time = _parse_slot(slot)
            dt_local = datetime.combine(day_local, slot_time, tzinfo=tz_local)
            schedule_iso = _format_schedule(dt_local)
            try:
                title = next(topic_iter)
            except StopIteration:  # pragma: no cover - defensive
                title = f"Topic #{day_offset * len(slots) + 1}"
            plan.append(
                TopicModel(
                    title=title,
                    lines=list(DEFAULT_LINES),
                    tags=list(DEFAULT_TAGS),
                    schedule=schedule_iso,
                )
            )

    return plan


def load_schedule() -> dict[str, Any]:
    """Load schedule JSON or return an empty structure."""

    if not SCHEDULE_FILE.exists():
        return {"items": []}
    try:
        raw = json.loads(SCHEDULE_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        logger.warning("schedule.json is not valid JSON; starting with empty queue")
        return {"items": []}
    if not isinstance(raw, dict):
        return {"items": []}
    items_raw = raw.get("items")
    if not isinstance(items_raw, list):
        return {"items": []}

    items: list[dict[str, Any]] = []
    for entry in items_raw:
        if not isinstance(entry, dict):
            continue
        title = str(entry.get("title", "")).strip()
        schedule_str = str(entry.get("schedule", "")).strip()
        if not title or not schedule_str:
            continue
        status = str(entry.get("status", "queued")).strip() or "queued"
        if status not in VALID_STATUSES:
            status = "queued"
        record = {
            "title": title,
            "schedule": schedule_str,
            "status": status,
            "lines": entry.get("lines") or list(DEFAULT_LINES),
            "tags": entry.get("tags") or list(DEFAULT_TAGS),
        }
        if "error" in entry and entry["error"]:
            record["error"] = str(entry["error"])
        items.append(record)
    items.sort(key=lambda item: item["schedule"])
    return {"items": items}


def save_schedule(items: Iterable[dict[str, Any]]) -> None:
    """Persist schedule items to ``data/schedule.json``."""

    payload = {"items": []}
    for entry in items:
        if not isinstance(entry, dict):
            continue
        title = str(entry.get("title", "")).strip()
        schedule = str(entry.get("schedule", "")).strip()
        if not title or not schedule:
            continue
        status = str(entry.get("status", "queued")).strip() or "queued"
        if status not in VALID_STATUSES:
            status = "queued"
        payload["items"].append(
            {
                "title": title,
                "schedule": schedule,
                "status": status,
                "lines": entry.get("lines") or list(DEFAULT_LINES),
                "tags": entry.get("tags") or list(DEFAULT_TAGS),
                **({"error": str(entry.get("error"))} if entry.get("error") else {}),
            }
        )

    SCHEDULE_FILE.parent.mkdir(parents=True, exist_ok=True)
    SCHEDULE_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _parse_schedule(value: str) -> datetime | None:
    if not value:
        return None
    raw = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        logger.warning("Invalid schedule entry encountered: %s", value)
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _render_topic(title: str, lines: list[str], tags: list[str], schedule: str) -> list[dict[str, Any]]:
    temp_payload = [
        {
            "title": title,
            "lines": list(lines) or list(DEFAULT_LINES),
            "tags": list(tags) or list(DEFAULT_TAGS),
            "schedule": schedule,
        }
    ]
    TEMP_TOPICS_PATH.parent.mkdir(parents=True, exist_ok=True)
    TEMP_TOPICS_PATH.write_text(
        yaml.safe_dump(temp_payload, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    try:
        produced = build_all(str(DEFAULT_CONFIG_PATH), str(TEMP_TOPICS_PATH), "all")
    finally:
        try:
            TEMP_TOPICS_PATH.unlink()
        except FileNotFoundError:
            pass
    return produced


def queue_due(
    limit: int = 1,
    upload: bool = True,
    dry_run: bool = False,
    validate_upload_env: Callable[[], None] | None = None,
) -> dict[str, Any]:
    """Pick queued topics with schedule <= now and build/upload them."""

    schedule_data = load_schedule()
    items = schedule_data.get("items", [])
    if not isinstance(items, list) or not items:
        return {"picked": 0, "produced": [], "errors": []}

    try:
        limit_value = int(limit)
    except (TypeError, ValueError):
        limit_value = 1
    if limit_value <= 0:
        return {"picked": 0, "produced": [], "errors": []}

    now_utc = datetime.now(timezone.utc)
    due_indices: list[int] = []
    for idx, entry in enumerate(items):
        if not isinstance(entry, dict):
            continue
        if entry.get("status") != "queued":
            continue
        schedule_dt = _parse_schedule(str(entry.get("schedule", "")))
        if schedule_dt is None:
            continue
        if schedule_dt <= now_utc:
            due_indices.append(idx)
        if len(due_indices) >= limit_value:
            break

    if not due_indices:
        return {"picked": 0, "produced": [], "errors": []}

    produced_summary: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    for idx in due_indices:
        entry = items[idx]
        title = entry.get("title", "Untitled")
        schedule_str = entry.get("schedule", "")
        lines = entry.get("lines") or list(DEFAULT_LINES)
        tags = entry.get("tags") or list(DEFAULT_TAGS)

        try:
            produced = _render_topic(str(title), list(lines), list(tags), str(schedule_str))
            if not produced:
                raise RuntimeError("Generation produced no artefacts")
            entry["status"] = "rendered"
            entry.pop("error", None)
            produced_item = {
                "title": title,
                "schedule": schedule_str,
                "video": produced[0].get("path") if isinstance(produced[0], dict) else None,
                "status": entry["status"],
            }

            upload_results: list[dict[str, Any]] = []
            if upload and not dry_run:
                if validate_upload_env is not None:
                    validate_upload_env()
                upload_results = upload_manifest(str(MANIFEST_PATH), str(DEFAULT_CONFIG_PATH))
                produced_item["upload"] = upload_results
                if not upload_results:
                    entry["status"] = "rendered"
                elif all(result.get("status") == "uploaded" for result in upload_results if isinstance(result, dict)):
                    entry["status"] = "uploaded"
                else:
                    entry["status"] = "failed"
                    entry["error"] = json.dumps(upload_results, ensure_ascii=False)
                    errors.append({"title": title, "error": entry["error"]})
            else:
                produced_item["upload"] = []

            produced_item["status"] = entry["status"]
            produced_summary.append(produced_item)
        except Exception as exc:  # pragma: no cover - defensive path depends on runtime env
            logger.exception("queue_due failed for %s", title)
            entry["status"] = "failed"
            entry["error"] = str(exc)
            errors.append({"title": title, "error": str(exc)})
        finally:
            items[idx] = entry

    save_schedule(items)

    return {"picked": len(due_indices), "produced": produced_summary, "errors": errors}


__all__ = [
    "ALMATY_TZ",
    "make_month_plan",
    "load_schedule",
    "save_schedule",
    "queue_due",
]
