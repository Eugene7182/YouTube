"""Utility to seed monthly cartoon/viral topics for YouTube Shorts.

This script can operate offline (saving payload to disk) or online (posting to
``/trends/generate`` when ``BASE_URL`` and ``ADMIN_TOKEN`` are present). It keeps
all generated titles unique, enforces schedule sanity, and mixes prompt
patterns from ``prompts/viral_cartoons.txt`` to build Hook/Setup/Twist lines.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Iterable, List, Sequence

import requests
from zoneinfo import ZoneInfo

PROMPTS_PATH = Path(__file__).resolve().parents[1] / "prompts" / "viral_cartoons.txt"
ET_ZONE = ZoneInfo("America/New_York")
TITLE_MAX_LENGTH = 60
REQUIRED_TAGS = {"#shorts", "#cartoon"}


@dataclass(frozen=True)
class Topic:
    """Single content plan entry."""

    title: str
    lines: List[str]
    tags: List[str]
    schedule: str


@dataclass(frozen=True)
class PromptPattern:
    """Prompt line triplet describing a hook, setup, and twist."""

    hook: str
    setup: str
    twist: str


def parse_args(argv: Iterable[str]) -> argparse.Namespace:
    """Parse CLI arguments."""

    parser = argparse.ArgumentParser(
        description="Generate a month of cartoon/viral YouTube Shorts topics."
    )
    parser.add_argument(
        "--start",
        default=None,
        help="Start date in YYYY-MM-DD (default: tomorrow in America/New_York).",
    )
    parser.add_argument("--days", type=int, default=30, help="Number of days to plan.")
    parser.add_argument(
        "--slots",
        default="09:00,15:00,20:00",
        help="Comma separated ET slots per day (HH:MM).",
    )
    parser.add_argument(
        "--tags",
        default="#shorts,#cartoon,#comedy,#viral",
        help="Comma separated hashtag list.",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="Optional path to dump the generated payload as JSON.",
    )
    return parser.parse_args(list(argv))


def resolve_start_date(start_value: str | None, tz: ZoneInfo) -> date:
    """Resolve the first schedule date.

    If ``start_value`` is provided it must be ``YYYY-MM-DD``. Otherwise the
    function returns tomorrow according to the supplied timezone.
    """

    if start_value:
        trimmed = start_value.strip()
        if trimmed:
            try:
                return datetime.strptime(trimmed, "%Y-%m-%d").date()
            except ValueError as exc:  # pragma: no cover - defensive branch
                raise SystemExit(f"Неверный формат --start: {trimmed}") from exc
    now = datetime.now(timezone.utc).astimezone(tz)
    return (now + timedelta(days=1)).date()


def parse_slots(slots_value: str) -> List[time]:
    """Convert ``HH:MM`` comma separated slots into :class:`datetime.time` list."""

    slots: List[time] = []
    for raw in slots_value.split(","):
        candidate = raw.strip()
        if not candidate:
            continue
        try:
            hours, minutes = map(int, candidate.split(":"))
        except ValueError as exc:  # pragma: no cover - defensive branch
            raise SystemExit(f"Неверный слот: {candidate}") from exc
        slots.append(time(hour=hours, minute=minutes))
    if not slots:
        raise SystemExit("Список слотов пустой.")
    return slots


def normalize_tags(tags_value: str) -> List[str]:
    """Prepare hashtag list ensuring required tags are present."""

    provided = []
    for raw in tags_value.split(","):
        candidate = raw.strip()
        if not candidate:
            continue
        if not candidate.startswith("#"):
            candidate = f"#{candidate}"
        provided.append(candidate)
    final_tags = list(dict.fromkeys(provided))  # preserve order while deduping
    for required in REQUIRED_TAGS:
        if required not in final_tags:
            final_tags.append(required)
    return final_tags


def load_prompt_patterns(path: Path) -> List[PromptPattern]:
    """Load hook/setup/twist patterns from the prompts file."""

    if not path.exists():
        raise SystemExit(f"Файл с паттернами не найден: {path}")
    raw = path.read_text(encoding="utf-8")
    blocks = [block.strip() for block in raw.split("\n\n") if block.strip()]
    patterns: List[PromptPattern] = []
    for block in blocks:
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        mapping: dict[str, str] = {}
        for line in lines:
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            mapping[key.lower()] = value.strip()
        hook = mapping.get("hook")
        setup = mapping.get("setup")
        twist = mapping.get("twist")
        if not (hook and setup and twist):
            continue
        patterns.append(PromptPattern(hook=hook, setup=setup, twist=twist))
    if len(patterns) < 10:
        raise SystemExit("Недостаточно паттернов в prompts/viral_cartoons.txt.")
    return patterns


def shuffle_cycle(values: Sequence[str], rng: random.Random) -> List[str]:
    """Return a shuffled copy for deterministic cycling."""

    pool = list(values)
    rng.shuffle(pool)
    return pool


def ensure_ascii(text: str) -> str:
    """Validate ASCII characters to avoid emoji/extended glyphs."""

    try:
        text.encode("ascii")
    except UnicodeEncodeError as exc:  # pragma: no cover - defensive branch
        raise SystemExit(f"В заголовке недопустимые символы: {text}") from exc
    return text


SUBJECTS = [
    "Jealous Toaster",
    "Sarcastic Microwave",
    "Quantum Spoon",
    "Time Loop Barista",
    "Sneaky Cookie",
    "Prankster Blender",
    "Sentient Sock",
    "Sleepy Elevator",
    "Pet Rock",
    "AI Toaster",
    "Grumpy Fridge",
    "Chatty Vacuum",
    "Daydreaming Lamp",
    "Rebel Cereal Box",
    "Nervous Remote",
    "Heroic Mop",
    "Plotting Hamster",
    "Mystic Coffee Mug",
    "Reluctant Alarm Clock",
    "Teleporting Cat",
    "Paranoid Doorbell",
    "Forgetful Drone",
    "Anxious Skateboard",
    "Gamified Mirror",
    "Bored Traffic Cone",
]

SCENARIOS = [
    "Runs Snack Heist",
    "Loops Monday Again",
    "Sabotages Breakfast",
    "Negotiates With Time",
    "Stages Quantum Prank",
    "Misplaces Gravity",
    "Races Elevator Ghost",
    "Confuses Parallel Self",
    "Breaks Reality Rules",
    "Hosts Midnight Trial",
    "Challenges Cartoon Physics",
    "Hijacks Morning Alarm",
    "Trades Places With Human",
    "Invents Rewind Button",
    "Sells Portal Passes",
    "Tricks Security Cam",
    "Crashes Into Yesterday",
    "Unlocks Secret Pantry",
    "Audits Pocket Universe",
    "Hacks Smart Fridge",
    "Wins Mini Heist",
    "Cancels Future Tuesday",
    "Bargains With Meteor",
    "Cheats Hide and Seek",
    "Delays Gravity Again",
]

SECONDARY_BEATS = [
    "While Gravity Takes Lunch",
    "Under Suspicious Moonlight",
    "Before Breakfast Resets",
    "During Elevator Reboot",
    "Inside Quantum Break Room",
    "With Zero Witnesses",
    "Between Two Tuesdays",
    "During Snack Curfew",
    "Before Coffee Wakes",
    "After Portal Inspection",
]


def compact_title(candidate: str) -> str:
    """Ensure title fits the required length without abrupt cuts."""

    if len(candidate) <= TITLE_MAX_LENGTH:
        return candidate
    words = candidate.split()
    trimmed = words[0]
    for word in words[1:]:
        proposal = f"{trimmed} {word}"
        if len(proposal) > TITLE_MAX_LENGTH:
            break
        trimmed = proposal
    return trimmed[:TITLE_MAX_LENGTH].rstrip(" -")


def build_title_base(rng: random.Random, used_pairs: set[tuple[str, str]]) -> str:
    """Compose a short descriptive base title from curated fragments."""

    for _ in range(20):
        subject = rng.choice(SUBJECTS)
        scenario = rng.choice(SCENARIOS)
        pair = (subject, scenario)
        if pair not in used_pairs:
            used_pairs.add(pair)
            break
    else:  # fallback if all unique pairs consumed
        subject = rng.choice(SUBJECTS)
        scenario = rng.choice(SCENARIOS)
    include_secondary = rng.random() < 0.35
    if include_secondary:
        beat = rng.choice(SECONDARY_BEATS)
        base = f"{subject} {scenario} {beat}"
    else:
        base = f"{subject} {scenario}"
    return compact_title(base)


def make_unique_title(base_title: str, usage: dict[str, int]) -> str:
    """Guarantee unique titles using ``v2``/``v3`` suffixes when necessary."""

    normalized = compact_title(base_title)
    usage.setdefault(normalized, 0)
    usage[normalized] += 1
    count = usage[normalized]
    if count == 1:
        candidate = normalized
    else:
        suffix = f" v{count}"
        trimmed = normalized
        if len(trimmed) + len(suffix) > TITLE_MAX_LENGTH:
            trimmed = trimmed[: TITLE_MAX_LENGTH - len(suffix)].rstrip(" -")
        candidate = f"{trimmed}{suffix}"
    ensure_ascii(candidate)
    if len(candidate) > TITLE_MAX_LENGTH:
        raise SystemExit(f"Не удалось сократить заголовок: {candidate}")
    return candidate


def build_schedule(slot_date: date, slot_time: time, tz: ZoneInfo) -> datetime:
    """Combine ``slot_date`` and ``slot_time`` into an aware UTC datetime."""

    local_dt = datetime.combine(slot_date, slot_time, tzinfo=tz)
    return local_dt.astimezone(timezone.utc)


def generate_topics(
    start_date: date,
    days: int,
    slots: Sequence[time],
    tags: List[str],
    patterns: Sequence[PromptPattern],
) -> List[Topic]:
    """Create content plan covering ``days`` * ``len(slots)`` entries."""

    if days <= 0:
        raise SystemExit("Количество дней должно быть положительным.")

    rng = random.Random(hash((start_date.toordinal(), days, len(slots))))
    hooks = shuffle_cycle([p.hook for p in patterns], rng)
    setups = shuffle_cycle([p.setup for p in patterns], rng)
    twists = shuffle_cycle([p.twist for p in patterns], rng)

    topics: List[Topic] = []
    title_usage: dict[str, int] = {}
    used_pairs: set[tuple[str, str]] = set()
    now_utc = datetime.now(timezone.utc)
    min_allowed = now_utc + timedelta(minutes=60)

    total_slots = days * len(slots)
    for index in range(total_slots):
        day_offset, slot_index = divmod(index, len(slots))
        current_date = start_date + timedelta(days=day_offset)
        slot_time = slots[slot_index]
        schedule_dt = build_schedule(current_date, slot_time, ET_ZONE)
        if schedule_dt < min_allowed:
            raise SystemExit(
                "Расписание должно быть не раньше чем через 60 минут от текущего времени."
            )
        hook = hooks[index % len(hooks)]
        setup = setups[(index + 5) % len(setups)]
        twist = twists[(index + 11) % len(twists)]
        base_title = build_title_base(rng, used_pairs)
        title = make_unique_title(base_title, title_usage)
        schedule_iso = schedule_dt.replace(tzinfo=timezone.utc).isoformat().replace(
            "+00:00", "Z"
        )
        topics.append(
            Topic(
                title=title,
                lines=[hook, setup, twist],
                tags=list(tags),
                schedule=schedule_iso,
            )
        )
    return topics


def build_payload(topics: Sequence[Topic]) -> dict:
    """Convert topics into API payload structure."""

    return {
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


def post_payload(base_url: str, token: str, payload: dict) -> dict:
    """Send payload to the admin API and return JSON response."""

    response = requests.post(
        f"{base_url.rstrip('/')}/trends/generate",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )
    if response.status_code >= 400:
        raise SystemExit(
            f"Ошибка API {response.status_code}: {response.text or response.reason}"
        )
    try:
        return response.json()
    except ValueError as exc:  # pragma: no cover - defensive branch
        raise SystemExit(f"Некорректный JSON от API: {response.text}") from exc


def dump_payload(path: Path, payload: dict) -> None:
    """Write payload to a JSON file with UTF-8 encoding."""

    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main(argv: Iterable[str]) -> None:
    """Script entrypoint."""

    args = parse_args(argv)
    start_date = resolve_start_date(args.start, ET_ZONE)
    slots = parse_slots(args.slots)
    tags = normalize_tags(args.tags)
    patterns = load_prompt_patterns(PROMPTS_PATH)
    topics = generate_topics(start_date, args.days, slots, tags, patterns)
    payload = build_payload(topics)

    base_url = os.getenv("BASE_URL")
    token = os.getenv("ADMIN_TOKEN")
    wrote_to_disk = False
    if base_url and token:
        response_data = post_payload(base_url, token, payload)
        count = response_data.get("count")
        if not isinstance(count, int) or count < len(topics):
            raise SystemExit(
                "API ответило без ожидаемого поля count (или число меньше количества тем)."
            )
        print(
            f"Готово: сгенерировано {len(topics)} тем, API подтвердило {count}.",
            flush=True,
        )
    else:
        default_path = Path(args.out) if args.out else Path("topics_month.json")
        dump_payload(default_path, payload)
        wrote_to_disk = True
        print(
            "BASE_URL/ADMIN_TOKEN не заданы. Payload сохранён в"
            f" {default_path}. Отправьте вручную, когда секреты будут доступны.",
            flush=True,
        )

    if args.out and not wrote_to_disk:
        dump_payload(Path(args.out), payload)
        print(f"Payload дополнительно сохранён в {args.out}.", flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])
