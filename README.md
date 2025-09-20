# Viral Shorts Autopipeline (US, free stack)
**What it does**
- Fetches US YouTube trends for cats (#shorts) with YouTube Data API v3 (free API key).
- Analyzes viral patterns (title length, hashtags, keywords, duration).
- Generates **inspired, original** scripts (no reuse) for meme-cats or tech-picks.
- Builds vertical **Shorts 1080×1920** with TTS + big captions.
- Uploads as **PRIVATE** drafts to YouTube (safe review).
- Exposes HTTP API for Render free tier; includes queue & GitHub Actions cron.

**Quick local test (no upload)**
```bash
pip install -r requirements.txt
python runner.py --topic "Box vs Bed — Cat chooses luxury cardboard" --mode shorts --dry-run
```

## Deploy on Render
- **Build:** `pip install -r requirements.txt`
- **Start:** `uvicorn server:app --host 0.0.0.0 --port 10000`
- **Required env vars:**
  - `YOUTUBE_API_KEY`
  - `YOUTUBE_CLIENT_SECRET_JSON` (вставьте полный JSON одной строкой)
  - `YOUTUBE_TOKEN_JSON` (вставьте полный JSON одной строкой)
  - `YOUTUBE_SCOPES = https://www.googleapis.com/auth/youtube.upload`
- **Endpoints:**
  - `GET /health`
  - `POST /trends/refresh`
  - `POST /trends/generate`
  - `POST /run` (topic/mode/script/draft)
  - `POST /run/queue` (берёт следующий топик из `topics.csv`)
