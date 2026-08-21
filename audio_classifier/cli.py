from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
from pathlib import Path
import sys
import time

from .config import load_config
from .db import connect, init_db, upsert_audio_file, store_fingerprint, store_identification, record_operation
from .fingerprint import run_fpcalc
from .renamer import make_safe_filename, dedupe_path
from .resolver import choose_best_result, lookup_acoustid, best_fingerprint_match_without_metadata
from .tags import write_mp3_tags

AUDIO_EXTS = {".mp3", ".flac", ".m4a", ".mp4", ".ogg", ".opus", ".wav", ".aac"}
DEFAULT_DB = Path.home() / ".local" / "share" / "audio-classifier" / "audio-classifier.db"


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


def target_for(path: Path, metadata, pattern: str) -> Path:
    ext = path.suffix.lower().lstrip(".")
    # Support the planned default and future simple custom patterns.
    safe_default = make_safe_filename(metadata.title, metadata.artist, ext)
    if pattern == "{title} - {artist}.{ext}":
        name = safe_default
    else:
        raw = pattern.format(title=metadata.title, artist=metadata.artist, ext=ext, album=metadata.album or "")
        if "/" in raw or "\\" in raw:
            name = make_safe_filename(metadata.title, metadata.artist, ext)
        else:
            name = raw
    return dedupe_path(path.with_name(name))


def process_folder(args, apply: bool = False) -> int:
    cfg = load_config(args.config)
    conn = connect(args.db)
    init_db(conn)
    root = Path(args.folder).expanduser().resolve()
    if not root.exists():
        print(f"Folder not found: {root}", file=sys.stderr)
        return 2
    rows = []
    for path in iter_audio_files(root, recursive=not args.no_recursive):
        stat = path.stat()
        file_id = upsert_audio_file(conn, path, stat.st_size, stat.st_mtime, sha256_head(path))
        try:
            fp = run_fpcalc(path)
            store_fingerprint(conn, file_id, fp.duration, fp.fingerprint)
            payload = lookup_acoustid(cfg.acoustid_api_key, fp.duration, fp.fingerprint)
            meta = choose_best_result(payload, min_score=args.min_score if args.min_score is not None else cfg.min_score)
            time.sleep(args.sleep)
            if not meta:
                fingerprint_only = best_fingerprint_match_without_metadata(payload, min_score=args.min_score if args.min_score is not None else cfg.min_score)
                if fingerprint_only:
                    score, acoustid_id = fingerprint_only
                    rows.append((path.name, f"{score:.3f}", "", "", "", f"fingerprint_only:{acoustid_id[:8]}"))
                    record_operation(conn, file_id, path, None, False, "fingerprint_only_no_metadata")
                else:
                    rows.append((path.name, "needs_review", "", "", "", ""))
                    record_operation(conn, file_id, path, None, False, "needs_review")
                continue
            store_identification(conn, file_id, meta)
            target = target_for(path, meta, args.pattern or cfg.pattern)
            action = []
            if target.name != path.name:
                action.append("rename")
            if path.suffix.lower() == ".mp3" and (args.write_tags or cfg.write_tags):
                action.append("tag")
            rows.append((path.name, f"{meta.score:.3f}", meta.title, meta.artist, target.name, "+".join(action) or "ok"))
            if apply:
                wrote = False
                actual_path = path
                if path.suffix.lower() == ".mp3" and (args.write_tags or cfg.write_tags):
                    updates = write_mp3_tags(path, meta.asdict(), overwrite=args.overwrite_tags)
                    wrote = bool(updates)
                if target.name != path.name:
                    actual_target = dedupe_path(path.with_name(target.name))
                    path.rename(actual_target)
                    actual_path = actual_target
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
        sp.add_argument("--config")
        sp.add_argument("--db", default=str(DEFAULT_DB))
        sp.add_argument("--pattern")
        sp.add_argument("--min-score", type=float)
        sp.add_argument("--sleep", type=float, default=1.0)
        sp.add_argument("--no-recursive", action="store_true")
        sp.add_argument("--write-tags", action="store_true", default=True)
        sp.add_argument("--overwrite-tags", action="store_true")
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
