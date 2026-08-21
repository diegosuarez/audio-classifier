# audio-classifier

Identify audio files with Chromaprint/AcoustID, rename them safely, and fill missing MP3 ID3 tags.

## Setup

The AcoustID API key is stored in `~/.config/audio-classifier/config.toml` with `0600` permissions. Do not paste it into logs or commits.

Install system dependency if needed:

```bash
apt-get update && apt-get install -y chromaprint-tools
```

## Usage

Dry-run first:

```bash
/opt/audio-classifier/.venv/bin/python -m audio_classifier.cli scan /path/to/folder --dry-run
```

Apply changes:

```bash
/opt/audio-classifier/.venv/bin/python -m audio_classifier.cli apply /path/to/folder --yes
```

Default rename pattern comes from config:

```text
{title} - {artist}.{ext}
```

MP3 tags are only filled when missing unless `--overwrite-tags` is passed.
