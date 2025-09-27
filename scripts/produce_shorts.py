# -*- coding: utf-8 -*-
"""
Auto production for Shorts:
topics.jsonl -> script JSON -> TTS (Piper) -> fetch scenes (Pexels/Pixabay/Commons) -> render -> thumbnail -> manifest.csv
Optional: upload to YouTube (private) if deps and creds exist.

ENV expected:
  PIPER_EXE=path_to\piper.exe (если не в PATH)
  PEXELS_API_KEY=... (опционально)
  PIXABAY_API_KEY=... (опционально)
  OLLAMA_HOST=http://localhost:11434 (если есть Ollama)
  OLLAMA_MODEL=mistral (или phi3)
  YT_CLIENT_SECRET_JSON=inline json (опционально для upload)
  YT_TOKEN_JSON=inline json (опционально для upload)
"""
import os, json, csv, argparse, subprocess, sys, time, shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable

# --- helpers -----------------------------------------------------------------
def sh(cmd, check=True):
    print(">>", " ".join(cmd))
    return subprocess.run(cmd, check=check)

def ensure_dir(p): Path(p).mkdir(parents=True, exist_ok=True)

def load_jsonl(path):
    rows=[]
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line=line.strip()
            if not line: continue
            rows.append(json.loads(line))
    return rows

def write_json(path, obj):
    ensure_dir(Path(path).parent)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)

def piper_exe():
    exe = os.getenv("PIPER_EXE")
    if exe and Path(exe).exists(): return exe
    # поиск локально
    cand = list(ROOT.glob("tools/piper/**/piper.exe"))
    if cand: return str(cand[0])
    return "piper.exe"  # вдруг уже в PATH

def ffprobe_exe():
    cand = list(ROOT.glob("tools/ffmpeg/**/ffprobe.exe"))
    return str(cand[0]) if cand else "ffprobe"

# --- script generation via Ollama (optional) ---------------------------------
def has_ollama():
    import requests
    try:
        host = os.getenv("OLLAMA_HOST","http://localhost:11434").rstrip("/")
        r = requests.get(host+"/api/tags", timeout=2)
        return r.status_code==200
    except Exception:
        return False

def gen_script_ollama(topic:str, series:str):
    """
    series in {horror_top_n, legends_short, mystery_short, weird_history}
    Returns JSON: {title, lines[], cta}
    """
    import requests
    host = os.getenv("OLLAMA_HOST","http://localhost:11434").rstrip("/")
    model = os.getenv("OLLAMA_MODEL","mistral")
    sys_prompt = {
      "horror_top_n": "You write concise, punchy 45s horror/legend shorts. Use hedging, no gore.",
      "legends_short": "You write 40–50s legend/mystery shorts. Avoid hard claims; intrigue over certainty.",
      "mystery_short": "You write 40–50s unexplained shorts. Avoid certainty; focus on clues.",
      "weird_history": "You write odd-but-safe history shorts. Prefer verifiable curiosities."
    }.get(series,"You write 45s Dark & Strange shorts. No gore.")
    user_tmpl = f"Topic: {topic}\nReturn JSON: {{\"title\": \"...\", \"lines\": [\"Hook\", \"Beat1\", \"Beat2\", \"Beat3-4\", \"Twist\"], \"cta\": \"Subscribe for nightly chills!\"}}"

    prompt = f"System:\n{sys_prompt}\n\nUser:\n{user_tmpl}\nOnly return valid JSON."
    data = {"model": model, "prompt": prompt, "stream": False, "options": {"temperature": 0.8}}
    r = requests.post(host+"/api/generate", json=data, timeout=60)
    r.raise_for_status()
    txt = r.json().get("response","{}").strip()
    # попытаться распарсить JSON из ответа
    start = txt.find("{"); end = txt.rfind("}")
    if start>=0 and end>start: txt = txt[start:end+1]
    try:
        js = json.loads(txt)
    except Exception:
        js = {"title": topic, "lines": ["Legend says...", "A witness reportedly...", "Another clue...", "Then—silence."], "cta":"Subscribe for nightly chills!"}
    return js

# --- main pipeline per item ---------------------------------------------------
def run_one(item, voice_path, outdir, want_assets=10, want_videos=3, bg_scenes=None, music=None, auto_script=True):
    """
    item expects dict with keys: title, topic, series (optional)
    """
    title = item.get("title") or item.get("topic") or "Untitled"
    series = item.get("series") or item.get("topic") or "mystery_short"
    slug = "".join([c for c in title.lower().replace(" ","_") if c.isalnum() or c in "._-"])[:60]
    jobdir = Path(outdir)/slug
    ensure_dir(jobdir)
    script_json = jobdir/"script.json"
    voice_wav   = jobdir/"voice.wav"
    scenes_dir  = jobdir/"scenes"
    out_mp4     = jobdir/"video.mp4"
    thumb_png   = jobdir/"thumb.png"

    # 1) script
    if auto_script and not script_json.exists():
        if has_ollama():
            try:
                js = gen_script_ollama(title, series)
                write_json(script_json, js)
            except Exception as e:
                print("OLLAMA failed, fallback:", e)
        if not script_json.exists():
            # fallback из data\one_short.json если есть
            src = ROOT/"data/one_short.json"
            if src.exists():
                shutil.copy(src, script_json)
            else:
                write_json(script_json, {"title": title, "lines":[title,"…","…","…","Twist"], "cta":"Subscribe."})

    # 2) TTS (Piper)
    if not voice_wav.exists():
        piper = piper_exe()
        # модель голоса берём из переданного voice_path
        cmd = [piper, "--model", str(voice_path), "--output_file", str(voice_wav), "--sample_rate", "48000"]
        # текст Piper берёт из stdin — соберём из строк
        import tempfile
        txt = "\n".join(json.load(open(script_json, "r", encoding="utf-8")).get("lines",[]))
        tmp = tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8"); tmp.write(txt); tmp.close()
        cmd += ["--text_file", tmp.name]
        sh(cmd)

    # 3) assets fetch
    if not scenes_dir.exists() or not any(scenes_dir.iterdir()):
        sh([PY, str(ROOT/"scripts/fetch_assets.py"),
            "--script_json", str(script_json),
            "--outdir", str(scenes_dir),
            "--want", str(want_assets),
            "--want_videos", str(want_videos)])

    # 4) render by scenes
    sh([PY, str(ROOT/"scripts/render_scenes.py"),
        "--script_json", str(script_json),
        "--voice", str(voice_wav),
        "--scenes_dir", str(scenes_dir),
        "--out", str(out_mp4)] + (['--music', music] if music else []) + (['--fast'] if os.getenv('FAST_RENDER','') or '--fast' in sys.argv else []))

    # 5) thumbnail (кадр 0 с тайтлом)
    try:
        probe = ffprobe_exe()
        # вытащим первый кадр
        thumb_raw = jobdir/"frame0.jpg"
        sh(["ffmpeg","-y","-i",str(out_mp4),"-vframes","1","-q:v","2",str(thumb_raw)])
        from PIL import Image, ImageDraw, ImageFont
        im = Image.open(thumb_raw).convert("RGB")
        draw = ImageDraw.Draw(im)
        W,H = im.size
        title_txt = title[:80]
        # фон под текст
        overlay = Image.new("RGBA",(W,int(H*0.28)),(0,0,0,130))
        im.paste(overlay,(0,int(H*0.72)),overlay)
        # шрифт
        font=None
        for cand in ["assets/fonts/Inter-Bold.ttf","assets/fonts/Roboto-Bold.ttf"]:
            if Path(cand).exists():
                try: font = ImageFont.truetype(cand, 76); break
                except: pass
        if not font: font = ImageFont.load_default()
        # текст по центру
        tw,th = draw.textlength(title_txt, font=font), 76
        draw.text(((W-tw)/2, int(H*0.76)), title_txt, fill=(232,230,227), font=font, stroke_width=3, stroke_fill=(0,0,0))
        im.save(thumb_png, quality=95)
        thumb_raw.unlink(missing_ok=True)
    except Exception as e:
        print("Thumb generation failed:", e)

    return dict(title=title, path=str(out_mp4), thumb=str(thumb_png), scenes=str(scenes_dir), script=str(script_json))

# --- optional upload ----------------------------------------------------------
def try_upload(manifest_row):
    try:
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload
        from google.oauth2.credentials import Credentials
        cs = json.loads(os.getenv("YT_CLIENT_SECRET_JSON","{}"))
        tk = json.loads(os.getenv("YT_TOKEN_JSON","{}"))
        if not tk: 
            print("No YT_TOKEN_JSON — skip upload"); return None
        creds = Credentials(
            token=tk.get("token"),
            refresh_token=tk.get("refresh_token"),
            token_uri=tk.get("token_uri","https://oauth2.googleapis.com/token"),
            client_id=tk.get("client_id"), client_secret=tk.get("client_secret"),
            scopes=tk.get("scopes",["https://www.googleapis.com/auth/youtube.upload","https://www.googleapis.com/auth/youtube"])
        )
        yt = build("youtube","v3", credentials=creds)
        body = dict(
            snippet=dict(
                title=manifest_row["title"],
                description=manifest_row.get("description",""),
                tags=manifest_row.get("tags", "").split(",") if manifest_row.get("tags") else [],
                categoryId="24"  # Entertainment
            ),
            status=dict(privacyStatus="private")
        )
        media = MediaFileUpload(manifest_row["path"], mimetype="video/mp4", chunksize=-1, resumable=True)
        req = yt.videos().insert(part="snippet,status", body=body, media_body=media)
        resp = req.execute()
        return resp.get("id")
    except Exception as e:
        print("Upload failed/skipped:", e)
        return None

# --- CLI ----------------------------------------------------------------------
if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--topics_jsonl", required=True, help="jsonl: one item per line: {title, series?, tags?}")
    ap.add_argument("--voice", required=True, help="piper onnx voice path")
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--want_assets", type=int, default=10)
    ap.add_argument("--want_videos", type=int, default=3)
    ap.add_argument("--music", default=None)
    ap.add_argument("--no_script_gen", action="store_true", help="do not call Ollama")
    ap.add_argument("--fast", action="store_true", help="use fast single-image ffmpeg render for testing")
    ap.add_argument("--upload", action="store_true", help="upload to YouTube private (needs creds)")
    args = ap.parse_args()

    ensure_dir(args.outdir)
    items = load_jsonl(args.topics_jsonl)
    manifest_path = Path(args.outdir)/"manifest.csv"
    with open(manifest_path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["title","path","thumb","script","scenes","tags","youtube_id"])
        w.writeheader()
        for it in items:
            res = run_one(it, args.voice, args.outdir, args.want_assets, args.want_videos, music=args.music, auto_script=not args.no_script_gen)
            row = {**res, "tags": it.get("tags","")}
            if args.upload:
                vid = try_upload({**row, "description": it.get("description", "")})
                if vid:
                    row["youtube_id"] = vid
            w.writerow(row)
            print("DONE:", res["path"])
    print("Manifest:", manifest_path)
