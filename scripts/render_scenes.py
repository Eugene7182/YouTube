# -*- coding: utf-8 -*-
import os, json, math, random, argparse, textwrap, subprocess
import numpy as np
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from moviepy.editor import (AudioFileClip, VideoFileClip, ImageClip,
                            CompositeVideoClip, concatenate_videoclips, vfx)

QUALITY = dict(FPS=60, CRF="18", PRESET="slow", PIX="yuv420p")
W, H = 1080, 1920
FG = (232,230,227); BG=(12,12,12)

def load_script(path):
    data = json.load(open(path, "r", encoding="utf-8"))
    lines = [s for s in data.get("lines", []) if s and isinstance(s, str)]
    if data.get("cta"): lines.append(data["cta"])
    return data.get("title","Dark & Strange"), lines

def wrap_text(txt, max_chars=34):
    out=[]
    for part in txt.split("\n"):
        out += textwrap.wrap(part, width=max_chars, break_long_words=False, break_on_hyphens=False) or [part]
    return "\n".join(out)

def make_text_img(text, w=W-140, font_path=None, base_size=56):
    for cand in (font_path, "assets/fonts/Inter-Bold.ttf", "assets/fonts/Roboto-Bold.ttf"):
        try:
            if cand and os.path.isfile(cand):
                font = ImageFont.truetype(cand, base_size); break
        except: pass
    else:
        font = ImageFont.load_default()
    text = wrap_text(text)
    im = Image.new("RGBA", (w, 10)); draw = ImageDraw.Draw(im)
    bbox = draw.multiline_textbbox((0,0), text, font=font, spacing=6, align="center")
    tw, th = bbox[2]-bbox[0], bbox[3]-bbox[1]; pad=24
    canvas = Image.new("RGBA", (w, th+pad*2), (0,0,0,0)); draw = ImageDraw.Draw(canvas)
    # reduce overlay alpha so background remains visible
    overlay = Image.new("RGBA", canvas.size, (0,0,0,60)); canvas.alpha_composite(overlay)
    def draw_stroked(x,y):
        for dx,dy in [(-2,0),(2,0),(0,-2),(0,2),(-1,-1),(1,1),(1,-1),(-1,1)]:
            draw.multiline_text((x+dx,y+dy), text, font=font, fill=(0,0,0,255), spacing=6, align="center")
        draw.multiline_text((x,y), text, font=font, fill=FG+(255,), spacing=6, align="center")
    draw_stroked((w-tw)//2, pad)
    return canvas

def txt_clip_for(text, dur, y_frac=0.78):
    img = make_text_img(text)
    clip = ImageClip(np.array(img)).set_duration(dur).fx(vfx.fadein,0.15).fx(vfx.fadeout,0.25)
    return clip.set_position(("center", int(H*y_frac)-10))

def scene_clip(path, dur):
    p = str(path).lower()
    if p.endswith((".mp4",".mov",".mkv",".webm",".m4v")):
        base = VideoFileClip(str(path)).without_audio()
        base = (base.subclip(0, min(dur, base.duration))
                    if base.duration >= dur else
                    concatenate_videoclips([base] * math.ceil(dur/base.duration)).subclip(0,dur))
    else:
        # Load and resize images using PIL to avoid reliance on deprecated PIL.Image.ANTIALIAS
        from PIL import Image as PILImage
        im = PILImage.open(str(path)).convert("RGB")
        w0, h0 = im.size
        scale = H / float(h0)
        nw, nh = int(w0 * scale), H
        im = im.resize((nw, nh), PILImage.LANCZOS)
        base = ImageClip(np.array(im)).set_duration(dur)
    zoom = random.uniform(0.01, 0.03)
    # If base is an ImageClip we've already resized it via PIL above; avoid calling
    # moviepy's .resize which uses deprecated PIL.ANTIALIAS in some environments.
    if p.endswith(('.mp4','.mov','.mkv','.webm','.m4v')):
        base = (base.resize(height=H)
                    .resize(lambda t: 1.0 + zoom * (t/max(dur,0.01)))
                    .fx(vfx.colorx, 1.08)
                    .fx(vfx.lum_contrast, lum=3, contrast=5, contrast_thr=127)
                    .fx(vfx.fadein, 0.15).fx(vfx.fadeout, 0.2))
    else:
        # already resized with PIL to have height H; apply color tweaks and fades only
        # soften contrast to avoid over-darkening
        base = (
            base
            .fx(vfx.colorx, 1.10)
            .fx(vfx.lum_contrast, lum=6, contrast=3, contrast_thr=127)
            .fx(vfx.fadein, 0.15)
            .fx(vfx.fadeout, 0.2)
        )
    return base.on_color(size=(W,H), color=BG, pos=("center","center"))

def allocate_durations(lines, voice_dur):
    weights = [max(1, len(l.split())) for l in lines]; s=sum(weights)
    raw = [max(1.5, voice_dur*w/s) for w in weights]
    k = voice_dur / sum(raw)
    return [r*k for r in raw]

def build_video(script_json, voice_wav, scenes_dir, out_mp4, music_path=None, brand_text="Dark & Strange", fast=False):
    title, lines = load_script(script_json)
    a_voice = AudioFileClip(voice_wav); voice_dur = a_voice.duration
    exts = {'.jpg','.jpeg','.png','.mp4','.mov','.mkv','.webm','.m4v'}
    files = sorted([p for p in Path(scenes_dir).glob("*.*") if p.suffix.lower() in exts and not p.name.startswith('_')])
    if not files: raise FileNotFoundError(f"No assets in {scenes_dir}")
    durs = allocate_durations(lines, voice_dur)
    clips=[]
    for text, path, dur in zip(lines, files*(len(lines)//len(files)+1), durs):
        comp = CompositeVideoClip([scene_clip(path, dur), txt_clip_for(text, dur)], size=(W,H)).set_duration(dur)
        clips.append(comp)
    # If fast mode is requested, bypass the MoviePy composition and create a deterministic
    # single-image video using ffmpeg (loop first scene and mux voice). This is much faster
    # and useful for headless/test runs.
    if fast:
        first = files[0]
        ffmpeg = "ffmpeg"
        # ensure audio sample rate and video properties
        cmd = [ffmpeg, "-y", "-loop", "1", "-i", str(first), "-i", str(a_voice.filename),
               "-c:v", "libx264", "-tune", "stillimage", "-pix_fmt", QUALITY["PIX"], "-r", str(QUALITY["FPS"]),
               "-crf", QUALITY["CRF"], "-preset", QUALITY["PRESET"], "-c:a", "aac", "-ar", "48000", "-b:a", "192k",
               "-shortest", str(out_mp4)]
        subprocess.check_call(cmd)
        return

    video = concatenate_videoclips(clips, method="compose")
    wm = txt_clip_for(brand_text, video.duration, y_frac=0.92).fx(vfx.colorx, 0.85)
    final = CompositeVideoClip([video, wm], size=(W,H)).set_audio(a_voice)
    tmp = str(Path(out_mp4).with_suffix(".temp.mp4"))
    final.write_videofile(tmp, fps=QUALITY["FPS"], codec="libx264", audio_codec="aac", audio_fps=48000,
                          preset=QUALITY["PRESET"], threads=os.cpu_count(), temp_audiofile="__temp_aac.m4a",
                          remove_temp=True, ffmpeg_params=["-pix_fmt", QUALITY["PIX"], "-movflags", "faststart"])
    ffmpeg="ffmpeg"
    vf="format=yuv420p"
    af="highpass=f=80,acompressor=threshold=-18dB:ratio=3:attack=10:release=120,volume=3dB,loudnorm=I=-14:TP=-1:LRA=11"
    if music_path:
        cmd=[ffmpeg,"-y","-i",tmp,"-i",music_path,"-filter_complex",
             f"[1:a]volume=0.12[m];[0:a]volume=1.0[voc];[m][voc]amix=inputs=2:normalize=0[aout]",
             "-map","0:v:0","-map","[aout]","-vf",vf,"-af",af,"-c:v","libx264","-preset",QUALITY["PRESET"],
             "-crf",QUALITY["CRF"],"-r",str(QUALITY["FPS"]), out_mp4]
    else:
        cmd=[ffmpeg,"-y","-i",tmp,"-vf",vf,"-af",af,"-c:v","libx264","-preset",QUALITY["PRESET"],
             "-crf",QUALITY["CRF"],"-pix_fmt",QUALITY["PIX"],"-r",str(QUALITY["FPS"]), out_mp4]
    try: subprocess.check_call(cmd)
    finally:
        try: os.remove(tmp)
        except: pass

if __name__ == "__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--script_json", required=True)
    ap.add_argument("--voice", required=True)
    ap.add_argument("--scenes_dir", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--music", default=None)
    ap.add_argument("--brand", default="Dark & Strange")
    a=ap.parse_args()
    build_video(a.script_json, a.voice, a.scenes_dir, a.out, a.music, a.brand)
