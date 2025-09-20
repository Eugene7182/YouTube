import os
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

SCOPES = [os.getenv("YOUTUBE_SCOPES", "https://www.googleapis.com/auth/youtube.upload")]
CLIENT_SECRET = os.getenv("YOUTUBE_CLIENT_SECRET", "client_secret.json")
TOKEN = "token.json"

def get_service():
    creds = None
    if os.path.exists(TOKEN):
        creds = Credentials.from_authorized_user_file(TOKEN, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN, 'w') as f:
            f.write(creds.to_json())
    return build('youtube', 'v3', credentials=creds)

def upload(video_path: str, title: str, description: str, tags: list[str], categoryId: str = "24", privacyStatus: str = "private"):
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
