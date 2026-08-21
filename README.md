# audio-classifier

Identify audio files by their acoustic fingerprint, enrich the result with
online music databases, rename them safely, and fill missing MP3 ID3 tags.

A file goes through four stages, all of them free and none requiring a paid
service:

| Stage | Provider | What it contributes |
| --- | --- | --- |
| Fingerprint | Chromaprint (`fpcalc`, local) | Acoustic fingerprint and duration |
| Identify | AcoustID | Title, artist, MusicBrainz recording id |
| Enrich | MusicBrainz | Album, original release date, track number |
| Genre | Last.fm | Genre, from crowd tags |

Each stage only fills what the previous one left empty, so an earlier, more
reliable answer is never overwritten by a later, fuzzier one. MusicBrainz also
rescues files that AcoustID matched by fingerprint but returned no title or
artist for.

## Requirements

- Linux (any distribution), x86_64 or arm64
- Python 3.12 or newer
- `fpcalc` from Chromaprint
- [uv](https://docs.astral.sh/uv/)

## Installation

### 1. Install `fpcalc`

`fpcalc` is the only system dependency. Package names differ per distribution:

```bash
# Debian, Ubuntu, Linux Mint, Pop!_OS
sudo apt update && sudo apt install -y libchromaprint-tools

# Fedora
sudo dnf install -y chromaprint-tools

# RHEL, Rocky, AlmaLinux (needs EPEL)
sudo dnf install -y epel-release && sudo dnf install -y chromaprint-tools

# Arch, Manjaro
sudo pacman -S --needed chromaprint

# openSUSE
sudo zypper install -y chromaprint-fpcalc

# Alpine
sudo apk add chromaprint
```

On older Debian and Ubuntu releases the package was named `chromaprint-tools`.
Verify whichever you installed:

```bash
fpcalc -version
```

If your distribution ships no package, take the static binary from the
[Chromaprint releases](https://github.com/acoustid/chromaprint/releases) —
it depends on nothing and runs anywhere:

```bash
VERSION=1.6.1
ARCH=$(uname -m | sed 's/aarch64/arm64/')   # x86_64 or arm64
curl -fsSL -o /tmp/chromaprint.tar.gz \
  "https://github.com/acoustid/chromaprint/releases/download/v$VERSION/chromaprint-fpcalc-$VERSION-linux-$ARCH.tar.gz"
tar -xzf /tmp/chromaprint.tar.gz -C /tmp
sudo install -m 0755 "/tmp/chromaprint-fpcalc-$VERSION-linux-$ARCH/fpcalc" /usr/local/bin/fpcalc
```

### 2. Install uv

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Your distribution may package it as well (`pacman -S uv`, `dnf install uv`).
uv downloads a suitable Python itself, so no system Python 3.12 is needed.

### 3. Install the project

```bash
git clone git@github.com:diegosuarez/audio-classifier.git
cd audio-classifier
uv sync
```

That creates `.venv/` and installs the `audio-classifier` command inside it.
Run it with `uv run audio-classifier`, or activate the environment first.

### 4. Get the API keys

- **AcoustID** (required): register an application at
  <https://acoustid.org/new-application>. Free, instant.
- **Last.fm** (optional, genres only): create a key at
  <https://www.last.fm/api/account/create>. Free. Without it the genre stage is
  skipped silently.

### 5. Configure

```bash
cp .env.example .env
chmod 600 .env
$EDITOR .env
```

## Configuration

Settings come from environment variables, backfilled by a `.env` file in the
project root. Real environment variables always win over the file, so a service
manager or container can override anything without touching `.env`.

| Variable | Default | Meaning |
| --- | --- | --- |
| `ACOUSTID_API_KEY` | — | **Required.** AcoustID application key |
| `LASTFM_API_KEY` | — | Last.fm key. Genres are skipped without it |
| `AUDIO_CLASSIFIER_PATTERN` | `{title} - {artist}.{ext}` | Filename pattern used when renaming |
| `AUDIO_CLASSIFIER_MIN_SCORE` | `0.85` | Minimum AcoustID score required to accept a match |
| `AUDIO_CLASSIFIER_WRITE_TAGS` | `true` | Write ID3 tags on MP3 files |
| `AUDIO_CLASSIFIER_MUSICBRAINZ` | `true` | Enrich metadata via MusicBrainz |
| `AUDIO_CLASSIFIER_CONTACT` | — | Email or URL sent in the MusicBrainz User-Agent |
| `AUDIO_CLASSIFIER_LASTFM` | `true` | Fill missing genres from Last.fm tags |

`.env` is gitignored and holds your API keys. Keep it at mode `600` and do not
paste its contents into logs or commits.

### Rename patterns

`AUDIO_CLASSIFIER_PATTERN` accepts `{title}`, `{artist}`, `{album}`, `{year}`,
`{track}` and `{ext}`. `{ext}` is mandatory. Any other placeholder is rejected
at startup rather than silently ignored. Both the substituted values and the
literal text of the pattern are sanitized, so a pattern can never emit a path
separator or a character the filesystem rejects, and empty optional fields do
not leave dangling separators behind:

```text
{track} - {title} ({year}).{ext}   ->  03 - Paranoid Android (1997).mp3
{album}/{title}.{ext}              ->  OK Computer Paranoid Android.mp3
{album} - {title}.{ext}            ->  Paranoid Android.mp3      (album unknown)
```

Names are truncated to 255 bytes, the per-filename limit on ext4 and xfs.

## Usage

Dry-run first. Nothing is written, and the reported names are exactly what an
apply would produce:

```bash
uv run audio-classifier scan /path/to/folder
```

```text
file                score  title             artist     target                       action
------------------  -----  ----------------  ---------  ---------------------------  -----------
01 - track.mp3      0.97   Paranoid Android  Radiohead  Paranoid Android - Radi....  rename+tag
unknown.mp3         0.93   Karma Police      Radiohead  Karma Police - Radiohead...  rename+tag+mb+fm
noise.wav           needs_review
```

The `action` column shows what would happen: `rename`, `tag`, plus `mb` and
`fm` when MusicBrainz or Last.fm contributed metadata.

Apply the changes:

```bash
uv run audio-classifier apply /path/to/folder --yes
```

`apply` refuses to run without `--yes`.

### Options

| Flag | Meaning |
| --- | --- |
| `--env-file PATH` | Use a specific `.env` instead of the nearest one |
| `--db PATH` | State database (default `~/.local/share/audio-classifier/audio-classifier.db`) |
| `--pattern PATTERN` | Override the rename pattern for this run |
| `--min-score FLOAT` | Override the minimum AcoustID score |
| `--sleep SECONDS` | Pause between AcoustID lookups (default `1.0`) |
| `--no-recursive` | Do not descend into subdirectories |
| `--write-tags` / `--no-write-tags` | Force ID3 tagging on or off |
| `--overwrite-tags` | Replace existing tags instead of only filling missing ones |
| `--musicbrainz` / `--no-musicbrainz` | Force MusicBrainz enrichment on or off |
| `--lastfm` / `--no-lastfm` | Force the Last.fm genre lookup on or off |

## Behaviour worth knowing

- **Tags are only filled when missing**, unless `--overwrite-tags` is passed.
- **Reruns are safe.** A file already sitting at its final name is left alone,
  not bumped to `(2)`.
- **Collisions are resolved once.** Two files that resolve to the same track
  get distinct names, and the dry run already shows them.
- **Enrichment never sinks a file.** If MusicBrainz or Last.fm is unreachable,
  the failure is reported on stderr and the file keeps whatever metadata
  AcoustID gave it.
- **A bad file does not stop the batch, but a bug does.** Unreadable audio, a
  network hiccup or a malformed response are recorded against that one file
  and the run continues. Any other exception is a defect in this program and
  is left to crash, because a batch tool that logs its own bugs once per file
  hides them.
- **Rate limits are respected**: one request per second to MusicBrainz, four
  per second to Last.fm, and `--sleep` between AcoustID lookups.
- **Genres are sparse.** MusicBrainz genres are user-voted and usually absent;
  Last.fm covers most of the gap but its tags are freeform, so decades,
  nationalities, moods and shelf labels are filtered out before a tag is
  accepted as a genre.

## Accuracy

Measured on 66 music videos downloaded from YouTube, transcoded to MP3 with
all metadata stripped, and renamed to their opaque video id so nothing but the
audio could identify them:

| Result | Files | |
| --- | ---: | ---: |
| Correct artist and title | 53 | 80% |
| Right track, variant naming (radio edit, unplugged) | 4 | 6% |
| Not in AcoustID | 8 | 12% |
| Wrong | 1 | 2% |

Every one of the eight misses is a live recording (Glastonbury, Pinkpop, a BBC
session); studio tracks were identified almost without exception.

Enrichment on those 58 identified files: album 55, release date 54, genre 58.
Genre coverage is what the Last.fm stage buys — without a key it is 21 of 58,
because MusicBrainz genres are voted by users and mostly absent.

## State

Fingerprints, identifications and every applied operation are recorded in a
SQLite database at `~/.local/share/audio-classifier/audio-classifier.db`
(override with `--db`), so a rename can always be traced back to the file it
came from.

```bash
sqlite3 ~/.local/share/audio-classifier/audio-classifier.db \
  "SELECT old_path, new_path, status FROM operations ORDER BY id DESC LIMIT 10;"
```

## Tests

```bash
uv run --with pytest pytest
```

The suite is offline: every network call is stubbed.
