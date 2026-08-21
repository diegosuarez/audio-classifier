from __future__ import annotations

from pathlib import Path
from mutagen.easyid3 import EasyID3
from mutagen.id3 import ID3NoHeaderError

KEY_MAP = {
    "title": "title",
    "artist": "artist",
    "album": "album",
    "release_date": "date",
    "track_number": "tracknumber",
    "genre": "genre",
}

TAG_SOURCE_KEYS = tuple(KEY_MAP)


def desired_tag_updates(existing: dict, metadata: dict, overwrite: bool = False) -> dict[str, str]:
    updates = {}
    for src_key in TAG_SOURCE_KEYS:
        value = metadata.get(src_key)
        if not value:
            continue
        tag_key = KEY_MAP[src_key]
        has_existing = bool(existing.get(tag_key) or existing.get(src_key))
        if overwrite or not has_existing:
            updates[src_key] = str(value)
    return updates


def read_easy_tags(path: str | Path) -> dict[str, str]:
    try:
        tags = EasyID3(str(path))
    except ID3NoHeaderError:
        return {}
    return {k: v[0] for k, v in tags.items() if v}


def write_mp3_tags(path: str | Path, metadata: dict, overwrite: bool = False) -> dict[str, str]:
    path = Path(path)
    if path.suffix.lower() != ".mp3":
        return {}
    try:
        tags = EasyID3(str(path))
    except ID3NoHeaderError:
        tags = EasyID3()
    existing = {k: v[0] for k, v in tags.items() if v}
    updates = desired_tag_updates(existing, metadata, overwrite)
    for src_key, value in updates.items():
        tags[KEY_MAP[src_key]] = value
    if updates:
        tags.save(str(path))
    return updates
