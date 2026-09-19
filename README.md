# Playlist FLAC Manager

A local Windows app that takes a track list (pasted text, CSV/TXT, or a
Spotify playlist URL), normalizes it, searches a Soulseek network through
your own [slskd](https://github.com/slskd/slskd) instance, scores the
results, and — only after you approve a specific source — hands the
download off to slskd and organizes the verified FLAC into a tidy library.

**Spotify is used only to read track metadata** (artist, title, album,
album artist, release year, track/disc number, ISRC, duration, Spotify
URL). This app never fetches, streams, decrypts, or caches any Spotify
audio. See `ARCHITECTURE.md` for the full design and `IMPLEMENTATION_PLAN.md`
for how the MVP was built.

Every download requires an explicit, human approval — there is no
unattended "download everything" mode.

## Prerequisites

1. **Python 3.12+** on Windows 11 (or Linux/macOS for development).
2. **[slskd](https://github.com/slskd/slskd)** already installed, configured
   with your own Soulseek account, and running (locally or on your
   network). You need:
   - Its base URL (e.g. `http://localhost:5030`)
   - Either an API key (`web.authentication.api_keys` in slskd's config -
     recommended) or its username/password
   - The local filesystem path slskd writes completed downloads to
3. *(Optional)* A [Spotify app](https://developer.spotify.com/dashboard)
   (Client ID + secret) if you want to import playlists directly instead of
   pasting text. This app uses the Client Credentials flow, which works for
   public/unlisted playlists.
4. *(Optional but recommended)* [FFmpeg](https://ffmpeg.org/download.html)
   on your `PATH`, so FLAC verification can use `ffprobe`. Without it,
   verification falls back to `mutagen` only (still functional, slightly
   less detailed).

## Setup (Windows)

1. Double-click `run_windows.bat` (or run `run_windows.ps1` in PowerShell).
   This creates a virtual environment, installs dependencies, copies
   `.env.example` to `.env` on first run, and starts the app at
   `http://127.0.0.1:8000`.
2. Edit the newly created `.env` with your slskd base URL/API key, your
   slskd download directory, and (optionally) your Spotify credentials.
   Restart the app after editing `.env`.
3. Open `http://127.0.0.1:8000` in your browser.

### Setup (manual / Linux / macOS, for development)

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate       # .venv\Scripts\activate on Windows
pip install -r requirements-dev.txt
cp ../.env.example ../.env      # then edit it
uvicorn app.main:app --reload
```

### Storing secrets

Two options, both supported:

- **`.env` file** (simplest): fill in `SLSKD_API_KEY` / `SPOTIFY_CLIENT_SECRET`.
  `.env` is git-ignored.
- **Windows Credential Manager**: leave those `.env` values blank and store
  them via `keyring` instead:
  ```python
  from app.secrets_store import set_secret
  set_secret("slskd_api_key", "...")
  set_secret("spotify_client_secret", "...")
  ```
  The app checks the credential store automatically when an env var is
  missing.

Secrets are never logged, written to the database, or included in the log
panel (messages that look like they contain a credential are withheld).

## Using it

1. Paste a track list (`Artist - Track`, one per line — also accepts `—`,
   `–`, `|`, `/` as separators), or paste a Spotify playlist URL, or upload
   a CSV/TXT file. Click **ANALYZE**.
2. The app parses, normalizes, and — in the background, at a configurable
   rate — searches each track on Soulseek via slskd. Watch the table and
   the log panel on the right for progress (`SEARCHING` → `MATCHED` /
   `REVIEW_REQUIRED` / `NOT_FOUND`).
3. Click a row to see its candidates, each with a separate **MATCH**
   score (is this the right track/version?) and **SOURCE** score (is this a
   good peer to download from?). Candidates whose version looks wrong
   (remix/live/instrumental/radio edit/cover/karaoke when you asked for the
   plain track, or an ambiguous top match) are flagged for review rather
   than auto-selected.
4. Click **Approve & download** on the candidate you want. This is the
   only action that ever sends a request to slskd to start a transfer.
5. The **Downloads** tab shows live transfer state; once a file completes,
   it's automatically verified (FLAC codec/sample rate/bit depth/channels/
   duration/size) and, if it passes, moved into your library under
   `Artist/Year - Album/NN - Track.flac` (or `Various Artists/...` for
   compilations). The **Library** tab lists everything that made it in,
   with its verification result (`likely_ok` / `suspicious` / `invalid`).

### Modes

- **SAFE** (default): every track needs an explicit approval click.
- **ASSISTED**: the app still requires your approval click, but you can see
  which candidate it considers best at a glance.

### Duplicate handling

If a file already exists at the target library path, it is **never**
silently overwritten - you choose the policy in Settings: `SKIP` (default),
`COMPARE` (byte-compare; keeps both if different), or `KEEP_BOTH`.

## Running the tests

```bash
cd backend
source .venv/bin/activate   # or .venv\Scripts\activate on Windows
pytest
```

The test suite (parser, normalizer, query builder, matcher/scorer, FLAC
verification heuristics, library organizer, and a full API smoke test using
an in-memory fake Soulseek provider) runs without any real slskd/Spotify
connection. **Running the app against a real slskd instance and confirming
an actual end-to-end download** is a manual step you perform on your
Windows machine per the Definition of Done in `IMPLEMENTATION_PLAN.md`,
since this repository was built in a sandbox without a real Soulseek
network to connect to.

## Project layout

See `ARCHITECTURE.md` for the full design, `IMPLEMENTATION_PLAN.md` for the
build order and what's deliberately deferred past the MVP.

```
backend/app/        FastAPI backend (parsing, matching, slskd adapter, API)
backend/tests/       pytest suite
frontend/             static HTML/CSS/JS UI (no build step)
```

## Known MVP limitations

- Spotify import supports public/unlisted playlists (Client Credentials
  flow). Private playlists would need the Authorization Code flow - not
  implemented yet.
- Settings changed in the UI (mode, strict-FLAC, duplicate policy, rewrite
  metadata) apply immediately but reset to your `.env` values on restart.
- Acoustic-fingerprint-based duplicate detection is not implemented (only
  artist/title/duration/album matching against your own history).
- No installer/`.exe` packaging yet - runs via `uvicorn` + the provided
  launcher scripts.
