from types import SimpleNamespace

from audio_classifier.cli import build_parser, process_folder, target_for
from audio_classifier.config import AppConfig
from audio_classifier.db import connect
from audio_classifier.fingerprint import FingerprintResult
from audio_classifier.resolver import TrackMetadata


def test_target_for_default_pattern_uses_uniform_title_artist_ext(tmp_path):
    src = tmp_path / "weird name.mp3"
    meta = SimpleNamespace(title="Título", artist="Autor", album="")
    target = target_for(src, meta, "{title} - {artist}.{ext}")
    assert target.name == "Título - Autor.mp3"


def test_target_for_dedupes_against_existing_file(tmp_path):
    (tmp_path / "Título - Autor.mp3").write_bytes(b"x")
    src = tmp_path / "weird name.mp3"
    meta = SimpleNamespace(title="Título", artist="Autor", album="")
    assert target_for(src, meta, "{title} - {artist}.{ext}").name == "Título - Autor (2).mp3"


def test_write_tags_flag_is_tri_state():
    parser = build_parser()
    assert parser.parse_args(["scan", "."]).write_tags is None
    assert parser.parse_args(["scan", ".", "--write-tags"]).write_tags is True
    assert parser.parse_args(["scan", ".", "--no-write-tags"]).write_tags is False


def _stub_pipeline(monkeypatch, tmp_path):
    from audio_classifier import cli

    monkeypatch.setattr(cli, "load_config", lambda _: AppConfig(acoustid_api_key="k"))
    monkeypatch.setattr(cli, "fpcalc_available", lambda: True)
    monkeypatch.setattr(cli, "run_fpcalc", lambda _: FingerprintResult(duration=180, fingerprint="fp"))
    monkeypatch.setattr(cli, "lookup_acoustid", lambda *a, **k: {})
    monkeypatch.setattr(
        cli,
        "choose_best_result",
        lambda payload, min_score: TrackMetadata(title="Title", artist="Artist", score=0.9),
    )


def test_apply_renames_file_and_records_operation(tmp_path, monkeypatch):
    _stub_pipeline(monkeypatch, tmp_path)
    music = tmp_path / "music"
    music.mkdir()
    (music / "track01.mp3").write_bytes(b"x")
    db = tmp_path / "state.db"

    args = build_parser().parse_args(
        ["apply", str(music), "--yes", "--sleep", "0", "--db", str(db), "--no-write-tags"]
    )
    assert process_folder(args, apply=True) == 0

    assert not (music / "track01.mp3").exists()
    assert (music / "Title - Artist.mp3").exists()

    row = connect(db).execute("SELECT old_path, new_path, status, wrote_tags FROM operations").fetchone()
    assert row["status"] == "applied"
    assert row["old_path"] == str(music / "track01.mp3")
    assert row["new_path"] == str(music / "Title - Artist.mp3")
    assert row["wrote_tags"] == 0


def test_scan_does_not_touch_files(tmp_path, monkeypatch):
    _stub_pipeline(monkeypatch, tmp_path)
    music = tmp_path / "music"
    music.mkdir()
    (music / "track01.mp3").write_bytes(b"x")

    args = build_parser().parse_args(["scan", str(music), "--sleep", "0", "--db", str(tmp_path / "state.db")])
    assert process_folder(args, apply=False) == 0
    assert (music / "track01.mp3").exists()


def test_scan_reports_distinct_targets_for_files_that_resolve_alike(tmp_path, monkeypatch, capsys):
    _stub_pipeline(monkeypatch, tmp_path)
    music = tmp_path / "music"
    music.mkdir()
    (music / "a.mp3").write_bytes(b"x")
    (music / "b.mp3").write_bytes(b"y")

    args = build_parser().parse_args(["scan", str(music), "--sleep", "0", "--db", str(tmp_path / "s.db")])
    assert process_folder(args, apply=False) == 0

    out = capsys.readouterr().out
    assert "Title - Artist.mp3" in out
    assert "Title - Artist (2).mp3" in out


def test_apply_is_idempotent_for_already_correct_names(tmp_path, monkeypatch):
    _stub_pipeline(monkeypatch, tmp_path)
    music = tmp_path / "music"
    music.mkdir()
    correct = music / "Title - Artist.mp3"
    correct.write_bytes(b"x")

    args = build_parser().parse_args(
        ["apply", str(music), "--yes", "--sleep", "0", "--db", str(tmp_path / "s.db"), "--no-write-tags"]
    )
    assert process_folder(args, apply=True) == 0
    assert correct.exists()
    assert not (music / "Title - Artist (2).mp3").exists()


def test_missing_fpcalc_fails_once_with_an_install_hint(tmp_path, monkeypatch, capsys):
    from audio_classifier import cli

    monkeypatch.setattr(cli, "load_config", lambda _: AppConfig(acoustid_api_key="k"))
    monkeypatch.setattr(cli, "fpcalc_available", lambda: False)
    music = tmp_path / "music"
    music.mkdir()
    (music / "a.mp3").write_bytes(b"x")

    args = build_parser().parse_args(["scan", str(music), "--db", str(tmp_path / "s.db")])
    assert process_folder(args, apply=False) == 2
    assert "fpcalc not found" in capsys.readouterr().err
