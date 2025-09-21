# main.py — минимальный FastAPI с веб-OAuth для Render
import asyncio
import json
import os

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import Flow

from config import settings
from core.env_compat import OAuthConfigError, ensure_legacy_oauth_env, get_oauth_client_config
from upload_youtube import UploadConfigurationError, get_credentials

app = FastAPI()

ensure_legacy_oauth_env()


try:  # noqa: SIM105 - optional dependency
    import httpx
except Exception:  # pragma: no cover - httpx missing locally is OK
    httpx = None

import ideas


@app.get("/auth/whoami")
def whoami():
    """Return channel metadata for the current OAuth credentials."""

    try:
        creds = get_credentials()
        yt = build("youtube", "v3", credentials=creds)
        me = yt.channels().list(part="id,snippet,statistics", mine=True).execute()
        return {"ok": True, "me": me}
    except UploadConfigurationError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - diagnostic helper
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/")
def root():
    return {"ok": True, "service": "youtube-bot"}

@app.get("/health")
def health():
    return {"ok": True}


@app.get("/config")
def read_config():
    """Expose active safe configuration values without leaking secrets."""

    return {
        "AUTO_ON": settings.AUTO_ON,
        "TIMEZONE": settings.TIMEZONE,
        "DAILY_SLOTS": settings.DAILY_SLOTS,
        "AUTO_TIMES": settings.AUTO_TIMES,
        "CONTENT_PLAN_PATH": settings.CONTENT_PLAN_PATH,
        "YOUTUBE_UPLOAD_PRIVACY": settings.YOUTUBE_UPLOAD_PRIVACY,
        "PING_URL": bool(settings.PING_URL),
    }


async def _internal_keepalive() -> None:
    """Fire-and-forget keep-alive loop for Render free tier."""

    if not settings.PING_URL or not httpx:
        return

    async with httpx.AsyncClient(timeout=10) as client:
        while True:
            try:
                await client.get(settings.PING_URL)
            except Exception:  # pragma: no cover - best-effort ping
                pass
            await asyncio.sleep(300)


@app.on_event("startup")
async def _maybe_start_keepalive() -> None:
    """Schedule keep-alive task without breaking existing startup logic."""

    try:
        asyncio.create_task(_internal_keepalive())
    except Exception:  # pragma: no cover - scheduler safety net
        pass

SCOPES = [os.getenv("YOUTUBE_SCOPES", "https://www.googleapis.com/auth/youtube.upload")]

def _cb_url(req: Request) -> str:
    host = req.headers.get("x-forwarded-host") or req.url.hostname
    return f"https://{host}/oauth/callback"

def _client_config(cb_url: str):
    try:
        return get_oauth_client_config(cb_url)
    except OAuthConfigError as exc:  # pragma: no cover - configuration error
        raise HTTPException(status_code=500, detail=str(exc)) from exc

@app.get("/auth/start")
def auth_start(request: Request):
    cb = _cb_url(request)
    flow = Flow.from_client_config(_client_config(cb), scopes=SCOPES, redirect_uri=cb)
    url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )
    return RedirectResponse(url)

@app.get("/oauth/callback", response_class=HTMLResponse)
def oauth_callback(request: Request):
    cb = _cb_url(request)
    flow = Flow.from_client_config(_client_config(cb), scopes=SCOPES, redirect_uri=cb)
    code = request.query_params.get("code")
    if not code:
        return HTMLResponse("<h3>Missing ?code</h3>", status_code=400)
    flow.fetch_token(code=code)
    c = flow.credentials
    token_json = {
        "token": c.token,
        "refresh_token": c.refresh_token,
        "token_uri": c.token_uri,
        "client_id": c.client_id,
        "client_secret": c.client_secret,
        "scopes": list(c.scopes or []),
    }
    pretty = json.dumps(token_json, ensure_ascii=False, indent=2)
    return f"<h2>Готово ✅ Скопируй JSON в Render → Environment → YOUTUBE_TOKEN_JSON</h2><pre>{pretty}</pre>"


@app.post("/ideas/refresh")
async def ideas_refresh():
    try:
        data = await ideas.refresh_ideas()
        return {"ok": True, "count": data.get("count", 0)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/ideas/sample")
def ideas_sample(count: int = 3):
    data = ideas.load_ideas()
    return {"ok": True, "available": data.get("count", 0), "items": data.get("items", [])[:count]}


@app.post("/ideas/pop")
def ideas_pop(count: int = 1):
    return {"ok": True, "items": ideas.pop_n(count)}


# optional alias to existing pipeline if any:
@app.post("/trends/refresh")
async def trends_refresh_alias():
    # keep backward-compat: call the same refresh
    data = await ideas.refresh_ideas()
    return {"ok": True, "count": data.get("count", 0)}
