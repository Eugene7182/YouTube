# ruff: noqa

import textwrap

try:
    from moviepy import AudioFileClip, ImageClip, CompositeVideoClip, TextClip, concatenate_videoclips, vfx
except ImportError:  # pragma: no cover - fallback for MoviePy<2.0
    from moviepy.editor import AudioFileClip, ImageClip, CompositeVideoClip, TextClip, concatenate_videoclips, vfx
from PIL import Image, ImageDraw, ImageFont

from utils.video_io import as_np_frame
from utils.moviepy_compat import (
    clip_with_audio,
    clip_with_duration,
)

FONT = None

def load_font(path: str, size: int) -> None:
    """Загрузить пользовательский шрифт для подписей."""
    global FONT
    try:
        FONT = ImageFont.truetype(path, size)
    except Exception:
        # Fallback to default PIL font
        FONT = ImageFont.load_default()

def caption_frame(
    text: str,
    size: tuple[int, int] = (1080, 1920),
    bg: tuple[int, int, int] = (20, 20, 25),
    fg: tuple[int, int, int] = (255, 255, 255),
    pad: int = 40,
):
    """Создать кадр ``ImageClip`` с перенесённым текстом."""
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
    return ImageClip(as_np_frame(img), duration=2.0)

def assemble_short(
    lines: list[str],
    audio_path: str,
    title: str,
    out_path: str,
    fps: int = 30,
    resolution: tuple[int, int] = (1080, 1920),
    max_duration: float = 12.0,
):
    """Собрать короткое видео из слайдов и озвучки."""

    prepared_lines = [str(line) for line in lines if str(line).strip()]
    if not prepared_lines:
        prepared_lines = ["Hook", "Setup", "Twist"]

    safe_max_duration = float(max_duration or 12.0)
    if safe_max_duration <= 0:
        safe_max_duration = 12.0

    with AudioFileClip(audio_path) as base_audio:
        if base_audio.duration > safe_max_duration:
            audio_clip = base_audio.subclip(0, safe_max_duration)
        else:
            audio_clip = base_audio

        target_duration = max(audio_clip.duration, 0.1)
        audio_clip = clip_with_duration(audio_clip, target_duration)
        segment_duration = target_duration / max(1, len(prepared_lines))

        clips = []
        elapsed = 0.0
        for index, line in enumerate(prepared_lines):
            remaining = len(prepared_lines) - index
            if remaining <= 1:
                duration = max(target_duration - elapsed, 0.1)
            else:
                duration = max(segment_duration, 0.1)
            clip = clip_with_duration(caption_frame(line, size=resolution), duration)
            clips.append(clip)
            elapsed += duration

        video = None
        rendered = None
        try:
            video = concatenate_videoclips(clips, method="compose")
            rendered = clip_with_audio(video, audio_clip)
            rendered.write_videofile(
                out_path,
                fps=fps,
                codec="libx264",
                audio_codec="aac",
                threads=1,
            )
        finally:
            if rendered is not None and rendered is not video:
                rendered.close()
            if video is not None:
                video.close()
            for clip in clips:
                clip.close()
            if audio_clip is not base_audio:
                audio_clip.close()

if __name__ == "__main__":
    load_font("DejaVuSans.ttf", 64)
    assemble_short(["Hook line","Setup","Twist","Punch"], "voice.mp3", "Demo", "video.mp4")
