#!/usr/bin/env python3
"""Quick test runner: run two topics with produce_shorts.run_one and write a report.
"""
import sys
from pathlib import Path
import shutil, json, traceback, os
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from scripts.produce_shorts import run_one, load_jsonl

OUT = ROOT / 'build' / 'test_run'
OUT.mkdir(parents=True, exist_ok=True)
report = []

items = load_jsonl('data/topics_test2.jsonl')
for it in items:
    title = it.get('title')
    slug = "".join([c for c in title.lower().replace(' ','_') if c.isalnum() or c in '._-'])[:60]
    jobdir = OUT / slug
    jobdir.mkdir(parents=True, exist_ok=True)
    # copy existing voice if present to avoid running Piper
    src_voice = ROOT / 'build' / 'voice.wav'
    if src_voice.exists():
        try:
            shutil.copy(src_voice, jobdir / 'voice.wav')
        except Exception:
            pass
    try:
        res = run_one(it, 'assets/voices/en_US-amy-medium.onnx', str(OUT), want_assets=10, want_videos=3)
        # collect files in jobdir
        files = [p.name for p in sorted(jobdir.glob('*'))]
        report.append({'title': title, 'status': 'ok', 'jobdir': str(jobdir), 'files': files, 'res': res})
    except Exception as e:
        tb = traceback.format_exc()
        report.append({'title': title, 'status': 'error', 'jobdir': str(jobdir), 'error': str(e), 'trace': tb})

# write report file
rep_file = OUT / 'quick_test_report.json'
rep_file.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print('WROTE', rep_file)
for r in report:
    print(r['title'], r['status'], r.get('files') or r.get('error'))
