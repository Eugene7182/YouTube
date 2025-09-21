from __future__ import annotations

import pytest

from utils import moviepy_compat as compat


class HybridClip:
    """Test double exposing both modern and legacy methods."""

    def __init__(self) -> None:
        self.invocations: list[tuple[str, float]] = []

    def with_duration(self, duration: float) -> "HybridClip":
        self.invocations.append(("with", duration))
        return self

    def set_duration(self, duration: float) -> "HybridClip":
        self.invocations.append(("set", duration))
        return self


class LegacyClip:
    """Test double that only provides the legacy MoviePy API surface."""

    def __init__(self) -> None:
        self.called: list[float] = []

    def set_duration(self, duration: float) -> "LegacyClip":
        self.called.append(duration)
        return self

    def set_audio(self, audio: object) -> "LegacyClip":
        self.called.append(-1.0)
        return self


def test_clip_with_duration_prefers_modern_method() -> None:
    clip = HybridClip()

    result = compat.clip_with_duration(clip, 2.5)

    assert result is clip
    assert clip.invocations == [("with", 2.5)]


def test_clip_with_duration_falls_back_to_legacy() -> None:
    clip = LegacyClip()

    result = compat.clip_with_duration(clip, 1.0)

    assert result is clip
    assert clip.called == [1.0]


def test_clip_with_audio_falls_back_to_legacy() -> None:
    clip = LegacyClip()

    result = compat.clip_with_audio(clip, object())

    assert result is clip
    assert clip.called[-1] == -1.0


def test_clip_with_audio_fadein_uses_fx(monkeypatch: pytest.MonkeyPatch) -> None:
    class FxClip:
        def __init__(self) -> None:
            self.args: tuple[object, float] | None = None

        def fx(self, func: object, duration: float) -> "FxClip":
            self.args = (func, duration)
            return self

    clip = FxClip()

    result = compat.clip_with_audio_fadein(clip, 0.75)

    assert result is clip
    assert clip.args is not None
    assert clip.args[1] == 0.75


def test_clip_with_audio_fadein_legacy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    class LegacyFadeClip:
        def __init__(self) -> None:
            self.called: list[float] = []

        def audio_fadein(self, duration: float) -> "LegacyFadeClip":
            self.called.append(duration)
            return self

    clip = LegacyFadeClip()
    monkeypatch.setattr(compat, "audio_fx", None)

    result = compat.clip_with_audio_fadein(clip, 1.5)

    assert result is clip
    assert clip.called == [1.5]


def test_clip_with_audio_fadeout_legacy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    class LegacyFadeClip:
        def __init__(self) -> None:
            self.called: list[float] = []

        def audio_fadeout(self, duration: float) -> "LegacyFadeClip":
            self.called.append(duration)
            return self

    clip = LegacyFadeClip()
    monkeypatch.setattr(compat, "audio_fx", None)

    result = compat.clip_with_audio_fadeout(clip, 2.0)

    assert result is clip
    assert clip.called == [2.0]
