from audio_classifier.musicbrainz import (
    is_incomplete,
    merge_recording_details,
    metadata_from_recording,
    user_agent,
)
from audio_classifier.resolver import TrackMetadata

RECORDING = {
    "id": "rec-1",
    "title": "Paranoid Android",
    "artist-credit": [{"name": "Radiohead"}],
    "genres": [{"name": "rock", "count": 2}, {"name": "alternative rock", "count": 9}],
    "releases": [
        {
            "title": "Greatest Hits",
            "status": "Bootleg",
            "date": "1990-01-01",
            "media": [{"tracks": [{"number": "1"}]}],
        },
        {
            "title": "OK Computer",
            "status": "Official",
            "date": "2009-03-23",
            "release-group": {"first-release-date": "1997-05-21"},
            "media": [{"tracks": [{"number": "2"}]}],
        },
        {
            "title": "OK Computer OKNOTOK",
            "status": "Official",
            "date": "2017-06-23",
            "media": [{"tracks": [{"number": "2"}]}],
        },
    ],
}


def test_user_agent_includes_contact_when_available():
    assert user_agent("me@example.com") == "audio-classifier/0.1.0 ( me@example.com )"
    assert user_agent("") == "audio-classifier/0.1.0"


def test_merge_prefers_the_earliest_official_release():
    meta = TrackMetadata(title="Paranoid Android", artist="Radiohead", score=0.95)
    merged = merge_recording_details(meta, RECORDING)
    assert merged.album == "OK Computer"
    assert merged.release_date == "1997-05-21"
    assert merged.track_number == "2"
    assert merged.genre == "alternative rock"


def test_merge_never_overwrites_what_acoustid_already_said():
    meta = TrackMetadata(title="Paranoid Android", artist="Radiohead", album="Kid A", genre="pop")
    merged = merge_recording_details(meta, RECORDING)
    assert merged.album == "Kid A"
    assert merged.genre == "pop"
    assert merged.release_date == "1997-05-21"


def test_merge_without_releases_keeps_metadata_untouched():
    meta = TrackMetadata(title="T", artist="A")
    assert merge_recording_details(meta, {"id": "x", "title": "T"}) is meta


def test_metadata_from_recording_builds_a_full_record():
    meta = metadata_from_recording(RECORDING, score=0.91, acoustid_id="aid")
    assert meta is not None
    assert (meta.title, meta.artist, meta.album) == ("Paranoid Android", "Radiohead", "OK Computer")
    assert meta.score == 0.91
    assert meta.acoustid_id == "aid"
    assert meta.recording_id == "rec-1"


def test_metadata_from_recording_requires_title_and_artist():
    assert metadata_from_recording({"id": "x", "title": "Only a title"}) is None


def test_is_incomplete_detects_missing_fields():
    full = TrackMetadata(title="T", artist="A", album="Al", release_date="1997", track_number="2", genre="rock")
    assert is_incomplete(full) is False
    assert is_incomplete(TrackMetadata(title="T", artist="A")) is True


def _no_network(*args, **kwargs):
    raise AssertionError("MusicBrainz should not have been queried")


def test_cli_skips_musicbrainz_when_metadata_is_already_complete(monkeypatch):
    from audio_classifier import cli

    monkeypatch.setattr(cli.musicbrainz, "fetch_recording", _no_network)
    meta = TrackMetadata(
        title="T", artist="A", album="Al", release_date="1997", track_number="2", genre="rock",
        recording_id="rec-1",
    )
    assert cli.enrich_with_musicbrainz({}, meta, 0.85, "") is meta


def test_cli_enriches_incomplete_metadata(monkeypatch):
    from audio_classifier import cli

    monkeypatch.setattr(cli.musicbrainz, "fetch_recording", lambda *a, **k: RECORDING)
    meta = TrackMetadata(title="Paranoid Android", artist="Radiohead", recording_id="rec-1", score=0.95)
    enriched = cli.enrich_with_musicbrainz({}, meta, 0.85, "")
    assert enriched.album == "OK Computer"
    assert enriched.score == 0.95


def test_cli_rescues_fingerprint_only_matches_via_musicbrainz(monkeypatch):
    from audio_classifier import cli

    monkeypatch.setattr(cli.musicbrainz, "fetch_recording", lambda *a, **k: RECORDING)
    payload = {"results": [{"score": 0.93, "id": "aid", "recordings": [{"id": "rec-1"}]}]}
    built = cli.enrich_with_musicbrainz(payload, None, 0.85, "")
    assert built is not None
    assert (built.title, built.artist) == ("Paranoid Android", "Radiohead")
    assert built.score == 0.93


def test_cli_keeps_acoustid_metadata_when_musicbrainz_fails(monkeypatch, capsys):
    from audio_classifier import cli

    def boom(*args, **kwargs):
        raise OSError("connection refused")

    monkeypatch.setattr(cli.musicbrainz, "fetch_recording", boom)
    meta = TrackMetadata(title="T", artist="A", recording_id="rec-1")
    assert cli.enrich_with_musicbrainz({}, meta, 0.85, "") is meta
    assert "MusicBrainz lookup failed" in capsys.readouterr().err


def test_release_group_first_release_date_beats_a_reissue_date():
    """The recording is linked to a 2009 reissue; 1997 is the honest year."""
    merged = merge_recording_details(TrackMetadata(title="T", artist="A"), RECORDING)
    assert merged.release_date == "1997-05-21"


def test_genre_falls_back_to_the_release_group():
    payload = {
        "id": "rec-2",
        "title": "T",
        "artist-credit": [{"name": "A"}],
        "releases": [
            {
                "title": "Al",
                "status": "Official",
                "date": "2000",
                "release-group": {"genres": [{"name": "post-rock", "count": 4}]},
            }
        ],
    }
    assert metadata_from_recording(payload).genre == "post-rock"


COMPILATION_VS_ALBUM = {
    "id": "rec-3",
    "title": "The Passenger",
    "artist-credit": [{"name": "Iggy Pop"}],
    "releases": [
        {
            "title": "A Million In Prizes: The Anthology",
            "status": "Official",
            "release-group": {
                "first-release-date": "2005-06-17",
                "primary-type": "Album",
                "secondary-types": ["Compilation"],
            },
        },
        {
            "title": "Lust for Life",
            "status": "Official",
            "release-group": {"first-release-date": "1977-08-29", "primary-type": "Album"},
        },
        {
            "title": "The Passenger",
            "status": "Official",
            "release-group": {"first-release-date": "1977-04-01", "primary-type": "Single"},
        },
    ],
}


def test_compilations_lose_to_the_original_studio_album():
    """An anthology is official and would win on date alone."""
    merged = merge_recording_details(TrackMetadata(title="T", artist="A"), COMPILATION_VS_ALBUM)
    assert merged.album == "Lust for Life"
    assert merged.release_date == "1977-08-29"


def test_an_album_beats_an_earlier_single():
    merged = merge_recording_details(TrackMetadata(title="T", artist="A"), COMPILATION_VS_ALBUM)
    assert merged.album != "The Passenger"


def test_fetch_recording_retries_while_musicbrainz_is_busy(monkeypatch):
    import urllib.error

    from audio_classifier import musicbrainz as mb

    attempts = []

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return b'{"id": "rec-1", "title": "T"}'

    def flaky_urlopen(req, timeout=30):
        attempts.append(req.full_url)
        if len(attempts) < 3:
            raise urllib.error.HTTPError(req.full_url, 503, "Busy", {}, None)
        return FakeResponse()

    monkeypatch.setattr(mb.urllib.request, "urlopen", flaky_urlopen)
    monkeypatch.setattr(mb.time, "sleep", lambda _: None)
    monkeypatch.setattr(mb, "_throttle", lambda: None)
    assert mb.fetch_recording("rec-1")["id"] == "rec-1"
    assert len(attempts) == 3


def test_fetch_recording_does_not_retry_a_404(monkeypatch):
    import urllib.error

    from audio_classifier import musicbrainz as mb

    attempts = []

    def missing(req, timeout=30):
        attempts.append(1)
        raise urllib.error.HTTPError(req.full_url, 404, "Not Found", {}, None)

    monkeypatch.setattr(mb.urllib.request, "urlopen", missing)
    monkeypatch.setattr(mb, "_throttle", lambda: None)
    try:
        mb.fetch_recording("nope")
    except urllib.error.HTTPError as exc:
        assert exc.code == 404
    assert len(attempts) == 1
