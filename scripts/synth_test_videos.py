#!/usr/bin/env python3
"""Synthesize short mp4 scenes from an existing image and run render_scenes.py --fast for test topics.
This forces the pipeline to have actual .mp4 scene files so MoviePy treats them as videos.
"""
import sys
from pathlib import Path
import json, subprocess, shutil
ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable
FF = ROOT / 'tools' / 'ffmpeg' / 'ffmpeg-8.0-essentials_build' / 'bin' / 'ffmpeg.exe'

in_topics = Path('data/topics_test2.jsonl')
if not in_topics.exists():
    print('topics_test2.jsonl not found; create data/topics_test2.jsonl or edit script')
    sys.exit(1)

with open(in_topics,'r',encoding='utf-8') as f:
    items = [json.loads(line) for line in f if line.strip()]

for it in items:
    title = it.get('title')
    slug = ''.join([c for c in title.lower().replace(' ','_') if c.isalnum() or c in '._-'])[:60]
    jobdir = Path('build/test_run')/slug
    scenes = jobdir/'scenes'
    jobdir.mkdir(parents=True, exist_ok=True)
    scenes.mkdir(parents=True, exist_ok=True)
    # prepare script.json
    script = jobdir/'script.json'
    if not script.exists():
        js = {"title":title, "lines":[title, 'Point 1','Point 2','Close','CTA'], 'cta':'Subscribe!'}
        script.write_text(json.dumps(js, ensure_ascii=False), encoding='utf-8')
    # copy voice if exists
    src_voice = ROOT/'build'/'voice.wav'
    if src_voice.exists():
        try:
            shutil.copy(src_voice, jobdir/'voice.wav')
        except:
            pass
    # create a short mp4 from existing image
    img = ROOT/'assets'/'bg'/'dark_texture_01.jpg'
    if not img.exists():
        # fallback to any jpg in assets
        imgs = list((ROOT/'assets').rglob('*.jpg'))
        if imgs: img = imgs[0]
    out_mp4 = scenes/'01.mp4'
    cmd = [str(FF), '-y', '-loop', '1', '-i', str(img), '-c:v', 'libx264', '-t', '6', '-pix_fmt', 'yuv420p', '-vf', 'scale=1080:1920', str(out_mp4)]
    print('creating video scene for', slug)
    subprocess.run(cmd, check=False)
    # run render_scenes.py --fast
    voice = jobdir/'voice.wav'
    if not voice.exists():
        print('no voice.wav in', jobdir, 'render may fail (Piper required)')
    out_video = jobdir/'video.mp4'
    print('running render_scenes for', slug)
    subprocess.run([PY, str(ROOT/'scripts'/'render_scenes.py'), '--script_json', str(script), '--voice', str(voice), '--scenes_dir', str(scenes), '--out', str(out_video), '--fast'], check=False)
    print('done', slug)

print('All topics processed')
