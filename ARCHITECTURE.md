# Playlist FLAC Manager — Architecture

## 0. Legal / scope guardrails

- Spotify is used **only** as a metadata catalogue (artist, track, album, album
  artist, release year, track/disc number, ISRC, duration, Spotify URL).
  No Spotify audio, stream, or DRM-protected content is ever fetched, cached,
  or reverse engineered.
- The only audio source is a **Soulseek** network the user already has
  legitimate access to, via a `slskd` instance the user runs and controls.
  The app never scrapes or connects to Soulseek directly — all protocol
  handling is delegated to `slskd`.
- The app never auto-downloads without a human approval step (see "Modes"
  below). There is no "download everything automatically" mode.

## 1. Research notes: slskd API (as of this writing, slskd `master`)

Source: `slskd/slskd` GitHub repo (`docs/config.md`, `src/slskd/Search/API`,
`src/slskd/Transfers/API`, `src/slskd/Users/API`) and `jpdillingham/Soulseek.NET`
(the library slskd wraps for the actual Soulseek protocol).

### Authentication

slskd supports two auth mechanisms on its HTTP API, either of which can be
disabled/enabled in `config.yaml` under `web.authentication`:

- **API key** (recommended for service-to-service use): configured under
  `web.authentication.api_keys.<name>.key` (16–255 chars) with optional CIDR
  restriction. Sent as the `X-API-Key` header on every request.
- **Username/password → JWT**: `POST /api/v0/session` with
  `{"username": "...", "password": "..."}` returns a bearer token
  (`Authorization: Bearer <token>`), valid for `jwt.ttl` ms (default 7 days).

Playlist FLAC Manager's `slskd_client.py` supports **both**; API key is the
default and recommended path for a long-running local orchestrator since it
never expires and does not require storing a session anywhere.

Secrets (slskd API key, Spotify client secret) are **never** committed or
hardcoded. They are read from `.env` (git-ignored) or, optionally, from the
Windows Credential Manager via the `keyring` package (`secrets_store.py`).

### Search

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/v0/searches` | Start a search (`{"searchText": "...", "id": "<guid>", ...}`) |
| GET | `/api/v0/searches` | List active/completed searches |
| GET | `/api/v0/searches/{id}?includeResponses=true` | Get one search + its responses |
| GET | `/api/v0/searches/{id}/responses` | Get just the per-peer responses |
| PUT | `/api/v0/searches/{id}` | Cancel an in-progress search |
| DELETE | `/api/v0/searches/{id}` | Delete a search record |

slskd enforces a concurrency limit on search creation (429 if exceeded) — the
orchestrator's `SearchQueue` respects a configurable rate limit and never
fires unbounded parallel searches (spec §3/§14).

Each search response (one per peer) roughly maps to Soulseek.NET's
`SearchResponse`: `username`, `token`, `fileCount`, `files[]`,
`lockedFileCount`, `lockedFiles[]`, `hasFreeUploadSlot`/`freeUploadSlots`,
`uploadSpeed`, `queueLength`. Each file (`Soulseek.File`) carries `filename`
(full remote path), `size` (bytes), `extension`, and an `attributes[]` list
(bitrate, duration/length, sample rate, bit depth, VBR flag) — attribute
availability depends on what the remote peer's client reports, so the
adapter treats all of these as optional/best-effort.

**We do not invent fields.** `slskd_client.py` parses defensively (`dict.get`
with `None` defaults) so it degrades gracefully across slskd versions instead
of crashing on a missing key.

### Transfers (downloads)

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/v0/transfers/downloads/{username}/{id}` \* | legacy single enqueue (deprecated upstream) |
| POST | `/api/v0/transfers/downloads/batches` | enqueue multiple files atomically, returns per-file enqueue result |
| GET | `/api/v0/transfers/downloads` | list all downloads, grouped by username/directory |
| GET | `/api/v0/transfers/downloads/{username}` | downloads for one user |
| GET | `/api/v0/transfers/downloads/{username}/{id}` | one transfer's state |
| GET | `/api/v0/transfers/downloads/{username}/{id}/position` | remote queue position |
| DELETE | `/api/v0/transfers/downloads/{username}/{id}?remove=true` | cancel (and optionally purge record) |
| DELETE | `/api/v0/transfers/downloads/all/completed` | clear completed |

\* Actual base path in current slskd is `/api/v0/transfers/downloads/...`
(the `Transfers` feature area groups downloads+uploads); some older
documentation shortens this to `/api/v0/downloads/...`. `slskd_client.py`
takes the base path from `.env`/settings (`SLSKD_API_BASE`) precisely so a
version skew doesn't require a code change — see "Configuration".

### Users

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v0/users/{username}/status` | online/away/offline |
| GET | `/api/v0/users/{username}/info` | peer info (free slots, queue, upload speed, shared file/dir counts where available) |

### Swagger

slskd can expose live OpenAPI/Swagger at `/swagger` when
`feature.swagger: true` — the recommended way to confirm the exact schema
against the user's specific slskd version before first use. The setup
instructions tell the user to check this once and adjust `SLSKD_API_BASE` in
`.env` if their version differs.

## 2. High-level architecture

```
 Spotify Web API / TXT / CSV
            │
            ▼
      Track Parser            (backend/app/parsing/track_parser.py)
            │
            ▼
   Metadata Normalizer         (backend/app/parsing/normalizer.py)
            │
            ▼
     Search Manager            (backend/app/search/query_builder.py +
            │                   backend/app/orchestrator/queue_worker.py)
            ▼
       slskd API               (backend/app/providers/slskd_client.py)
            │
            ▼
   Candidate Matcher           (backend/app/matching/scorer.py)
            │
            ▼
   Quality / Source Scoring    (backend/app/matching/source_score.py)
            │
            ▼
 User Approval (SAFE/ASSISTED) (backend/app/api/routes_tracks.py)
            │
            ▼
   Authorized Download         (backend/app/providers/slskd_provider.py)
            │
            ▼
     File Validator            (backend/app/verification/flac_verifier.py)
            │
            ▼
 Metadata / Folder Organizer   (backend/app/library/organizer.py, metadata_writer.py)
            │
            ▼
          Library
```

Everything left of "slskd API" never touches audio. Everything right of it
only ever acts on a file the user explicitly approved.

## 3. Plugin architecture: `MusicSourceProvider`

To avoid permanently coupling the app to Soulseek (spec §21), all source
interaction goes through an abstract interface:

```python
class MusicSourceProvider(ABC):
    def search(self, query: str) -> str: ...          # returns a provider search handle/id
    def get_candidates(self, handle: str) -> list[RawCandidate]: ...
    def request_download(self, candidate: RawCandidate) -> DownloadHandle: ...
    def status(self, download: DownloadHandle) -> DownloadStatus: ...
```

`SlskdProvider` is the first (and, for MVP, only) implementation. Everything
above the provider boundary (matcher, scoring, orchestration, API routes)
only knows about `RawCandidate` / `DownloadHandle` / `DownloadStatus` —
never slskd-specific types. Future providers (`LocalLibraryProvider`,
purchased-music providers) plug in without touching the pipeline.

All slskd HTTP calls live in exactly one file, `slskd_client.py`
(spec §4 requirement — "no spreading API calls across the project").

## 4. Backend layout

```
backend/
  app/
    main.py                 FastAPI app, mounts routers + static frontend
    config.py                Settings (pydantic-settings), .env / keyring
    secrets_store.py         Windows Credential Manager helper (keyring)
    database.py               SQLAlchemy engine/session, SQLite file
    models.py                 ORM tables: playlists, tracks, searches,
                               candidates, downloads, files, settings
    schemas.py                 Pydantic request/response models
    logging_utils.py          In-memory + DB event log (never logs secrets)
    parsing/
      track_parser.py          text / CSV / TXT → RawTrackLine
      normalizer.py             RawTrackLine → NormalizedTrack (+ version tag)
    search/
      query_builder.py          NormalizedTrack → ordered list of query strings
    spotify/
      client.py                  Client-Credentials metadata-only Spotify client
    providers/
      base.py                    MusicSourceProvider ABC + shared dataclasses
      slskd_client.py             ALL slskd HTTP calls (search/downloads/users)
      slskd_provider.py           SlskdProvider(MusicSourceProvider)
    matching/
      scorer.py                   match_score (0-100) + REVIEW_REQUIRED guard
      source_score.py             source_score (0-100), kept separate from match
    verification/
      flac_verifier.py            ffprobe/mutagen based FLAC verification
    library/
      organizer.py                 file placement + SKIP/COMPARE/KEEP_BOTH
      metadata_writer.py           mutagen tag normalization (opt-in, backs up original)
    orchestrator/
      pipeline.py                  per-track state machine (spec §14 statuses)
      queue_worker.py              rate-limited async search/download worker
    api/
      routes_import.py, routes_tracks.py, routes_search.py,
      routes_downloads.py, routes_library.py, routes_settings.py
  tests/
  requirements.txt
frontend/
  index.html, app.js, styles.css   (static, no build step — served by FastAPI)
```

## 5. Data model (SQLite)

- **playlists** — id, source (`text`/`csv`/`spotify`), source_ref (URL or filename), imported_at
- **tracks** — id, playlist_id, raw_line, artist, title, album, album_artist,
  version_tag, release_year, track_number, disc_number, duration_ms, isrc,
  spotify_url, status, local_match_id (nullable FK to a library file)
- **searches** — id, track_id, query_text, provider, created_at, raw_response_count
- **candidates** — id, track_id, search_id, provider, username, remote_path,
  size_bytes, extension, bitrate, sample_rate, bit_depth, duration_sec,
  match_score, source_score, status (`OK`/`REVIEW_REQUIRED`), reason
- **downloads** — id, candidate_id, provider_download_id, state, queued_at,
  completed_at, error
- **files** — id, download_id, local_path, verification_state
  (`likely_ok`/`suspicious`/`invalid`), codec, sample_rate, bit_depth,
  channels, duration_sec, size_bytes, library_path
- **settings** — key/value store (strict_flac_only, mode SAFE/ASSISTED,
  duplicate policy, slskd base URL, rate limit, library root, rewrite_metadata)

Every track keeps its original input string (`raw_line`) next to the
normalized fields, per spec §19.

## 6. Track status machine (spec §14)

```
IMPORTED → SEARCHING → MATCHED ─┬→ REVIEW_REQUIRED → (user resolves) → APPROVED
                                 └→ APPROVED → QUEUED → DOWNLOADING → VERIFYING → COMPLETED
                                                                     └→ FAILED
SEARCHING → NOT_FOUND   (no usable candidate after all query variants)
```

## 7. Modes (spec §16)

- **SAFE** (default): nothing is queued automatically. Every track needs an
  explicit "approve candidate" click.
- **ASSISTED**: the pipeline pre-selects the best candidate (highest
  match_score among non-`REVIEW_REQUIRED` results) but still stops before
  calling `enqueue_authorized_file` — the user must click "confirm" to
  actually hand the file to slskd.

There is no unattended/auto-download mode, by design.

## 8. Dependencies

Backend (`backend/requirements.txt`): `fastapi`, `uvicorn[standard]`,
`sqlalchemy`, `pydantic-settings`, `httpx`, `rapidfuzz`, `mutagen`,
`python-dotenv`, `keyring` (optional Windows credential store), `pytest`
(dev). `ffprobe` (from FFmpeg) is an optional external binary — if absent,
verification falls back to `mutagen`-only checks.

Frontend: no build toolchain — a single static HTML/CSS/vanilla-JS page
served by FastAPI's `StaticFiles`, calling the JSON API. This keeps the
Windows setup to "install Python, `pip install -r requirements.txt`, run
`uvicorn`" with no Node.js requirement. (React remains a documented future
option once the API surface stabilizes — see IMPLEMENTATION_PLAN.md §"Future work".)

## 9. What was deliberately reused/avoided from prior art

- **slskd**: treated strictly as an external service reached over HTTP; its
  source is *read* (for endpoint discovery) but never vendored or modified.
- **Soulseek.NET**: used only as a reference for what fields a Soulseek
  search/file object can realistically contain, so the matcher doesn't
  assume data that peers don't actually send.
- **nicotine+**: reviewed conceptually for how it buckets/filters search
  results and displays folders, to inform `source_score`'s "has full album
  folder" signal — no GPL code copied (license risk noted, spec §22).
