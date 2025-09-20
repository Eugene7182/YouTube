# US YouTube Shorts Autopipeline (free)
Vertical Shorts (cats & tech) generator: TTS → captions video → upload as PRIVATE to YouTube.
Deployable on Render free tier with a simple HTTP trigger.

## Quick start (local)
```bash
pip install -r requirements.txt
python runner.py --topic "Box vs Bed — Cat chooses luxury cardboard" --mode shorts --lang en --dry-run
```
This creates `voice.mp3` and `video.mp4` (no upload). Remove `--dry-run` to upload as PRIVATE.

## Render deploy
1) Obtain YouTube OAuth `client_secret.json` from Google Cloud and create `token.json` locally via `bootstrap_token.py`.
2) In Render → Web Service:
   - Build: `pip install -r requirements.txt`
   - Start: `uvicorn server:app --host 0.0.0.0 --port 10000`
   - Secrets:
     - `YOUTUBE_CLIENT_SECRET_JSON` = contents of client_secret.json (one line)
     - `YOUTUBE_TOKEN_JSON` = contents of token.json (one line)
     - `YOUTUBE_SCOPES` = `https://www.googleapis.com/auth/youtube.upload`
3) Ping `POST /run` with JSON `{ "topic": "...", "mode": "shorts", "script": "HOOK: ...\nSETUP: ...\nTWIST: ...\nPUNCH: ...\nCTA: ...", "draft": true }`

## Notes
- Uses free stack: edge-tts, MoviePy, YouTube API OAuth.
- Default privacy is PRIVATE (draft); publish manually after review.
