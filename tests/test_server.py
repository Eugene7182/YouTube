"""Unit tests for FastAPI server utilities."""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Mapping
from pathlib import Path

from starlette.datastructures import URL
from starlette.requests import Request

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_DEFAULT_CLIENT = {
    "installed": {
        "client_id": "test-client",
        "client_secret": "test-secret",
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "redirect_uris": ["http://localhost"],
    }
}

_DEFAULT_TOKEN = {
    "refresh_token": "test-refresh",
    "client_id": "test-client",
    "client_secret": "test-secret",
    "token_uri": "https://oauth2.googleapis.com/token",
}

os.environ.setdefault("YOUTUBE_CLIENT_SECRET_JSON", json.dumps(_DEFAULT_CLIENT))
os.environ.setdefault("YOUTUBE_TOKEN_JSON", json.dumps(_DEFAULT_TOKEN))

from server import build_flow  # noqa: E402


def make_request(url: str, headers: Mapping[str, str] | None = None) -> Request:
    """Create a Starlette request instance for testing utilities."""

    parsed = URL(url)
    scope = {
        "type": "http",
        "method": "GET",
        "scheme": parsed.scheme,
        "path": parsed.path,
        "root_path": "",
        "query_string": parsed.query.encode("utf-8"),
        "headers": [
            (key.lower().encode("latin-1"), value.encode("latin-1"))
            for key, value in (headers or {}).items()
        ],
        "server": (
            parsed.hostname,
            parsed.port or (443 if parsed.scheme == "https" else 80),
        ),
        "client": ("127.0.0.1", 12345),
    }
    return Request(scope)


def test_build_flow_fallback_without_forwarded_headers(monkeypatch) -> None:
    """Redirect URI should be built from request URL if headers are missing."""

    client_config = {
        "web": {
            "client_id": "test-client-id",
            "client_secret": "test-client-secret",
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }
    monkeypatch.setenv("YOUTUBE_CLIENT_SECRET_JSON", json.dumps(client_config))

    request = make_request("http://internal.example:8080/auth/start")

    flow, redirect_uri = build_flow(request)

    assert redirect_uri == "http://internal.example:8080/oauth/callback"
    assert flow.redirect_uri == redirect_uri
