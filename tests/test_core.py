from pathlib import Path

from audio_idtag.renamer import make_safe_filename, dedupe_path
from audio_idtag.fingerprint import parse_fpcalc_output
from audio_idtag.resolver import choose_best_result, normalize_acoustid_result
from audio_idtag.tags import desired_tag_updates


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
