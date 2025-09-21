"""YouTube upload helpers with retries and dry-run support."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

from core.env_compat import OAuthConfigError, load_authorized_user_info
from core.settings import get_settings

YOUTUBE_SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
RETRIABLE_STATUS = {429, 500, 502, 503, 504}
MAX_RETRIES = 5

logger = logging.getLogger(__name__)


class UploadConfigurationError(RuntimeError):
    """Raised when OAuth credentials are missing or invalid."""


def _build_credentials() -> Credentials:
    try:
        info = load_authorized_user_info()
    except OAuthConfigError as exc:  # pragma: no cover - validated via dedicated tests
        raise UploadConfigurationError(str(exc)) from exc

    scopes = info.get("scopes") or YOUTUBE_SCOPES
    credentials = Credentials.from_authorized_user_info(info, scopes=scopes)
    if not credentials.valid:
        credentials.refresh(Request())
    return credentials


def upload_video(
    video_path: str | Path,
    title: str,
    description: str,
    tags: Sequence[str],
    *,
    category_id: str = "24",
    privacy_status: str = "private",
    publish_at: datetime | None = None,
    dry_run: bool | None = None,
    max_retries: int = MAX_RETRIES,
) -> dict[str, str]:
    """Upload a single video file to YouTube."""

    settings = get_settings()
    if dry_run is None:
        dry_run = settings.dry_run

    tags_unique: list[str] = []
    for tag in tags:
        normalized = str(tag).strip()
        if normalized and normalized not in tags_unique:
            tags_unique.append(normalized)

    status_payload = {"privacyStatus": privacy_status}
    if publish_at is not None:
        publish_utc = publish_at.astimezone(timezone.utc)
        status_payload["publishAt"] = publish_utc.isoformat().replace("+00:00", "Z")

    body = {
        "snippet": {
            "title": title,
            "description": description[:4900],
            "tags": tags_unique,
            "categoryId": str(category_id),
        },
        "status": status_payload,
    }

    if dry_run:
        logger.info("YouTube upload dry-run", extra={"title": title, "body": body})
        return {"videoId": "dry-run", "title": title, "status": "dry-run"}

    credentials = _build_credentials()
    youtube = build("youtube", "v3", credentials=credentials, cache_discovery=False)
    media = MediaFileUpload(str(video_path), chunksize=-1, resumable=True)

    attempt = 0
    while True:
        try:
            request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
            response = request.execute()
            video_id = response.get("id", "")
            logger.info("YouTube upload success", extra={"title": title, "videoId": video_id})
            return {"videoId": video_id, "title": title, "status": "uploaded"}
        except HttpError as exc:  # pragma: no cover - network interaction
            status = getattr(exc.resp, "status", None)
            if status in RETRIABLE_STATUS and attempt < max_retries:
                sleep_for = min(60, 2 ** attempt)
                logger.warning(
                    "YouTube upload retry", extra={"title": title, "status": status, "retry_in": sleep_for}
                )
                time.sleep(sleep_for)
                attempt += 1
                continue
            logger.error("YouTube upload failed", exc_info=True)
            raise


def get_credentials() -> Credentials:
    """Expose credential builder for compatibility helpers."""

    return _build_credentials()


__all__ = ["upload_video", "UploadConfigurationError", "get_credentials"]
