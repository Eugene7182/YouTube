"""Utilities for uploading rendered Shorts to YouTube."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Sequence

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from core.env_compat import ensure_legacy_oauth_env

YOUTUBE_SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
TOKEN_URI = os.getenv("GOOGLE_TOKEN_URI", "https://oauth2.googleapis.com/token")


class UploadConfigurationError(RuntimeError):
    """Raised when OAuth credentials are missing or invalid."""


def get_credentials() -> Credentials:
    """Load OAuth credentials, refreshing the access token if needed."""

    ensure_legacy_oauth_env()

    client_id = os.getenv("YT_CLIENT_ID", "").strip()
    client_secret = os.getenv("YT_CLIENT_SECRET", "").strip()
    refresh_token = os.getenv("YT_REFRESH_TOKEN", "").strip()

    if not (client_id and client_secret and refresh_token):
        raise UploadConfigurationError("YouTube OAuth credentials are not fully configured")

    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri=os.getenv("GOOGLE_TOKEN_URI", TOKEN_URI),
        client_id=client_id,
        client_secret=client_secret,
        scopes=YOUTUBE_SCOPES,
    )
    creds.refresh(Request())
    return creds


def upload_video(
    video_path: str | Path,
    title: str,
    description: str,
    tags: Sequence[str],
    *,
    category_id: str = "24",
    privacy_status: str = "private",
) -> dict[str, str]:
    """Upload a single video file to YouTube."""

    credentials = get_credentials()
    youtube = build("youtube", "v3", credentials=credentials, cache_discovery=False)

    tags_unique: list[str] = []
    for tag in tags:
        normalized = str(tag).strip()
        if normalized and normalized not in tags_unique:
            tags_unique.append(normalized)

    body = {
        "snippet": {
            "title": title,
            "description": description[:4800],
            "tags": tags_unique,
            "categoryId": str(category_id),
        },
        "status": {"privacyStatus": privacy_status},
    }

    media = MediaFileUpload(str(video_path), chunksize=-1, resumable=True)
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
    response = request.execute()

    return {"videoId": response.get("id"), "title": title}


__all__ = ["upload_video", "UploadConfigurationError", "get_credentials"]
