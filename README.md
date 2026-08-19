# YouTube Toolkit

A desktop app for pulling transcripts, comments, and media out of any YouTube
link. Built from `YouTube_Transcript_Comments_Video_Audio_Downloader.ipynb`.

![tabs: Transcript, Comments, Media](docs/screenshot.png)

## Setup

Double-click **`install.bat`** once. It creates a private Python environment in
`.venv`, installs the Python packages, installs FFmpeg and Deno via winget, and
sets up the PO token provider (see below).

Then double-click **`run.bat`** to start the app.

Node.js is needed for the PO token provider. If it is missing, install it with
`winget install OpenJS.NodeJS` and rerun `install.bat`.

## Using it

### Transcript tab
Paste a link, press **Enter**. The transcript is shown as timestamped
paragraphs and copied to your clipboard, prefixed with
`Summarize this YouTube Transcript -->`.

### Comments tab
Paste a link, press **Enter**. Fetches the top 3,000 comments, trims the
clipboard payload to 100,000 characters, and copies it with an
analysis-only preamble. Takes 20–60 seconds.

### Media tab
Paste a link, choose your options, then click **Download** (or press Enter in
the link box).

| Option | Choices |
| --- | --- |
| Format | MKV, MP4, MP3 |
| Quality | 720p / 1080p / 2K / 4K / Best — or 128–320 kbps for MP3 |
| Cookies | None, Chrome, Edge, Firefox, Brave |
| Save to | Type a path or click **Browse Folder** |

Picking MP3 swaps the quality row to bitrates automatically. The chosen folder
is remembered in `settings.json`.

## Files

| File | Purpose |
| --- | --- |
| `install.bat` | One-time setup |
| `run.bat` | Starts the app |
| `app.py` | The window, tabs, and widgets |
| `core.py` | Transcript, comment, and download logic (no UI) |
| `requirements.txt` | Python dependencies |
| `potprovider/` | PO token provider, fetched by `install.bat` (not in git) |

## Troubleshooting

**"FFmpeg was not found" / "Deno was not found"** — rerun `install.bat`. If it
still fails, sign out of Windows and back in so the new PATH entries register.

**HTTP 403 on a download** — YouTube is refusing the stream, which is not a bug
in the app. In order of likelihood:

1. **Rate limiting.** Too many requests from your connection in a short window
   makes YouTube reject *every* stream, including 360p. It clears on its own;
   wait 30–60 minutes.
2. **Missing PO token.** YouTube requires a "GVS PO token" before it will serve
   the adaptive streams that every quality above 360p uses, and yt-dlp cannot
   mint one by itself. `install.bat` sets up the
   [bgutil provider](https://github.com/Brainicism/bgutil-ytdlp-pot-provider)
   for this. If `potprovider/node_modules` is missing, rerun `install.bat`.
3. **SABR-only rollout.** For some videos YouTube now serves only its SABR
   protocol, which yt-dlp cannot download
   ([issue #12482](https://github.com/yt-dlp/yt-dlp/issues/12482)). Nothing in
   this app works around that.

If it outlasts an hour, update yt-dlp:

```bash
.venv\Scripts\python.exe -m pip install -U "yt-dlp[default]"
```

**The Cookies dropdown does nothing on Chrome or Edge** — Chromium's app-bound
encryption blocks yt-dlp from reading their cookie stores on Windows
([issue #10927](https://github.com/yt-dlp/yt-dlp/issues/10927)). Only Firefox
cookies are usable. The PO token provider is the real fix, not cookies.

**`CERTIFICATE_VERIFY_FAILED`** — antivirus and corporate proxies re-sign HTTPS
traffic with their own root certificate. `core.py` handles this by routing
verification through the Windows certificate store via `truststore`.

**The app does not open** — check `error.log` next to `app.py`. `run.bat` uses
`pythonw.exe`, so there is no console window to read errors from.
