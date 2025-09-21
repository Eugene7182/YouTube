"""Utilities for generating narration audio using Google Text-to-Speech."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from pathlib import Path

from typing import TYPE_CHECKING

try:  # pragma: no cover - import guard for environments without gTTS
    from gtts import gTTS  # type: ignore
except ImportError:  # pragma: no cover - handled gracefully in synth_sync
    gTTS = None  # type: ignore

if TYPE_CHECKING:  # pragma: no cover
    from gtts import gTTS as gTTSProtocol


class TextToSpeechError(RuntimeError):
    """Raised when narration synthesis fails or times out."""


def synth_sync(
    text: str,
    out_path: str | Path,
    *,
    lang: str = "ru",
    timeout: float = 30.0,
    slow: bool = False,
) -> Path:
    """Generate narration audio synchronously using gTTS.

    Args:
        text: Source text to vocalise.
        out_path: Target path for the generated audio file.
        lang: Language code for the voice. Defaults to Russian (``ru``).
        timeout: Maximum amount of seconds to wait for the TTS API.
        slow: Whether to request the slower speech variant from gTTS.

    Returns:
        The :class:`~pathlib.Path` pointing to the rendered audio file.

    Raises:
        TextToSpeechError: If synthesis fails or the timeout is exceeded.
    """

    if gTTS is None:  # pragma: no cover - runtime guard for optional dependency
        raise TextToSpeechError("gTTS package is not installed")

    destination = Path(out_path)
    destination.parent.mkdir(parents=True, exist_ok=True)

    def _render() -> Path:
        tts = gTTS(text=text, lang=lang, slow=slow)
        tts.save(destination.as_posix())
        return destination

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(_render)
        try:
            return future.result(timeout=timeout)
        except FuturesTimeoutError as exc:
            if destination.exists():
                destination.unlink(missing_ok=True)
            raise TextToSpeechError("TTS synthesis timed out") from exc
        except Exception as exc:  # pragma: no cover - defensive programming
            if destination.exists():
                destination.unlink(missing_ok=True)
            raise TextToSpeechError("TTS synthesis failed") from exc
