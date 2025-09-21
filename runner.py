from dotenv import load_dotenv
import argparse, yaml
from pathlib import Path
from generate_script import generate_script
from tts import synth_sync
from build_short import assemble_short, load_font
from upload_youtube import upload

load_dotenv()

def to_lines(script: str, mode: str):
    if mode == "shorts":
        lines = []
        for raw in script.split("\n"):
            if any(raw.startswith(p) for p in ["HOOK:", "SETUP:", "TWIST:", "PUNCH:"]):
                lines.append(raw.split(":",1)[1].strip())
        return lines
    return [s for s in script.split("\n") if s.strip()]

if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--topic', required=True)
    ap.add_argument('--mode', choices=['shorts','picks'], default='shorts')
    ap.add_argument('--lang', choices=['en'], default='en')
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()

    cfg = yaml.safe_load(open('config.yaml','r',encoding='utf-8'))
    lang = cfg.get('tts_lang', 'ru')
    timeout = float(cfg.get('tts_timeout', 30))
    font = cfg.get('font','DejaVuSans.ttf')
    load_font(font, 64)

    script = generate_script(args.topic, mode=args.mode)
    Path('out_script.md').write_text(script, encoding='utf-8')

    synth_sync(script, 'voice.mp3', lang=lang, timeout=timeout)

    lines = to_lines(script, args.mode)
    assemble_short(lines, 'voice.mp3', args.topic, 'video.mp4', fps=cfg.get('fps',30), resolution=tuple(cfg.get('resolution',[1080,1920])))

    if not args.dry_run:
        desc = script + "\n\n" + ' '.join(cfg.get('shorts_hashtags',['#shorts']))
        yt_id = upload('video.mp4', args.topic, desc, tags=cfg.get('shorts_hashtags',['#shorts']), categoryId=str(cfg.get('categoryId','24')), privacyStatus=cfg.get('privacyStatus','private'))
        print('YouTube draft video id:', yt_id)
    print('OK')
