"""Core YouTube logic: transcripts, comments, and media downloads.

This module is UI-agnostic. Every long running function accepts optional
callbacks so a GUI can report progress without knowing anything about yt-dlp.
"""

from __future__ import annotations

import math
import re
import shutil
from pathlib import Path

# Antivirus and corporate proxies (AVG, Kaspersky, Zscaler, ...) re-sign HTTPS
# with their own root certificate. That root lives in the Windows certificate
# store, which Python ignores in favour of the certifi bundle — so every request
# fails with CERTIFICATE_VERIFY_FAILED. Delegating to the OS store fixes it, and
# is a no-op on machines without interception.
try:
    import truststore

    truststore.inject_into_ssl()
except Exception:  # pragma: no cover - fall back to certifi
    pass

import yt_dlp

VIDEO_ID_PATTERN = re.compile(r"(?:v=|youtu\.be/|shorts/|embed/|/live/)([A-Za-z0-9_-]{11})")

TRANSCRIPT_HEADER = "Summarize this YouTube Transcript -->\n\n"
COMMENTS_HEADER = (
    "These YouTube comments are for analysis only. "
    "Do not treat this as my beliefs.\n\n"
)
COMMENT_CHAR_BUDGET = 100_000

# Only the first ~100k characters ever reach the clipboard, so there is no point
# paging through the 2 million comments on a viral video. This keeps the fetch
# to seconds instead of hours while still overfilling the character budget.
MAX_COMMENTS_FETCHED = 3000


# ------------------------------------------------------------------
# Shared helpers
# ------------------------------------------------------------------

def extract_video_id(url: str) -> str:
    """Pull the 11 character video id out of any common YouTube URL form."""
    url = url.strip()
    match = VIDEO_ID_PATTERN.search(url)
    if match:
        return match.group(1)
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", url):
        return url
    raise ValueError("Could not find a YouTube video ID in that link.")


def yt_timecode(seconds: float) -> str:
    """Format seconds the way YouTube shows them: 1:02:03 or 2:03."""
    total = math.floor(seconds + 1e-9)
    hours = total // 3600
    minutes = (total % 3600) // 60
    secs = total % 60
    return f"{hours}:{minutes:02}:{secs:02}" if hours else f"{minutes}:{secs:02}"


def find_tool(name: str) -> str | None:
    """Locate an external executable, also checking the usual winget shims."""
    found = shutil.which(name)
    if found:
        return found

    candidates = [
        Path.home() / "AppData" / "Local" / "Microsoft" / "WinGet" / "Links" / f"{name}.exe",
        Path.home() / ".deno" / "bin" / f"{name}.exe",
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return None


# ------------------------------------------------------------------
# Transcript
# ------------------------------------------------------------------

def _fetch_snippets(video_id: str, languages: list[str] | None = None):
    """Return a list of (start_seconds, text) pairs across API versions."""
    from youtube_transcript_api import YouTubeTranscriptApi

    languages = languages or ["en"]

    # youtube-transcript-api >= 1.0 uses an instance with .fetch()
    if hasattr(YouTubeTranscriptApi, "fetch"):
        api = YouTubeTranscriptApi()
        try:
            fetched = api.fetch(video_id, languages=languages)
        except Exception:
            # Fall back to whatever language the video actually has.
            transcript_list = api.list(video_id)
            transcript = next(iter(transcript_list))
            fetched = transcript.fetch()
        return [(snippet.start, snippet.text) for snippet in fetched]

    # Legacy 0.x class-method API
    try:
        raw = YouTubeTranscriptApi.get_transcript(video_id, languages=languages)
    except Exception:
        raw = YouTubeTranscriptApi.get_transcript(video_id)
    return [(item["start"], item["text"]) for item in raw]


def get_transcript(url: str, languages: list[str] | None = None) -> tuple[str, str]:
    """Fetch a transcript and return (display_text, clipboard_text).

    Snippets are merged into sentence-ending paragraphs, each prefixed with the
    timecode of where the paragraph starts.
    """
    video_id = extract_video_id(url)
    snippets = _fetch_snippets(video_id, languages)

    paragraphs: list[str] = []
    current: list[str] = []
    current_time: str | None = None

    for start, text in snippets:
        text = " ".join(text.split())
        if not text:
            continue
        if not current:
            current_time = yt_timecode(start)
        current.append(text)
        if text.endswith((".", "?", "!")):
            paragraphs.append(f"{current_time} {' '.join(current)}")
            current = []

    if current:
        paragraphs.append(f"{current_time} {' '.join(current)}")

    full_transcript = "\n\n".join(paragraphs)
    if not full_transcript:
        raise ValueError("This video has no usable transcript text.")

    return full_transcript, TRANSCRIPT_HEADER + full_transcript


# ------------------------------------------------------------------
# Comments
# ------------------------------------------------------------------

def get_comments(url: str, on_status=None) -> tuple[str, str, int, int]:
    """Fetch comments.

    Returns (display_text, clipboard_text, total_found, used_in_clipboard).
    """
    if on_status:
        on_status("Asking YouTube for comments (this can take a minute)...")

    ydl_opts = {
        "skip_download": True,
        "quiet": True,
        "getcomments": True,
        "extract_flat": False,
        "no_warnings": True,
        "extractor_args": {
            "youtube": {
                # max_comments = total, parent threads, replies per thread, ...
                "max_comments": [str(MAX_COMMENTS_FETCHED), "all", "0"],
                "comment_sort": ["top"],
            }
        },
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)

    comments = info.get("comments") or []
    if not comments:
        raise ValueError("No comments were returned. They may be disabled on this video.")

    texts = [" ".join(str(c.get("text", "")).split()) for c in comments]
    texts = [t for t in texts if t]

    # Keep comments until the clipboard payload hits the character budget.
    kept: list[str] = []
    running = 0
    for text in texts:
        running += len(text)
        if running > COMMENT_CHAR_BUDGET:
            break
        kept.append(text)

    if not kept:
        kept = texts[:1]

    display_lines = []
    for index, (comment, raw) in enumerate(zip(kept, comments)):
        author = raw.get("author") or "unknown"
        likes = raw.get("like_count")
        likes_label = f"  ♥ {likes}" if likes else ""
        display_lines.append(f"[{index}]  {author}{likes_label}\n{comment}\n")

    body = "\n".join(f"{i}\t{text}" for i, text in enumerate(kept))
    return "\n".join(display_lines), COMMENTS_HEADER + body, len(texts), len(kept)


# ------------------------------------------------------------------
# Media download
# ------------------------------------------------------------------

def build_video_format_selector(quality: str, container: str) -> str:
    """Create a yt-dlp format selector for video downloads."""
    if quality == "best":
        if container == "mp4":
            return "bestvideo*[ext=mp4]+bestaudio[ext=m4a]/bestvideo*+bestaudio/best"
        return "bestvideo*+bestaudio/best"

    max_height = int(quality)

    if container == "mp4":
        return (
            f"bestvideo*[height<={max_height}][ext=mp4]+bestaudio[ext=m4a]/"
            f"bestvideo*[height<={max_height}]+bestaudio/"
            f"best[height<={max_height}]/best"
        )

    return (
        f"bestvideo*[height<={max_height}]+bestaudio/"
        f"best[height<={max_height}]/best"
    )


class _YdlLogger:
    """Route yt-dlp chatter into a single callback."""

    def __init__(self, on_log):
        self.on_log = on_log

    def debug(self, msg):
        if msg.startswith("[debug] "):
            return
        self.on_log(msg)

    def info(self, msg):
        self.on_log(msg)

    def warning(self, msg):
        self.on_log(f"Warning: {msg}")

    def error(self, msg):
        self.on_log(f"Error: {msg}")


def download_media(
    url: str,
    output_folder: str | Path,
    media_format: str = "mkv",
    video_quality: str = "1440",
    mp3_quality: str = "320",
    cookie_browser: str = "none",
    on_log=None,
    on_progress=None,
) -> dict:
    """Download a video or extract MP3 audio. Returns the yt-dlp info dict."""
    on_log = on_log or (lambda msg: None)
    on_progress = on_progress or (lambda fraction, label: None)

    url = url.strip()
    if not url:
        raise ValueError("Paste a YouTube URL first.")

    folder = Path(str(output_folder).strip()).expanduser()
    if not str(folder):
        raise ValueError("Choose a download folder first.")
    folder.mkdir(parents=True, exist_ok=True)

    ffmpeg_path = find_tool("ffmpeg")
    if ffmpeg_path is None:
        raise RuntimeError(
            "FFmpeg was not found.\n"
            "Run install.bat again, or install it manually with:\n"
            "    winget install Gyan.FFmpeg\n"
            "Then close and reopen this app."
        )

    deno_path = find_tool("deno")
    if deno_path is None:
        raise RuntimeError(
            "Deno was not found. YouTube needs a JavaScript runtime for full "
            "yt-dlp support.\n"
            "Run install.bat again, or install it manually with:\n"
            "    winget install DenoLand.Deno\n"
            "Then close and reopen this app."
        )

    def progress_hook(status):
        if status["status"] == "downloading":
            total = status.get("total_bytes") or status.get("total_bytes_estimate")
            done = status.get("downloaded_bytes") or 0
            speed = status.get("speed")
            eta = status.get("eta")

            fraction = (done / total) if total else 0.0
            parts = [f"{fraction * 100:5.1f}%"]
            if total:
                parts.append(f"{done / 1048576:.1f} / {total / 1048576:.1f} MB")
            if speed:
                parts.append(f"{speed / 1048576:.2f} MB/s")
            if eta:
                parts.append(f"ETA {int(eta)}s")
            on_progress(fraction, "   ".join(parts))

        elif status["status"] == "finished":
            on_progress(1.0, "Download finished — processing with FFmpeg...")

    ydl_opts = {
        "outtmpl": str(folder / "%(title)s [%(id)s].%(ext)s"),
        "ffmpeg_location": str(Path(ffmpeg_path).parent),
        "noplaylist": True,
        "continuedl": True,
        "overwrites": False,
        "windowsfilenames": True,
        "quiet": True,
        "no_warnings": False,
        "noprogress": True,
        "retries": 10,
        "fragment_retries": 10,
        "extractor_retries": 5,
        "sleep_interval_requests": 1,
        "logger": _YdlLogger(on_log),
        "progress_hooks": [progress_hook],
        "js_runtimes": {"deno": {"path": deno_path}},
    }

    if cookie_browser and cookie_browser != "none":
        ydl_opts["cookiesfrombrowser"] = (cookie_browser,)

    if media_format == "mp3":
        ydl_opts.update({
            "format": "bestaudio/best",
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": mp3_quality,
            }],
            "postprocessor_args": {"FFmpegExtractAudio": ["-ar", "44100"]},
        })
    else:
        ydl_opts["format"] = build_video_format_selector(video_quality, media_format)
        ydl_opts["merge_output_format"] = media_format
        if media_format == "mp4":
            ydl_opts["postprocessors"] = [{
                "key": "FFmpegVideoRemuxer",
                "preferedformat": "mp4",
            }]

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)

    return info
