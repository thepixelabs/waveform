"""
preview_audio.py — 30-second song preview player.

Strategy pattern: "pygame", "vlc", or "noop".

Decision (CEO Q6, resolved Phase 7): pygame.mixer is the MVP choice.
It ships with the package (no system dependency), handles MP3 via URL
with a two-step download+play flow, and is adequate for 30-second clips.

To switch to python-vlc: pass strategy="vlc" and ensure VLC is installed.
No other changes needed — the interface is identical.
"""
from __future__ import annotations

import threading
import urllib.request
from io import BytesIO
from typing import Any, Callable, Optional


class PreviewAudioPlayer:
    """
    Play a 30-second Spotify preview clip.

    strategy: "pygame" | "vlc" | "noop"
    """

    def __init__(self, strategy: str = "pygame") -> None:
        self._strategy = strategy
        self._mixer: Any = None
        self._vlc_instance: Any = None
        self._vlc_player: Any = None
        self._is_playing = False
        self._current_url: Optional[str] = None
        self._start_time: Optional[float] = None
        self._lock = threading.Lock()

        if strategy == "pygame":
            self._init_pygame()

    def _init_pygame(self) -> None:
        try:
            import pygame  # type: ignore

            if not pygame.mixer.get_init():
                pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)
            self._mixer = pygame.mixer
        except Exception:
            self._strategy = "noop"

    def play(self, url: str, on_finish: Optional[Callable] = None) -> None:
        """Start playing the preview URL asynchronously."""
        self.stop()
        self._current_url = url
        t = threading.Thread(
            target=self._play_worker, args=(url, on_finish), daemon=True
        )
        t.start()

    def _play_worker(self, url: str, on_finish: Optional[Callable]) -> None:
        import time

        with self._lock:
            self._is_playing = True

        try:
            if self._strategy == "pygame" and self._mixer is not None:
                # Download to memory buffer
                data = urllib.request.urlopen(url, timeout=10).read()
                buf = BytesIO(data)
                self._mixer.music.load(buf)
                self._mixer.music.play()
                self._start_time = time.time()
                # Poll until done or stopped
                while self._mixer.music.get_busy():
                    if not self._is_playing:
                        break
                    time.sleep(0.1)
                self._mixer.music.stop()

            elif self._strategy == "vlc":
                import vlc  # type: ignore

                self._vlc_instance = vlc.Instance()
                self._vlc_player = self._vlc_instance.media_player_new()
                media = self._vlc_instance.media_new(url)
                self._vlc_player.set_media(media)
                self._vlc_player.play()
                self._start_time = time.time()
                import time as _t
                _t.sleep(0.5)  # let VLC start
                while self._vlc_player.is_playing():
                    if not self._is_playing:
                        break
                    _t.sleep(0.1)
                self._vlc_player.stop()

        except Exception:
            pass
        finally:
            with self._lock:
                self._is_playing = False
            if on_finish:
                try:
                    on_finish()
                except Exception:
                    pass

    def stop(self) -> None:
        with self._lock:
            self._is_playing = False
        if self._strategy == "pygame" and self._mixer is not None:
            try:
                self._mixer.music.stop()
            except Exception:
                pass
        if self._vlc_player is not None:
            try:
                self._vlc_player.stop()
            except Exception:
                pass
        self._start_time = None

    @property
    def is_playing(self) -> bool:
        with self._lock:
            return self._is_playing

    def elapsed_seconds(self) -> float:
        import time
        if self._start_time is None:
            return 0.0
        return time.time() - self._start_time

    def elapsed_ms(self) -> int:
        return int(self.elapsed_seconds() * 1000)


# ---------------------------------------------------------------------------
# Fake for tests
# ---------------------------------------------------------------------------

class FakePreviewAudioPlayer:
    def __init__(self) -> None:
        self._is_playing = False
        self.plays: list = []
        self.stops: int = 0

    def play(self, url: str, on_finish: Optional[Callable] = None) -> None:
        self._is_playing = True
        self.plays.append(url)

    def stop(self) -> None:
        self._is_playing = False
        self.stops += 1

    @property
    def is_playing(self) -> bool:
        return self._is_playing

    def elapsed_seconds(self) -> float:
        return 0.0

    def elapsed_ms(self) -> int:
        return 0
