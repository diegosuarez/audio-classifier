from __future__ import annotations

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
    raw: dict | None = None

    def asdict(self) -> dict:
        data = asdict(self)
        return data


def _artist_phrase(recording: dict) -> str:
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


def normalize_acoustid_result(result: dict) -> TrackMetadata | None:
    recordings = result.get("recordings") or []
    if not recordings:
        return None
    rec = recordings[0]
    title = (rec.get("title") or "").strip()
    artist = _artist_phrase(rec)
    if not title or not artist:
        return None
    releases = rec.get("releases") or []
    album = (releases[0].get("title") or "") if releases else ""
    release_date = (releases[0].get("date") or "") if releases else ""
    return TrackMetadata(
        title=title,
        artist=artist,
        score=float(result.get("score") or 0.0),
        acoustid_id=result.get("id") or "",
        recording_id=rec.get("id") or "",
        album=album,
        release_date=release_date,
        raw=result,
    )


def choose_best_result(payload: dict, min_score: float = 0.85) -> TrackMetadata | None:
    candidates = []
    for result in payload.get("results") or []:
        meta = normalize_acoustid_result(result)
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


def lookup_acoustid(api_key: str, duration: int, fingerprint: str, *, timeout: int = 30) -> dict:
    params = {
        "client": api_key,
        "duration": str(duration),
        "fingerprint": fingerprint,
        "meta": "recordings+recordingids+releases+releasegroups+tracks+compress",
    }
    url = "https://api.acoustid.org/v2/lookup?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "audio-classifier/0.1"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))
