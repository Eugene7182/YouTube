"""Adapters for coercing arbitrary image/frame objects into numpy arrays."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterable, Sequence

import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)


def as_np_frame(source: object) -> np.ndarray:
    """Return an RGB numpy frame for MoviePy from multiple input types."""

    if isinstance(source, np.ndarray):
        return source
    if isinstance(source, Image.Image):
        return np.array(source.convert("RGB"))
    if isinstance(source, (str, Path)):
        path = Path(source)
        try:
            pil_image = Image.open(path)
        except Exception as exc:  # pragma: no cover - delegated to PIL
            logger.error("Failed to open image", extra={"path": path.as_posix(), "error": str(exc)})
            raise
        try:
            return np.array(pil_image.convert("RGB"))
        finally:
            pil_image.close()
    raise TypeError(f"Unsupported frame type: {type(source)!r}")


def as_np_frames(frames: Iterable[object]) -> list[np.ndarray]:
    """Convert an iterable of frame-like objects into numpy arrays."""

    return [as_np_frame(frame) for frame in frames]


__all__: Sequence[str] = ["as_np_frame", "as_np_frames"]
