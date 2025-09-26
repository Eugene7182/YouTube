Set-StrictMode -Version Latest; $ErrorActionPreference="Stop"

# 1) venv + dependencies (Python 3.11)
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -U pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

# 2) Piper (CLI)
mkdir tools\piper -ea 0
curl.exe -L -o tools\piper\piper_win.zip https://github.com/rhasspy/piper/releases/download/2023.11.14-2/piper_windows_amd64.zip
Expand-Archive tools\piper\piper_win.zip -DestinationPath tools\piper -Force
$Piper = (Get-ChildItem tools\piper -Recurse -Filter piper.exe | Select-Object -First 1).FullName
if (-not $Piper) { throw "piper.exe not found after expand." }
$env:PIPER_EXE = $Piper
$env:Path = (Split-Path $Piper) + ";" + $env:Path

# 3) Voice model
mkdir assets\voices -ea 0
curl.exe -L -o assets\voices\en_US-amy-medium.onnx "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/amy/medium/en_US-amy-medium.onnx?download=true"

# 4) Voice synthesis + test render (1080x1920@60fps, CRF 18)
.\.venv\Scripts\python.exe scripts\tts_piper.py --script_json data\one_short.json --voice assets\voices\en_US-amy-medium.onnx --out build\voice.wav
.\.venv\Scripts\python.exe scripts\render_short.py --script data\one_short.json --voice build\voice.wav --bg assets\bg\dark_texture_01.jpg --out build\test.mp4

Write-Host 'DONE: build\test.mp4'
