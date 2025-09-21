import pytest

from core.metadata import VideoInspection, normalize_metadata, validate_video


def test_normalize_metadata_limits_tags_and_appends_hashtags():
    payload = normalize_metadata(
        "  Заголовок, который длиннее нормы * 2  ",
        "Описание",
        ["#Fun", "Trend", "Extra Tag", "ignored"],
    )
    assert len(payload.title) <= 100
    assert payload.tags == ["fun", "trend", "extratag"]
    assert all(hashtag.startswith("#") for hashtag in payload.hashtags)
    assert payload.hashtags[0] in payload.description


def test_normalize_metadata_requires_tag():
    with pytest.raises(ValueError):
        normalize_metadata("Title", "Description", [])


def test_validate_video_constraints():
    validate_video(VideoInspection(duration=59.0, width=1080, height=1920))
    with pytest.raises(ValueError):
        validate_video(VideoInspection(duration=61.0, width=1080, height=1920))
    with pytest.raises(ValueError):
        validate_video(VideoInspection(duration=10.0, width=1920, height=1080))
