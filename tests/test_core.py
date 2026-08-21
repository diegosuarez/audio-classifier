from pathlib import Path

from audio_classifier.renamer import make_safe_filename, dedupe_path
from audio_classifier.fingerprint import parse_fpcalc_output
from audio_classifier.resolver import choose_best_result, normalize_acoustid_result
from audio_classifier.tags import desired_tag_updates


def test_parse_fpcalc_output_extracts_duration_and_fingerprint():
    out = "FILE=x.mp3\nDURATION=123\nFINGERPRINT=abc123\n"
    result = parse_fpcalc_output(out)
    assert result.duration == 123
    assert result.fingerprint == "abc123"


def test_make_safe_filename_preserves_accents_and_removes_path_breakers():
    name = make_safe_filename("Niña / Demo: Live", "AC/DC", "mp3")
    assert name == "Niña - Demo Live - AC DC.mp3"


def test_dedupe_path_adds_numeric_suffix(tmp_path):
    target = tmp_path / "Song - Artist.mp3"
    target.write_bytes(b"x")
    assert dedupe_path(target).name == "Song - Artist (2).mp3"


def test_choose_best_result_requires_threshold_and_metadata():
    payload = {
        "results": [
            {"score": 0.7, "recordings": [{"title": "Low", "artists": [{"name": "Artist"}]}]},
            {"score": 0.91, "id": "aid", "recordings": [{"id": "rid", "title": "Title", "artists": [{"name": "Artist"}]}]},
        ]
    }
    best = choose_best_result(payload, min_score=0.85)
    assert best is not None
    assert best.title == "Title"
    assert best.artist == "Artist"
    assert best.score == 0.91


def test_normalize_artist_credit_phrase():
    result = {"score": 0.9, "id": "aid", "recordings": [{"id": "rid", "title": "T", "artists": [{"name": "A"}, {"name": "B"}]}]}
    meta = normalize_acoustid_result(result)
    assert meta.artist == "A, B"


def test_desired_tag_updates_fills_missing_only():
    updates = desired_tag_updates({"artist": "Existing"}, {"title": "Title", "artist": "New", "album": "Album"}, overwrite=False)
    assert updates == {"title": "Title", "album": "Album"}


def test_acoustid_meta_survives_url_encoding():
    """A literal "+" would be escaped to %2B and silently disable metadata."""
    import urllib.parse

    from audio_classifier.resolver import lookup_acoustid

    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return b'{"results": []}'

    def fake_urlopen(req, timeout=30):
        captured["url"] = req.full_url
        return FakeResponse()

    import audio_classifier.resolver as resolver

    original = resolver.urllib.request.urlopen
    resolver.urllib.request.urlopen = fake_urlopen
    try:
        lookup_acoustid("key", 200, "fp")
    finally:
        resolver.urllib.request.urlopen = original

    query = urllib.parse.parse_qs(urllib.parse.urlparse(captured["url"]).query)
    assert "%2B" not in captured["url"]
    assert query["meta"] == ["recordings"]


SEVEN_NATION_ARMY = {
    "score": 0.993,
    "id": "aid",
    "recordings": [
        {"id": "r0", "duration": 229.0, "title": "Seven Nation Army",
         "artists": [{"name": "Tradelove"}]},
        {"id": "r1", "duration": 231.813, "title": "Seven Nation Army",
         "artists": [{"name": "The White Stripes"}]},
        {"id": "r2", "duration": 232.0, "title": "The White Stripes 'Seven Nation Army'",
         "artists": [{"name": "Walt Ribeiro"}]},
        {"id": "r3", "duration": 238.0, "title": "Seven Nation Army",
         "artists": [{"name": "The White Stripes"}]},
    ],
}


def test_recording_is_chosen_by_closest_duration():
    """The first recording is a remix; the 238s one is the actual file."""
    from audio_classifier.resolver import pick_recording

    assert pick_recording(SEVEN_NATION_ARMY, duration=238)["id"] == "r3"


def test_recording_selection_without_a_duration_still_uses_consensus():
    """Two entries say The White Stripes; the arbitrary first one does not."""
    from audio_classifier.resolver import pick_recording

    assert pick_recording(SEVEN_NATION_ARMY)["id"] == "r1"


def test_recordings_without_metadata_are_skipped():
    from audio_classifier.resolver import pick_recording

    result = {"recordings": [{"id": "empty"}, {"id": "ok", "title": "T", "artists": [{"name": "A"}]}]}
    assert pick_recording(result, duration=100)["id"] == "ok"


def test_choose_best_result_uses_the_duration_hint():
    best = choose_best_result({"results": [SEVEN_NATION_ARMY]}, min_score=0.85, duration=238)
    assert best.artist == "The White Stripes"


TAKE_ON_ME = {
    "score": 0.958,
    "id": "aid",
    "recordings": [
        {"id": "r0", "duration": 227.0, "title": "Take On Me", "artists": [{"name": "a-ha"}]},
        {"id": "r1", "title": "Take on Me", "artists": [{"name": "a-ha"}]},
        {"id": "r2", "duration": 288.84, "title": "Take On Me", "artists": [{"name": "a-ha"}]},
        {"id": "r3", "duration": 243.96, "title": "A&E", "artists": [{"name": "The Ting Tings"}]},
        {"id": "r4", "title": "Take On Me", "artists": [{"name": "a-ha"}]},
        {"id": "r5", "duration": 227.0, "title": "Take On Me", "artists": [{"name": "a-ha"}]},
    ],
}


def test_a_mislabelled_outlier_does_not_win_on_duration_alone():
    """The Ting Tings entry is 1s from the file; five other entries say a-ha."""
    from audio_classifier.resolver import pick_recording

    assert pick_recording(TAKE_ON_ME, duration=243)["artists"][0]["name"] == "a-ha"


def test_duration_still_decides_within_the_consensus_artist():
    from audio_classifier.resolver import pick_recording

    assert pick_recording(TAKE_ON_ME, duration=290)["id"] == "r2"
