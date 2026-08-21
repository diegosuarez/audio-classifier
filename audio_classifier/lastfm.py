"""Last.fm genre lookup.

MusicBrainz genres are user-voted and absent for most recordings, so Last.fm's
crowd tags fill the gap. Those tags are freeform text, not a controlled
vocabulary: they carry moods, decades, nationalities and personal shelf labels
alongside real genres, so they are filtered before any of them is trusted.

The API is free and needs a key from https://www.last.fm/api/account/create.
"""

from __future__ import annotations

import json
import re
import threading
import time
import urllib.parse
import urllib.request

from . import __version__

LASTFM_BASE = "https://ws.audioscrobbler.com/2.0/"
# Last.fm asks for no more than 5 requests per second per key.
MIN_INTERVAL_SECONDS = 0.25
# Tag counts are a 0-100 popularity score; below this it is noise.
MIN_TAG_COUNT = 10

# Decades are written 60s, 60's, '60s, 1960s and 1960's.
_DECADE = re.compile(r"^'?(19|20)?\d0'?s$")

# Tags that are popular on Last.fm but say nothing about genre.
NON_GENRE_TAGS = frozenset({
    "seen live", "favorites", "favourites", "favorite", "favourite",
    "favorite songs", "favourite songs", "my favorites", "my favourites",
    "albums i own", "albums i have", "own it", "my music", "spotify",
    "mp3", "vinyl", "cd", "radio", "playlist", "soundtrack of my life",
    "awesome", "amazing", "beautiful", "epic", "chill", "cool",
    "love", "love at first listen", "loved", "best songs ever",
    "check out", "under 2000 listeners", "male vocalists", "female vocalists",
    "male vocalist", "female vocalist", "vocal", "band", "music",
})

# Nationality and language tags are among the most-voted on artist pages and
# would otherwise become the genre for any act whose tracks are untagged.
# Demonyms that are also genre names (latin, celtic, nordic, afro...) are
# deliberately absent.
NATIONALITY_TAGS = frozenset({
    "american", "argentine", "argentinian", "australian", "austrian",
    "belgian", "brazilian", "british", "bulgarian", "canadian", "chilean",
    "chinese", "colombian", "croatian", "cuban", "czech", "danish", "dutch",
    "english", "estonian", "european", "finnish", "french", "german",
    "greek", "hungarian", "icelandic", "indian", "indonesian", "iranian",
    "irish", "israeli", "italian", "jamaican", "japanese", "korean",
    "mexican", "new zealand", "nigerian", "norwegian", "polish",
    "portuguese", "romanian", "russian", "scottish", "serbian", "slovenian",
    "south african", "spanish", "swedish", "swiss", "turkish", "ukrainian",
    "uk", "usa", "venezuelan", "welsh",
})

BLOCKED_TAGS = NON_GENRE_TAGS | NATIONALITY_TAGS

_throttle_lock = threading.Lock()
_last_call = 0.0


def _throttle() -> None:
    global _last_call
    with _throttle_lock:
        wait = MIN_INTERVAL_SECONDS - (time.monotonic() - _last_call)
        if wait > 0:
            time.sleep(wait)
        _last_call = time.monotonic()


def _call(method: str, api_key: str, params: dict[str, str], *, timeout: int = 30) -> dict:
    query = {"method": method, "api_key": api_key, "format": "json", **params}
    url = LASTFM_BASE + "?" + urllib.parse.urlencode(query)
    req = urllib.request.Request(url, headers={"User-Agent": f"audio-classifier/{__version__}"})
    _throttle()
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def parse_tags(payload: dict) -> list[dict]:
    """Pull the tag list out of a Last.fm response.

    Last.fm reports "not found" as a payload field rather than an HTTP error,
    and collapses a single-element list into a bare object.
    """
    if payload.get("error"):
        return []
    tags = (payload.get("toptags") or {}).get("tag")
    if isinstance(tags, dict):
        return [tags]
    return [tag for tag in (tags or []) if isinstance(tag, dict)]


def is_genre_like(name: str, blocked: frozenset[str] | set[str]) -> bool:
    key = name.strip().lower()
    if not key or key in blocked or key in BLOCKED_TAGS:
        return False
    return not _DECADE.match(key)


def pick_genre(tags: list[dict], *, exclude: tuple[str, ...] = (), min_count: int = MIN_TAG_COUNT) -> str:
    """Most popular tag that actually looks like a genre.

    `exclude` holds the artist, title and album, which routinely appear as
    their own top tag and would otherwise be written into the genre field.
    """
    blocked = {value.strip().lower() for value in exclude if value and value.strip()}
    for tag in sorted(tags, key=lambda t: int(t.get("count") or 0), reverse=True):
        if int(tag.get("count") or 0) < min_count:
            break  # sorted descending: nothing further can qualify either
        name = (tag.get("name") or "").strip()
        if is_genre_like(name, blocked):
            return name
    return ""


def lookup_genre(api_key: str, artist: str, title: str, *, album: str = "", timeout: int = 30) -> str:
    """Genre for a track, falling back to the artist's own tags.

    A track that nobody has tagged is common; its artist almost always has
    tags, and an artist-level genre still beats an empty field.
    """
    if not api_key or not artist:
        return ""
    exclude = (artist, title, album)
    if title:
        payload = _call("track.gettoptags", api_key, {"artist": artist, "track": title}, timeout=timeout)
        genre = pick_genre(parse_tags(payload), exclude=exclude)
        if genre:
            return genre
    payload = _call("artist.gettoptags", api_key, {"artist": artist}, timeout=timeout)
    return pick_genre(parse_tags(payload), exclude=exclude)
