import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / 'tools' / 'ffmpeg'

# find ffmpeg
ff = None
for p in TOOLS.rglob('ffmpeg.exe'):
    ff = str(p)
    break
if not ff:
    print('ffmpeg not found under tools/ffmpeg')
    sys.exit(2)
ffprobe = None
for p in TOOLS.rglob('ffprobe.exe'):
    ffprobe = str(p)
    break

print('ffmpeg:', ff)
# prepend ffmpeg bin folder to PATH for this process
ffdir = str(Path(ff).parent)
os.environ['PATH'] = ffdir + os.pathsep + os.environ.get('PATH','')

# print version
try:
    out = subprocess.check_output([ff, '-version'], stderr=subprocess.STDOUT, text=True)
    print(out.splitlines()[0])
except Exception as e:
    print('error calling ffmpeg -version:', e)

# run render
render_cmd = [sys.executable, str(ROOT / 'scripts' / 'render_short.py'), '--script', str(ROOT / 'data' / 'one_short.json'), '--voice', str(ROOT / 'build' / 'voice.wav'), '--bg', str(ROOT / 'assets' / 'bg' / 'dark_texture_01.jpg'), '--out', str(ROOT / 'build' / 'output_short_final.mp4')]
print('Running render:', ' '.join(render_cmd))
try:
    subprocess.check_call(render_cmd)
    print('Render finished')
except subprocess.CalledProcessError as e:
    print('Render failed:', e)
    sys.exit(e.returncode)

# probe results
if not ffprobe:
    for p in TOOLS.rglob('ffprobe.exe'):
        ffprobe = str(p)

if not ffprobe:
    print('ffprobe not found; skipping probe')
    sys.exit(0)

print('ffprobe:', ffprobe)
try:
    vinfo = subprocess.check_output([ffprobe, '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=width,height,avg_frame_rate,pix_fmt', '-of', 'default=nk=1:nw=1', str(ROOT / 'build' / 'output_short_final.mp4')], text=True)
    ainfo = subprocess.check_output([ffprobe, '-v', 'error', '-select_streams', 'a:0', '-show_entries', 'stream=sample_rate,channels', '-of', 'default=nk=1:nw=1', str(ROOT / 'build' / 'output_short_final.mp4')], text=True)
    print('VIDEO STREAM INFO:\n' + vinfo)
    print('AUDIO STREAM INFO:\n' + ainfo)
except Exception as e:
    print('ffprobe failed:', e)
    sys.exit(3)
