from __future__ import annotations

import numpy as np
from moviepy.editor import ImageSequenceClip
from PIL import Image

from utils.video_io import as_np_frame, as_np_frames


def test_as_np_frame_pil_to_np() -> None:
    img = Image.new("RGB", (4, 2), color=(10, 20, 30))
    frame = as_np_frame(img)

    assert isinstance(frame, np.ndarray)
    assert frame.shape == (2, 4, 3)
    assert frame.dtype == np.uint8
    assert frame[0, 0, 0] == 10


def test_image_sequence_clip_accepts_pil_list() -> None:
    frames = [Image.new("RGB", (4, 4), color=(index, index, index)) for index in range(3)]
    clip = ImageSequenceClip(as_np_frames(frames), fps=2)

    # Ensure clip can render a few frames without invoking ffmpeg writes
    snapshot = clip.get_frame(0)
    assert snapshot.shape == (4, 4, 3)
