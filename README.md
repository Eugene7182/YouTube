
# Dark & Strange — Local Render Kit

Quality local rendering of YouTube Shorts (1080×1920, 60 fps, CRF 18) with offline TTS (Piper/XTTS) and stylized captions.

## Quickstart
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Run TTS (Piper)
python scripts/tts_piper.py --script_json data/one_short.json --voice ~/piper/en_US-amy-medium.onnx --out build/voice.wav

# Render high quality
python scripts/render_short.py --script data/one_short.json --voice build/voice.wav   --bg assets/bg/dark_texture_01.jpg --music assets/music/library_track.mp3   --out build/2025-09-26_haunted_bridges.mp4
```
