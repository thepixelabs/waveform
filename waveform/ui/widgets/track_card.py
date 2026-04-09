"""
track_card.py — TrackCard: compact row widget for approved songs list.

Shows 32x32 thumbnail, track name, artist + duration meta.
Right-click context menu with "Remove from playlist."
"""
from __future__ import annotations

from typing import Any, Callable, Optional

try:
    import customtkinter as ctk  # type: ignore
    import tkinter as tk
    HAS_CTK = True
except ImportError:
    HAS_CTK = False

from waveform.ui import theme


class TrackCard(ctk.CTkFrame if HAS_CTK else object):  # type: ignore
    def __init__(
        self,
        parent: Any,
        song: Any,
        on_remove: Optional[Callable[[Any], None]] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            parent,
            fg_color=theme.BG_OVERLAY,
            corner_radius=theme.RADIUS_INPUT,
            **kwargs,
        )
        self._song = song
        self._on_remove = on_remove

        self.grid_columnconfigure(1, weight=1)

        # Thumbnail placeholder (32x32)
        self._thumb = ctk.CTkFrame(
            self,
            width=32,
            height=32,
            fg_color=theme.BG_SURFACE,
            corner_radius=4,
        )
        self._thumb.grid(row=0, column=0, rowspan=2, padx=(theme.SP_2, theme.SP_2), pady=theme.SP_1, sticky="w")
        self._thumb.grid_propagate(False)

        # Async art load
        track = getattr(song, "track", None)
        art_url = getattr(track, "album_art_url", None) if track else None
        if art_url:
            self._load_thumb_async(art_url)

        # Track name
        title = song.title[:40]
        ctk.CTkLabel(
            self,
            text=title,
            font=(theme.FONT_UI, theme.TEXT_SM, "bold"),
            text_color=theme.TEXT_PRIMARY,
            anchor="w",
        ).grid(row=0, column=1, sticky="w", pady=(theme.SP_1, 0))

        # Artist + duration
        duration_ms = getattr(track, "duration_ms", 0) if track else 0
        duration_str = f"{duration_ms // 60000}:{(duration_ms % 60000) // 1000:02d}" if duration_ms else ""
        meta = f"{song.artist[:30]}  {duration_str}".strip()
        ctk.CTkLabel(
            self,
            text=meta,
            font=(theme.FONT_UI, theme.TEXT_XS),
            text_color=theme.TEXT_MUTED,
            anchor="w",
        ).grid(row=1, column=1, sticky="w", pady=(0, theme.SP_1))

        # Right-click context menu
        self.bind("<Button-2>", self._show_context_menu)
        self.bind("<Button-3>", self._show_context_menu)

    def _load_thumb_async(self, url: str) -> None:
        import threading

        def _fetch() -> None:
            try:
                import urllib.request
                from io import BytesIO
                from PIL import Image  # type: ignore
                import customtkinter as ctk  # type: ignore

                data = urllib.request.urlopen(url, timeout=5).read()
                img = Image.open(BytesIO(data)).convert("RGB").resize((32, 32))
                ctk_img = ctk.CTkImage(img, size=(32, 32))
                self.after(0, lambda: self._set_thumb_image(ctk_img))
            except Exception:
                pass

        threading.Thread(target=_fetch, daemon=True).start()

    def _set_thumb_image(self, ctk_img: Any) -> None:
        try:
            lbl = ctk.CTkLabel(self._thumb, image=ctk_img, text="")
            lbl.place(x=0, y=0, relwidth=1, relheight=1)
        except Exception:
            pass

    def _show_context_menu(self, event: Any) -> None:
        if not self._on_remove:
            return
        try:
            import tkinter as tk
            menu = tk.Menu(self, tearoff=0)
            menu.add_command(
                label="Remove from playlist",
                command=lambda: self._on_remove(self._song) if self._on_remove else None,
            )
            menu.tk_popup(event.x_root, event.y_root)
        except Exception:
            pass
