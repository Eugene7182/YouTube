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
