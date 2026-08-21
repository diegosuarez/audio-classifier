"""MusicBrainz enrichment.

AcoustID identifies a recording; MusicBrainz is where the rest of the metadata
lives (album, release date, track number, genre). Both are free, and the
MusicBrainz web service asks callers for at most one request per second and a
User-Agent that identifies the application and a contact.
"""

from __future__ import annotations

from dataclasses import replace
import json
import threading
import time
import urllib.parse
import urllib.request

from . import __version__
from .resolver import TrackMetadata, artist_phrase

MB_BASE = "https://musicbrainz.org/ws/2"
MB_INCLUDES = "artists+releases+release-groups+media+genres"
MIN_INTERVAL_SECONDS = 1.0

_throttle_lock = threading.Lock()
_last_call = 0.0


def user_agent(contact: str = "") -> str:
    suffix = f" ( {contact.strip()} )" if contact and contact.strip() else ""
    return f"audio-classifier/{__version__}{suffix}"


def _throttle() -> None:
    global _last_call
    with _throttle_lock:
        wait = MIN_INTERVAL_SECONDS - (time.monotonic() - _last_call)
        if wait > 0:
            time.sleep(wait)
        _last_call = time.monotonic()


def fetch_recording(recording_id: str, *, contact: str = "", timeout: int = 30) -> dict:
    url = f"{MB_BASE}/recording/{urllib.parse.quote(recording_id)}?inc={MB_INCLUDES}&fmt=json"
    req = urllib.request.Request(url, headers={"User-Agent": user_agent(contact)})
    _throttle()
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _pick_release(releases: list[dict]) -> dict | None:
    """Prefer an official release, then the earliest one.

    The earliest official release is usually the original album rather than a
    later compilation or reissue.
    """
    if not releases:
        return None
    def sort_key(release: dict) -> tuple[int, str]:
        official = 0 if (release.get("status") or "") == "Official" else 1
        return (official, release.get("date") or "9999-99-99")
    return sorted(releases, key=sort_key)[0]


def _track_number(release: dict) -> str:
    for medium in release.get("media") or []:
        for track in medium.get("tracks") or []:
            number = track.get("number") or track.get("position")
            if number:
                return str(number)
    return ""


def _top_genre(*sources: dict | None) -> str:
    """Most-voted genre across the entities that carry one.

    MusicBrainz genres are user-voted and frequently absent on a recording,
    so the release and its release group are consulted as well.
    """
    candidates: list[dict] = []
    for source in sources:
        candidates.extend((source or {}).get("genres") or [])
    for genre in sorted(candidates, key=lambda g: int(g.get("count") or 0), reverse=True):
        name = (genre.get("name") or "").strip()
        if name:
            return name
    return ""


def _details(payload: dict) -> dict[str, str]:
    release = _pick_release(payload.get("releases") or [])
    group = (release or {}).get("release-group") or {}
    details = {
        "title": (payload.get("title") or "").strip(),
        "artist": artist_phrase(payload),
        "genre": _top_genre(payload, release, group),
        "album": "",
        "release_date": "",
        "track_number": "",
    }
    if release:
        details["album"] = (release.get("title") or "").strip()
        # A recording is usually linked to reissues rather than the original
        # pressing, so the release group's first release date is the honest
        # answer for "when did this track come out".
        details["release_date"] = (group.get("first-release-date") or release.get("date") or "").strip()
        details["track_number"] = _track_number(release)
    return details


def merge_recording_details(metadata: TrackMetadata, payload: dict) -> TrackMetadata:
    """Fill only the empty fields of `metadata` from a MusicBrainz payload.

    AcoustID's answer wins wherever it said something; MusicBrainz fills gaps.
    """
    updates = {
        field: value
        for field, value in _details(payload).items()
        if value and not getattr(metadata, field)
    }
    return replace(metadata, **updates) if updates else metadata


def metadata_from_recording(
    payload: dict, *, score: float = 0.0, acoustid_id: str = ""
) -> TrackMetadata | None:
    """Build metadata from MusicBrainz alone, for fingerprint-only AcoustID hits."""
    details = _details(payload)
    if not details["title"] or not details["artist"]:
        return None
    return TrackMetadata(
        score=score,
        acoustid_id=acoustid_id,
        recording_id=payload.get("id") or "",
        raw={"musicbrainz": payload},
        **details,
    )


def is_incomplete(metadata: TrackMetadata) -> bool:
    return not all([metadata.album, metadata.release_date, metadata.track_number, metadata.genre])
