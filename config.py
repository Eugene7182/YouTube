from __future__ import annotations

import os
from dataclasses import dataclass
from zoneinfo import ZoneInfo


def _env(name: str, default: str | None = None) -> str | None:
    v = os.getenv(name)
    if v is None or v == "":
        return default
    return v


def _env_int(name: str, default: int) -> int:
    try:
        return int(_env(name, str(default)))
    except Exception:
        return default


def _env_list(name: str, default: list[str]) -> list[str]:
    raw = _env(name)
    if not raw:
        return default
    return [x.strip() for x in raw.split(",") if x.strip()]


@dataclass(frozen=True)
class Settings:
    """Typed application settings with safe defaults for Render environment."""

    # Автопилот
    AUTO_ON: bool = (_env("AUTO_ON", "true").lower() == "true")
    TIMEZONE: str = _env("TIMEZONE", "Asia/Almaty") or "Asia/Almaty"
    DAILY_SLOTS: int = _env_int("DAILY_SLOTS", 3)
    AUTO_TIMES: list[str] = _env_list("AUTO_TIMES", ["10:05", "16:05", "21:05"])
    CONTENT_PLAN_PATH: str = _env("CONTENT_PLAN_PATH", "content/cats/calendar.csv") or "content/cats/calendar.csv"

    # YouTube
    YOUTUBE_TOKEN_JSON: str = _env("YOUTUBE_TOKEN_JSON", "") or ""
    YOUTUBE_UPLOAD_PRIVACY: str = _env("YOUTUBE_UPLOAD_PRIVACY", "public") or "public"

    # Keep-alive (внешний пинг предпочтительнее, но поддержим и внутренний)
    PING_URL: str | None = _env("PING_URL", None)

    @property
    def tz(self) -> ZoneInfo:
        """Return configured timezone instance."""

        return ZoneInfo(self.TIMEZONE)


settings = Settings()
