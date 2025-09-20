import os
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

SCOPES = [os.getenv("YOUTUBE_SCOPES", "https://www.googleapis.com/auth/youtube.upload")]
CLIENT_SECRET_PATH = Path(os.getenv("YOUTUBE_CLIENT_SECRET", "client_secret.json"))
TOKEN_PATH = Path("token.json")


def ensure_oauth_files_from_env() -> None:
    """Persist OAuth secrets from environment variables when provided."""

    token_json = os.getenv("YOUTUBE_TOKEN_JSON", "").strip()
    client_json = os.getenv("YOUTUBE_CLIENT_SECRET_JSON", "").strip()

    if token_json:
        TOKEN_PATH.write_text(token_json, encoding="utf-8")
    if client_json:
        CLIENT_SECRET_PATH.write_text(client_json, encoding="utf-8")


def get_service():
    """Create an authenticated YouTube API client."""

    ensure_oauth_files_from_env()

    creds = None
    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET_PATH), SCOPES)
            creds = flow.run_local_server(port=0)
        TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")
    return build('youtube', 'v3', credentials=creds)


def upload(video_path: str, title: str, description: str, tags: list[str], categoryId: str = "24", privacyStatus: str = "private") -> str:
    """Upload a video to YouTube and return its identifier."""

    yt = get_service()
    body = {
        'snippet': {
            'title': title,
            'description': description[:4800],
            'tags': list(set(tags + ['shorts'])),
            'categoryId': categoryId,
        },
        'status': {'privacyStatus': privacyStatus}
    }
    media = MediaFileUpload(video_path, chunksize=-1, resumable=True)
    request = yt.videos().insert(part=','.join(body.keys()), body=body, media_body=media)
    response = request.execute()
    return response.get('id')
