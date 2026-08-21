from audio_classifier.lastfm import (
    MIN_TAG_COUNT,
    lookup_genre,
    parse_tags,
    pick_genre,
)

TRACK_TAGS = {
    "toptags": {
        "tag": [
            {"name": "Radiohead", "count": 100},
            {"name": "seen live", "count": 90},
            {"name": "90s", "count": 80},
            {"name": "alternative rock", "count": 70},
            {"name": "rock", "count": 60},
        ]
    }
}


def test_parse_tags_handles_a_single_tag_returned_as_an_object():
    assert parse_tags({"toptags": {"tag": {"name": "rock", "count": 50}}}) == [{"name": "rock", "count": 50}]


def test_parse_tags_treats_a_lastfm_error_payload_as_no_tags():
    assert parse_tags({"error": 6, "message": "Track not found"}) == []


def test_parse_tags_handles_a_missing_tag_list():
    assert parse_tags({"toptags": {"@attr": {"artist": "X"}}}) == []


def test_pick_genre_skips_the_artist_name_decades_and_shelf_labels():
    genre = pick_genre(parse_tags(TRACK_TAGS), exclude=("Radiohead", "Paranoid Android", "OK Computer"))
    assert genre == "alternative rock"


def test_pick_genre_ignores_unpopular_tags():
    tags = [{"name": "trip hop", "count": MIN_TAG_COUNT - 1}]
    assert pick_genre(tags) == ""


def test_pick_genre_returns_empty_when_everything_is_filtered_out():
    tags = [{"name": "seen live", "count": 100}, {"name": "00s", "count": 90}]
    assert pick_genre(tags) == ""


def test_lookup_genre_falls_back_to_artist_tags(monkeypatch):
    from audio_classifier import lastfm

    calls = []

    def fake_call(method, api_key, params, timeout=30):
        calls.append(method)
        if method == "track.gettoptags":
            return {"error": 6, "message": "Track not found"}
        return {"toptags": {"tag": [{"name": "shoegaze", "count": 95}]}}

    monkeypatch.setattr(lastfm, "_call", fake_call)
    assert lookup_genre("key", "Slowdive", "Unknown Track") == "shoegaze"
    assert calls == ["track.gettoptags", "artist.gettoptags"]


def test_lookup_genre_does_not_query_the_artist_when_the_track_has_tags(monkeypatch):
    from audio_classifier import lastfm

    calls = []

    def fake_call(method, api_key, params, timeout=30):
        calls.append(method)
        return TRACK_TAGS

    monkeypatch.setattr(lastfm, "_call", fake_call)
    assert lookup_genre("key", "Radiohead", "Paranoid Android") == "alternative rock"
    assert calls == ["track.gettoptags"]


def test_lookup_genre_without_a_key_makes_no_request(monkeypatch):
    from audio_classifier import lastfm

    def boom(*args, **kwargs):
        raise AssertionError("Last.fm should not have been queried")

    monkeypatch.setattr(lastfm, "_call", boom)
    assert lookup_genre("", "Radiohead", "Paranoid Android") == ""


def test_cli_only_queries_lastfm_when_the_genre_is_missing(monkeypatch):
    from audio_classifier import cli
    from audio_classifier.resolver import TrackMetadata

    monkeypatch.setattr(cli.lastfm, "lookup_genre", lambda *a, **k: "shoegaze")
    meta = TrackMetadata(title="T", artist="A")
    assert cli.add_lastfm_genre(meta, "key").genre == "shoegaze"


def test_cli_keeps_metadata_when_lastfm_fails(monkeypatch, capsys):
    from audio_classifier import cli
    from audio_classifier.resolver import TrackMetadata

    def boom(*args, **kwargs):
        raise OSError("connection refused")

    monkeypatch.setattr(cli.lastfm, "lookup_genre", boom)
    meta = TrackMetadata(title="T", artist="A")
    assert cli.add_lastfm_genre(meta, "key") is meta
    assert "Last.fm lookup failed" in capsys.readouterr().err
