"""FastAPI server for orchestrating YouTube Shorts automation."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable

from fastapi import FastAPI, HTTPException
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
