import os
from fastapi import FastAPI
from pydantic import BaseModel
from pathlib import Path
from yaml import safe_load

from generate_script import generate_script
from tts import synth_sync
from build_short import assemble_short, load_font
from upload_youtube import upload

app = FastAPI()

def ensure_oauth_files():
    token_json = os.getenv("YOUTUBE_TOKEN_JSON", "")
    client_json = os.getenv("YOUTUBE_CLIENT_SECRET_JSON", "")
    if token_json:
        Path("token.json").write_text(token_json, encoding="utf-8")
    if client_json:
        Path("client_secret.json").write_text(client_json, encoding="utf-8")

class RunReq(BaseModel):
    topic: str
    mode: str = "shorts"
    script: str | None = None
    draft: bool = True

@app.get("/health")
def health():
    return {"ok": True}

@app.post("/run")
def run(req: RunReq):
    ensure_oauth_files()
    cfg = safe_load(open("config.yaml","r",encoding="utf-8"))
    voice = cfg.get("voice","en-US-JennyNeural")
    font = cfg.get("font","DejaVuSans.ttf")
    load_font(font, 64)

    script = req.script if req.script else generate_script(req.topic, mode=req.mode)
    Path("out_script.md").write_text(script, encoding="utf-8")
    synth_sync(script, "voice.mp3", voice=voice)

    def to_lines(s: str, mode: str):
        if mode == "shorts":
            lines = []
            for raw in s.split("\n"):
                if any(raw.startswith(p) for p in ["HOOK:","SETUP:","TWIST:","PUNCH:"]):
                    lines.append(raw.split(":",1)[1].strip())
            return lines
        return [x for x in s.split("\n") if x.strip()]

    lines = to_lines(script, req.mode)
    assemble_short(lines, "voice.mp3", req.topic, "video.mp4", fps=cfg.get("fps",30), resolution=tuple(cfg.get("resolution",[1080,1920])))

    privacy = "private" if req.draft else "public"
    desc = (script[:4800] + "\n\n#shorts") if req.mode=="shorts" else script[:4800]
    vid = upload("video.mp4", req.topic, desc, tags=cfg.get("shorts_hashtags",["#shorts"]), categoryId=str(cfg.get("categoryId","24")), privacyStatus=privacy)
    return {"ok": True, "youtubeVideoId": vid}

@app.post("/run/queue")
def run_queue():
    p = Path("topics.csv")
    if not p.exists():
        return {"ok": False, "err": "topics.csv missing"}
    lines = [ln.strip() for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]
    if not lines:
        return {"ok": False, "err": "no topics"}
    topic = lines[0]
    p.write_text("\n".join(lines[1:])+"\n", encoding="utf-8")
    return run(RunReq(topic=topic))
