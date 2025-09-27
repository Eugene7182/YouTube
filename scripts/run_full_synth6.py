#!/usr/bin/env python3
"""Create short video scenes from an image for each topic in data/topics_today.jsonl
and run render_scenes.py --fast to produce video.mp4 and thumbnail.
"""
import sys, json, shutil, subprocess
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable
FF = ROOT / 'tools' / 'ffmpeg' / 'ffmpeg-8.0-essentials_build' / 'bin' / 'ffmpeg.exe'
OUTROOT = ROOT / 'build' / 'today'
OUTROOT.mkdir(parents=True, exist_ok=True)
LOG = OUTROOT / 'run_full_synth6.log'
_log_lines = []
def log(s):
    _log_lines.append(str(s))
    print(s)

topics_file = ROOT / 'data' / 'topics_today.jsonl'
if not topics_file.exists():
    print('topics file not found:', topics_file)
    sys.exit(1)

with open(topics_file, 'r', encoding='utf-8') as f:
    items = [json.loads(line) for line in f if line.strip()]

img = ROOT / 'assets' / 'bg' / 'dark_texture_01.jpg'
if not img.exists():
    imgs = list((ROOT/'assets').rglob('*.jpg'))
    if imgs:
        img = imgs[0]
    else:
        print('No image found in assets to synthesize scenes.'); sys.exit(1)

manifest = []
for it in items:
    title = it.get('title')
    slug = ''.join([c for c in title.lower().replace(' ','_') if c.isalnum() or c in '._-'])[:60]
    jobdir = OUTROOT / slug
    scenes = jobdir / 'scenes'
    jobdir.mkdir(parents=True, exist_ok=True)
    scenes.mkdir(parents=True, exist_ok=True)
    script_json = jobdir / 'script.json'
    if not script_json.exists():
        js = {'title': title, 'lines': [title, 'Point 1', 'Point 2', 'Close', 'CTA'], 'cta': 'Subscribe!'}
        script_json.write_text(json.dumps(js, ensure_ascii=False), encoding='utf-8')
    # copy voice if exists
    vsrc = ROOT / 'build' / 'voice.wav'
    if vsrc.exists():
        try:
            shutil.copy(vsrc, jobdir / 'voice.wav')
            log(f'Copied voice.wav to {jobdir}')
        except Exception as e:
            log(f'Failed to copy voice.wav: {e}')
    else:
        log(f'No voice.wav in build for {slug}; TTS will run if Piper is present')
    # create a short mp4 scene (6s)
    out_scene = scenes / '01.mp4'
    cmd = [str(FF), '-y', '-loop', '1', '-i', str(img), '-c:v', 'libx264', '-t', '6', '-pix_fmt', 'yuv420p', '-vf', 'scale=1080:1920', str(out_scene)]
    log('Creating scene for ' + slug)
    p = subprocess.run(cmd, capture_output=True, text=True)
    log('ffmpeg rc: ' + str(p.returncode))
    if p.stdout: log('ffmpeg stdout: ' + p.stdout[:2000])
    if p.stderr: log('ffmpeg stderr: ' + p.stderr[:2000])
    # run render_scenes --fast
    out_mp4 = jobdir / 'video.mp4'
    cmd2 = [PY, str(ROOT / 'scripts' / 'render_scenes.py'), '--script_json', str(script_json), '--voice', str(jobdir / 'voice.wav'), '--scenes_dir', str(scenes), '--out', str(out_mp4), '--fast']
    log('Rendering ' + slug)
    proc = subprocess.run(cmd2, capture_output=True, text=True)
    log('render rc: ' + str(proc.returncode))
    if proc.stdout: log('render stdout: ' + proc.stdout[:4000])
    if proc.stderr: log('render stderr: ' + proc.stderr[:8000])
    # attempt to extract thumbnail
    thumb = jobdir / 'thumb.png'
    if not thumb.exists() and out_mp4.exists():
        ffprobe = str(ROOT / 'tools' / 'ffmpeg' / 'ffmpeg-8.0-essentials_build' / 'bin' / 'ffmpeg.exe')
        p3 = subprocess.run([ffprobe, '-y', '-i', str(out_mp4), '-vframes', '1', '-q:v', '2', str(jobdir / 'frame0.jpg')], capture_output=True, text=True)
        log('thumb rc: ' + str(p3.returncode))
        if p3.stderr: log('thumb stderr: ' + p3.stderr[:2000])
        # rudimentary thumb: copy frame0 as thumb.png
        try:
            from PIL import Image
            im = Image.open(jobdir / 'frame0.jpg').convert('RGB')
            im.save(thumb, format='PNG')
            log('Saved thumb.png')
        except Exception as e:
            log('Thumb save failed: ' + str(e))
    manifest.append({'title': title, 'slug': slug, 'video': str(out_mp4), 'thumb': str(thumb) if thumb.exists() else ''})

# write manifest
mfn = OUTROOT / 'manifest.csv'
with open(mfn, 'w', encoding='utf-8', newline='') as f:
    import csv
    w = csv.DictWriter(f, fieldnames=['title','slug','video','thumb'])
    w.writeheader()
    for r in manifest: w.writerow(r)
print('Done. Manifest:', mfn)
print('Listing build/today')
for d in OUTROOT.iterdir():
    if d.is_dir():
        print(d)
        for f in d.iterdir(): print('  ', f.name)
# write log file
try:
    LOG.write_text('\n'.join(_log_lines), encoding='utf-8')
    print('Wrote log', LOG)
except Exception:
    pass
