# Dark & Strange - Local Render Kit

High quality rendering of Shorts (1080x1920 @ 60 fps, CRF 18) with scripted captions, offline narration (Piper/XTTS), and automatic stock backgrounds.

## Quickstart (Windows PowerShell)

### 1. Grab API keys
- Create free accounts at [Pexels](https://www.pexels.com/api/new/) and [Pixabay](https://pixabay.com/api/docs/).
- Copy the generated keys and either export them in your shell or place them in a `.env` file at the project root:
  ```powershell
  # .env example
  PEXELS_API_KEY=pexels_your_key
  PIXABAY_API_KEY=pixabay_your_key
  ```

### 2. Prepare the environment
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
.\.venv\Scripts\python.exe -m pip install --upgrade pip setuptools wheel
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### 3. Run the production tasks (VS Code > Tasks)
Run these four tasks in order for a full smoke render:
1. `FFmpeg PATH (session)` - prepends the bundled `tools\ffmpeg` binaries to `PATH`.
2. `Short: TTS (Piper)` - synthesises narration into `build\voice.wav`.
3. `Short: Fetch BG` - downloads a vertical background into `assets\bg\auto_bg.jpg` using Pexels/Pixabay (falls back to defaults if nothing matches).
4. `Short: Render 60fps CRF18` - builds `build\short_test.mp4` with the new audio and background.

If `Short: Fetch BG` prints `NO_RESULTS`, copy or choose a local fallback (for example `assets\bg\dark_texture_01.jpg`) and rerun step 4 with that path.

### 4. Check results manually (optional)
```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\ffmpeg_path.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\check_env.ps1
.\.venv\Scripts\python.exe scripts\render_short.py --script data\one_short.json --voice build\voice.wav --bg assets\bg\auto_bg.jpg --out build\short_test.mp4
```

The final MP4 lives in `build\short_test.mp4`; narration is stored at `build\voice.wav`; downloaded artwork ends up in `assets\bg\auto_bg.jpg`.
