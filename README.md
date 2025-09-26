
# Dark & Strange — Local Render Kit

Quality local rendering of YouTube Shorts (1080×1920, 60 fps, CRF 18) with offline TTS (Piper/XTTS) and stylized captions.

## Quickstart
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
## Windows PowerShell setup

If you're on Windows (PowerShell), these commands will create a virtual environment, install dependencies and run the smoke import test:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
.\.venv\Scripts\python.exe -m pip install --upgrade pip setuptools wheel
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe .\scripts\smoke_imports.py
```

VS Code tasks are already defined in the workspace (see `.vscode/tasks.json` or the Tasks view). Two helpful tasks are:
- "Render one" — runs `scripts/render_short.py` with inputs
- "Batch render" — runs `scripts/batch_render.py` for multiple jobs

If you want me to run the full test suite (`pytest`) or wire up a developer `Makefile`/task runners, tell me and I'll add it.

# Run TTS (Piper)
python scripts/tts_piper.py --script_json data/one_short.json --voice ~/piper/en_US-amy-medium.onnx --out build/voice.wav

# Render high quality
python scripts/render_short.py --script data/one_short.json --voice build/voice.wav   --bg assets/bg/dark_texture_01.jpg --music assets/music/library_track.mp3   --out build/2025-09-26_haunted_bridges.mp4
```
