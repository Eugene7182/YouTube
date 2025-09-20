from moviepy.editor import *
from PIL import Image, ImageDraw, ImageFont
from pathlib import Path
import textwrap

FONT = None

def load_font(path: str, size: int):
    global FONT
    try:
        FONT = ImageFont.truetype(path, size)
    except Exception:
        # Fallback to default PIL font
        FONT = ImageFont.load_default()

def caption_frame(text: str, size=(1080,1920), bg=(20,20,25), fg=(255,255,255), pad=40):
    img = Image.new("RGB", size, bg)
    draw = ImageDraw.Draw(img)
    w, h = size
    max_chars = 28
    wrapped = []
    for line in text.split("\n"):
        if not line.strip():
            wrapped.append("")
        else:
            wrapped += textwrap.wrap(line, width=max_chars)
    y = int(h*0.2)
    for ln in wrapped:
        bbox = draw.textbbox((0,0), ln, font=FONT)
        tw, th = bbox[2]-bbox[0], bbox[3]-bbox[1]
        x = (w - tw)//2
        # caption background
        draw.rectangle((x-14, y-10, x+tw+14, y+th+10), fill=(0,0,0,140))
        draw.text((x, y), ln, font=FONT, fill=fg)
        y += th + 28
    return ImageClip(img).set_duration(2.0)

def assemble_short(lines: list[str], audio_path: str, title: str, out_path: str, fps=30, resolution=(1080,1920)):
    aclip = AudioFileClip(audio_path)
    seg = max(1.8, aclip.duration / max(1, len(lines)))
    clips = [caption_frame(ln, size=resolution).set_duration(seg) for ln in lines]
    v = concatenate_videoclips(clips, method="compose").set_audio(aclip)
    v.write_videofile(out_path, fps=fps, codec="libx264", audio_codec="aac")

if __name__ == "__main__":
    load_font("DejaVuSans.ttf", 64)
    assemble_short(["Hook line","Setup","Twist","Punch"], "voice.mp3", "Demo", "video.mp4")
