"""Helpers for reconciling legacy OAuth environment variables."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

DEFAULT_AUTH_URI = "https://accounts.google.com/o/oauth2/auth"
DEFAULT_TOKEN_URI = os.getenv("GOOGLE_TOKEN_URI", "https://oauth2.googleapis.com/token")


class OAuthConfigError(RuntimeError):
    """Raised when OAuth client configuration is missing or invalid."""


def _extract_section(payload: dict[str, Any]) -> dict[str, Any]:
    """Return the most relevant section from a legacy client secret payload."""

    if not isinstance(payload, dict):
        return {}
    if "web" in payload and isinstance(payload["web"], dict):
        return payload["web"]
    if "installed" in payload and isinstance(payload["installed"], dict):
        return payload["installed"]
    return payload


def _normalise_client_config(section: dict[str, Any], redirect_uri: str | None) -> dict[str, Any]:
    config: dict[str, Any] = {
        "client_id": str(section.get("client_id", "")).strip(),
        "client_secret": str(section.get("client_secret", "")).strip(),
        "auth_uri": str(
            section.get("auth_uri")
            or os.getenv("GOOGLE_AUTH_URI", DEFAULT_AUTH_URI)
            or DEFAULT_AUTH_URI
        ).strip(),
        "token_uri": str(
            section.get("token_uri")
            or os.getenv("GOOGLE_TOKEN_URI", DEFAULT_TOKEN_URI)
            or DEFAULT_TOKEN_URI
        ).strip(),
    }
    redirects = section.get("redirect_uris")
    if isinstance(redirects, (list, tuple)):
        redirect_list = [str(item).strip() for item in redirects if str(item).strip()]
    elif isinstance(redirects, str):
        redirect_list = [redirects.strip()]
    else:
        redirect_list = []
    if redirect_uri:
        redirect_list = [redirect_uri]
    elif not redirect_list:
        redirect_list = ["http://localhost"]
    config["redirect_uris"] = redirect_list
    return config


def _load_json_from_string(raw: str, source_label: str) -> dict[str, Any]:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise OAuthConfigError(f"{source_label} содержит некорректный JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise OAuthConfigError(f"{source_label} не содержит объект с OAuth-кредитенциалами")
    return payload


def _load_client_payload() -> dict[str, Any] | None:
    """Load client secret payload from the supported environment sources."""

    raw_json = os.getenv("YOUTUBE_CLIENT_SECRET_JSON", "").strip()
    if raw_json:
        return _extract_section(_load_json_from_string(raw_json, "YOUTUBE_CLIENT_SECRET_JSON"))

    file_path = os.getenv("YOUTUBE_CLIENT_SECRET_FILE", "").strip()
    if file_path:
        path = Path(file_path)
        if not path.exists():
            raise OAuthConfigError(
                f"Файл client_secret не найден по пути, указанному в YOUTUBE_CLIENT_SECRET_FILE: {path}"
            )
        try:
            file_raw = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise OAuthConfigError(
                f"Не удалось прочитать файл client_secret из {path}: {exc}"
            ) from exc
        return _extract_section(_load_json_from_string(file_raw, "YOUTUBE_CLIENT_SECRET_FILE"))

    return None


def _propagate_client_env(section: dict[str, Any]) -> None:
    client_id = str(section.get("client_id", "")).strip()
    client_secret = str(section.get("client_secret", "")).strip()
    auth_uri = str(section.get("auth_uri") or "").strip()
    token_uri = str(section.get("token_uri") or "").strip()
    if client_id and not os.getenv("YT_CLIENT_ID"):
        os.environ["YT_CLIENT_ID"] = client_id
    if client_secret and not os.getenv("YT_CLIENT_SECRET"):
        os.environ["YT_CLIENT_SECRET"] = client_secret
    if auth_uri and not os.getenv("GOOGLE_AUTH_URI"):
        os.environ["GOOGLE_AUTH_URI"] = auth_uri
    if token_uri and not os.getenv("GOOGLE_TOKEN_URI"):
        os.environ["GOOGLE_TOKEN_URI"] = token_uri


def ensure_legacy_oauth_env() -> None:
    """Populate modern env variables from legacy JSON payloads if needed."""

    payload = _load_client_payload()
    if payload:
        _propagate_client_env(payload)

    token_raw = os.getenv("YOUTUBE_TOKEN_JSON", "").strip()
    if token_raw:
        try:
            token_payload = json.loads(token_raw)
        except json.JSONDecodeError as exc:
            raise OAuthConfigError("YOUTUBE_TOKEN_JSON содержит некорректный JSON") from exc
        if isinstance(token_payload, dict):
            refresh_token = str(
                token_payload.get("refresh_token")
                or token_payload.get("refreshToken")
                or ""
            ).strip()
            client_id = str(
                token_payload.get("client_id")
                or token_payload.get("clientId")
                or ""
            ).strip()
            client_secret = str(
                token_payload.get("client_secret")
                or token_payload.get("clientSecret")
                or ""
            ).strip()
            token_uri = str(
                token_payload.get("token_uri")
                or token_payload.get("tokenUri")
                or ""
            ).strip()
            if refresh_token and not os.getenv("YT_REFRESH_TOKEN"):
                os.environ["YT_REFRESH_TOKEN"] = refresh_token
            if client_id and not os.getenv("YT_CLIENT_ID"):
                os.environ["YT_CLIENT_ID"] = client_id
            if client_secret and not os.getenv("YT_CLIENT_SECRET"):
                os.environ["YT_CLIENT_SECRET"] = client_secret
            if token_uri and not os.getenv("GOOGLE_TOKEN_URI"):
                os.environ["GOOGLE_TOKEN_URI"] = token_uri


def get_oauth_client_config(redirect_uri: str | None = None) -> dict[str, Any]:
    """Resolve OAuth client configuration using both modern and legacy env vars."""

    ensure_legacy_oauth_env()

    section = _load_client_payload()
    if section:
        config = _normalise_client_config(section, redirect_uri)
        return {"web": config}

    client_id = os.getenv("YT_CLIENT_ID", "").strip()
    client_secret = os.getenv("YT_CLIENT_SECRET", "").strip()
    if client_id and client_secret:
        auth_uri = os.getenv("GOOGLE_AUTH_URI", DEFAULT_AUTH_URI) or DEFAULT_AUTH_URI
        token_uri = os.getenv("GOOGLE_TOKEN_URI", DEFAULT_TOKEN_URI) or DEFAULT_TOKEN_URI
        config = {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": auth_uri,
            "token_uri": token_uri,
            "redirect_uris": [redirect_uri or "http://localhost"],
        }
        return {"web": config}

    raise OAuthConfigError(
        "OAuth client credentials are not настроены: укажите YOUTUBE_CLIENT_SECRET_JSON, "
        "YOUTUBE_CLIENT_SECRET_FILE или пару YT_CLIENT_ID/YT_CLIENT_SECRET"
    )


__all__ = [
    "DEFAULT_AUTH_URI",
    "DEFAULT_TOKEN_URI",
    "OAuthConfigError",
    "ensure_legacy_oauth_env",
    "get_oauth_client_config",
]
