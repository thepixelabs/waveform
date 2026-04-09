"""
export_dialog.py — ExportDialog: Spotify export flow modal.

Handles playlist name, full-night/split mode, collision resolution, progress,
success (Spotify URL), and error states.

Phase 11: store.set("export_completed", True) on success for analytics.
"""
from __future__ import annotations

import webbrowser
from typing import Any, Callable, Optional

try:
    import customtkinter as ctk  # type: ignore
    HAS_CTK = True
except ImportError:
    HAS_CTK = False

from waveform.app.export import ExistingPlaylistAction, ExportMode, ExportResult
from waveform.ui import theme


class ExportDialog(ctk.CTkToplevel if HAS_CTK else object):  # type: ignore
    def __init__(
        self,
        parent: Any,
        store: Any,
        export_controller: Any,
        session: Any,
        approved_songs: Any,
        app_open_time_ms: int = 0,
        **kwargs: Any,
    ) -> None:
        super().__init__(parent, **kwargs)
        self.title("Export to Spotify")
        self.geometry("480x420")
        self.transient(parent)
        self.grab_set()
        self.focus_set()
        self.resizable(False, False)

        self._store = store
        self._controller = export_controller
        self._session = session
        self._approved_songs = approved_songs
        self._app_open_time_ms = app_open_time_ms
        self._result: Optional[ExportResult] = None
        self._collision_resolve: Optional[Callable] = None

        self.grid_columnconfigure(0, weight=1)

        # Playlist name
        ctk.CTkLabel(
            self,
            text="Playlist Name",
            font=(theme.FONT_UI, theme.TEXT_XS),
            text_color=theme.TEXT_MUTED,
        ).grid(row=0, column=0, padx=theme.SP_4, pady=(theme.SP_4, theme.SP_1), sticky="w")

        template = getattr(session, "event_template", None)
        default_name = session.event_name or (getattr(template, "name", "My Event") if template else "My Event")

        self._name_var = ctk.StringVar(value=default_name)
        name_entry = ctk.CTkEntry(self, textvariable=self._name_var, height=36, font=(theme.FONT_UI, theme.TEXT_SM))
        name_entry.grid(row=1, column=0, padx=theme.SP_4, pady=(0, theme.SP_3), sticky="ew")

        # Mode toggle
        ctk.CTkLabel(
            self,
            text="Export Mode",
            font=(theme.FONT_UI, theme.TEXT_XS),
            text_color=theme.TEXT_MUTED,
        ).grid(row=2, column=0, padx=theme.SP_4, pady=(0, theme.SP_1), sticky="w")

        self._mode_var = ctk.StringVar(value="full_night")
        mode_row = ctk.CTkFrame(self, fg_color="transparent")
        mode_row.grid(row=3, column=0, padx=theme.SP_4, pady=(0, theme.SP_3), sticky="w")

        ctk.CTkRadioButton(
            mode_row,
            text="Full Night (one playlist)",
            variable=self._mode_var,
            value="full_night",
            font=(theme.FONT_UI, theme.TEXT_SM),
        ).pack(side="left", padx=(0, theme.SP_4))

        ctk.CTkRadioButton(
            mode_row,
            text="Split (one per block)",
            variable=self._mode_var,
            value="split",
            font=(theme.FONT_UI, theme.TEXT_SM),
        ).pack(side="left")

        # Live preview
        total_tracks = sum(len(songs) for songs in (approved_songs or {}).values())
        n_blocks = len(getattr(session, "blocks", []))

        self._preview_label = ctk.CTkLabel(
            self,
            text=f"{total_tracks} tracks  •  {n_blocks} blocks",
            font=(theme.FONT_UI, theme.TEXT_SM),
            text_color=theme.TEXT_SECONDARY,
        )
        self._preview_label.grid(row=4, column=0, padx=theme.SP_4, pady=(0, theme.SP_3))

        # Progress bar (hidden initially)
        self._progress = ctk.CTkProgressBar(self, mode="indeterminate", height=4)
        self._progress_label = ctk.CTkLabel(
            self,
            text="",
            font=(theme.FONT_UI, theme.TEXT_SM),
            text_color=theme.TEXT_SECONDARY,
        )

        # Export button
        self._export_btn = ctk.CTkButton(
            self,
            text="Export to Spotify",
            font=(theme.FONT_UI, theme.TEXT_SM, "bold"),
            fg_color=theme.SUCCESS_GREEN,
            hover_color="#2CBF8A",
            height=44,
            command=self._start_export,
        )
        self._export_btn.grid(row=7, column=0, padx=theme.SP_4, pady=(0, theme.SP_2), sticky="ew")

        ctk.CTkButton(
            self,
            text="Cancel",
            font=(theme.FONT_UI, theme.TEXT_SM),
            fg_color="transparent",
            text_color=theme.TEXT_MUTED,
            command=self.destroy,
        ).grid(row=8, column=0, padx=theme.SP_4, pady=(0, theme.SP_3))

    def _start_export(self) -> None:
        self._export_btn.configure(state="disabled", text="Exporting…")
        self._progress.grid(row=5, column=0, padx=theme.SP_4, sticky="ew")
        self._progress.start()
        self._progress_label.grid(row=6, column=0, padx=theme.SP_4)

        mode = ExportMode.SPLIT if self._mode_var.get() == "split" else ExportMode.FULL_NIGHT

        self._controller.export_session(
            session=self._session,
            approved_songs=self._approved_songs,
            mode=mode,
            playlist_name=self._name_var.get().strip(),
            on_progress=lambda msg: self.after(0, lambda m=msg: self._progress_label.configure(text=m)),
            on_existing_playlist=self._on_collision,
            on_complete=lambda result: self.after(0, lambda r=result: self._on_export_complete(r)),
            on_error=lambda err: self.after(0, lambda e=err: self._on_export_error(e)),
            app_open_time_ms=self._app_open_time_ms,
        )

    def _on_collision(self, name: str, resolve: Callable) -> None:
        self.after(0, lambda: self._show_collision_dialog(name, resolve))

    def _show_collision_dialog(self, name: str, resolve: Callable) -> None:
        dialog = _CollisionDialog(self, name=name, on_resolve=resolve)

    def _on_export_complete(self, result: ExportResult) -> None:
        self._progress.stop()
        self._progress.grid_remove()
        self._progress_label.grid_remove()
        self._export_btn.grid_remove()

        # Success state
        ctk.CTkLabel(
            self,
            text="Exported successfully!",
            font=(theme.FONT_UI, theme.TEXT_MD, "bold"),
            text_color=theme.SUCCESS_GREEN,
        ).grid(row=5, column=0, padx=theme.SP_4, pady=(0, theme.SP_2))

        ctk.CTkLabel(
            self,
            text=f"{result.track_count} tracks across {result.block_count} blocks",
            font=(theme.FONT_UI, theme.TEXT_SM),
            text_color=theme.TEXT_SECONDARY,
        ).grid(row=6, column=0, padx=theme.SP_4, pady=(0, theme.SP_3))

        if result.primary_url:
            url = result.primary_url
            ctk.CTkButton(
                self,
                text="Open in Spotify",
                fg_color=theme.SUCCESS_GREEN,
                command=lambda: webbrowser.open(url),
            ).grid(row=7, column=0, padx=theme.SP_4, pady=(0, theme.SP_2), sticky="ew")

        ctk.CTkButton(
            self,
            text="Done",
            fg_color=theme.BG_OVERLAY,
            command=self.destroy,
        ).grid(row=8, column=0, padx=theme.SP_4, pady=(0, theme.SP_3), sticky="ew")

        # Signal export_completed to analytics
        if self._store:
            self._store.set("export_completed", True)

    def _on_export_error(self, message: str) -> None:
        self._progress.stop()
        self._progress.grid_remove()

        self._export_btn.configure(state="normal", text="Retry")
        self._progress_label.configure(
            text=f"Export failed: {message[:80]}",
            text_color=theme.DANGER_RED,
        )


class _CollisionDialog(ctk.CTkToplevel if HAS_CTK else object):  # type: ignore
    def __init__(self, parent: Any, name: str, on_resolve: Callable, **kwargs: Any) -> None:
        super().__init__(parent, **kwargs)
        self.title("Playlist Exists")
        self.geometry("380x240")
        self.transient(parent)
        self.grab_set()
        self.focus_set()
        self._on_resolve = on_resolve
        self._rename_var = ctk.StringVar(value=f"{name} (2)")

        ctk.CTkLabel(
            self,
            text=f'A playlist named "{name}" already exists.',
            font=(theme.FONT_UI, theme.TEXT_SM),
            wraplength=340,
        ).pack(padx=theme.SP_4, pady=(theme.SP_4, theme.SP_2))

        ctk.CTkButton(
            self,
            text="Overwrite",
            fg_color=theme.DANGER_RED,
            command=lambda: self._resolve(ExistingPlaylistAction.OVERWRITE),
        ).pack(fill="x", padx=theme.SP_4, pady=(0, theme.SP_1))

        ctk.CTkButton(
            self,
            text="Append to existing",
            fg_color=theme.BG_OVERLAY,
            command=lambda: self._resolve(ExistingPlaylistAction.APPEND),
        ).pack(fill="x", padx=theme.SP_4, pady=(0, theme.SP_1))

        rename_row = ctk.CTkFrame(self, fg_color="transparent")
        rename_row.pack(fill="x", padx=theme.SP_4, pady=(0, theme.SP_3))
        rename_row.grid_columnconfigure(0, weight=1)

        ctk.CTkEntry(
            rename_row, textvariable=self._rename_var, font=(theme.FONT_UI, theme.TEXT_SM), height=32
        ).grid(row=0, column=0, sticky="ew", padx=(0, theme.SP_2))

        ctk.CTkButton(
            rename_row,
            text="Save as new",
            fg_color=theme.ACCENT_VIOLET,
            width=100,
            command=lambda: self._resolve(ExistingPlaylistAction.RENAME, self._rename_var.get()),
        ).grid(row=0, column=1)

    def _resolve(self, action: ExistingPlaylistAction, new_name: Optional[str] = None) -> None:
        self.destroy()
        self._on_resolve(action, new_name)
