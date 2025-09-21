"""Совместимость между API MoviePy 1.x и 2.x.

Функции ниже сначала пытаются использовать современный интерфейс ``with_*`` из
MoviePy 2.x, а при его отсутствии откатываются к легаси-методам ``set_*`` из
MoviePy 1.x. Это позволяет писать код под новую версию и при этом не ломать
локальные окружения, где ещё не произошёл апгрейд.

Каждый хелпер повторяет сигнатуру соответствующего метода ``with_*`` и
возвращает исходный клип после применения преобразования.
"""

from __future__ import annotations

from typing import Any, TypeVar

try:  # pragma: no cover - optional for MoviePy<2.0
    from moviepy import vfx
except ImportError:  # pragma: no cover - fallback for MoviePy 1.x
    from moviepy.video.fx import all as vfx  # type: ignore

try:  # pragma: no cover - available on both branches, but defensive
    from moviepy.audio.fx import all as audio_fx
except ImportError:  # pragma: no cover - very old MoviePy versions
    audio_fx = None  # type: ignore[assignment]


ClipT = TypeVar("ClipT")


def _call_preferred(
    clip: ClipT,
    modern: str,
    legacy: str,
    *args: Any,
    **kwargs: Any,
) -> ClipT:
    """Вызвать метод ``modern`` или откатиться к ``legacy``."""

    preferred = getattr(clip, modern, None)
    if callable(preferred):
        return preferred(*args, **kwargs)

    fallback = getattr(clip, legacy, None)
    if callable(fallback):
        return fallback(*args, **kwargs)

    raise AttributeError(
        f"{clip!r} does not implement '{modern}' or '{legacy}' methods",
    )


def clip_with_duration(clip: ClipT, duration: float) -> ClipT:
    """Выставить длительность клипа с учётом версии MoviePy."""

    return _call_preferred(clip, "with_duration", "set_duration", duration)


def clip_with_position(clip: ClipT, position: Any) -> ClipT:
    """Разместить клип на заданной позиции композиции."""

    return _call_preferred(clip, "with_position", "set_position", position)


def clip_with_fps(clip: ClipT, fps: float) -> ClipT:
    """Изменить FPS клипа вне зависимости от API."""

    return _call_preferred(clip, "with_fps", "set_fps", fps)


def clip_with_start(clip: ClipT, start: float) -> ClipT:
    """Сдвинуть старт клипа на ``start`` секунд."""

    return _call_preferred(clip, "with_start", "set_start", start)


def clip_with_end(clip: ClipT, end: float) -> ClipT:
    """Ограничить завершение клипа абсолютной отметкой."""

    return _call_preferred(clip, "with_end", "set_end", end)


def clip_with_opacity(clip: ClipT, opacity: float) -> ClipT:
    """Применить прозрачность к клипу независимо от версии."""

    return _call_preferred(clip, "with_opacity", "set_opacity", opacity)


def clip_with_audio(clip: ClipT, audio_clip: Any) -> ClipT:
    """Прикрепить аудиодорожку, не завися от версии MoviePy."""

    return _call_preferred(clip, "with_audio", "set_audio", audio_clip)


def clip_with_audio_fadein(clip: ClipT, duration: float) -> ClipT:
    """Применить fade-in к аудио с учётом доступного API."""

    if hasattr(clip, "fx") and audio_fx is not None:
        return clip.fx(audio_fx.audio_fadein, duration)  # type: ignore[attr-defined]

    legacy = getattr(clip, "audio_fadein", None)
    if callable(legacy):  # pragma: no cover - MoviePy<2 provides bound method
        return legacy(duration)

    raise AttributeError("Audio fade-in is not supported by this clip")


def clip_with_audio_fadeout(clip: ClipT, duration: float) -> ClipT:
    """Применить fade-out к аудио независимо от версии MoviePy."""

    if hasattr(clip, "fx") and audio_fx is not None:
        return clip.fx(audio_fx.audio_fadeout, duration)  # type: ignore[attr-defined]

    legacy = getattr(clip, "audio_fadeout", None)
    if callable(legacy):  # pragma: no cover - MoviePy<2 provides bound method
        return legacy(duration)

    raise AttributeError("Audio fade-out is not supported by this clip")


__all__ = [
    "clip_with_duration",
    "clip_with_position",
    "clip_with_fps",
    "clip_with_start",
    "clip_with_end",
    "clip_with_opacity",
    "clip_with_audio",
    "clip_with_audio_fadein",
    "clip_with_audio_fadeout",
]

