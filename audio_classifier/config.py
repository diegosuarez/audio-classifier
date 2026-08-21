from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os

from dotenv import load_dotenv

from .renamer import DEFAULT_PATTERN, validate_pattern

_TRUTHY = {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class AppConfig:
    acoustid_api_key: str
    pattern: str = DEFAULT_PATTERN
    min_score: float = 0.85
    write_tags: bool = True
    musicbrainz: bool = True
    contact: str = ""
    lastfm_api_key: str = ""
    lastfm: bool = True


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in _TRUTHY


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number, got {raw!r}") from exc


def load_config(env_file: str | Path | None = None) -> AppConfig:
    """Read settings from the environment, backfilled by a .env file.

    Real environment variables always win; the .env file only fills gaps.
    """
    if env_file:
        path = Path(env_file).expanduser()
        if not path.exists():
            raise FileNotFoundError(f"Env file not found: {path}")
        load_dotenv(path)
    else:
        load_dotenv()
    key = (os.getenv("ACOUSTID_API_KEY") or "").strip()
    if not key:
        raise ValueError("Missing ACOUSTID_API_KEY (set it in the environment or in .env)")
    pattern = (os.getenv("AUDIO_CLASSIFIER_PATTERN") or "").strip() or DEFAULT_PATTERN
    validate_pattern(pattern)
    return AppConfig(
        acoustid_api_key=key,
        pattern=pattern,
        min_score=_env_float("AUDIO_CLASSIFIER_MIN_SCORE", 0.85),
        write_tags=_env_bool("AUDIO_CLASSIFIER_WRITE_TAGS", True),
        musicbrainz=_env_bool("AUDIO_CLASSIFIER_MUSICBRAINZ", True),
        contact=(os.getenv("AUDIO_CLASSIFIER_CONTACT") or "").strip(),
        lastfm_api_key=(os.getenv("LASTFM_API_KEY") or "").strip(),
        lastfm=_env_bool("AUDIO_CLASSIFIER_LASTFM", True),
    )
