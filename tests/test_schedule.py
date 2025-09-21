from core.schedule import to_utc_iso


def test_to_utc_iso_et():
    iso = to_utc_iso("2024-01-10", "09:00 ET", "America/New_York")
    assert iso.startswith("2024-01-10T14:00:00+")


def test_to_utc_iso_asia_almaty():
    iso = to_utc_iso("2024-06-15", "19:00 Asia/Almaty", "Asia/Almaty")
    assert iso.startswith("2024-06-15T14:00:00+")


def test_to_utc_iso_default_timezone():
    iso = to_utc_iso("2024-03-01", "21:30", "Asia/Almaty")
    assert iso.startswith("2024-03-01T16:30:00+")
