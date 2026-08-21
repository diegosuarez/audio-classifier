from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, asdict
import json
import time
import urllib.parse
import urllib.request


@dataclass(frozen=True)
class TrackMetadata:
    title: str
    artist: str
    score: float = 0.0
    acoustid_id: str = ""
    recording_id: str = ""
    album: str = ""
    release_date: str = ""
    track_number: str = ""
    genre: str = ""
    raw: dict | None = None

    def asdict(self) -> dict:
        data = asdict(self)
        return data


def artist_phrase(recording: dict) -> str:
    # AcoustID commonly returns "artists"; MusicBrainz APIs may return "artist-credit".
    artists = recording.get("artists") or []
    names = [a.get("name", "").strip() for a in artists if a.get("name")]
    if names:
        return ", ".join(names)
    credit = recording.get("artist-credit") or []
    parts = []
    for item in credit:
        if isinstance(item, str):
            parts.append(item)
        elif isinstance(item, dict):
            parts.append((item.get("name") or item.get("artist", {}).get("name") or "").strip())
            if item.get("joinphrase"):
                parts.append(item["joinphrase"])
    return "".join(parts).strip()


def _recording_rank(recording: dict, duration: int | None) -> tuple[int, float]:
    """Closest length first; recordings that declare no length go last."""
    length = recording.get("duration")
    if duration is None or not length:
        return (1, 0.0)
    return (0, abs(float(length) - duration))


def pick_recording(result: dict, duration: int | None = None) -> dict | None:
    """Best recording inside one AcoustID result.

    A single fingerprint routinely maps to several MusicBrainz recordings:
    covers, remixes and mislabelled submissions that users attached to the
    same acoustic id. The first entry is arbitrary, and length alone is a
    trap, because a mislabelled outlier is often the closest match by a
    second or two while every other entry agrees on the real artist. So the
    artist most entries agree on wins, and length only breaks ties inside
    that group.
    """
    usable = [
        rec for rec in (result.get("recordings") or [])
        if (rec.get("title") or "").strip() and artist_phrase(rec)
    ]
    if not usable:
        return None
    votes = Counter(artist_phrase(rec).casefold() for rec in usable)
    most_votes = max(votes.values())
    consensus = {artist for artist, count in votes.items() if count == most_votes}
    candidates = [rec for rec in usable if artist_phrase(rec).casefold() in consensus]
    return sorted(candidates, key=lambda rec: _recording_rank(rec, duration))[0]


def normalize_acoustid_result(result: dict, duration: int | None = None) -> TrackMetadata | None:
    rec = pick_recording(result, duration)
    if rec is None:
        return None
    title = (rec.get("title") or "").strip()
    artist = artist_phrase(rec)
    return TrackMetadata(
        title=title,
        artist=artist,
        score=float(result.get("score") or 0.0),
        acoustid_id=result.get("id") or "",
        recording_id=rec.get("id") or "",
        raw=result,
    )


def choose_best_result(payload: dict, min_score: float = 0.85, duration: int | None = None) -> TrackMetadata | None:
    candidates = []
    for result in payload.get("results") or []:
        meta = normalize_acoustid_result(result, duration)
        if meta and meta.score >= min_score:
            candidates.append(meta)
    if not candidates:
        return None
    return sorted(candidates, key=lambda m: m.score, reverse=True)[0]


def best_fingerprint_match_without_metadata(payload: dict, min_score: float = 0.85) -> tuple[float, str] | None:
    matches: list[tuple[float, str]] = []
    for result in payload.get("results") or []:
        score = float(result.get("score") or 0.0)
        acoustid_id = result.get("id") or ""
        if score >= min_score and acoustid_id:
            matches.append((score, acoustid_id))
    if not matches:
        return None
    return sorted(matches, key=lambda item: item[0], reverse=True)[0]


def best_result_recording_ids(payload: dict, min_score: float = 0.85) -> tuple[float, str, list[str]] | None:
    """Best-scoring result with its MusicBrainz recording ids, metadata or not.

    AcoustID sometimes matches a fingerprint but returns recordings without a
    title or artist. The recording ids are still usable to ask MusicBrainz.
    """
    best: tuple[float, str, list[str]] | None = None
    for result in payload.get("results") or []:
        score = float(result.get("score") or 0.0)
        if score < min_score:
            continue
        recording_ids = [rec["id"] for rec in result.get("recordings") or [] if rec.get("id")]
        candidate = (score, result.get("id") or "", recording_ids)
        if best is None or score > best[0]:
            best = candidate
    return best


def lookup_acoustid(api_key: str, duration: int, fingerprint: str, *, timeout: int = 30) -> dict:
    params = {
        "client": api_key,
        "duration": str(duration),
        "fingerprint": fingerprint,
        # AcoustID separates meta values with "+". urlencode escapes a literal
        # "+" to %2B, which the API reads as one unknown value and answers with
        # no metadata at all, so the separator must be a space. Only identity
        # is requested here; MusicBrainz is a better source for the rest.
        "meta": "recordings",
    }
    url = "https://api.acoustid.org/v2/lookup?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "audio-classifier/0.1"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))
