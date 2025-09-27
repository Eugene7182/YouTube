import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path

import numpy as np
from moviepy.editor import AudioFileClip, CompositeVideoClip, ImageClip, VideoFileClip, vfx
from PIL import Image, ImageDraw, ImageFont

from utils_textimg import render_text_frame

W, H = 1080, 1920
QUALITY = dict(FPS=60, CRF="18", PRESET="slow", PIX="yuv420p")
AUDIO_FILTER_WITH_DEESSER = "deesser=f=6500:t=0.8,acompressor=threshold=-14dB:ratio=3:attack=10:release=120,highpass=f=80,loudnorm=I=-14:TP=-1:LRA=11"
AUDIO_FILTER_NO_DEESSER = "acompressor=threshold=-14dB:ratio=3:attack=10:release=120,highpass=f=80,loudnorm=I=-14:TP=-1:LRA=11"
DEFAULT_BG = Path("assets/bg/dark_texture_01.jpg")
TEMP_AUDIO = Path("build/_tmp_aac.m4a")

VIDEO_EXTENSIONS = (".mp4", ".mov", ".mkv", ".webm")

if not hasattr(Image, "ANTIALIAS"):
    Image.ANTIALIAS = Image.Resampling.LANCZOS


def log(message: str) -> None:
    print(message)


def resolve_background(path_str: str) -> Path:
    path = Path(path_str)
    if path.exists():
        return path
    fallback = DEFAULT_BG
    log(f"Background '{path}' not found; falling back to {fallback}")
    return fallback


def make_background_clip(bg_path: Path, duration: float):
    path_lower = bg_path.suffix.lower()
    if path_lower in VIDEO_EXTENSIONS:
        clip = VideoFileClip(str(bg_path)).without_audio()
        clip = clip.fx(vfx.loop, duration=duration)
        clip = clip.resize(height=H)
        if clip.w != W:
            clip = clip.fx(vfx.crop, width=W, x_center=clip.w / 2)
        return clip.set_duration(duration)

    image = Image.open(bg_path).convert("RGB").resize((W, H))
    clip = ImageClip(np.array(image)).set_duration(duration)
    clip = clip.fx(vfx.resize, lambda t: 1 + (0.08 / max(duration, 1.0)) * t)
    return clip.set_position(("center", "center"))


def add_watermark(duration: float, brand_text: str) -> ImageClip:
    watermark = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(watermark)
    try:
        font = ImageFont.truetype("assets/fonts/Inter-Medium.ttf", 36)
    except OSError:
        font = ImageFont.load_default()
    draw.text((W - 20, H - 20), brand_text, anchor="rd", fill=(232, 230, 227, 200), font=font)
    return ImageClip(np.array(watermark)).set_duration(duration)


def build_caption_clips(lines, duration: float):
    clips = []
    step = max(3.0, duration / max(len(lines), 1))
    cursor = 0.35
    for line in lines:
        frame = render_text_frame(line)
        clips.append(ImageClip(np.array(frame)).set_duration(step).set_start(cursor).set_position((0, 0)))
        cursor += step
    return clips


def write_temp_video(composite: CompositeVideoClip, tmp_path: Path) -> None:
    tmp_path.parent.mkdir(parents=True, exist_ok=True)
    TEMP_AUDIO.parent.mkdir(parents=True, exist_ok=True)
    composite.write_videofile(
        str(tmp_path),
        fps=QUALITY["FPS"],
        codec="libx264",
        audio_codec="aac",
        audio_fps=48000,
        preset=QUALITY["PRESET"],
        ffmpeg_params=["-pix_fmt", QUALITY["PIX"], "-crf", QUALITY["CRF"]],
        temp_audiofile=str(TEMP_AUDIO),
        remove_temp=True,
        threads=0,
    )


def resolve_ffmpeg() -> str:
    binary = shutil.which("ffmpeg")
    if binary:
        return binary
    search_root = Path("tools/ffmpeg")
    if search_root.exists():
        for candidate in search_root.rglob("ffmpeg.exe"):
            return str(candidate)
    raise FileNotFoundError("ffmpeg executable not found. Run 'scripts/ffmpeg_path.ps1' first or install ffmpeg.")


def build_ffmpeg_cmd(ffmpeg_bin: str, src: Path, dst: Path, audio_filter: str, music_path: str | None) -> list[str]:
    base_cmd = [
        ffmpeg_bin,
        "-y",
        "-i",
        str(src),
    ]

    video_args = [
        "-c:v",
        "libx264",
        "-preset",
        QUALITY["PRESET"],
        "-crf",
        QUALITY["CRF"],
        "-pix_fmt",
        QUALITY["PIX"],
        "-r",
        str(QUALITY["FPS"]),
    ]

    if music_path and Path(music_path).exists():
        return [
            ffmpeg_bin,
            "-y",
            "-i",
            str(src),
            "-stream_loop",
            "-1",
            "-i",
            music_path,
            "-filter_complex",
            "[1:a]volume=0.12,apad[a2];[0:a][a2]amix=inputs=2:normalize=0[a]",
            "-map",
            "0:v",
            "-map",
            "[a]",
            "-af",
            audio_filter,
            "-ar",
            "48000",
            *video_args,
            str(dst),
        ]

    return base_cmd + [
        "-af",
        audio_filter,
        "-ar",
        "48000",
        *video_args,
        str(dst),
    ]


def run_ffmpeg_postprocess(ffmpeg_bin: str, src: Path, dst: Path, music_path: str | None) -> None:
    commands = [
        (AUDIO_FILTER_WITH_DEESSER, True),
        (AUDIO_FILTER_NO_DEESSER, False),
    ]

    last_error: subprocess.CalledProcessError | None = None

    for audio_filter, is_primary in commands:
        cmd = build_ffmpeg_cmd(ffmpeg_bin, src, dst, audio_filter, music_path)
        log_suffix = " (with deesser)" if is_primary else " (without deesser)"
        log("Running ffmpeg" + log_suffix)
        try:
            result = subprocess.run(cmd, check=True, capture_output=True, text=True)
            if result.stdout:
                log(result.stdout.strip())
            if result.stderr:
                log(result.stderr.strip())
            return
        except subprocess.CalledProcessError as exc:
            stderr = exc.stderr or ""
            last_error = exc
            if is_primary and "deesser" in stderr.lower():
                log("FFmpeg reported an issue with deesser; retrying without it")
                continue
            raise

    if last_error is not None:
        raise last_error


def build_video(script_json: str, voice_wav: str, bg_path: str, music_path: str, out_mp4: str, brand_text: str = "Dark & Strange") -> None:
    script_data = json.load(open(script_json, encoding="utf-8"))
    lines = [line for line in script_data.get("lines", []) if line.strip()]
    cta = script_data.get("cta", "").strip()
    if cta:
        lines.append(cta)

    voice_clip = AudioFileClip(voice_wav)
    duration = max(10.0, voice_clip.duration)

    background_path = resolve_background(bg_path)
    background_clip = make_background_clip(background_path, duration)

    clips = [background_clip, add_watermark(duration, brand_text)]
    clips.extend(build_caption_clips(lines, duration))

    composite = CompositeVideoClip(clips, size=(W, H)).set_audio(voice_clip)
    composite.fps = QUALITY["FPS"]

    tmp_path = Path(out_mp4).with_suffix(".temp.mp4")

    write_temp_video(composite, tmp_path)

    composite.close()
    voice_clip.close()

    ffmpeg_bin = resolve_ffmpeg()
    run_ffmpeg_postprocess(ffmpeg_bin, tmp_path, Path(out_mp4), music_path if music_path else None)

    tmp_path.unlink(missing_ok=True)
    log(f"Render complete -> {out_mp4}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--script", required=True)
    parser.add_argument("--voice", required=True)
    parser.add_argument("--bg", required=True)
    parser.add_argument("--music", default="")
    parser.add_argument("--out", required=True)
    return parser.parse_args()


if __name__ == "__main__":
    arguments = parse_args()
    build_video(arguments.script, arguments.voice, arguments.bg, arguments.music, arguments.out)



