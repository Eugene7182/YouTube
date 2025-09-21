import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.env_compat import ensure_legacy_oauth_env, get_oauth_client_config


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch):
    for key in [
        "YOUTUBE_CLIENT_SECRET_JSON",
        "YOUTUBE_TOKEN_JSON",
        "YOUTUBE_CLIENT_SECRET_FILE",
        "YT_CLIENT_ID",
        "YT_CLIENT_SECRET",
        "YT_REFRESH_TOKEN",
        "GOOGLE_TOKEN_URI",
    ]:
        monkeypatch.delenv(key, raising=False)
    yield


def test_get_oauth_client_config_from_json(monkeypatch):
    payload = {
        "installed": {
            "client_id": "legacy-client",
            "client_secret": "legacy-secret",
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["https://example.com/callback"],
        }
    }
    monkeypatch.setenv("YOUTUBE_CLIENT_SECRET_JSON", json.dumps(payload))

    config = get_oauth_client_config("https://service.local/oauth/callback")

    assert config["web"]["client_id"] == "legacy-client"
    assert config["web"]["client_secret"] == "legacy-secret"
    assert config["web"]["redirect_uris"] == ["https://service.local/oauth/callback"]


def test_get_oauth_client_config_from_file(monkeypatch, tmp_path: Path):
    payload = {
        "web": {
            "client_id": "file-client",
            "client_secret": "file-secret",
            "redirect_uris": ["http://localhost"],
        }
    }
    secret_file = tmp_path / "client_secret.json"
    secret_file.write_text(json.dumps(payload), encoding="utf-8")

    monkeypatch.setenv("YOUTUBE_CLIENT_SECRET_FILE", str(secret_file))

    config = get_oauth_client_config("https://service.local/oauth/callback")

    assert config["web"]["client_id"] == "file-client"
    assert config["web"]["client_secret"] == "file-secret"
    assert config["web"]["redirect_uris"] == ["https://service.local/oauth/callback"]


def test_ensure_legacy_oauth_env_extracts_refresh_token(monkeypatch):
    monkeypatch.setenv("YOUTUBE_TOKEN_JSON", json.dumps({
        "refresh_token": "legacy-refresh",
        "client_id": "legacy-client",
        "client_secret": "legacy-secret",
        "token_uri": "https://oauth2.googleapis.com/token",
    }))

    ensure_legacy_oauth_env()

    assert os.getenv("YT_REFRESH_TOKEN") == "legacy-refresh"
    assert os.getenv("YT_CLIENT_ID") == "legacy-client"
    assert os.getenv("YT_CLIENT_SECRET") == "legacy-secret"
    assert os.getenv("GOOGLE_TOKEN_URI") == "https://oauth2.googleapis.com/token"
