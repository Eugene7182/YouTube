#!/usr/bin/env python3
"""Simple batch test runner: run a quick pipeline for each topic in a jsonl file.
This script skips TTS if build/voice.wav exists (it will copy it), otherwise it attempts to generate via piper.
It uses fetch_assets to auto-download assets (images+videos) and render_scenes.py with --fast for quick results.
"""
import sys
from pathlib import Path
import json, shutil, subprocess
ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable

def slugify(title: str) -> str:
    return "".join([c for c in title.lower().replace(' ', '_') if c.isalnum() or c in '._-'])[:60]

def run_topic(item, outroot: Path, voice_path: str):
    title = item.get('title')
    slug = slugify(title)
    jobdir = outroot / slug
    jobdir.mkdir(parents=True, exist_ok=True)
    script_json = jobdir / 'script.json'
    # create a minimal script.json if not exists
    if not script_json.exists():
        js = {"title": title, "lines": [title, "Brief beat 1", "Brief beat 2", "Close", "CTA"], "cta": "Subscribe"}
        script_json.write_text(json.dumps(js, ensure_ascii=False), encoding='utf-8')
    # copy voice if available
    src_voice = ROOT / 'build' / 'voice.wav'
    if src_voice.exists():
        try:
            shutil.copy(src_voice, jobdir / 'voice.wav')
            print('copied existing voice to', jobdir/'voice.wav')
        except Exception as e:
            print('copy voice failed', e)
    # fetch assets
    scenes_dir = jobdir / 'scenes'
    scenes_dir.mkdir(parents=True, exist_ok=True)
    print('fetching assets to', scenes_dir)
    subprocess.run([PY, str(ROOT/'scripts'/'fetch_assets.py'), '--script_json', str(script_json), '--outdir', str(scenes_dir), '--want', '10', '--want_videos', '3'], check=False)
    # render (fast)
    out_mp4 = jobdir / 'video.mp4'
    print('rendering to', out_mp4)
    subprocess.run([PY, str(ROOT/'scripts'/'render_scenes.py'), '--script_json', str(script_json), '--voice', str(jobdir/'voice.wav'), '--scenes_dir', str(scenes_dir), '--out', str(out_mp4), '--fast'], check=False)
    # create thumb if not exists
    thumb = jobdir / 'thumb.png'
    if not thumb.exists() and out_mp4.exists():
        subprocess.run(['.\\tools\\ffmpeg\\ffmpeg-8.0-essentials_build\\bin\\ffmpeg.exe','-y','-i',str(out_mp4),'-vframes','1','-q:v','2',str(jobdir/'frame0.jpg')], check=False)
        try:
            from PIL import Image, ImageDraw, ImageFont
            im = Image.open(jobdir/'frame0.jpg').convert('RGB')
            W,H = im.size
            overlay = Image.new('RGBA',(W,int(H*0.28)),(0,0,0,120))
            im.paste(overlay,(0,int(H*0.72)),overlay)
            im.save(thumb, quality=90)
            print('thumb saved', thumb)
        except Exception as e:
            print('thumb failed', e)
    return jobdir

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('Usage: run_batch_test.py topics.jsonl')
        sys.exit(1)
    topics = sys.argv[1]
    voice = sys.argv[2] if len(sys.argv)>2 else 'assets/voices/en_US-amy-medium.onnx'
    outroot = Path('build/test_run')
    outroot.mkdir(parents=True, exist_ok=True)
    items = []
    with open(topics, 'r', encoding='utf-8') as f:
        for line in f:
            line=line.strip()
            if not line: continue
            items.append(json.loads(line))
    for it in items:
        print('\n=== TOPIC ===', it.get('title'))
        jobdir = run_topic(it, outroot, voice)
        print('done jobdir', jobdir)
    print('All done')
