"""Scheduling helpers for converting human-readable slots into UTC."""

from __future__ import annotations

from datetime import datetime, time, timezone
from typing import Tuple

from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

TZ_ALIASES = {
    "ET": "America/New_York",
    "EST": "America/New_York",
    "EDT": "America/New_York",
    "UTC": "UTC",
}


class ScheduleParseError(ValueError):
    """Raised when a human-readable schedule cannot be parsed."""


def _resolve_timezone(label: str, default_tz: str) -> ZoneInfo:
    candidate = TZ_ALIASES.get(label.upper(), label) if label else default_tz
    try:
        return ZoneInfo(candidate)
    except ZoneInfoNotFoundError as exc:  # pragma: no cover - misconfiguration
        raise ScheduleParseError(f"Не найдена таймзона '{candidate}'") from exc


def parse_slot(slot: str, default_tz: str) -> Tuple[time, ZoneInfo]:
    """Parse "HH:MM <TZ>" notation into a ``time`` and timezone."""

    if not slot:
        raise ScheduleParseError("Пустой слот расписания")
    parts = slot.strip().split()
    hhmm = parts[0]
    tz_part = parts[1] if len(parts) > 1 else default_tz
    try:
        hour_str, minute_str = hhmm.split(":", 1)
        hour = int(hour_str)
        minute = int(minute_str)
    except (ValueError, AttributeError) as exc:
        raise ScheduleParseError("Слот должен быть в формате HH:MM [TZ]") from exc
    if not (0 <= hour < 24 and 0 <= minute < 60):
        raise ScheduleParseError("Часы и минуты должны быть в допустимом диапазоне")
    tz = _resolve_timezone(tz_part, default_tz)
    return time(hour=hour, minute=minute), tz


def combine_date_slot(date_str: str, slot: str, default_tz: str) -> datetime:
    """Combine a YYYY-MM-DD string with a slot definition into a datetime."""

    try:
        date_base = datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError as exc:
        raise ScheduleParseError("Дата должна быть в формате YYYY-MM-DD") from exc
    slot_time, tz = parse_slot(slot, default_tz)
    return datetime(
        year=date_base.year,
        month=date_base.month,
        day=date_base.day,
        hour=slot_time.hour,
        minute=slot_time.minute,
        tzinfo=tz,
    )


def to_utc_iso(date_str: str, slot: str, default_tz: str) -> str:
    """Convert human-friendly slot to UTC ISO string."""

    scheduled = combine_date_slot(date_str, slot, default_tz)
    return scheduled.astimezone(timezone.utc).isoformat()


__all__ = ["ScheduleParseError", "parse_slot", "combine_date_slot", "to_utc_iso"]
