import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.env_compat import (
    OAuthConfigError,
    ensure_inline_oauth_env,
    get_oauth_client_config,
    load_authorized_user_info,
)


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch):
    for key in [
        "YOUTUBE_CLIENT_SECRET_JSON",
        "YOUTUBE_TOKEN_JSON",
    ]:
        monkeypatch.delenv(key, raising=False)
    yield


def _set_client(monkeypatch):
    payload = {
        "installed": {
            "client_id": "test-client",
            "client_secret": "test-secret",
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"]
        }
    }
    monkeypatch.setenv("YOUTUBE_CLIENT_SECRET_JSON", json.dumps(payload))


def _set_token(monkeypatch):
    token_payload = {
        "refresh_token": "refresh-token",
        "client_id": "ignored-client",
        "token_uri": "https://oauth2.googleapis.com/token",
    }
    monkeypatch.setenv("YOUTUBE_TOKEN_JSON", json.dumps(token_payload))


def test_get_oauth_client_config_from_inline_json(monkeypatch):
    _set_client(monkeypatch)
    config = get_oauth_client_config("https://service.local/oauth/callback")
    web_cfg = config["web"]
    assert web_cfg["client_id"] == "test-client"
    assert web_cfg["client_secret"] == "test-secret"
    assert web_cfg["redirect_uris"] == ["https://service.local/oauth/callback"]


def test_load_authorized_user_info_merges_client_fields(monkeypatch):
    _set_client(monkeypatch)
    _set_token(monkeypatch)
    info = load_authorized_user_info()
    assert info["client_id"] == "test-client"
    assert info["client_secret"] == "test-secret"
    assert info["refresh_token"] == "refresh-token"
    assert info["token_uri"] == "https://oauth2.googleapis.com/token"


def test_ensure_inline_oauth_env_requires_payloads(monkeypatch):
    with pytest.raises(OAuthConfigError):
        ensure_inline_oauth_env()
    _set_client(monkeypatch)
    with pytest.raises(OAuthConfigError):
        ensure_inline_oauth_env()
    _set_token(monkeypatch)
    ensure_inline_oauth_env()
