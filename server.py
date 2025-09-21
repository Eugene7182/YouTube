"""FastAPI service layer for Shorts-Bot PRO."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any, Iterable, List

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google_auth_oauthlib.flow import Flow
from pydantic import BaseModel, Field, validator
import yaml

from core.env_compat import (
    OAuthConfigError,
    ensure_inline_oauth_env,
    get_oauth_client_config,
)
from core.generate import MANIFEST_PATH, build_all
from core.settings import get_settings
from core.upload import upload_manifest
from tts import TextToSpeechError
from upload_youtube import UploadConfigurationError

load_dotenv()
ensure_inline_oauth_env()

ENV = get_settings()
logger = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = Path("config.yaml")
DEFAULT_TOPICS_PATH = Path("config/topics.yaml")
TOPICS_BUFFER_PATH = Path("data/input/topics_buffer.json")

app = FastAPI(title="Shorts-Bot PRO", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
security = HTTPBearer(
    auto_error=False,
    scheme_name="AdminToken",
    bearerFormat="Bearer",
    description="Вставьте значение ADMIN_TOKEN без префикса",
)


def _ensure_timezone() -> None:
    tz = ENV.tz_local
    os.environ["TZ"] = tz
    if hasattr(time, "tzset"):
        time.tzset()  # type: ignore[attr-defined]


@app.on_event("startup")
def _startup() -> None:
    _ensure_timezone()


def require_admin(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> None:
    token_expected = ENV.admin_token
    if not token_expected:
        return
    if not credentials or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Bearer token required")
    if credentials.credentials != token_expected:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid bearer token")


class IdeasRefreshRequest(BaseModel):
    queries: list[str] | None = None
    region: str | None = None
    limit: int | None = Field(default=None, ge=1, le=100)


class IdeaItem(BaseModel):
    title: str
    lines: list[str]
    tags: list[str]


class IdeasRefreshResponse(BaseModel):
    items: list[IdeaItem]


class TopicModel(BaseModel):
    title: str
    lines: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    bg_video_path: str | None = None
    bg_image_path: str | None = None
    music_path: str | None = None
    schedule: str | None = None

    @validator("lines", pre=True)
    def _normalise_lines(cls, value: Any) -> list[str]:  # type: ignore[override]
        if value is None:
            return []
        if isinstance(value, str):
            return [segment.strip() for segment in value.splitlines() if segment.strip()]
        return [str(segment).strip() for segment in value if str(segment).strip()]

    @validator("tags", pre=True)
    def _normalise_tags(cls, value: Any) -> list[str]:  # type: ignore[override]
        if value is None:
            return []
        if isinstance(value, str):
            return [segment.strip() for segment in value.split(",") if segment.strip()]
        return [str(segment).strip() for segment in value if str(segment).strip()]


class TrendsGenerateRequest(BaseModel):
    topics: list[TopicModel]


class TrendsGenerateResponse(BaseModel):
    count: int


class RunQueueRequest(BaseModel):
    topics: str | List[int | str] = "all"
    upload: bool = False
    dry_run: bool = False


class UploadResult(BaseModel):
    title: str
    status: str
    videoId: str | None = None
    reason: str | None = None


class RunQueueResponse(BaseModel):
    status: str
    produced: list[dict[str, Any]]
    uploaded: list[UploadResult]


def _load_client_config(redirect_uri: str) -> dict[str, Any]:
    try:
        return get_oauth_client_config(redirect_uri)
    except OAuthConfigError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc


def _resolve_scopes() -> list[str]:
    raw = os.getenv("YOUTUBE_SCOPES", "https://www.googleapis.com/auth/youtube.upload").strip()
    if not raw:
        raw = "https://www.googleapis.com/auth/youtube.upload"
    separators = ",\n\t"
    buffer = raw
    for sep in separators:
        buffer = buffer.replace(sep, " ")
    scopes = [segment.strip() for segment in buffer.split(" ") if segment.strip()]
    return scopes or ["https://www.googleapis.com/auth/youtube.upload"]


def _load_topics_file(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    if isinstance(data, dict):
        topics = data.get("topics", [])
    else:
        topics = data
    result: list[dict[str, Any]] = []
    for raw in topics:
        if isinstance(raw, dict) and raw.get("title"):
            result.append(raw)
    return result


def _validate_upload_env() -> None:
    checks = {
        "YOUTUBE_TOKEN_JSON": "вставьте payload из OAuth Playground (refresh_token)",
        "YOUTUBE_CLIENT_SECRET_JSON": "укажите client_secret.json как inline JSON",
        "YOUTUBE_SCOPES": "укажите список scope, например https://www.googleapis.com/auth/youtube.upload",
    }
    missing = [name for name in checks if not os.getenv(name, "").strip()]
    if not missing:
        return
    hints = ", ".join(f"{name}: {checks[name]}" for name in missing)
    raise RuntimeError(
        "Отсутствуют переменные окружения для загрузки: "
        f"{', '.join(missing)}. Подсказки: {hints}"
    )


def _title_to_lines(title: str) -> list[str]:
    fragments = re.split(r"[.!?]| - | – | : ", title)
    segments = [fragment.strip() for fragment in fragments if fragment.strip()]
    lines: list[str] = []
    for segment in segments:
        words = segment.split()
        while words:
            chunk = words[:5]
            lines.append(" ".join(chunk))
            words = words[5:]
    if len(lines) < 2:
        words = title.split()
        chunk_size = max(1, min(4, len(words) // 2 or 1))
        for index in range(0, len(words), chunk_size):
            lines.append(" ".join(words[index:index + chunk_size]))
    return lines[:6]


def _title_to_tags(title: str) -> list[str]:
    words = re.findall(r"[\w']+", title.lower())
    tags: list[str] = []
    for word in words:
        if len(word) < 3:
            continue
        if word not in tags:
            tags.append(word)
    return tags[:12]


def _parse_queries(raw: str) -> list[str]:
    parts = [segment.strip() for segment in raw.split(",") if segment.strip()]
    return parts


def _fetch_ideas(queries: list[str], region: str, limit: int) -> list[IdeaItem]:
    api_key = ENV.youtube_api_key
    if not api_key:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="YOUTUBE_API_KEY is not configured")

    youtube = build("youtube", "v3", developerKey=api_key, cache_discovery=False)
    collected: list[IdeaItem] = []
    for query in queries:
        remaining = limit - len(collected)
        if remaining <= 0:
            break
        try:
            response = youtube.search().list(
                part="snippet",
                maxResults=min(50, remaining),
                q=query,
                regionCode=region,
                type="video",
                order="viewCount",
            ).execute()
        except HttpError as exc:  # pragma: no cover - network dependent
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"YouTube API error: {exc}") from exc

        for item in response.get("items", []):
            snippet = item.get("snippet") or {}
            title = snippet.get("title") or snippet.get("channelTitle") or ""
            title = str(title).strip()
            if not title:
                continue
            idea = IdeaItem(title=title, lines=_title_to_lines(title), tags=_title_to_tags(title))
            collected.append(idea)
            if len(collected) >= limit:
                break
    return collected


def _topic_hash(topic: TopicModel) -> str:
    key = "|".join([topic.title, *topic.lines])
    return hashlib.sha1(key.encode("utf-8")).hexdigest()


def _load_existing_hashes(buffer_path: Path, yaml_path: Path) -> tuple[dict[str, dict[str, Any]], set[str]]:
    existing_map: dict[str, dict[str, Any]] = {}
    hashes: set[str] = set()

    if buffer_path.exists():
        try:
            buffer = json.loads(buffer_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            buffer = {}
        entries = buffer.get("items") if isinstance(buffer, dict) else buffer
        if isinstance(entries, list):
            for entry in entries:
                if isinstance(entry, dict) and "hash" in entry:
                    hashes.add(entry["hash"])
                    existing_map[entry["hash"]] = entry

    topics_yaml = _load_topics_file(yaml_path)
    for topic in topics_yaml:
        model = TopicModel.parse_obj(topic)
        digest = _topic_hash(model)
        hashes.add(digest)
        existing_map.setdefault(digest, {"hash": digest, **model.dict()})

    return existing_map, hashes


def _persist_topics(buffer_path: Path, yaml_path: Path, topics: Iterable[TopicModel]) -> int:
    existing_map, hashes = _load_existing_hashes(buffer_path, yaml_path)

    created = 0
    for topic in topics:
        digest = _topic_hash(topic)
        if digest in hashes:
            continue
        hashes.add(digest)
        existing_map[digest] = {"hash": digest, **topic.dict()}
        created += 1

    if created == 0:
        return 0

    buffer_path.parent.mkdir(parents=True, exist_ok=True)
    yaml_path.parent.mkdir(parents=True, exist_ok=True)

    buffer_payload = {"items": sorted(existing_map.values(), key=lambda item: item["hash"])}
    buffer_path.write_text(json.dumps(buffer_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    yaml_topics = [
        {k: v for k, v in entry.items() if k not in {"hash"}}
        for entry in buffer_payload["items"]
    ]
    yaml_path.write_text(yaml.safe_dump(yaml_topics, allow_unicode=True, sort_keys=False), encoding="utf-8")

    return created


def _resolve_queries(payload: IdeasRefreshRequest) -> list[str]:
    if payload.queries:
        return [query.strip() for query in payload.queries if query.strip()]
    if ENV.search_queries:
        return list(ENV.search_queries)
    return ["Shorts"]


def _resolve_region(payload: IdeasRefreshRequest) -> str:
    if payload.region:
        return payload.region
    return ENV.youtube_region


def _resolve_limit(payload: IdeasRefreshRequest) -> int:
    if payload.limit is not None:
        return payload.limit
    return ENV.ideas_per_refresh


def build_flow(request: Request) -> tuple[Flow, str]:
    """Compatibility helper for OAuth flow generation."""

    forwarded_host = request.headers.get("x-forwarded-host")
    if forwarded_host:
        host = forwarded_host.split(",")[0].strip()
    else:
        hostname = request.url.hostname or ""
        if not hostname:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unable to resolve request host")
        port = request.url.port
        if port and port not in {80, 443}:
            host = f"{hostname}:{port}"
        else:
            host = hostname

    forwarded_proto = request.headers.get("x-forwarded-proto")
    if forwarded_proto:
        scheme = forwarded_proto.split(",")[0].strip() or request.url.scheme
    else:
        scheme = request.url.scheme or "https"

    redirect_uri = f"{scheme}://{host}/oauth/callback"
    flow = Flow.from_client_config(
        _load_client_config(redirect_uri),
        scopes=_resolve_scopes(),
        redirect_uri=redirect_uri,
    )
    return flow, redirect_uri


@app.get("/", response_model=dict)
def root() -> dict[str, Any]:
    return {
        "message": "Shorts-Bot PRO backend активен",
        "links": {"health": "/health", "docs": "/docs", "trends": "/trends/generate"},
    }


@app.get("/health", response_model=dict)
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/ideas/refresh", response_model=dict)
def ideas_refresh_hint() -> dict[str, str]:
    return {"hint": "используй POST /trends/generate для ручного ввода тем"}


@app.post("/ideas/refresh", response_model=IdeasRefreshResponse, dependencies=[Depends(require_admin)])
def ideas_refresh(payload: IdeasRefreshRequest) -> IdeasRefreshResponse:
    queries = _resolve_queries(payload)
    region = _resolve_region(payload)
    limit = _resolve_limit(payload)
    items = _fetch_ideas(queries, region, limit)
    return IdeasRefreshResponse(items=items)


@app.post("/trends/generate", response_model=TrendsGenerateResponse, dependencies=[Depends(require_admin)])
def trends_generate(payload: TrendsGenerateRequest) -> TrendsGenerateResponse:
    if not payload.topics:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Topics payload is empty")
    created = _persist_topics(TOPICS_BUFFER_PATH, DEFAULT_TOPICS_PATH, payload.topics)
    return TrendsGenerateResponse(count=created)


@app.post("/run/queue", response_model=RunQueueResponse, dependencies=[Depends(require_admin)])
def run_queue(payload: RunQueueRequest) -> RunQueueResponse:
    logger.info("run_queue invoked", extra={"topics": payload.topics, "upload": payload.upload, "dry_run": payload.dry_run})
    all_topics = _load_topics_file(DEFAULT_TOPICS_PATH)
    if not all_topics:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No topics configured")
    try:
        produced = build_all(
            str(DEFAULT_CONFIG_PATH),
            str(DEFAULT_TOPICS_PATH),
            payload.topics,
        )
    except TextToSpeechError as exc:
        logger.exception("TTS synthesis failed during run_queue")
        return JSONResponse(
            status_code=status.HTTP_502_BAD_GATEWAY,
            content={"status": "error", "reason": str(exc)},
        )
    except ValueError as exc:
        logger.exception("Topic selection failed during run_queue")
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"status": "error", "reason": str(exc)},
        )
    except RuntimeError as exc:
        logger.exception("Generation failed during run_queue")
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"status": "error", "reason": str(exc)},
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("Unexpected failure during run_queue")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"status": "error", "reason": str(exc)},
        )

    uploaded: list[UploadResult] = []
    if payload.upload and not payload.dry_run:
        try:
            _validate_upload_env()
        except RuntimeError as exc:
            logger.exception("Upload environment validation failed")
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={"status": "error", "reason": str(exc)},
            )
        try:
            raw_results = upload_manifest(str(MANIFEST_PATH), str(DEFAULT_CONFIG_PATH))
            uploaded = [UploadResult.parse_obj(item) for item in raw_results]
        except UploadConfigurationError as exc:
            logger.exception("Uploader configuration error during run_queue")
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={"status": "error", "reason": str(exc)},
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("Unexpected upload failure during run_queue")
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={"status": "error", "reason": str(exc)},
            )

    if payload.upload and payload.dry_run:
        logger.info("run_queue dry-run requested; upload skipped", extra={"topics": payload.topics})

    return RunQueueResponse(status="ok", produced=produced, uploaded=uploaded)


