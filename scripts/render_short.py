
import argparse, json, os, subprocess, numpy as np
from moviepy.editor import ImageClip, AudioFileClip, CompositeVideoClip, vfx
from PIL import Image, ImageDraw, ImageFont
from utils_textimg import render_text_frame

W, H = 1080, 1920

def ken_burns(bg_path, dur, zoom=0.08):
    img = Image.open(bg_path).convert("RGB").resize((W, H))
    clip = ImageClip(np.array(img)).set_duration(dur)
    clip = clip.fx(vfx.resize, lambda t: 1 + (zoom/dur)*t).set_position(("center", "center"))
    return clip

def build_video(script_json, voice_wav, bg_path, music_path, out_mp4, brand_text="Dark & Strange"):
    j = json.load(open(script_json, encoding="utf-8"))
    lines = j["lines"] + [j.get("cta","")]
    a_voice = AudioFileClip(voice_wav)
    duration = max(10.0, a_voice.duration)

    bg = ken_burns(bg_path, dur=duration, zoom=0.08)

    clips = [bg]
    # watermark
    wm_img = Image.new("RGBA", (W, H), (0,0,0,0))
    draw = ImageDraw.Draw(wm_img)
    try: font = ImageFont.truetype("assets/fonts/Inter-Medium.ttf", 36)
    except: font = ImageFont.load_default()
    draw.text((W-20, H-20), brand_text, anchor="rd", fill=(232,230,227,200), font=font)
    from numpy import array as nparr
    clips.append(ImageClip(nparr(wm_img)).set_duration(duration))

    # captions
    step = max(3.0, duration/len(lines))
    t = 0.35
    for line in lines:
        img = render_text_frame(line)
        clips.append(ImageClip(nparr(img)).set_duration(step).set_start(t).set_position((0,0)))
        t += step

    comp = CompositeVideoClip(clips, size=(W,H)).set_audio(a_voice)
    comp.fps = 60

    tmp = out_mp4.replace(".mp4",".temp.mp4")
    os.makedirs(os.path.dirname(out_mp4), exist_ok=True)
    comp.write_videofile(tmp, fps=60, codec="libx264", audio_codec="aac", audio_fps=48000,
                         bitrate=None, preset="slow", ffmpeg_params=["-pix_fmt","yuv420p","-crf","18"])

    # loudness norm and optional music bed
    cmd = ["ffmpeg","-y","-i", tmp, "-af","loudnorm=I=-14:TP=-1:LRA=11",
           "-c:v","libx264","-preset","slow","-crf","18","-pix_fmt","yuv420p", out_mp4]
    if music_path and os.path.exists(music_path):
        cmd = ["ffmpeg","-y","-i", tmp, "-stream_loop","-1","-i", music_path,
               "-filter_complex","[1:a]volume=0.12,apad[a2];[0:a][a2]amix=inputs=2:normalize=0[a]",
               "-map","0:v","-map","[a]","-af","loudnorm=I=-14:TP=-1:LRA=11",
               "-c:v","libx264","-preset","slow","-crf","18","-pix_fmt","yuv420p", out_mp4]
    subprocess.check_call(cmd); os.remove(tmp)

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--script", required=True)
    ap.add_argument("--voice", required=True)
    ap.add_argument("--bg", required=True)
    ap.add_argument("--music", default="")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    build_video(args.script, args.voice, args.bg, args.music, args.out)
