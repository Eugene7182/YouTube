#!/usr/bin/env python3
"""Diagnostic runner: create a scene mp4, run render_scenes.py --fast for first test topic,
capture stdout/stderr and write to build/test_run/diag_log.txt, then list files produced.
"""
import subprocess, sys, os
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / 'build' / 'test_run' / 'diag_log.txt'
LOG.parent.mkdir(parents=True, exist_ok=True)
ff = ROOT / 'tools' / 'ffmpeg' / 'ffmpeg-8.0-essentials_build' / 'bin' / 'ffmpeg.exe'
img = ROOT / 'assets' / 'bg' / 'dark_texture_01.jpg'
scene = ROOT / 'build' / 'test_run' / 'diag_scene.mp4'

with open(LOG, 'w', encoding='utf-8') as log:
    try:
        log.write('=== START DIAG ===\n')
        # create scene
        cmd = [str(ff), '-y', '-loop', '1', '-i', str(img), '-c:v', 'libx264', '-t', '6', '-pix_fmt', 'yuv420p', '-vf', 'scale=1080:1920', str(scene)]
        log.write('RUN: ' + ' '.join(cmd) + '\n')
        p = subprocess.run(cmd, capture_output=True, text=True)
        log.write('ffmpeg rc: ' + str(p.returncode) + '\n')
        log.write('ffmpeg stdout:\n' + (p.stdout or '')[:10000] + '\n')
        log.write('ffmpeg stderr:\n' + (p.stderr or '')[:20000] + '\n')

        # prepare scenes dir
        sdir = ROOT / 'build' / 'test_run' / 'diag_scenes'
        sdir.mkdir(parents=True, exist_ok=True)
        (sdir / '01.mp4').write_bytes(scene.read_bytes())

        # copy script for first topic
        topics = ROOT / 'data' / 'topics_today.jsonl'
        first = None
        with open(topics, 'r', encoding='utf-8') as f:
            for line in f:
                line=line.strip()
                if not line: continue
                first=line
                break
        if not first:
            log.write('No topics in data/topics_today.jsonl\n')
            raise SystemExit(1)
        import json
        it = json.loads(first)
        slug = ''.join([c for c in it['title'].lower().replace(' ','_') if c.isalnum() or c in '._-'])[:60]
        jobdir = ROOT / 'build' / 'test_run' / slug
        jobdir.mkdir(parents=True, exist_ok=True)
        # write script.json
        script = jobdir / 'script.json'
        js = {'title': it['title'], 'lines': [it['title'],'Point1','Point2','Close','CTA'], 'cta':'Subscribe!'}
        script.write_text(json.dumps(js, ensure_ascii=False), encoding='utf-8')
        # copy voice if exists
        vsrc = ROOT / 'build' / 'voice.wav'
        if vsrc.exists():
            (jobdir / 'voice.wav').write_bytes(vsrc.read_bytes())
        else:
            log.write('No voice.wav in build; TTS will run (may fail if Piper not present)\n')

        outmp4 = jobdir / 'video.mp4'
        cmd2 = [sys.executable, str(ROOT / 'scripts' / 'render_scenes.py'), '--script_json', str(script), '--voice', str(jobdir / 'voice.wav'), '--scenes_dir', str(sdir), '--out', str(outmp4), '--fast']
        log.write('RUN: ' + ' '.join(cmd2) + '\n')
        p2 = subprocess.run(cmd2, capture_output=True, text=True)
        log.write('render rc: ' + str(p2.returncode) + '\n')
        log.write('render stdout:\n' + (p2.stdout or '')[:10000] + '\n')
        log.write('render stderr:\n' + (p2.stderr or '')[:20000] + '\n')

        # attempt thumbnail extraction
        thumb = jobdir / 'thumb.png'
        if not thumb.exists() and outmp4.exists():
            cmd3 = [str(ROOT / 'tools' / 'ffmpeg' / 'ffmpeg-8.0-essentials_build' / 'bin' / 'ffmpeg.exe'), '-y', '-i', str(outmp4), '-vframes', '1', '-q:v', '2', str(jobdir / 'frame0.jpg')]
            log.write('RUN: ' + ' '.join(cmd3) + '\n')
            p3 = subprocess.run(cmd3, capture_output=True, text=True)
            log.write('thumb rc: ' + str(p3.returncode) + '\n')
            log.write('thumb stderr:\n' + (p3.stderr or '')[:10000] + '\n')

        # list jobdir
        log.write('FILES in ' + str(jobdir) + '\n')
        for p in sorted(jobdir.glob('*')):
            log.write(' - ' + p.name + '\n')

    except Exception as e:
        import traceback
        log.write('EXCEPTION:\n')
        log.write(''.join(traceback.format_exception(e.__class__, e, e.__traceback__)))
    finally:
        log.write('\n=== END DIAG ===\n')

print('Wrote', LOG)
print(LOG.read_text(encoding='utf-8'))
