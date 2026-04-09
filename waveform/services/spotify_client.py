"""
spotify_client.py — Spotipy wrapper with retries, timeouts, and a Fake for tests.

SpotifyClient: real Spotify API wrapper.
FakeSpotifyClient: in-memory test double.
SpotifyTrack / SongSuggestion: lightweight data transfer objects.
"""
from __future__ import annotations

import dataclasses
import io
import time
from typing import Any, Dict, Iterator, List, Optional


SPOTIFY_SCOPE = (
    "playlist-modify-private "
    "playlist-modify-public "
    "playlist-read-private "
    "ugc-image-upload"
)

MAX_RETRIES = 3
RETRY_DELAY = 1.0  # seconds


@dataclasses.dataclass
class SpotifyTrack:
    uri: str
    title: str
    artist: str
    album: str = ""
    duration_ms: int = 0
    preview_url: Optional[str] = None
    album_art_url: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "uri": self.uri,
            "title": self.title,
            "artist": self.artist,
            "album": self.album,
            "duration_ms": self.duration_ms,
            "preview_url": self.preview_url,
            "album_art_url": self.album_art_url,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SpotifyTrack":
        return cls(
            uri=data.get("uri", ""),
            title=data.get("title", ""),
            artist=data.get("artist", ""),
            album=data.get("album", ""),
            duration_ms=int(data.get("duration_ms", 0)),
            preview_url=data.get("preview_url"),
            album_art_url=data.get("album_art_url"),
        )


@dataclasses.dataclass
class SongSuggestion:
    """A song as returned by the AI — before Spotify lookup."""
    title: str
    artist: str
    reasoning: str = ""
    track: Optional[SpotifyTrack] = None

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "artist": self.artist,
            "reasoning": self.reasoning,
            "track": self.track.to_dict() if self.track else None,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SongSuggestion":
        track_data = data.get("track")
        return cls(
            title=data.get("title", ""),
            artist=data.get("artist", ""),
            reasoning=data.get("reasoning", ""),
            track=SpotifyTrack.from_dict(track_data) if track_data else None,
        )


class SpotifyClient:
    """Real Spotipy wrapper.  Auth is handled via SpotifyOAuth (opens browser on first run)."""

    def __init__(
        self,
        client_id: str = "",
        client_secret: str = "",
        redirect_uri: str = "http://127.0.0.1:8888/callback/",
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._redirect_uri = redirect_uri
        self._sp: Any = None

    def _client(self) -> Any:
        if self._sp is None:
            import spotipy  # type: ignore
            from spotipy.oauth2 import SpotifyOAuth  # type: ignore

            self._sp = spotipy.Spotify(
                auth_manager=SpotifyOAuth(
                    client_id=self._client_id,
                    client_secret=self._client_secret,
                    redirect_uri=self._redirect_uri,
                    scope=SPOTIFY_SCOPE,
                )
            )
        return self._sp

    def _with_retry(self, fn: Any, *args: Any, **kwargs: Any) -> Any:
        last_exc: Optional[Exception] = None
        for attempt in range(MAX_RETRIES):
            try:
                return fn(*args, **kwargs)
            except Exception as exc:
                last_exc = exc
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_DELAY * (attempt + 1))
        raise RuntimeError(f"Spotify call failed after {MAX_RETRIES} retries") from last_exc

    def search_tracks(self, query: str, limit: int = 5) -> List[SpotifyTrack]:
        sp = self._client()
        result = self._with_retry(sp.search, q=query, type="track", limit=limit)
        tracks = []
        for item in result.get("tracks", {}).get("items", []):
            images = item.get("album", {}).get("images", [])
            art_url = images[0]["url"] if images else None
            tracks.append(SpotifyTrack(
                uri=item["uri"],
                title=item["name"],
                artist=", ".join(a["name"] for a in item.get("artists", [])),
                album=item.get("album", {}).get("name", ""),
                duration_ms=item.get("duration_ms", 0),
                preview_url=item.get("preview_url"),
                album_art_url=art_url,
            ))
        return tracks

    def find_track(self, title: str, artist: str) -> Optional[SpotifyTrack]:
        results = self.search_tracks(f'track:"{title}" artist:"{artist}"', limit=3)
        if results:
            return results[0]
        # Fallback to looser search
        results = self.search_tracks(f"{title} {artist}", limit=3)
        return results[0] if results else None

    def create_playlist(
        self, name: str, description: str = "", public: bool = False
    ) -> str:
        """Returns playlist id."""
        sp = self._client()
        user_id = self._with_retry(sp.current_user)["id"]
        playlist = self._with_retry(
            sp.user_playlist_create,
            user=user_id,
            name=name,
            public=public,
            description=description,
        )
        return playlist["id"]

    def add_tracks(self, playlist_id: str, track_uris: List[str]) -> None:
        sp = self._client()
        # Spotify allows max 100 tracks per request
        for i in range(0, len(track_uris), 100):
            self._with_retry(sp.playlist_add_items, playlist_id, track_uris[i : i + 100])

    def replace_tracks(self, playlist_id: str, track_uris: List[str]) -> None:
        """Clear existing tracks and add new ones (overwrite mode)."""
        sp = self._client()
        self._with_retry(sp.playlist_replace_items, playlist_id, [])
        if track_uris:
            self.add_tracks(playlist_id, track_uris)

    def upload_cover_art(self, playlist_id: str, image_bytes: bytes) -> None:
        """Upload JPEG cover art (≤256 KB)."""
        sp = self._client()
        import base64
        encoded = base64.b64encode(image_bytes).decode("utf-8")
        self._with_retry(sp.playlist_upload_cover_image, playlist_id, encoded)

    def get_playlist_tracks(self, playlist_id: str) -> List[str]:
        """Returns list of track URIs."""
        sp = self._client()
        uris = []
        result = self._with_retry(sp.playlist_items, playlist_id)
        while result:
            for item in result.get("items", []):
                track = item.get("track")
                if track:
                    uris.append(track["uri"])
            result = self._with_retry(sp.next, result) if result.get("next") else None
        return uris

    def get_preview_url(self, track_uri: str) -> Optional[str]:
        sp = self._client()
        track_id = track_uri.split(":")[-1]
        result = self._with_retry(sp.track, track_id)
        return result.get("preview_url")

    def search_user_playlists(self, name: str) -> List[str]:
        """Return playlist IDs whose name matches (case-insensitive)."""
        sp = self._client()
        matching = []
        try:
            result = self._with_retry(sp.current_user_playlists, limit=50)
            while result:
                for pl in result.get("items", []):
                    if pl and pl.get("name", "").lower() == name.lower():
                        matching.append(pl["id"])
                result = self._with_retry(sp.next, result) if result.get("next") else None
        except Exception:
            import logging
            logging.getLogger(__name__).warning("search_user_playlists failed", exc_info=True)
        return matching


# ---------------------------------------------------------------------------
# Fake for tests
# ---------------------------------------------------------------------------

class FakeSpotifyClient:
    def __init__(self) -> None:
        self._playlists: Dict[str, Dict[str, Any]] = {}
        self._tracks: Dict[str, List[str]] = {}
        self._covers: Dict[str, bytes] = {}
        self._search_results: Dict[str, List[SpotifyTrack]] = {}

    def search_tracks(self, query: str, limit: int = 5) -> List[SpotifyTrack]:
        # Return pre-configured results or a single synthetic track
        if query in self._search_results:
            return self._search_results[query][:limit]
        q_lower = query.lower()
        track_id = f"fake:{q_lower[:20].replace(' ', '_')}"
        return [SpotifyTrack(
            uri=f"spotify:track:{track_id}",
            title=query[:40],
            artist="Fake Artist",
            album="Fake Album",
            duration_ms=210000,
            preview_url=f"https://fake.preview/{track_id}",
            album_art_url=None,
        )]

    def find_track(self, title: str, artist: str) -> Optional[SpotifyTrack]:
        key = f"{title.lower()}_{artist.lower()}"
        return SpotifyTrack(
            uri=f"spotify:track:fake_{key[:20]}",
            title=title,
            artist=artist,
            album="Fake Album",
            duration_ms=210000,
            preview_url=f"https://fake.preview/{key[:20]}",
            album_art_url=None,
        )

    def create_playlist(self, name: str, description: str = "", public: bool = False) -> str:
        import uuid
        pid = str(uuid.uuid4())
        self._playlists[pid] = {"name": name, "description": description, "public": public}
        self._tracks[pid] = []
        return pid

    def add_tracks(self, playlist_id: str, track_uris: List[str]) -> None:
        self._tracks.setdefault(playlist_id, []).extend(track_uris)

    def replace_tracks(self, playlist_id: str, track_uris: List[str]) -> None:
        self._tracks[playlist_id] = list(track_uris)

    def upload_cover_art(self, playlist_id: str, image_bytes: bytes) -> None:
        self._covers[playlist_id] = image_bytes

    def get_playlist_tracks(self, playlist_id: str) -> List[str]:
        return list(self._tracks.get(playlist_id, []))

    def get_preview_url(self, track_uri: str) -> Optional[str]:
        return f"https://fake.preview/{track_uri.split(':')[-1]}"

    def search_user_playlists(self, name: str) -> List[str]:
        return [
            pid
            for pid, pl in self._playlists.items()
            if pl.get("name", "").lower() == name.lower()
        ]
