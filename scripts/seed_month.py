"""Скрипт автоматической генерации контент-плана на месяц."""
from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Iterable, List

import requests

TITLE_TEMPLATES = [
    "Cartoon chaos",
    "Unexpected punchline",
    "Mini comedy sketch",
    "Animated prank",
    "Plot twist incoming",
    "Super short story",
    "Daily laugh dose",
    "Ridiculous rewind",
    "Speedrun gag",
    "Lo-fi giggle"
]


def parse_args(argv: Iterable[str]) -> argparse.Namespace:
    """Разбор аргументов командной строки."""
    parser = argparse.ArgumentParser(description="Сформировать и загрузить 30-дневный план тем.")
    parser.add_argument(
        "--start",
        default=None,
        help="Дата первого слота в формате YYYY-MM-DD (по умолчанию завтра по ET).",
    )
    parser.add_argument("--days", type=int, default=30, help="Количество дней для генерации тем.")
    parser.add_argument(
        "--slots",
        default="09:00,15:00,20:00",
        help="Список временных слотов через запятую (формат HH:MM по ET).",
    )
    parser.add_argument(
        "--tags",
        default="#shorts,#cartoon,#comedy",
        help="Теги через запятую (с символами #, без пробелов).",
    )
    return parser.parse_args(argv)


@dataclass(frozen=True)
class Topic:
    """Модель генерируемой темы."""

    title: str
    lines: List[str]
    tags: List[str]
    schedule: str


def ensure_environment() -> tuple[str, str]:
    """Считывает переменные окружения и валидирует их наличие."""
    base_url = os.getenv("BASE_URL")
    token = os.getenv("ADMIN_TOKEN")
    if not base_url:
        sys.exit("Переменная BASE_URL не задана.")
    if not token:
        sys.exit("Переменная ADMIN_TOKEN не задана.")
    return base_url.rstrip("/"), token


def nth_weekday(year: int, month: int, weekday: int, occurrence: int) -> date:
    """Возвращает дату n-го указанного дня недели в месяце."""
    first_day = date(year, month, 1)
    first_weekday = first_day.weekday()
    delta_days = (weekday - first_weekday) % 7 + 7 * (occurrence - 1)
    return first_day + timedelta(days=delta_days)


def et_utc_offset(current_date: date) -> int:
    """Возвращает смещение ET относительно UTC для указанной даты."""
    dst_start = nth_weekday(current_date.year, 3, 6, 2)  # вторая воскресенье марта
    dst_end = nth_weekday(current_date.year, 11, 6, 1)  # первое воскресенье ноября
    if dst_start <= current_date < dst_end:
        return -4
    return -5


def convert_utc_to_et(now_utc: datetime) -> datetime:
    """Переводит время UTC в ET с учётом переходов на летнее время."""
    for offset in (-4, -5):
        candidate = now_utc + timedelta(hours=offset)
        if et_utc_offset(candidate.date()) == offset:
            return candidate.replace(tzinfo=timezone(timedelta(hours=offset)))
    offset = -5
    fallback = now_utc + timedelta(hours=offset)
    return fallback.replace(tzinfo=timezone(timedelta(hours=offset)))


def resolve_default_start(start_arg: str | None) -> date:
    """Определяет стартовую дату, используя аргумент либо завтра по ET."""
    if start_arg:
        value = start_arg.strip()
        if value:
            try:
                return datetime.strptime(value, "%Y-%m-%d").date()
            except ValueError as exc:
                raise SystemExit(f"Неверный формат --start: {value}") from exc
    now_et = convert_utc_to_et(datetime.now(timezone.utc))
    return now_et.date() + timedelta(days=1)


def parse_slots(slots_str: str) -> List[time]:
    """Преобразует строку слотов во временные объекты."""
    slots: List[time] = []
    for raw in slots_str.split(","):
        trimmed = raw.strip()
        if not trimmed:
            continue
        try:
            hour, minute = map(int, trimmed.split(":"))
        except ValueError as exc:
            raise SystemExit(f"Неверный слот: {trimmed}") from exc
        slots.append(time(hour=hour, minute=minute))
    if not slots:
        raise SystemExit("Список слотов пустой.")
    return slots


def parse_tags(tags_str: str) -> List[str]:
    """Разбивает строку тегов на список."""
    tags = [tag.strip() for tag in tags_str.split(",") if tag.strip()]
    if not tags:
        raise SystemExit("Необходимо указать хотя бы один тег.")
    return tags


def build_schedule(slot_date: date, slot_time: time) -> str:
    """Формирует ISO-строку расписания с часовым поясом ET."""
    offset_hours = et_utc_offset(slot_date)
    tz = timezone(timedelta(hours=offset_hours))
    scheduled = datetime.combine(slot_date, slot_time, tzinfo=tz)
    return scheduled.isoformat()


def generate_topics(start_date: date, days: int, slots: List[time], tags: List[str]) -> List[Topic]:
    """Генерирует список тем по дням и слотам."""
    topics: List[Topic] = []
    template_count = len(TITLE_TEMPLATES)
    total_slots = days * len(slots)
    for index in range(total_slots):
        day_offset, slot_index = divmod(index, len(slots))
        current_date = start_date + timedelta(days=day_offset)
        slot_time = slots[slot_index]
        template = TITLE_TEMPLATES[index % template_count]
        title = f"{template} #{index + 1:03d}"
        schedule = build_schedule(current_date, slot_time)
        topics.append(Topic(title=title, lines=["Hook", "Setup", "Twist"], tags=tags, schedule=schedule))
    return topics


def post_topics(base_url: str, token: str, topics: List[Topic]) -> int:
    """Отправляет темы в API и возвращает количество, указанное сервисом."""
    payload = {
        "topics": [
            {
                "title": topic.title,
                "lines": topic.lines,
                "tags": topic.tags,
                "schedule": topic.schedule,
            }
            for topic in topics
        ]
    }
    response = requests.post(
        f"{base_url}/trends/generate",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )
    if response.status_code >= 400:
        message = response.text or response.reason
        sys.exit(f"Ошибка API {response.status_code}: {message}")
    try:
        data = response.json()
    except ValueError as exc:
        raise SystemExit(f"Некорректный JSON от API: {response.text}") from exc
    count = data.get("count")
    if not isinstance(count, int) or count < 1:
        raise SystemExit(f"API вернуло неожиданный ответ: {data}")
    return count


def main(argv: Iterable[str]) -> None:
    """Точка входа скрипта."""
    args = parse_args(argv)
    start_date = resolve_default_start(args.start)
    if args.days <= 0:
        sys.exit("Количество дней должно быть положительным.")
    slots = parse_slots(args.slots)
    tags = parse_tags(args.tags)

    base_url, token = ensure_environment()
    topics = generate_topics(start_date, args.days, slots, tags)
    count = post_topics(base_url, token, topics)
    print(f"Готово: сгенерировано {len(topics)} тем, API подтвердило {count}.")


if __name__ == "__main__":
    main(sys.argv[1:])
