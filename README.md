# audio-classifier

Identify audio files by their acoustic fingerprint, enrich the result with free
online music databases, rename them safely, and fill missing MP3 ID3 tags.

Point it at a folder of badly named music, preview what it would do, and apply
the changes when the preview looks right. Nothing is written without an
explicit `--yes`.

```bash
uv run audio-classifier scan  ~/Music/unsorted          # preview
uv run audio-classifier apply ~/Music/unsorted --yes    # do it
```

```text
file             score  title                 artist             target                                      action
---------------  -----  --------------------  -----------------  ------------------------------------------  ----------------
0J2QdDbelmY.mp3  0.993  Seven Nation Army     The White Stripes  Seven Nation Army - The White Stripes.mp3   rename+tag+mb
0-EF60neguk.mp3  0.988  Nothing Compares 2 U  Sinéad O’Connor    Nothing Compares 2 U - Sinéad O’Con....mp3  rename+tag+mb+fm
noise.wav        needs_review
```

## How it works

The filename and any existing tags are ignored. Identification rests entirely
on what the audio sounds like.

| Stage | Provider | Contributes | Cost |
| --- | --- | --- | --- |
| Fingerprint | Chromaprint (`fpcalc`, local) | Acoustic fingerprint, duration | — |
| Identify | [AcoustID](https://acoustid.org/) | Title, artist, MusicBrainz recording id | Free key |
| Enrich | [MusicBrainz](https://musicbrainz.org/) | Album, original release date, track number | Free, no key |
| Genre | [Last.fm](https://www.last.fm/) | Genre | Free key, optional |

Each stage only fills what the previous one left empty, so an earlier and more
reliable answer is never overwritten by a later, fuzzier one. Two details are
worth knowing:

- **MusicBrainz also rescues files AcoustID could not name.** A fingerprint
  sometimes matches with no title or artist attached. The MusicBrainz recording
  ids in that answer are still usable, and querying them directly recovers the
  track.
- **Genre is what Last.fm is for.** MusicBrainz genres are user-voted and
  absent for most recordings — 21 of 58 files in the test below. Last.fm's
  crowd tags cover the rest, at the price of filtering: those tags are freeform
  and their most popular entries are frequently decades, nationalities, moods
  or personal shelf labels rather than genres.

## Accuracy

Measured on 66 music videos downloaded from YouTube, transcoded to MP3 with all
metadata stripped, and renamed to their opaque video id, so nothing but the
audio could identify them.

| Result | Files | |
| --- | ---: | ---: |
| Correct artist and title | 53 | 80% |
| Right track, variant naming (radio edit, unplugged) | 4 | 6% |
| Not in AcoustID | 8 | 12% |
| Wrong | 1 | 2% |

Every one of the eight misses is a live recording — Glastonbury, Pinkpop, a BBC
session, a Netflix sing-along. Studio tracks were identified almost without
exception.

Enrichment across those 58 identified files: album 55, release date 54, genre
58. Without a Last.fm key, genre falls to 21.

The single wrong answer is instructive and is described under
[Limitations](#limitations).

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
[Chromaprint releases](https://github.com/acoustid/chromaprint/releases). It
depends on nothing and runs anywhere:

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

Your distribution may package it too (`pacman -S uv`, `dnf install uv`). uv
downloads a suitable Python itself, so no system Python 3.12 is required.

### 3. Install the project

```bash
git clone https://github.com/diegosuarez/audio-classifier.git
cd audio-classifier
uv sync
```

That creates `.venv/` and installs the `audio-classifier` command inside it.
Run it with `uv run audio-classifier`, or activate the environment first.

### 4. Get the API keys

- **AcoustID** — required. Register an application at
  <https://acoustid.org/new-application>. Free and instant.
- **Last.fm** — optional, genres only. Create a key at
  <https://www.last.fm/api/account/create>. Free. It hands you an *API key* and
  a *shared secret*; only the API key is needed, because the tag methods used
  here are unauthenticated. Without a key the genre stage is skipped silently.

### 5. Configure

```bash
cp .env.example .env
chmod 600 .env
$EDITOR .env
```

## Configuration

Settings come from environment variables, backfilled by a `.env` file in the
project root. Real environment variables always win over the file, so a service
manager or a container can override anything without touching `.env`.

| Variable | Default | Meaning |
| --- | --- | --- |
| `ACOUSTID_API_KEY` | — | **Required.** AcoustID application key |
| `LASTFM_API_KEY` | — | Last.fm API key. Genres are skipped without it |
| `AUDIO_CLASSIFIER_PATTERN` | `{title} - {artist}.{ext}` | Filename pattern used when renaming |
| `AUDIO_CLASSIFIER_MIN_SCORE` | `0.85` | Minimum AcoustID score required to accept a match |
| `AUDIO_CLASSIFIER_WRITE_TAGS` | `true` | Write ID3 tags on MP3 files |
| `AUDIO_CLASSIFIER_MUSICBRAINZ` | `true` | Enrich metadata via MusicBrainz |
| `AUDIO_CLASSIFIER_CONTACT` | — | Email or URL sent in the MusicBrainz User-Agent |
| `AUDIO_CLASSIFIER_LASTFM` | `true` | Fill missing genres from Last.fm tags |

`.env` is gitignored and holds your API keys. Keep it at mode `600` and do not
paste its contents into logs or commits.

`AUDIO_CLASSIFIER_CONTACT` is not required, but the MusicBrainz
[etiquette](https://musicbrainz.org/doc/MusicBrainz_API/Rate_Limiting) asks
callers to identify themselves so they can get in touch instead of blocking
you. Set it to an email address or a project URL.

### Rename patterns

`AUDIO_CLASSIFIER_PATTERN` accepts `{title}`, `{artist}`, `{album}`, `{year}`,
`{track}` and `{ext}`. `{ext}` is mandatory. Any other placeholder is rejected
at startup rather than silently ignored, so a typo fails immediately instead of
halfway through a folder.

Both the substituted values and the literal text of the pattern are sanitized.
A pattern can never emit a path separator or a character the filesystem
rejects, and empty optional fields do not leave dangling separators behind:

```text
{title} - {artist}.{ext}           ->  Paranoid Android - Radiohead.mp3
{track} - {title} ({year}).{ext}   ->  03 - Paranoid Android (1997).mp3
{album}/{title}.{ext}              ->  OK Computer Paranoid Android.mp3
{album} - {title}.{ext}            ->  Paranoid Android.mp3      (album unknown)
```

Names are truncated to 255 bytes, the per-filename limit on ext4 and xfs.
Accents and non-Latin scripts are preserved; only characters that break paths
are replaced.

## Usage

### Preview

```bash
uv run audio-classifier scan /path/to/folder
```

Nothing is written. The reported names are exactly what an apply would produce:
collisions inside the batch are already resolved during the preview.

### Apply

```bash
uv run audio-classifier apply /path/to/folder --yes
```

`apply` refuses to run without `--yes`.

### Options

Both subcommands take the same options.

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
| `--yes` | `apply` only. Required to write anything |

### Reading the output

The `action` column says what would happen, or what happened:

| Token | Meaning |
| --- | --- |
| `rename` | The file would be renamed |
| `tag` | ID3 tags would be written |
| `mb` | MusicBrainz contributed metadata |
| `fm` | Last.fm contributed the genre |
| `ok` | Identified, but nothing to change |

The `score` column holds the AcoustID confidence, or one of:

| Value | Meaning |
| --- | --- |
| `needs_review` | No fingerprint match above the threshold |
| `fingerprint_only:<id>` | The fingerprint matched, but no usable metadata was found anywhere |
| `error` | This file failed; the reason is in the last column |

Supported extensions: `.mp3`, `.flac`, `.m4a`, `.mp4`, `.ogg`, `.opus`, `.wav`,
`.aac`. Renaming works for all of them; ID3 tags are only written to `.mp3`.

## Behaviour worth knowing

- **Tags are only filled when missing**, unless `--overwrite-tags` is passed.
  Your existing metadata is never clobbered by default.
- **Reruns are safe.** A file already sitting at its final name is left alone,
  not bumped to `(2)`.
- **Collisions are resolved once.** Two files that resolve to the same track
  get distinct names, and the preview already shows them.
- **Enrichment never sinks a file.** If MusicBrainz or Last.fm is unreachable,
  the failure is reported on stderr and the file keeps whatever metadata
  AcoustID gave it.
- **A bad file does not stop the batch, but a bug does.** Unreadable audio, a
  network hiccup or a malformed response are recorded against that one file and
  the run continues. Any other exception is a defect in this program and is
  left to crash, because a batch tool that logs its own bugs once per file
  hides them.
- **Rate limits are respected**: one request per second to MusicBrainz (with a
  retry while it answers 503, which it does often under load), four per second
  to Last.fm, and `--sleep` between AcoustID lookups.

## State

Fingerprints, identifications and every applied operation are recorded in a
SQLite database at `~/.local/share/audio-classifier/audio-classifier.db`
(override with `--db`), so a rename can always be traced back to the file it
came from.

| Table | Holds |
| --- | --- |
| `audio_files` | One row per file: path, size, mtime, a hash of the first megabyte, duration, fingerprint |
| `identifications` | Every accepted identification, with the raw provider response in `raw_json`. `chosen = 1` marks the current one |
| `operations` | One row per attempt: old path, new path, whether tags were written, status, error |

`operations.status` is one of `applied`, `needs_review`,
`fingerprint_only_no_metadata` or `error`.

```bash
DB=~/.local/share/audio-classifier/audio-classifier.db

# What did the last run do?
sqlite3 "$DB" "SELECT old_path, new_path, status FROM operations ORDER BY id DESC LIMIT 20;"

# Which files still need attention?
sqlite3 "$DB" "SELECT old_path, status, error FROM operations WHERE status != 'applied';"

# What was identified, and how confidently?
sqlite3 "$DB" "SELECT artist, title, album, release_date, genre, ROUND(score,3)
               FROM identifications WHERE chosen = 1 ORDER BY score;"
```

Undoing a run is a matter of reading `operations` back:

```bash
sqlite3 "$DB" "SELECT new_path, old_path FROM operations
               WHERE status = 'applied' AND new_path IS NOT NULL ORDER BY id DESC;"
```

## Limitations

- **Live recordings are mostly absent from AcoustID.** Every miss in the
  measurement above was a live version. There is no fix short of lowering
  `--min-score`, which buys false positives instead.
- **Compilations sometimes win as the album.** Release groups carrying a
  secondary type (Compilation, Live, Soundtrack) are demoted, but a recording
  that MusicBrainz never linked to the original album has nothing better to
  offer.
- **A wrong AcoustID entry is undetectable from here.** In the measurement, a
  live Sia track matched "Buzzy Linhart — That's the Bag I'm In" at 0.96 with a
  one-second duration difference. AcoustID returned a single result, a single
  recording, and thirteen independent submissions behind it: users who had the
  file mislabelled in their own libraries. Nothing in the response separates
  that from a correct answer — a submission count threshold would reject
  genuine matches sooner, since a correctly identified track in the same run
  had only one submission. Fixing it means editing the entry at acoustid.org.
- **Genres are approximate.** They come from crowd tags, filtered but not
  curated.
- **MP3 only for tagging.** Other formats are renamed but not tagged.

## Development

```bash
uv sync
uv run --with pytest pytest
```

The suite is offline: every network call is stubbed, so it runs without API
keys and without touching AcoustID, MusicBrainz or Last.fm.

| Module | Responsibility |
| --- | --- |
| `cli.py` | Argument parsing, the per-file pipeline, the output table |
| `config.py` | Environment and `.env` loading, validation |
| `fingerprint.py` | Running `fpcalc` and parsing its output |
| `resolver.py` | AcoustID lookup and choosing among the recordings it returns |
| `musicbrainz.py` | Recording lookup, release selection, metadata merging |
| `lastfm.py` | Tag lookup and the filtering that turns tags into a genre |
| `renamer.py` | Pattern validation, sanitizing, collision handling |
| `tags.py` | Reading and writing ID3 tags |
| `db.py` | SQLite schema and writes |

Two pieces carry most of the subtlety and are worth reading before changing:

- `resolver.pick_recording` — one fingerprint maps to several MusicBrainz
  recordings, including covers and mislabelled submissions. The first entry is
  arbitrary, and length alone is a trap: a mislabelled outlier is often the
  closest match by a second while every other entry agrees on the real artist.
  The artist most entries agree on wins, and length only breaks ties inside
  that group.
- `lastfm.pick_genre` — the most popular tag is very often not a genre.

## License

Copyright 2026 Diego Suárez.

Licensed under the Apache License, Version 2.0. You may obtain a copy of the
License at <http://www.apache.org/licenses/LICENSE-2.0>, or read [LICENSE](LICENSE)
in this repository.

Unless required by applicable law or agreed to in writing, software distributed
under the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR
CONDITIONS OF ANY KIND, either express or implied. See the License for the
specific language governing permissions and limitations under the License.

This project talks to third-party services under their own terms: AcoustID
([data licensed CC0](https://acoustid.org/), client keys are per-application),
MusicBrainz ([their API rate limiting and etiquette](https://musicbrainz.org/doc/MusicBrainz_API/Rate_Limiting))
and Last.fm ([API terms of service](https://www.last.fm/api/tos)).
