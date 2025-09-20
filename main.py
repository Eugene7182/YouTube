# main.py — минимальный FastAPI с веб-OAuth для Render
import os, json
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse, HTMLResponse
from google_auth_oauthlib.flow import Flow

app = FastAPI()

@app.get("/")
def root():
    return {"ok": True, "service": "youtube-bot"}

@app.get("/health")
def health():
    return {"ok": True}

SCOPES = [os.getenv("YOUTUBE_SCOPES", "https://www.googleapis.com/auth/youtube.upload")]

def _cb_url(req: Request) -> str:
    host = req.headers.get("x-forwarded-host") or req.url.hostname
    return f"https://{host}/oauth/callback"

def _client_config(cb_url: str):
    cfg = json.loads(os.environ["YOUTUBE_CLIENT_SECRET_JSON"])
    if "web" in cfg:
        web = cfg["web"]
        web["redirect_uris"] = [cb_url]
        return {"web": web}
    if "installed" in cfg:
        ins = cfg["installed"]
        return {"web": {
            "client_id": ins["client_id"],
            "client_secret": ins["client_secret"],
            "auth_uri": ins["auth_uri"],
            "token_uri": ins["token_uri"],
            "redirect_uris": [cb_url],
        }}
    raise RuntimeError("Bad YOUTUBE_CLIENT_SECRET_JSON")

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
