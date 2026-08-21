from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import tomllib


@dataclass(frozen=True)
class AppConfig:
    acoustid_api_key: str
    pattern: str = "{title} - {artist}.{ext}"
    min_score: float = 0.85
    write_tags: bool = True


def default_config_path() -> Path:
    return Path(os.getenv("AUDIO_CLASSIFIER_CONFIG", Path.home() / ".config" / "audio-classifier" / "config.toml")).expanduser()


def load_config(path: str | Path | None = None) -> AppConfig:
    cfg_path = Path(path).expanduser() if path else default_config_path()
    if not cfg_path.exists():
        raise FileNotFoundError(f"Config not found: {cfg_path}")
    data = tomllib.loads(cfg_path.read_text())
    key = (data.get("acoustid", {}).get("api_key") or "").strip()
    if not key:
        raise ValueError("Missing acoustid.api_key in config")
    rename = data.get("rename", {})
    return AppConfig(
        acoustid_api_key=key,
        pattern=rename.get("pattern") or "{title} - {artist}.{ext}",
        min_score=float(rename.get("min_score", 0.85)),
        write_tags=bool(rename.get("write_tags", True)),
    )
