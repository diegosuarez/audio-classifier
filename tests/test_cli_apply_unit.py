from pathlib import Path
from types import SimpleNamespace

from audio_idtag.cli import target_for


def test_target_for_default_pattern_uses_uniform_title_artist_ext(tmp_path):
    src = tmp_path / "weird name.mp3"
    meta = SimpleNamespace(title="Título", artist="Autor", album="")
    target = target_for(src, meta, "{title} - {artist}.{ext}")
    assert target.name == "Título - Autor.mp3"
