"""
session_history.py — SessionHistoryDialog: browse and resume past sessions.

Phase 2A: Fork session.
Phase 2C: Multi-select delete, bulk clear, relative dates, "Open in Spotify",
          event type in metadata, empty state with CTA, store kwarg.
"""
from __future__ import annotations

import copy
import datetime
import uuid
import webbrowser
from typing import Any, Callable, Dict, List, Optional

try:
    import customtkinter as ctk  # type: ignore
    HAS_CTK = True
except ImportError:
    HAS_CTK = False

from waveform.ui import theme
from waveform.ui.widgets.waveform_anim import WaveformAnim


def _relative_date(iso_str: str) -> str:
    try:
        dt = datetime.datetime.fromisoformat(iso_str.rstrip("Z"))
        now = datetime.datetime.utcnow()
        delta = (now - dt).days
        if delta == 0:
            return "Today"
        if delta == 1:
            return "Yesterday"
        if delta < 7:
            return f"{delta} days ago"
        if delta < 14:
            return "Last week"
        try:
            return dt.strftime("%-d %B")
        except ValueError:
            return dt.strftime("%d %B")
    except Exception:
        return iso_str[:10] if iso_str else ""


def _make_fork_data(snapshot: dict) -> dict:
    data = copy.deepcopy(snapshot)
    data["session_id"] = str(uuid.uuid4())
    data["id"] = data["session_id"]
    name = data.get("event_name", "Session")
    data["event_name"] = f"{name} (Copy)"
    data["playlist_name"] = f"{data.get('playlist_name', name)} (Copy)"
    data["playlist_urls"] = []
    data["playlist_url"] = ""
    data["playlist_id"] = ""
    # Clear history fields
    for key in ("veto_entries", "keep_entries", "approved_songs", "keep_history"):
        data[key] = {} if key == "keep_history" else []
    data["veto_count"] = 0
    data["exported_at"] = ""
    return data


class SessionHistoryDialog(ctk.CTkToplevel if HAS_CTK else object):  # type: ignore
    def __init__(
        self,
        parent: Any,
        persistence: Any,
        on_resume: Optional[Callable[[dict], None]] = None,
        on_fork: Optional[Callable[[dict], None]] = None,
        store: Any = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(parent, **kwargs)
        self.title("Session History")
        self.geometry("680x520")
        self.transient(parent)
        self.grab_set()
        self.focus_set()

        self._persistence = persistence
        self._on_resume = on_resume
        self._on_fork = on_fork
        self._store = store
        self._selected_ids: List[str] = []

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self._build_ui()

    def _build_ui(self) -> None:
        session_ids = self._persistence.list_sessions()
        sessions: List[dict] = []
        for sid in session_ids:
            data = self._persistence.load_session(sid)
            if data:
                sessions.append(data)

        # Sort newest first
        sessions.sort(key=lambda d: d.get("exported_at", ""), reverse=True)

        if not sessions:
            self._show_empty_state()
            return

        # Main scroll list
        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scroll.grid(row=0, column=0, sticky="nsew", padx=theme.SP_3, pady=(theme.SP_3, 0))
        scroll.grid_columnconfigure(0, weight=1)

        self._delete_selected_btn = ctk.CTkButton(
            self,
            text="Delete selected",
            fg_color=theme.DANGER_RED,
            state="disabled",
            font=(theme.FONT_UI, theme.TEXT_XS),
            height=32,
            command=self._delete_selected,
        )
        self._delete_selected_btn.grid(row=1, column=0, padx=theme.SP_4, pady=(theme.SP_2, theme.SP_1), sticky="w")

        ctk.CTkButton(
            self,
            text="Clear all history",
            fg_color="transparent",
            text_color=theme.TEXT_MUTED,
            font=(theme.FONT_UI, theme.TEXT_XS),
            height=28,
            command=self._clear_all,
        ).grid(row=2, column=0, padx=theme.SP_4, pady=(0, theme.SP_3), sticky="w")

        self._rows: List[_SessionRow] = []
        for i, data in enumerate(sessions):
            row = _SessionRow(
                scroll,
                data=data,
                on_resume=self._on_resume,
                on_fork=self._on_fork_session,
                on_select=self._on_row_selected,
            )
            row.grid(row=i, column=0, sticky="ew", pady=(0, theme.SP_1))
            self._rows.append(row)

    def _show_empty_state(self) -> None:
        inner = ctk.CTkFrame(self, fg_color="transparent")
        inner.place(relx=0.5, rely=0.5, anchor="center")

        WaveformAnim(inner, width=60, height=48, animate=True).pack(pady=(0, theme.SP_3))

        ctk.CTkLabel(
            inner,
            text="No sessions yet",
            font=(theme.FONT_UI, theme.TEXT_LG, "bold"),
            text_color=theme.TEXT_PRIMARY,
        ).pack()

        ctk.CTkLabel(
            inner,
            text="Your exported playlists will appear here.",
            font=(theme.FONT_UI, theme.TEXT_SM),
            text_color=theme.TEXT_SECONDARY,
        ).pack(pady=(theme.SP_1, theme.SP_3))

        def _go_start() -> None:
            self.destroy()
            if self._store:
                from waveform.app.state import AppScreen
                self._store.set("current_screen", AppScreen.EVENT_SETUP)

        ctk.CTkButton(
            inner,
            text="Start your first event",
            fg_color=theme.ACCENT_VIOLET,
            command=_go_start,
        ).pack()

    def _on_fork_session(self, snapshot: dict) -> None:
        forked = _make_fork_data(snapshot)
        if self._on_fork:
            self._on_fork(forked)
        self.destroy()

    def _on_row_selected(self, session_id: str, selected: bool) -> None:
        if selected:
            if session_id not in self._selected_ids:
                self._selected_ids.append(session_id)
        else:
            self._selected_ids = [sid for sid in self._selected_ids if sid != session_id]

        state = "normal" if self._selected_ids else "disabled"
        try:
            self._delete_selected_btn.configure(state=state)
        except Exception:
            pass

    def _delete_selected(self) -> None:
        for sid in list(self._selected_ids):
            self._persistence.delete_session(sid)
        self.destroy()
        # Reopen
        SessionHistoryDialog(
            self.master,
            persistence=self._persistence,
            on_resume=self._on_resume,
            on_fork=self._on_fork,
            store=self._store,
        )

    def _clear_all(self) -> None:
        try:
            import tkinter.messagebox as mb
            if not mb.askyesno("Clear History", "Delete all session history? This cannot be undone."):
                return
        except Exception:
            pass
        self._persistence.clear_all_sessions()
        self.destroy()


class _SessionRow(ctk.CTkFrame if HAS_CTK else object):  # type: ignore
    def __init__(
        self,
        parent: Any,
        data: dict,
        on_resume: Optional[Callable[[dict], None]] = None,
        on_fork: Optional[Callable[[dict], None]] = None,
        on_select: Optional[Callable[[str, bool], None]] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            parent,
            fg_color=theme.BG_OVERLAY,
            corner_radius=theme.RADIUS_CARD,
            **kwargs,
        )
        self._data = data
        self._on_resume = on_resume
        self._on_fork = on_fork
        self._on_select = on_select
        self._selected_var = ctk.BooleanVar(value=False)

        session_id = data.get("session_id") or data.get("id", "")

        self.grid_columnconfigure(1, weight=1)

        # Checkbox
        cb = ctk.CTkCheckBox(
            self,
            text="",
            variable=self._selected_var,
            command=lambda: on_select(session_id, self._selected_var.get()) if on_select else None,
            width=20,
        )
        cb.grid(row=0, column=0, rowspan=2, padx=(theme.SP_3, theme.SP_2), pady=theme.SP_2)

        # Info block
        info = ctk.CTkFrame(self, fg_color="transparent")
        info.grid(row=0, column=1, rowspan=2, sticky="ew", pady=theme.SP_2)
        info.grid_columnconfigure(0, weight=1)

        name = data.get("event_name", "Unnamed Event")
        ctk.CTkLabel(
            info,
            text=name,
            font=(theme.FONT_UI, theme.TEXT_SM, "bold"),
            text_color=theme.TEXT_PRIMARY,
            anchor="w",
        ).grid(row=0, column=0, sticky="w")

        track_count = data.get("track_count", 0)
        n_blocks = len(data.get("blocks", []))
        event_type = data.get("event_type") or data.get("template_id", "")
        event_type_display = event_type.replace("_", " ").title() if event_type else ""
        date_str = _relative_date(data.get("exported_at", ""))
        meta_parts = [p for p in [event_type_display, f"{track_count} tracks", f"{n_blocks} blocks", date_str] if p]
        ctk.CTkLabel(
            info,
            text="  •  ".join(meta_parts),
            font=(theme.FONT_UI, theme.TEXT_XS),
            text_color=theme.TEXT_MUTED,
            anchor="w",
        ).grid(row=1, column=0, sticky="w")

        # Buttons
        btn_col = ctk.CTkFrame(self, fg_color="transparent")
        btn_col.grid(row=0, column=2, rowspan=2, padx=theme.SP_2, pady=theme.SP_2)

        # Open in Spotify
        playlist_url = data.get("playlist_url") or (data.get("playlist_urls") or [None])[0]
        if playlist_url:
            ctk.CTkButton(
                btn_col,
                text="Open in Spotify",
                font=(theme.FONT_UI, theme.TEXT_XS),
                fg_color=theme.ACCENT_CYAN,
                text_color=theme.BG_BASE,
                width=120,
                height=28,
                command=lambda u=playlist_url: webbrowser.open(u),
            ).pack(pady=(0, theme.SP_1))

        if on_resume:
            ctk.CTkButton(
                btn_col,
                text="Resume",
                font=(theme.FONT_UI, theme.TEXT_XS),
                fg_color=theme.ACCENT_VIOLET,
                width=80,
                height=28,
                command=lambda: on_resume(data),
            ).pack(pady=(0, theme.SP_1))

        if on_fork:
            ctk.CTkButton(
                btn_col,
                text="Fork",
                font=(theme.FONT_UI, theme.TEXT_XS),
                fg_color="transparent",
                border_color=theme.BG_OVERLAY,
                border_width=1,
                text_color=theme.TEXT_MUTED,
                width=60,
                height=28,
                command=lambda: on_fork(data),
            ).pack()
