"""YouTube Toolkit — transcripts, comments, and media downloads in one window.

Run it with run.bat, or directly:  python app.py
"""

from __future__ import annotations

import queue
import sys
import threading
import traceback
from pathlib import Path
from tkinter import filedialog

try:
    import customtkinter as ctk
except ImportError:  # pragma: no cover - friendly message instead of a traceback
    import tkinter.messagebox as mb

    mb.showerror(
        "Missing packages",
        "customtkinter is not installed.\n\nRun install.bat once, then start "
        "the app again with run.bat.",
    )
    sys.exit(1)

import pyperclip

import core

APP_NAME = "YouTube Toolkit"
SETTINGS_FILE = Path(__file__).with_name("settings.json")

# ------------------------------------------------------------------
# Palette
# ------------------------------------------------------------------

BG = "#0D0E12"
CARD = "#15171F"
CARD_SOFT = "#1C1F2A"
STROKE = "#262A38"
ACCENT = "#FF3B5C"
ACCENT_HOVER = "#FF5F7B"
ACCENT_DIM = "#3A1620"
TEXT = "#E9EBF2"
MUTED = "#868C9E"
GREEN = "#31D07B"
AMBER = "#FFB020"
RED = "#FF5A5A"

FONT_UI = "Segoe UI"
FONT_MONO = "Cascadia Mono"


def ui(size=13, weight="normal"):
    return ctk.CTkFont(family=FONT_UI, size=size, weight=weight)


def mono(size=12):
    return ctk.CTkFont(family=FONT_MONO, size=size)


# ------------------------------------------------------------------
# Reusable pieces
# ------------------------------------------------------------------

class Card(ctk.CTkFrame):
    """A padded panel with a hairline border."""

    def __init__(self, master, **kwargs):
        kwargs.setdefault("fg_color", CARD)
        kwargs.setdefault("corner_radius", 14)
        kwargs.setdefault("border_width", 1)
        kwargs.setdefault("border_color", STROKE)
        super().__init__(master, **kwargs)


class StatusLine(ctk.CTkFrame):
    """Dot + message, used as the feedback strip on every tab."""

    def __init__(self, master):
        super().__init__(master, fg_color="transparent")
        self.dot = ctk.CTkLabel(self, text="●", font=ui(13), text_color=MUTED, width=14)
        self.dot.pack(side="left")
        self.message = ctk.CTkLabel(
            self, text="Ready.", font=ui(12), text_color=MUTED, anchor="w", justify="left"
        )
        self.message.pack(side="left", padx=(6, 0))

    def set(self, text: str, tone: str = "idle"):
        colors = {"idle": MUTED, "busy": AMBER, "ok": GREEN, "error": RED}
        color = colors.get(tone, MUTED)
        self.dot.configure(text_color=color)
        self.message.configure(text=text, text_color=TEXT if tone != "idle" else MUTED)


class OutputBox(ctk.CTkTextbox):
    """Read-only monospace text area."""

    def __init__(self, master, **kwargs):
        kwargs.setdefault("fg_color", "#0A0B0F")
        kwargs.setdefault("border_color", STROKE)
        kwargs.setdefault("border_width", 1)
        kwargs.setdefault("corner_radius", 12)
        kwargs.setdefault("text_color", "#C9CEDC")
        kwargs.setdefault("font", mono(12))
        kwargs.setdefault("wrap", "word")
        super().__init__(master, **kwargs)
        self.configure(state="disabled")

    def set_text(self, text: str):
        self.configure(state="normal")
        self.delete("1.0", "end")
        self.insert("1.0", text)
        self.configure(state="disabled")

    def append(self, text: str):
        self.configure(state="normal")
        self.insert("end", text)
        self.see("end")
        self.configure(state="disabled")

    def clear(self):
        self.set_text("")


def make_entry(master, placeholder: str) -> ctk.CTkEntry:
    entry = ctk.CTkEntry(
        master,
        placeholder_text=placeholder,
        height=44,
        corner_radius=10,
        border_width=1,
        border_color=STROKE,
        fg_color=CARD_SOFT,
        text_color=TEXT,
        placeholder_text_color=MUTED,
        font=ui(13),
    )
    # Light the border while typing so the active field is obvious.
    entry.bind("<FocusIn>", lambda _e: entry.configure(border_color=ACCENT))
    entry.bind("<FocusOut>", lambda _e: entry.configure(border_color=STROKE))
    return entry


def make_label(master, text, size=12, color=MUTED, weight="normal"):
    return ctk.CTkLabel(master, text=text, font=ui(size, weight), text_color=color, anchor="w")


def make_button(master, text, command, kind="accent", width=130):
    styles = {
        "accent": dict(fg_color=ACCENT, hover_color=ACCENT_HOVER, text_color="#FFFFFF"),
        "ghost": dict(fg_color=CARD_SOFT, hover_color=STROKE, text_color=TEXT),
    }
    return ctk.CTkButton(
        master,
        text=text,
        command=command,
        height=40,
        width=width,
        corner_radius=10,
        font=ui(13, "bold"),
        **styles[kind],
    )


def make_segmented(master, values, command=None):
    seg = ctk.CTkSegmentedButton(
        master,
        values=values,
        command=command,
        height=38,
        corner_radius=9,
        font=ui(12, "bold"),
        fg_color=CARD_SOFT,
        selected_color=ACCENT,
        selected_hover_color=ACCENT_HOVER,
        unselected_color=CARD_SOFT,
        unselected_hover_color=STROKE,
        text_color=TEXT,
        text_color_disabled=MUTED,
    )
    seg.set(values[0])
    return seg


# ------------------------------------------------------------------
# Tabs
# ------------------------------------------------------------------

class FetchTab:
    """Shared skeleton for the Transcript and Comments tabs."""

    hint = ""
    empty_text = ""
    action_verb = "Fetch"

    def __init__(self, app, parent):
        self.app = app
        self.clipboard_payload = ""

        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(1, weight=1)

        top = Card(parent)
        top.grid(row=0, column=0, sticky="ew", padx=2, pady=(2, 12))
        top.grid_columnconfigure(0, weight=1)

        make_label(top, "YOUTUBE LINK", size=11, weight="bold").grid(
            row=0, column=0, sticky="w", padx=18, pady=(16, 6)
        )

        row = ctk.CTkFrame(top, fg_color="transparent")
        row.grid(row=1, column=0, columnspan=2, sticky="ew", padx=18)
        row.grid_columnconfigure(0, weight=1)

        self.entry = make_entry(row, "Paste a YouTube URL and press Enter")
        self.entry.grid(row=0, column=0, sticky="ew")
        self.entry.bind("<Return>", lambda _e: self.run())

        self.go_button = make_button(row, self.action_verb, self.run, width=118)
        self.go_button.grid(row=0, column=1, padx=(10, 0))

        self.copy_button = make_button(row, "Copy", self.copy_again, kind="ghost", width=92)
        self.copy_button.grid(row=0, column=2, padx=(8, 0))
        self.copy_button.configure(state="disabled")

        make_label(top, self.hint, size=11).grid(
            row=2, column=0, sticky="w", padx=18, pady=(10, 0)
        )

        self.status = StatusLine(top)
        self.status.grid(row=3, column=0, sticky="w", padx=16, pady=(10, 16))

        self.output = OutputBox(parent)
        self.output.grid(row=1, column=0, sticky="nsew", padx=2, pady=(0, 2))
        self.output.set_text(self.empty_text)

    # -- overridden by subclasses -------------------------------------

    def work(self, url):
        raise NotImplementedError

    # -- shared plumbing ----------------------------------------------

    def set_busy(self, busy: bool):
        state = "disabled" if busy else "normal"
        self.entry.configure(state=state)
        self.go_button.configure(state=state, text="Working..." if busy else self.action_verb)

    def run(self):
        url = self.entry.get().strip()
        if not url:
            self.status.set("Paste a YouTube link first.", "error")
            return

        self.set_busy(True)
        self.copy_button.configure(state="disabled")
        self.status.set("Working...", "busy")
        self.output.set_text("")

        def worker():
            try:
                display, clipboard, summary = self.work(url)
                self.app.post(self.on_success, display, clipboard, summary)
            except Exception as error:  # surfaced in the UI, not the console
                self.app.post(self.on_failure, error)

        threading.Thread(target=worker, daemon=True).start()

    def on_success(self, display, clipboard, summary):
        self.clipboard_payload = clipboard
        self.output.set_text(display)
        copied = self.copy_to_clipboard(clipboard)
        self.copy_button.configure(state="normal")
        note = "Copied to clipboard." if copied else "Clipboard copy failed — use the Copy button."
        self.status.set(f"{summary}  {note}", "ok" if copied else "error")
        self.set_busy(False)

    def on_failure(self, error):
        self.output.set_text(f"{type(error).__name__}: {error}\n\n{traceback.format_exc()}")
        self.status.set(str(error).splitlines()[0] if str(error) else "Something went wrong.", "error")
        self.set_busy(False)

    def copy_to_clipboard(self, text: str) -> bool:
        try:
            pyperclip.copy(text)
            return True
        except Exception:
            try:
                self.app.clipboard_clear()
                self.app.clipboard_append(text)
                self.app.update()
                return True
            except Exception:
                return False

    def copy_again(self):
        if not self.clipboard_payload:
            return
        if self.copy_to_clipboard(self.clipboard_payload):
            self.status.set("Copied to clipboard again.", "ok")
        else:
            self.status.set("Clipboard is not available right now.", "error")


class TranscriptTab(FetchTab):
    hint = "Timestamped paragraphs, prefixed with a summarize prompt on the clipboard."
    empty_text = "Paste a link above and press Enter.\n\nThe transcript appears here and is copied to your clipboard automatically."
    action_verb = "Get Transcript"

    def work(self, url):
        display, clipboard = core.get_transcript(url)
        words = len(display.split())
        return display, clipboard, f"Transcript ready — {words:,} words."


class CommentsTab(FetchTab):
    hint = (
        f"Top {core.MAX_COMMENTS_FETCHED:,} comments, trimmed to "
        f"{core.COMMENT_CHAR_BUDGET:,} characters so they fit in a chat window."
    )
    empty_text = "Paste a link above and press Enter.\n\nComments appear here and the text is copied to your clipboard automatically.\n\nThis usually takes 20-60 seconds."
    action_verb = "Get Comments"

    def work(self, url):
        display, clipboard, total, used = core.get_comments(url)
        summary = f"{total:,} comments fetched, {used:,} copied."
        return display, clipboard, summary


class MediaTab:
    VIDEO_QUALITIES = ["720p", "1080p", "2K", "4K", "Best"]
    VIDEO_QUALITY_MAP = {"720p": "720", "1080p": "1080", "2K": "1440", "4K": "2160", "Best": "best"}
    AUDIO_QUALITIES = ["128 kbps", "192 kbps", "256 kbps", "320 kbps"]
    AUDIO_QUALITY_MAP = {"128 kbps": "128", "192 kbps": "192", "256 kbps": "256", "320 kbps": "320"}
    COOKIE_OPTIONS = ["No browser cookies", "Chrome", "Edge", "Firefox", "Brave"]
    COOKIE_MAP = {
        "No browser cookies": "none",
        "Chrome": "chrome",
        "Edge": "edge",
        "Firefox": "firefox",
        "Brave": "brave",
    }

    def __init__(self, app, parent):
        self.app = app
        self.busy = False

        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(1, weight=1)

        card = Card(parent)
        card.grid(row=0, column=0, sticky="ew", padx=2, pady=(2, 12))
        card.grid_columnconfigure(0, weight=1)

        pad = 18

        # --- URL -----------------------------------------------------
        make_label(card, "YOUTUBE LINK", size=11, weight="bold").grid(
            row=0, column=0, sticky="w", padx=pad, pady=(16, 6)
        )
        self.entry = make_entry(card, "Paste a YouTube URL, then set the options below")
        self.entry.grid(row=1, column=0, sticky="ew", padx=pad)
        self.entry.bind("<Return>", lambda _e: self.start_download())

        # --- Format + quality ---------------------------------------
        options = ctk.CTkFrame(card, fg_color="transparent")
        options.grid(row=2, column=0, sticky="ew", padx=pad, pady=(18, 0))
        options.grid_columnconfigure(1, weight=1)

        make_label(options, "FORMAT", size=11, weight="bold").grid(row=0, column=0, sticky="w")
        make_label(options, "QUALITY", size=11, weight="bold").grid(
            row=0, column=1, sticky="w", padx=(18, 0)
        )

        self.format_seg = make_segmented(options, ["MKV", "MP4", "MP3"], self.on_format_change)
        self.format_seg.grid(row=1, column=0, sticky="w", pady=(6, 0))

        self.quality_seg = make_segmented(options, self.VIDEO_QUALITIES)
        self.quality_seg.set("2K")
        self.quality_seg.grid(row=1, column=1, sticky="w", padx=(18, 0), pady=(6, 0))

        # --- Folder --------------------------------------------------
        make_label(card, "SAVE TO", size=11, weight="bold").grid(
            row=3, column=0, sticky="w", padx=pad, pady=(18, 6)
        )
        folder_row = ctk.CTkFrame(card, fg_color="transparent")
        folder_row.grid(row=4, column=0, sticky="ew", padx=pad)
        folder_row.grid_columnconfigure(0, weight=1)

        self.folder_entry = make_entry(folder_row, "Download folder")
        self.folder_entry.grid(row=0, column=0, sticky="ew")
        self.folder_entry.insert(0, self.app.settings.get("folder", str(Path.home() / "Downloads" / "YouTube")))

        self.browse_button = make_button(
            folder_row, "Browse Folder", self.browse_folder, kind="ghost", width=140
        )
        self.browse_button.grid(row=0, column=1, padx=(10, 0))

        # --- Cookies + download -------------------------------------
        bottom = ctk.CTkFrame(card, fg_color="transparent")
        bottom.grid(row=5, column=0, sticky="ew", padx=pad, pady=(18, 0))
        bottom.grid_columnconfigure(1, weight=1)

        cookie_col = ctk.CTkFrame(bottom, fg_color="transparent")
        cookie_col.grid(row=0, column=0, sticky="w")
        make_label(cookie_col, "COOKIES", size=11, weight="bold").pack(anchor="w")
        self.cookie_menu = ctk.CTkOptionMenu(
            cookie_col,
            values=self.COOKIE_OPTIONS,
            width=210,
            height=38,
            corner_radius=9,
            font=ui(12),
            fg_color=CARD_SOFT,
            button_color=STROKE,
            button_hover_color=ACCENT,
            text_color=TEXT,
            dropdown_fg_color=CARD_SOFT,
            dropdown_hover_color=ACCENT_DIM,
            dropdown_text_color=TEXT,
        )
        self.cookie_menu.set(self.COOKIE_OPTIONS[0])
        self.cookie_menu.pack(anchor="w", pady=(6, 0))

        self.download_button = ctk.CTkButton(
            bottom,
            text="⬇   Download Video",
            command=self.start_download,
            height=52,
            width=230,
            corner_radius=11,
            font=ui(15, "bold"),
            fg_color=ACCENT,
            hover_color=ACCENT_HOVER,
            text_color="#FFFFFF",
        )
        self.download_button.grid(row=0, column=2, sticky="e", pady=(20, 0))

        # --- Progress -----------------------------------------------
        self.progress = ctk.CTkProgressBar(
            card, height=8, corner_radius=4, progress_color=ACCENT, fg_color=CARD_SOFT
        )
        self.progress.grid(row=6, column=0, sticky="ew", padx=pad, pady=(20, 0))
        self.progress.set(0)

        self.status = StatusLine(card)
        self.status.grid(row=7, column=0, sticky="w", padx=pad - 2, pady=(10, 16))

        self.log = OutputBox(parent)
        self.log.grid(row=1, column=0, sticky="nsew", padx=2, pady=(0, 2))
        self.log.set_text(
            "Set your options above, then click Download.\n\n"
            "MKV keeps the highest quality streams as-is. MP4 is the most "
            "compatible. MP3 extracts audio only.\n\n"
            "If YouTube returns a 403, pick your browser under Cookies and keep "
            "that browser closed while downloading."
        )

    # -- options --------------------------------------------------------

    def on_format_change(self, value):
        if value == "MP3":
            self.quality_seg.configure(values=self.AUDIO_QUALITIES)
            self.quality_seg.set("320 kbps")
            self.download_button.configure(text="⬇   Download MP3")
        else:
            current = self.quality_seg.get()
            self.quality_seg.configure(values=self.VIDEO_QUALITIES)
            self.quality_seg.set(current if current in self.VIDEO_QUALITIES else "2K")
            self.download_button.configure(text="⬇   Download Video")

    def browse_folder(self):
        current = Path(self.folder_entry.get().strip() or Path.home() / "Downloads")
        initial = current if current.exists() else Path.home() / "Downloads"
        selected = filedialog.askdirectory(
            parent=self.app,
            title="Select the download folder",
            initialdir=str(initial),
            mustexist=True,
        )
        if selected:
            selected = str(Path(selected))
            self.folder_entry.delete(0, "end")
            self.folder_entry.insert(0, selected)
            self.app.settings["folder"] = selected
            self.app.save_settings()
            self.status.set(f"Saving to {selected}", "ok")

    # -- download -------------------------------------------------------

    def set_busy(self, busy: bool):
        self.busy = busy
        state = "disabled" if busy else "normal"
        for widget in (
            self.entry,
            self.browse_button,
            self.folder_entry,
            self.format_seg,
            self.quality_seg,
            self.cookie_menu,
        ):
            widget.configure(state=state)
        self.download_button.configure(
            state=state,
            text="Downloading..." if busy else (
                "⬇   Download MP3" if self.format_seg.get() == "MP3" else "⬇   Download Video"
            ),
        )

    def start_download(self):
        if self.busy:
            return

        url = self.entry.get().strip()
        if not url:
            self.status.set("Paste a YouTube link first.", "error")
            return

        folder = self.folder_entry.get().strip()
        if not folder:
            self.status.set("Choose a download folder first.", "error")
            return

        media_format = self.format_seg.get().lower()
        quality_label = self.quality_seg.get()
        video_quality = self.VIDEO_QUALITY_MAP.get(quality_label, "1440")
        mp3_quality = self.AUDIO_QUALITY_MAP.get(quality_label, "320")
        cookie_browser = self.COOKIE_MAP.get(self.cookie_menu.get(), "none")

        self.app.settings["folder"] = folder
        self.app.save_settings()

        self.set_busy(True)
        self.progress.set(0)
        self.status.set("Starting download...", "busy")
        self.log.set_text("")

        def on_log(message):
            self.app.post(self.log.append, message.rstrip() + "\n")

        def on_progress(fraction, label):
            self.app.post(self._update_progress, fraction, label)

        def worker():
            try:
                info = core.download_media(
                    url=url,
                    output_folder=folder,
                    media_format=media_format,
                    video_quality=video_quality,
                    mp3_quality=mp3_quality,
                    cookie_browser=cookie_browser,
                    on_log=on_log,
                    on_progress=on_progress,
                )
                self.app.post(self.on_done, info, folder, media_format, quality_label)
            except Exception as error:
                self.app.post(self.on_error, error)

        threading.Thread(target=worker, daemon=True).start()

    def _update_progress(self, fraction, label):
        self.progress.set(max(0.0, min(1.0, fraction)))
        self.status.set(label, "busy")

    def on_done(self, info, folder, media_format, quality_label):
        title = info.get("title", "Unknown title")
        self.progress.set(1.0)
        self.status.set(f"Saved “{title}” to {folder}", "ok")
        self.log.append(
            f"\n{'=' * 60}\nDownload complete\n"
            f"Title:  {title}\n"
            f"Format: {media_format.upper()} — {quality_label}\n"
            f"Folder: {Path(folder).resolve()}\n"
        )
        self.entry.delete(0, "end")
        self.set_busy(False)

    def on_error(self, error):
        self.progress.set(0)
        first_line = str(error).splitlines()[0] if str(error) else "Download failed."
        self.status.set(first_line, "error")
        self.log.append(f"\n{'=' * 60}\n{type(error).__name__}: {error}\n")
        self.set_busy(False)


# ------------------------------------------------------------------
# Application shell
# ------------------------------------------------------------------

class App(ctk.CTk):
    def __init__(self):
        super().__init__(fg_color=BG)

        self.title(APP_NAME)
        self.geometry("1020x820")
        self.minsize(900, 700)
        self._ui_queue: queue.Queue = queue.Queue()
        self.settings = self.load_settings()

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._build_header()
        self._build_tabs()

        self.after(60, self._drain_queue)

    # -- header ---------------------------------------------------------

    def _build_header(self):
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=26, pady=(22, 14))
        header.grid_columnconfigure(1, weight=1)

        badge = ctk.CTkLabel(
            header,
            text="▶",
            width=46,
            height=46,
            corner_radius=13,
            fg_color=ACCENT,
            text_color="#FFFFFF",
            font=ctk.CTkFont(family=FONT_UI, size=19, weight="bold"),
        )
        badge.grid(row=0, column=0, rowspan=2, sticky="w")

        ctk.CTkLabel(
            header,
            text=APP_NAME,
            font=ui(21, "bold"),
            text_color=TEXT,
            anchor="w",
        ).grid(row=0, column=1, sticky="sw", padx=(14, 0))

        ctk.CTkLabel(
            header,
            text="Transcripts, comments, and downloads from any YouTube link",
            font=ui(12),
            text_color=MUTED,
            anchor="w",
        ).grid(row=1, column=1, sticky="nw", padx=(14, 0))

    # -- tabs -----------------------------------------------------------

    def _build_tabs(self):
        self.tabs = ctk.CTkTabview(
            self,
            fg_color=BG,
            corner_radius=0,
            border_width=0,
            segmented_button_fg_color=CARD,
            segmented_button_selected_color=ACCENT,
            segmented_button_selected_hover_color=ACCENT_HOVER,
            segmented_button_unselected_color=CARD,
            segmented_button_unselected_hover_color=CARD_SOFT,
            text_color=TEXT,
            anchor="w",
        )
        self.tabs.grid(row=1, column=0, sticky="nsew", padx=22, pady=(0, 18))
        self.tabs._segmented_button.configure(font=ui(13, "bold"), height=40, corner_radius=10)

        # Row weights are set by each tab class: the options card stays its
        # natural height and the output box below it takes the leftover space.
        for name in ("  Transcript  ", "  Comments  ", "  Media  "):
            self.tabs.add(name)
            self.tabs.tab(name).grid_columnconfigure(0, weight=1)

        self.transcript_tab = TranscriptTab(self, self.tabs.tab("  Transcript  "))
        self.comments_tab = CommentsTab(self, self.tabs.tab("  Comments  "))
        self.media_tab = MediaTab(self, self.tabs.tab("  Media  "))

        self.tabs.set("  Transcript  ")

    # -- thread-safe UI updates -----------------------------------------

    def post(self, func, *args):
        """Queue a callable to run on the Tk main thread."""
        self._ui_queue.put((func, args))

    def _drain_queue(self):
        while True:
            try:
                func, args = self._ui_queue.get_nowait()
            except queue.Empty:
                break
            try:
                func(*args)
            except Exception:
                traceback.print_exc()
        self.after(60, self._drain_queue)

    # -- settings --------------------------------------------------------

    def load_settings(self) -> dict:
        import json

        try:
            return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def save_settings(self):
        import json

        try:
            SETTINGS_FILE.write_text(json.dumps(self.settings, indent=2), encoding="utf-8")
        except Exception:
            pass


def _report_crash(message: str):
    """run.bat starts the app with pythonw, so failures need a visible home."""
    log = Path(__file__).with_name("error.log")
    try:
        log.write_text(message, encoding="utf-8")
    except Exception:
        pass
    try:
        import tkinter.messagebox as mb

        mb.showerror(APP_NAME, f"{message[:1500]}\n\nFull details: {log}")
    except Exception:
        print(message, file=sys.stderr)


def main():
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("dark-blue")
    try:
        app = App()
        app.report_callback_exception = lambda *a: traceback.print_exc()
        app.mainloop()
    except Exception:
        _report_crash(traceback.format_exc())
        sys.exit(1)


if __name__ == "__main__":
    main()
