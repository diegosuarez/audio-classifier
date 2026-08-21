from __future__ import annotations

from pathlib import Path
import re
import unicodedata

_DASHES = re.compile(r"\s*[-–—]+\s*")
_SPACES = re.compile(r"\s+")
_FORBIDDEN = re.compile(r"[\\/?:*\"<>|\x00-\x1f]")


def _clean_part(value: str, *, slash_as_dash: bool = False) -> str:
    value = unicodedata.normalize("NFC", str(value or "")).strip()
    if slash_as_dash:
        value = re.sub(r"\s*[\\/]\s*", " - ", value)
    value = _FORBIDDEN.sub(" ", value)
    value = _DASHES.sub(" - ", value)
    value = _SPACES.sub(" ", value).strip(" .-")
    return value or "Desconocido"


def make_safe_filename(title: str, artist: str, ext: str) -> str:
    ext = ext.lower().lstrip(".") or "mp3"
    return f"{_clean_part(title, slash_as_dash=True)} - {_clean_part(artist)}.{ext}"


def dedupe_path(target: Path) -> Path:
    if not target.exists():
        return target
    for n in range(2, 10000):
        candidate = target.with_name(f"{target.stem} ({n}){target.suffix}")
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"Could not dedupe path: {target}")
