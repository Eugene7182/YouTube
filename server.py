"""FastAPI server for orchestrating YouTube Shorts automation."""

from __future__ import annotations

import html
import json
import os
from json import JSONDecodeError
from pathlib import Path
from typing import Any, Iterable

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from google_auth_oauthlib.flow import Flow
from pydantic import BaseModel
from yaml import YAMLError, safe_load

from build_short import assemble_short, load_font
from generate_script import generate_script
from tts import synth_sync
from upload_youtube import upload


CONFIG_PATH = Path("config.yaml")
CLIENT_SECRET_PATH = Path("client_secret.json")
TOKEN_PATH = Path("token.json")

app = FastAPI(title="YouTube Shorts Runner")


def ensure_oauth_files() -> None:
    """Persist OAuth secrets from environment variables to disk if provided."""

    token_json = os.getenv("YOUTUBE_TOKEN_JSON", "").strip()
    client_json = os.getenv("YOUTUBE_CLIENT_SECRET_JSON", "").strip()

    if token_json:
        TOKEN_PATH.write_text(token_json, encoding="utf-8")
    if client_json:
        CLIENT_SECRET_PATH.write_text(client_json, encoding="utf-8")


def load_client_config() -> dict[str, Any]:
    """Load OAuth client configuration from environment variables."""

    client_json = os.getenv("YOUTUBE_CLIENT_SECRET_JSON", "").strip()
    if not client_json:
        raise HTTPException(status_code=500, detail="YOUTUBE_CLIENT_SECRET_JSON is not configured")
    try:
        client_config = json.loads(client_json)
    except JSONDecodeError as exc:  # pragma: no cover - defensive branch
        raise HTTPException(status_code=500, detail="Invalid YOUTUBE_CLIENT_SECRET_JSON payload") from exc
    if not isinstance(client_config, dict):
        raise HTTPException(status_code=500, detail="YOUTUBE_CLIENT_SECRET_JSON must be a JSON object")
    return client_config


def resolve_scopes() -> list[str]:
    """Derive OAuth scopes from environment with a sensible default."""

    raw_scopes = os.getenv("YOUTUBE_SCOPES", "https://www.googleapis.com/auth/youtube.upload").strip()
    if not raw_scopes:
        raw_scopes = "https://www.googleapis.com/auth/youtube.upload"
    separators = ",\n\t"
    scopes: list[str] = []
    buffer = raw_scopes
    for sep in separators:
        buffer = buffer.replace(sep, " ")
    for scope in buffer.split(" "):
        normalized = scope.strip()
        if normalized:
            scopes.append(normalized)
    if not scopes:
        scopes = ["https://www.googleapis.com/auth/youtube.upload"]
    return scopes


def build_flow(request: Request) -> tuple[Flow, str]:
    """Construct a Google OAuth flow using request context for redirect URI."""

    forwarded_host = request.headers.get("x-forwarded-host")
    if not forwarded_host:
        raise HTTPException(status_code=400, detail="Missing x-forwarded-host header")
    redirect_uri = f"https://{forwarded_host}/oauth/callback"
    flow = Flow.from_client_config(
        load_client_config(),
        scopes=resolve_scopes(),
        redirect_uri=redirect_uri,
    )
    return flow, redirect_uri


@app.on_event("startup")
def on_startup() -> None:
    """Prepare required OAuth files when the application boots."""

    ensure_oauth_files()

class RunReq(BaseModel):
    """Payload contract for executing the Shorts generation pipeline."""

    topic: str
    mode: str = "shorts"
    script: str | None = None
    draft: bool = True


@app.get("/health")
def health() -> dict[str, bool]:
    """Health probe for Render and monitoring systems."""

    return {"ok": True}


@app.get("/auth/start")
def auth_start(request: Request) -> RedirectResponse:
    """Initiate Google OAuth flow for obtaining YouTube upload credentials."""

    flow, _ = build_flow(request)
    authorization_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )
    return RedirectResponse(authorization_url)


@app.get("/oauth/callback", response_class=HTMLResponse)
def oauth_callback(request: Request) -> HTMLResponse:
    """Exchange the OAuth authorization code and present resulting credentials."""

    code = request.query_params.get("code")
    if not code:
        raise HTTPException(status_code=400, detail="Missing authorization code")

    flow, redirect_uri = build_flow(request)
    flow.redirect_uri = redirect_uri
    flow.fetch_token(code=code)

    credentials = flow.credentials
    token_payload = {
        "token": credentials.token,
        "refresh_token": credentials.refresh_token,
        "token_uri": credentials.token_uri,
        "client_id": credentials.client_id,
        "client_secret": credentials.client_secret,
        "scopes": credentials.scopes,
    }

    token_json = json.dumps(token_payload, indent=2, ensure_ascii=False)
    content = f"""
    <!DOCTYPE html>
    <html lang=\"en\">
      <head>
        <meta charset=\"utf-8\" />
        <title>YouTube OAuth Token</title>
        <style>
          body {{ font-family: sans-serif; max-width: 720px; margin: 2rem auto; line-height: 1.5; }}
          pre {{ background: #f5f5f5; padding: 1rem; border-radius: 8px; overflow-x: auto; }}
          code {{ font-family: monospace; }}
        </style>
      </head>
      <body>
        <h1>OAuth credentials generated</h1>
        <p>
          Скопируйте JSON ниже и вставьте его в Render → Environment →
          <strong>YOUTUBE_TOKEN_JSON</strong>.
        </p>
        <pre><code>{html.escape(token_json)}</code></pre>
        <p>После сохранения переменных перезапустите сервис, чтобы применить токен.</p>
      </body>
    </html>
    """
    return HTMLResponse(content=content.strip())


@app.post("/run")
def run(req: RunReq) -> dict[str, object]:
    """Generate, render, and upload a YouTube video for the provided topic."""

    ensure_oauth_files()

    config: dict[str, object] = {}
    if CONFIG_PATH.exists():
        try:
            with CONFIG_PATH.open("r", encoding="utf-8") as cfg_file:
                config = safe_load(cfg_file) or {}
        except (OSError, YAMLError) as exc:  # pragma: no cover - defensive
            raise HTTPException(status_code=500, detail=f"Failed to load config.yaml: {exc}") from exc

    voice = str(config.get("voice", "en-US-JennyNeural"))
    font = str(config.get("font", "DejaVuSans.ttf"))
    load_font(font, 64)

    script = req.script if req.script else generate_script(req.topic, mode=req.mode)
    Path("out_script.md").write_text(script, encoding="utf-8")
    synth_sync(script, "voice.mp3", voice=voice)

    def to_lines(text: str, mode: str) -> Iterable[str]:
        """Transform a generated script into caption lines for the assembler."""

        if mode == "shorts":
            cues = ("HOOK:", "SETUP:", "TWIST:", "PUNCH:")
            lines: list[str] = []
            for raw in text.splitlines():
                if any(raw.startswith(prefix) for prefix in cues):
                    _, _, remainder = raw.partition(":")
                    lines.append(remainder.strip())
            return lines
        return [line for line in text.splitlines() if line.strip()]

    lines = list(to_lines(script, req.mode))

    fps = int(config.get("fps", 30))
    resolution_config = config.get("resolution", [1080, 1920])
    if isinstance(resolution_config, (list, tuple)) and len(resolution_config) >= 2:
        resolution = (int(resolution_config[0]), int(resolution_config[1]))
    else:  # pragma: no cover - configuration fallback
        resolution = (1080, 1920)

    assemble_short(
        lines,
        "voice.mp3",
        req.topic,
        "video.mp4",
        fps=fps,
        resolution=resolution,
    )

    privacy = "private" if req.draft else "public"
    description_suffix = "\n\n#shorts" if req.mode == "shorts" else ""
    description = f"{script[:4800]}{description_suffix}"
    configured_tags = config.get("shorts_hashtags", ["#shorts"])
    if isinstance(configured_tags, str):
        configured_tags = [configured_tags]
    sanitized_tags = [str(tag).strip() for tag in configured_tags if str(tag).strip()]

    tags: list[str] = []
    for tag in ["shorts", *sanitized_tags]:
        if tag not in tags:
            tags.append(tag)
    category_id = str(config.get("categoryId", "24"))

    video_id = upload(
        "video.mp4",
        req.topic,
        description,
        tags=tags,
        categoryId=category_id,
        privacyStatus=privacy,
    )
    return {"ok": True, "youtubeVideoId": video_id}


@app.post("/run/queue")
def run_queue() -> dict[str, object]:
    """Dequeue the next topic from topics.csv and process it via /run."""

    ensure_oauth_files()

    topics_path = Path("topics.csv")
    if not topics_path.exists():
        return {"ok": False, "err": "topics.csv missing"}

    lines = [line.strip() for line in topics_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not lines:
        return {"ok": False, "err": "no topics"}

    next_topic, remaining = lines[0], lines[1:]
    topics_path.write_text("\n".join(remaining) + ("\n" if remaining else ""), encoding="utf-8")
    return run(RunReq(topic=next_topic))
