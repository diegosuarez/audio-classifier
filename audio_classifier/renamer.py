from __future__ import annotations

from collections.abc import Collection
from pathlib import Path
from string import Formatter
import re
import unicodedata

_DASHES = re.compile(r"\s*[-–—]+\s*")
_SPACES = re.compile(r"\s+")
_FORBIDDEN = re.compile(r"[\\/?:*\"<>|\x00-\x1f]")

DEFAULT_PATTERN = "{title} - {artist}.{ext}"
ALLOWED_PATTERN_FIELDS = ("title", "artist", "album", "year", "track", "ext")
UNKNOWN = "Unknown"
# ext4/xfs cap a single filename at 255 bytes, not characters.
MAX_FILENAME_BYTES = 255


def _clean_part(value: str, *, slash_as_dash: bool = False, fallback: str = UNKNOWN) -> str:
    value = unicodedata.normalize("NFC", str(value or "")).strip()
    if slash_as_dash:
        value = re.sub(r"\s*[\\/]\s*", " - ", value)
    value = _FORBIDDEN.sub(" ", value)
    value = _DASHES.sub(" - ", value)
    value = _SPACES.sub(" ", value).strip(" .-")
    return value or fallback


def normalize_ext(ext: str) -> str:
    return (str(ext or "").lower().lstrip(".").strip() or "mp3")


def pattern_fields(pattern: str) -> list[str]:
    """Placeholder names used by a pattern, in order of appearance."""
    return [name for _, name, _, _ in Formatter().parse(pattern) if name is not None]


def validate_pattern(pattern: str) -> None:
    """Raise ValueError if a rename pattern cannot produce a usable filename."""
    if not (pattern or "").strip():
        raise ValueError("Rename pattern is empty")
    fields = pattern_fields(pattern)
    unknown = sorted({f or "<positional>" for f in fields if f not in ALLOWED_PATTERN_FIELDS})
    if unknown:
        raise ValueError(
            f"Unknown placeholder(s) in rename pattern: {', '.join(unknown)}. "
            f"Allowed: {', '.join('{' + f + '}' for f in ALLOWED_PATTERN_FIELDS)}"
        )
    if "ext" not in fields:
        raise ValueError("Rename pattern must include {ext} so files keep their extension")


def _truncate(stem: str, ext: str) -> str:
    budget = MAX_FILENAME_BYTES - len(f".{ext}".encode())
    encoded = stem.encode("utf-8")
    if len(encoded) <= budget:
        return stem
    return encoded[:budget].decode("utf-8", "ignore").rstrip(" .-") or UNKNOWN


def _finalize(rendered: str, ext: str) -> str:
    suffix = f".{ext}"
    stem = rendered[: -len(suffix)] if rendered.lower().endswith(suffix) else rendered
    # Runs again over the rendered string: literal text in the pattern is not
    # sanitized by the per-field cleanup and may itself break a path.
    stem = _FORBIDDEN.sub(" ", stem)
    stem = _DASHES.sub(" - ", stem)
    stem = _SPACES.sub(" ", stem).strip(" .-") or UNKNOWN
    return f"{_truncate(stem, ext)}{suffix}"


def render_pattern(
    pattern: str,
    *,
    title: str,
    artist: str,
    ext: str,
    album: str = "",
    year: str = "",
    track: str = "",
) -> str:
    """Build a safe filename from a rename pattern.

    Every substituted value is sanitized before formatting and the result is
    sanitized again, so no pattern can emit a path separator or a reserved
    character. Unknown placeholders raise instead of silently falling back.
    """
    validate_pattern(pattern)
    ext = normalize_ext(ext)
    values = {
        "title": _clean_part(title, slash_as_dash=True),
        "artist": _clean_part(artist),
        "album": _clean_part(album, fallback=""),
        "year": _clean_part(year, fallback=""),
        "track": _clean_part(track, fallback=""),
        "ext": ext,
    }
    return _finalize(pattern.format(**values), ext)


def make_safe_filename(title: str, artist: str, ext: str) -> str:
    return render_pattern(DEFAULT_PATTERN, title=title, artist=artist, ext=ext)


def dedupe_path(target: Path, *, ignore: Path | None = None, taken: Collection[Path] | None = None) -> Path:
    """Return a free path near `target`.

    `ignore` is the file being renamed: a file already sitting at its final
    name must not be bumped to "(2)" on a second run. `taken` holds names
    already claimed earlier in the same batch but not yet written to disk, so
    a dry-run reports the same names an apply would produce.
    """
    claimed = set(taken or ())

    def is_free(candidate: Path) -> bool:
        if candidate in claimed:
            return False
        return not candidate.exists() or candidate == ignore

    if is_free(target):
        return target
    for n in range(2, 10000):
        candidate = target.with_name(f"{target.stem} ({n}){target.suffix}")
        if is_free(candidate):
            return candidate
    raise RuntimeError(f"Could not dedupe path: {target}")
