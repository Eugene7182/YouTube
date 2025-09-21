import json
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture(autouse=True)
def _setup_oauth(monkeypatch):
    client_payload = {
        "installed": {
            "client_id": "test-client",
            "client_secret": "test-secret",
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"],
        }
    }
    token_payload = {
        "refresh_token": "test-refresh",
        "client_id": "test-client",
        "client_secret": "test-secret",
        "token_uri": "https://oauth2.googleapis.com/token",
    }
    monkeypatch.setenv("YOUTUBE_CLIENT_SECRET_JSON", json.dumps(client_payload))
    monkeypatch.setenv("YOUTUBE_TOKEN_JSON", json.dumps(token_payload))
    monkeypatch.setenv("CHANNEL_DEFAULT_TAGS", "shorts,test")
    monkeypatch.setenv("YOUTUBE_SCOPES", "https://www.googleapis.com/auth/youtube.upload")
    monkeypatch.delenv("ADMIN_TOKEN", raising=False)
    yield


def test_run_queue_dry_run_ok(monkeypatch, tmp_path):
    import server
    from core import generate

    topics_path = tmp_path / "topics.yaml"
    topics_path.write_text(yaml.safe_dump([
        {"title": "Test topic", "lines": ["line1", "line2"], "tags": ["shorts"]}
    ], allow_unicode=True), encoding="utf-8")
    config_path = tmp_path / "config.yaml"
    config_path.write_text("default_tags:\n  - shorts\n", encoding="utf-8")
    manifest_path = tmp_path / "manifest.json"

    monkeypatch.setattr(server, "DEFAULT_TOPICS_PATH", topics_path)
    monkeypatch.setattr(server, "DEFAULT_CONFIG_PATH", config_path)
    monkeypatch.setattr(server, "MANIFEST_PATH", manifest_path)
    monkeypatch.setattr(generate, "MANIFEST_PATH", manifest_path)

    def fake_build_all(settings_path, topics_path, selection):
        return [{"path": "/tmp/video.mp4", "title": "Test", "tags": ["shorts"], "schedule": None}]

    monkeypatch.setattr(server, "build_all", fake_build_all)

    request = server.RunQueueRequest(topics="all", upload=True, dry_run=True)
    response = server.run_queue(request)

    assert response.status == "ok"
    assert len(response.produced) == 1
    assert response.uploaded == []
