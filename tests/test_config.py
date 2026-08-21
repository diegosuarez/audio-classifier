import pytest

from audio_classifier.config import DEFAULT_PATTERN, load_config

ENV_VARS = [
    "ACOUSTID_API_KEY",
    "AUDIO_CLASSIFIER_PATTERN",
    "AUDIO_CLASSIFIER_MIN_SCORE",
    "AUDIO_CLASSIFIER_WRITE_TAGS",
]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in ENV_VARS:
        monkeypatch.delenv(name, raising=False)


def write_env(tmp_path, body: str):
    path = tmp_path / ".env"
    path.write_text(body)
    return path


def test_load_config_reads_values_from_env_file(tmp_path):
    env = write_env(
        tmp_path,
        "ACOUSTID_API_KEY=abc123\n"
        "AUDIO_CLASSIFIER_PATTERN={artist} - {title}.{ext}\n"
        "AUDIO_CLASSIFIER_MIN_SCORE=0.5\n"
        "AUDIO_CLASSIFIER_WRITE_TAGS=false\n",
    )
    cfg = load_config(env)
    assert cfg.acoustid_api_key == "abc123"
    assert cfg.pattern == "{artist} - {title}.{ext}"
    assert cfg.min_score == 0.5
    assert cfg.write_tags is False


def test_load_config_applies_defaults_when_only_key_is_set(tmp_path):
    cfg = load_config(write_env(tmp_path, "ACOUSTID_API_KEY=abc123\n"))
    assert cfg.pattern == DEFAULT_PATTERN
    assert cfg.min_score == 0.85
    assert cfg.write_tags is True


def test_real_environment_wins_over_env_file(tmp_path, monkeypatch):
    monkeypatch.setenv("ACOUSTID_API_KEY", "from-environment")
    cfg = load_config(write_env(tmp_path, "ACOUSTID_API_KEY=from-file\n"))
    assert cfg.acoustid_api_key == "from-environment"


def test_missing_api_key_raises(tmp_path):
    with pytest.raises(ValueError, match="ACOUSTID_API_KEY"):
        load_config(write_env(tmp_path, "AUDIO_CLASSIFIER_MIN_SCORE=0.9\n"))


def test_missing_env_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_config(tmp_path / "nope.env")


def test_non_numeric_min_score_raises(tmp_path):
    env = write_env(tmp_path, "ACOUSTID_API_KEY=abc123\nAUDIO_CLASSIFIER_MIN_SCORE=high\n")
    with pytest.raises(ValueError, match="AUDIO_CLASSIFIER_MIN_SCORE"):
        load_config(env)
