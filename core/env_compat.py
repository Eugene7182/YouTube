"""Helpers for validating inline OAuth environment variables."""

from __future__ import annotations

import json
import os
from typing import Any

DEFAULT_AUTH_URI = "https://accounts.google.com/o/oauth2/auth"
DEFAULT_TOKEN_URI = "https://oauth2.googleapis.com/token"


class OAuthConfigError(RuntimeError):
    """Raised when OAuth client configuration is missing or invalid."""


def _extract_section(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    if "installed" in payload and isinstance(payload["installed"], dict):
        return payload["installed"]
    if "web" in payload and isinstance(payload["web"], dict):
        return payload["web"]
    return payload


def _load_json_from_string(raw: str, source_label: str) -> dict[str, Any]:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise OAuthConfigError(f"{source_label} содержит некорректный JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise OAuthConfigError(f"{source_label} должен быть JSON-объектом")
    return payload


def _load_client_section() -> dict[str, Any]:
    raw_json = os.getenv("YOUTUBE_CLIENT_SECRET_JSON", "").strip()
    if not raw_json:
        raise OAuthConfigError(
            "YOUTUBE_CLIENT_SECRET_JSON не задан: вставьте client_secret.json как inline JSON"
        )
    section = _extract_section(_load_json_from_string(raw_json, "YOUTUBE_CLIENT_SECRET_JSON"))
    client_id = str(section.get("client_id", "")).strip()
    client_secret = str(section.get("client_secret", "")).strip()
    if not client_id or not client_secret:
        raise OAuthConfigError("client_secret.json должен содержать client_id и client_secret")
    section.setdefault("auth_uri", DEFAULT_AUTH_URI)
    section.setdefault("token_uri", DEFAULT_TOKEN_URI)
    redirects = section.get("redirect_uris")
    if isinstance(redirects, list) and redirects:
        section["redirect_uris"] = [str(item).strip() for item in redirects if str(item).strip()]
    else:
        section["redirect_uris"] = ["http://localhost"]
    return section


def ensure_inline_oauth_env() -> None:
    """Validate inline OAuth JSON payloads early and log friendly errors."""

    _ = _load_client_section()
    _ = load_authorized_user_info()  # noqa: F841 - только проверка


def load_authorized_user_info() -> dict[str, Any]:
    raw = os.getenv("YOUTUBE_TOKEN_JSON", "").strip()
    if not raw:
        raise OAuthConfigError(
            "YOUTUBE_TOKEN_JSON не задан: вставьте payload из OAuth Playground с refresh_token"
        )
    payload = _load_json_from_string(raw, "YOUTUBE_TOKEN_JSON")
    refresh_token = str(
        payload.get("refresh_token") or payload.get("refreshToken") or ""
    ).strip()
    if not refresh_token:
        raise OAuthConfigError("YOUTUBE_TOKEN_JSON должен содержать refresh_token")

    client_section = _load_client_section()
    payload["client_id"] = client_section.get("client_id")
    payload["client_secret"] = client_section.get("client_secret")
    payload["token_uri"] = payload.get("token_uri") or client_section.get("token_uri", DEFAULT_TOKEN_URI)
    scopes = payload.get("scopes")
    if not scopes:
        payload["scopes"] = ["https://www.googleapis.com/auth/youtube.upload"]
    payload.setdefault("type", "authorized_user")
    return payload


def get_oauth_client_config(redirect_uri: str | None = None) -> dict[str, Any]:
    section = _load_client_section()
    redirect = redirect_uri or section.get("redirect_uris", ["http://localhost"])[0]
    config = {
        "client_id": section.get("client_id"),
        "client_secret": section.get("client_secret"),
        "auth_uri": section.get("auth_uri", DEFAULT_AUTH_URI),
        "token_uri": section.get("token_uri", DEFAULT_TOKEN_URI),
        "redirect_uris": [redirect],
    }
    if redirect_uri:
        config["redirect_uris"] = [redirect_uri]
    return {"web": config}


__all__ = [
    "DEFAULT_AUTH_URI",
    "DEFAULT_TOKEN_URI",
    "OAuthConfigError",
    "ensure_inline_oauth_env",
    "get_oauth_client_config",
    "load_authorized_user_info",
]
