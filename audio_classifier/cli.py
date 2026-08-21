from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import sys
import time

from dataclasses import replace

from . import lastfm, musicbrainz
from .config import load_config
from .db import connect, init_db, upsert_audio_file, store_fingerprint, store_identification, record_operation
from .fingerprint import fpcalc_available, run_fpcalc
from .renamer import dedupe_path, render_pattern, validate_pattern
from .resolver import (
    best_fingerprint_match_without_metadata,
    best_result_recording_ids,
    choose_best_result,
    lookup_acoustid,
)
from .tags import write_mp3_tags

AUDIO_EXTS = {".mp3", ".flac", ".m4a", ".mp4", ".ogg", ".opus", ".wav", ".aac"}
DEFAULT_DB = Path.home() / ".local" / "share" / "audio-classifier" / "audio-classifier.db"
# How many MusicBrainz recordings to try when AcoustID matched without metadata.
MUSICBRAINZ_MAX_CANDIDATES = 3


def sha256_head(path: Path, max_bytes: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        h.update(f.read(max_bytes))
    return h.hexdigest()


def iter_audio_files(root: Path, recursive: bool = True):
    files = root.rglob("*") if recursive else root.iterdir()
    for path in sorted(files):
        if path.is_file() and path.suffix.lower() in AUDIO_EXTS:
            yield path


def target_for(path: Path, metadata, pattern: str, taken=None) -> Path:
    name = render_pattern(
        pattern,
        title=metadata.title,
        artist=metadata.artist,
        ext=path.suffix,
        album=getattr(metadata, "album", "") or "",
        year=(getattr(metadata, "release_date", "") or "")[:4],
        track=getattr(metadata, "track_number", "") or "",
    )
    return dedupe_path(path.with_name(name), ignore=path, taken=taken)


def enrich_with_musicbrainz(payload: dict, meta, min_score: float, contact: str):
    """Fill metadata gaps from MusicBrainz, or build metadata AcoustID could not.

    Enrichment must never sink a file AcoustID already identified, so network
    and payload failures degrade to whatever metadata we already had.
    """
    try:
        if meta is not None:
            if not meta.recording_id or not musicbrainz.is_incomplete(meta):
                return meta
            details = musicbrainz.fetch_recording(meta.recording_id, contact=contact)
            return musicbrainz.merge_recording_details(meta, details)
        fallback = best_result_recording_ids(payload, min_score)
        if not fallback:
            return None
        score, acoustid_id, recording_ids = fallback
        for recording_id in recording_ids[:MUSICBRAINZ_MAX_CANDIDATES]:
            details = musicbrainz.fetch_recording(recording_id, contact=contact)
            built = musicbrainz.metadata_from_recording(details, score=score, acoustid_id=acoustid_id)
            if built:
                return built
        return None
    except (OSError, ValueError) as exc:
        print(f"MusicBrainz lookup failed: {exc}", file=sys.stderr)
        return meta


def add_lastfm_genre(meta, api_key: str):
    """Fill an empty genre from Last.fm tags, or return the metadata untouched."""
    try:
        genre = lastfm.lookup_genre(api_key, meta.artist, meta.title, album=meta.album)
    except (OSError, ValueError) as exc:
        print(f"Last.fm lookup failed: {exc}", file=sys.stderr)
        return meta
    return replace(meta, genre=genre) if genre else meta


def process_folder(args, apply: bool = False) -> int:
    cfg = load_config(args.env_file)
    conn = connect(args.db)
    init_db(conn)
    root = Path(args.folder).expanduser().resolve()
    if not root.exists():
        print(f"Folder not found: {root}", file=sys.stderr)
        return 2
    if not fpcalc_available():
        print(
            "fpcalc not found in PATH. Install Chromaprint "
            "(Debian/Ubuntu: libchromaprint-tools, Fedora: chromaprint-tools, "
            "Arch: chromaprint) or see the README.",
            file=sys.stderr,
        )
        return 2
    min_score = cfg.min_score if args.min_score is None else args.min_score
    write_tags = cfg.write_tags if args.write_tags is None else args.write_tags
    use_musicbrainz = cfg.musicbrainz if args.musicbrainz is None else args.musicbrainz
    # Last.fm needs a key; without one the step is simply skipped.
    use_lastfm = (cfg.lastfm if args.lastfm is None else args.lastfm) and bool(cfg.lastfm_api_key)
    pattern = args.pattern or cfg.pattern
    validate_pattern(pattern)
    rows = []
    # Names claimed earlier in this batch. Without it a dry-run would report
    # the same target twice for two files that resolve to the same track.
    claimed: set[Path] = set()
    for path in iter_audio_files(root, recursive=not args.no_recursive):
        stat = path.stat()
        file_id = upsert_audio_file(conn, path, stat.st_size, stat.st_mtime, sha256_head(path))
        try:
            fp = run_fpcalc(path)
            store_fingerprint(conn, file_id, fp.duration, fp.fingerprint)
            payload = lookup_acoustid(cfg.acoustid_api_key, fp.duration, fp.fingerprint)
            meta = choose_best_result(payload, min_score=min_score)
            time.sleep(args.sleep)
            enriched = enrich_with_musicbrainz(payload, meta, min_score, cfg.contact) if use_musicbrainz else meta
            used_musicbrainz = enriched is not meta
            meta = enriched
            used_lastfm = False
            if meta is not None and use_lastfm and not meta.genre:
                tagged = add_lastfm_genre(meta, cfg.lastfm_api_key)
                used_lastfm = tagged is not meta
                meta = tagged
            if not meta:
                fingerprint_only = best_fingerprint_match_without_metadata(payload, min_score=min_score)
                if fingerprint_only:
                    score, acoustid_id = fingerprint_only
                    rows.append((path.name, f"{score:.3f}", "", "", "", f"fingerprint_only:{acoustid_id[:8]}"))
                    record_operation(conn, file_id, path, None, False, "fingerprint_only_no_metadata")
                else:
                    rows.append((path.name, "needs_review", "", "", "", ""))
                    record_operation(conn, file_id, path, None, False, "needs_review")
                continue
            store_identification(conn, file_id, meta)
            target = target_for(path, meta, pattern, claimed)
            claimed.add(target)
            tagging = path.suffix.lower() == ".mp3" and write_tags
            action = []
            if target.name != path.name:
                action.append("rename")
            if tagging:
                action.append("tag")
            if used_musicbrainz:
                action.append("mb")
            if used_lastfm:
                action.append("fm")
            rows.append((path.name, f"{meta.score:.3f}", meta.title, meta.artist, target.name, "+".join(action) or "ok"))
            if apply:
                wrote = False
                actual_path = path
                if tagging:
                    updates = write_mp3_tags(path, meta.asdict(), overwrite=args.overwrite_tags)
                    wrote = bool(updates)
                if target.name != path.name:
                    path.rename(target)
                    actual_path = target
                record_operation(conn, file_id, path, actual_path, wrote, "applied")
        except Exception as exc:
            rows.append((path.name, "error", "", "", "", str(exc)))
            record_operation(conn, file_id, path, None, False, "error", str(exc))
    print_table(rows)
    return 0


def print_table(rows):
    headers = ("file", "score", "title", "artist", "target", "action")
    all_rows = [headers] + rows
    widths = [min(42, max(len(str(r[i])) for r in all_rows)) for i in range(len(headers))]
    for idx, row in enumerate(all_rows):
        line = "  ".join(str(row[i])[:widths[i]].ljust(widths[i]) for i in range(len(headers)))
        print(line)
        if idx == 0:
            print("  ".join("-" * w for w in widths))


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="audio-classifier")
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ["scan", "apply"]:
        sp = sub.add_parser(name)
        sp.add_argument("folder")
        sp.add_argument("--env-file", help="Path to a .env file (default: nearest .env)")
        sp.add_argument("--db", default=str(DEFAULT_DB))
        sp.add_argument("--pattern")
        sp.add_argument("--min-score", type=float)
        sp.add_argument("--sleep", type=float, default=1.0)
        sp.add_argument("--no-recursive", action="store_true")
        sp.add_argument("--write-tags", action=argparse.BooleanOptionalAction, default=None,
                        help="Write ID3 tags on MP3 files (default: from config)")
        sp.add_argument("--overwrite-tags", action="store_true")
        sp.add_argument("--musicbrainz", action=argparse.BooleanOptionalAction, default=None,
                        help="Enrich metadata via MusicBrainz (default: from config)")
        sp.add_argument("--lastfm", action=argparse.BooleanOptionalAction, default=None,
                        help="Fill missing genres from Last.fm tags (default: from config)")
        if name == "scan":
            sp.add_argument("--dry-run", action="store_true", default=True)
        else:
            sp.add_argument("--yes", action="store_true", help="Actually apply changes")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.cmd == "scan":
        return process_folder(args, apply=False)
    if args.cmd == "apply":
        if not args.yes:
            print("Refusing to apply without --yes. Run scan first.", file=sys.stderr)
            return 2
        return process_folder(args, apply=True)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
