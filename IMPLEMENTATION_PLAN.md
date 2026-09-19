# Implementation Plan

## Guiding rule

Ship the MVP vertical slice from spec §23 first, end-to-end, before adding
anything else. Everything below is ordered so each step is independently
testable.

## MVP definition of done (spec §25)

Paste:
```
Vitalic - Poison Lips
Acid Arab - Gul l'Abi
The Chemical Brothers - Star Guitar
```
→ 3 tracks recognized → each searched via slskd → best FLAC candidates
shown with Match Score → user picks a source → slskd receives the download →
app tracks its status → completed file passes FLAC verification → file
appears in the Library view.

## Steps

1. **Backend skeleton** — FastAPI app factory, SQLAlchemy models for the 7
   tables, Pydantic settings loaded from `.env`, static frontend mount.
2. **Import & normalize** — `POST /api/import/text` (and CSV/TXT file
   upload) parses `Artist - Track (Version)` style lines (multiple
   separators: `-`, `—`, `–`, `|`, `/`), strips noise (`.flac`, `[FLAC]`,
   `(Lossless)`, bitrate strings, CD-rip markers, leading track numbers),
   keeps musically meaningful version words (Remix/Extended/Edit/Live/
   Instrumental/Remaster/Version/Mix). Unit-tested against the 3 example
   lines plus edge cases.
3. **Query builder** — generates an ordered list of search strings per
   track (bare, with dash, +FLAC, +album, +version) for fallback search.
4. **slskd adapter** — `slskd_client.py` wraps `POST /searches`,
   `GET /searches/{id}`, `GET /searches/{id}/responses`,
   `GET /users/{u}/status`, `GET /transfers/downloads*`,
   `POST /transfers/downloads/batches`, `DELETE .../{id}`. Auth via
   `X-API-Key` (default) from `.env`/keyring. `SlskdProvider` adapts this to
   the `MusicSourceProvider` interface.
5. **Search orchestration** — `SearchQueue` in `queue_worker.py`: asyncio
   queue + configurable requests/sec limiter, runs query variants in order,
   stops at first variant that yields ≥1 usable (FLAC, if strict mode)
   candidate or exhausts the list → `NOT_FOUND`.
6. **Candidate matcher** — `scorer.py` implements the exact weighted rubric
   from spec §6 (artist 25 / track 30 / version 15 / album 10 / duration 10
   / file properties 10) using `rapidfuzz` for fuzzy string comparison, plus
   the version-guard from spec §8 (never silently prefer remix/live/
   instrumental/radio edit/major-remaster/cover/karaoke over what the user
   actually asked for → forces `REVIEW_REQUIRED`).
7. **Source score** — `source_score.py`, kept as a distinct number from
   match_score, using online/free-slot/queue/speed/size/folder-completeness
   signals available from the search response.
8. **Approval + download** — `POST /api/tracks/{id}/approve` with a chosen
   candidate id; SAFE mode requires this call for every track, ASSISTED
   mode pre-fills the best candidate but still requires this call to fire
   the actual enqueue. Enqueues via `slskd_provider.request_download`.
9. **Status polling** — background task polls `GET /transfers/downloads`
   and updates `downloads`/`tracks` rows; exposed via `GET /api/downloads`.
10. **FLAC verification** — on `COMPLETED`, `flac_verifier.py` runs
    `ffprobe` (if present) else `mutagen.flac.FLAC`, records codec/sample
    rate/bit depth/channels/duration/size, and classifies
    `likely_ok` / `suspicious` / `invalid` using the heuristics in spec §10
    (never claims certainty about transcoding).
11. **Library organizer** — moves verified files into
    `Music/Artist/Year - Album/NN - Track.flac` (or
    `Music/Various Artists/Year - Album/NN - Artist - Track.flac` for
    compilations), never silently overwriting — SKIP/COMPARE/KEEP_BOTH.
12. **Frontend** — single static page: paste box (text or Spotify URL) +
    file import, `ANALYZE` button, results table
    (Artist/Track/Match/Source/Format/Size/Status), row click → candidate
    modal with per-candidate scores and an Approve button, a log panel
    (poll `GET /api/logs`), and a mode switch (SAFE/ASSISTED).
13. **Spotify import** — `POST /api/import/spotify` with a playlist URL;
    Client-Credentials Spotify Web API call fetches track metadata only
    (artist/title/album/album_artist/year/track#/disc#/isrc/duration_ms/
    spotify url) and feeds it through the same normalizer/query pipeline as
    text import. No audio/stream endpoints are ever called.
14. **Duplicate detection** — before searching, check the `files`/library
    index for an existing artist+title+duration(±)+album match →
    `LOCAL_MATCH`, skip search. Acoustic fingerprinting is out of scope for
    MVP (interface left open — see Future work).
15. **Tests + docs + run scripts** — pytest for parser/normalizer/query
    builder/scorer (pure functions, no network), README with Windows setup,
    `.env.example`, `run_windows.ps1`.

## Dependencies to install (backend/requirements.txt)

```
fastapi
uvicorn[standard]
sqlalchemy
pydantic-settings
httpx
rapidfuzz
mutagen
python-dotenv
keyring
```

Dev/test only: `pytest`.

External, optional: FFmpeg's `ffprobe` on PATH (verification falls back to
mutagen-only if absent — degraded but functional).

## Out of scope for MVP (explicitly deferred)

- OAuth (Authorization Code) Spotify flow for private playlists — MVP
  supports public/unlisted playlists via Client Credentials; private
  playlists are a documented follow-up.
- Acoustic fingerprinting for duplicate detection.
- `LocalLibraryProvider` / purchased-music providers (interface exists,
  not implemented).
- Packaging as a signed Windows installer/exe (MVP runs via
  `uvicorn` + a `.bat`/`.ps1` launcher; PyInstaller packaging is a later
  step once the feature set is stable).
- React frontend (current plain HTML/JS frontend already satisfies "simple
  modern web frontend" from the spec; swapping in React/Vite is additive
  and doesn't change the API).

## Manual verification checklist (since this is a Windows desktop app being
built in a Linux CI-like sandbox)

- [ ] `pytest backend/tests` green (parser, normalizer, query builder,
      scorer — all pure-function, no slskd/Spotify network needed).
- [ ] `python -m compileall backend/app` clean.
- [ ] App boots (`uvicorn app.main:app`) against a **mocked** slskd (tests
      use `respx`/monkeypatched `httpx` — no real slskd instance available
      in this environment) — full live-slskd run must happen on the user's
      Windows machine with a real `slskd` instance, per spec §24-25. This is
      called out explicitly in the README as the final manual acceptance
      step the user performs locally.
