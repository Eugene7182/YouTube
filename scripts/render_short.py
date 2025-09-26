import argparse, json, os, subprocess, numpy as np
from moviepy.editor import ImageClip, AudioFileClip, CompositeVideoClip, vfx
from PIL import Image, ImageDraw, ImageFont
import shutil

if not hasattr(Image, "ANTIALIAS"):
    Image.ANTIALIAS = Image.Resampling.LANCZOS

from utils_textimg import render_text_frame

W, H = 1080, 1920
# Audio polish chain applied via FFmpeg
# safer audio chain without deesser (FFmpeg deesser has varying syntax across builds)
AUDIO_POLISH = "highpass=f=80,acompressor=threshold=-18dB:ratio=3:attack=10:release=120,loudnorm=I=-14:TP=-1:LRA=11"

def ken_burns(bg_path, dur, zoom=0.18):
    img = Image.open(bg_path).convert("RGB").resize((W, H))
    clip = ImageClip(np.array(img)).set_duration(dur)
    # slightly brighten background for better contrast with captions
    try:
        # brighten and slightly increase contrast for visibility
        clip = clip.fx(vfx.colorx, 1.25)
    except Exception:
        pass
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
    # Prefer a local ffmpeg in tools/ffmpeg if present (avoids relying on PATH); else check PATH
    ffmpeg_exec = None
    try:
        from pathlib import Path
        ff_local = list(Path("tools/ffmpeg").glob("**/bin/ffmpeg.exe")) if Path("tools/ffmpeg").exists() else []
        if ff_local:
            ffmpeg_exec = str(ff_local[0])
    except Exception:
        ffmpeg_exec = None

    if not ffmpeg_exec:
        ffmpeg_exec = shutil.which("ffmpeg")

    if ffmpeg_exec:
        # safe ffmpeg audio filter (no deesser) and fixed video/audio params
        ff_af = "highpass=f=80,acompressor=threshold=-18dB:ratio=3:attack=10:release=120,loudnorm=I=-14:TP=-1:LRA=11"
        cmd = [ffmpeg_exec, "-y", "-i", tmp,
               "-vf", "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2,format=yuv420p",
               "-af", ff_af, "-ar", "48000",
               "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-pix_fmt", "yuv420p",
               "-r", "60", out_mp4]
    else:
        print("ffmpeg not found in PATH — skipping audio polish step. Final file may not be loudness-normalized.")
        # Move temp file to final path
        try:
            os.replace(tmp, out_mp4)
            print(f"Wrote output (no ffmpeg): {out_mp4}")
            return
        except Exception:
            # fallback to subprocess call which will raise the original error
            pass
    if music_path and os.path.exists(music_path):
        ff_af = AUDIO_POLISH
        cmd = [ffmpeg_exec or "ffmpeg", "-y", "-i", tmp, "-stream_loop", "-1", "-i", music_path,
               "-filter_complex", "[1:a]volume=0.12,apad[a2];[0:a][a2]amix=inputs=2:normalize=0[a]",
               "-map", "0:v", "-map", "[a]",
               "-vf", "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2,format=yuv420p",
               "-af", ff_af,
               "-ar", "48000",
               "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-pix_fmt", "yuv420p",
               "-r", "60", out_mp4]
    # Run ffmpeg post-processing (no retry with deesser)
    subprocess.check_call(cmd)
    # remove temporary file
    try:
        if os.path.exists(tmp):
            os.remove(tmp)
    except Exception:
        pass

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--script", required=True)
    ap.add_argument("--voice", required=True)
    ap.add_argument("--bg", required=True)
    ap.add_argument("--music", default="")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    build_video(args.script, args.voice, args.bg, args.music, args.out)

