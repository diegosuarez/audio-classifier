from pathlib import Path

import pytest

from audio_classifier.renamer import (
    MAX_FILENAME_BYTES,
    dedupe_path,
    render_pattern,
    validate_pattern,
)


def test_custom_pattern_strips_reserved_characters_from_values():
    name = render_pattern(
        "{album} - {title}.{ext}",
        title="Song: Part 1",
        artist="Artist",
        album="Best of? *Ever*",
        ext="mp3",
    )
    assert name == "Best of Ever - Song Part 1.mp3"


def test_custom_pattern_cannot_emit_a_path_separator():
    name = render_pattern("{artist}/{title}.{ext}", title="Title", artist="Artist", ext="mp3")
    assert "/" not in name
    assert name == "Artist Title.mp3"


def test_literal_separators_in_pattern_are_sanitized_too():
    name = render_pattern("{artist}: {title}.{ext}", title="Title", artist="Artist", ext="mp3")
    assert name == "Artist Title.mp3"


def test_empty_optional_fields_do_not_leave_dangling_separators():
    name = render_pattern("{album} - {title}.{ext}", title="Title", artist="A", album="", ext="mp3")
    assert name == "Title.mp3"


def test_pattern_supports_year_and_track():
    name = render_pattern(
        "{track} - {title} ({year}).{ext}", title="Title", artist="A", year="1994", track="03", ext="mp3"
    )
    assert name == "03 - Title (1994).mp3"


def test_unknown_placeholder_is_rejected():
    with pytest.raises(ValueError, match="composer"):
        validate_pattern("{composer} - {title}.{ext}")


def test_positional_placeholder_is_rejected():
    with pytest.raises(ValueError, match="positional"):
        validate_pattern("{} - {title}.{ext}")


def test_pattern_without_ext_is_rejected():
    with pytest.raises(ValueError, match="{ext}"):
        validate_pattern("{artist} - {title}")


def test_long_names_are_truncated_to_the_filesystem_limit():
    name = render_pattern("{title}.{ext}", title="á" * 400, artist="A", ext="mp3")
    assert len(name.encode("utf-8")) <= MAX_FILENAME_BYTES
    assert name.endswith(".mp3")


def test_dedupe_ignores_the_file_being_renamed(tmp_path):
    already_correct = tmp_path / "Song - Artist.mp3"
    already_correct.write_bytes(b"x")
    assert dedupe_path(already_correct, ignore=already_correct) == already_correct


def test_dedupe_respects_names_claimed_earlier_in_the_batch(tmp_path):
    target = tmp_path / "Song - Artist.mp3"
    assert dedupe_path(target, taken={target}).name == "Song - Artist (2).mp3"


def test_dedupe_skips_both_disk_and_claimed_names(tmp_path):
    target = tmp_path / "Song - Artist.mp3"
    target.write_bytes(b"x")
    claimed = {tmp_path / "Song - Artist (2).mp3"}
    assert dedupe_path(target, taken=claimed).name == "Song - Artist (3).mp3"
