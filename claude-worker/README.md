# voice-claude: the slow, smart path of a Hungarian voice assistant

A small HTTP service that takes a transcribed spoken request ("tegyél be valami smooth jazzt munkához"), runs a
Claude tool-use loop against the home's music library (Music Assistant + Tidal) and film library (Jellyfin), and
speaks short Hungarian status lines and the final answer on the voice satellite through Home Assistant. A monthly
budget caps what it can spend.

The fast path (device control, play/pause, exact film titles) stays local in `voice_brain`
(`../voice_brain/custom_components/voice_brain/`). Everything else is handed to this worker, which answers
immediately with an acknowledgement and then works in the background.

```
satellite ─► HA Assist (STT) ─► voice_brain ──POST /task──► voice-claude ──► Claude API (tool-use loop)
                                    │  says "Szólok Claude-nak."   │  ├─► Music Assistant websocket (search, play, playlists)
                                    │                              │  ├─► Jellyfin (films, series, Hungarian titles)
                                    │                              │  └─► HA jellyfin_panel/play (wakes the TV)
satellite ◄── assist_satellite.announce (Piper TTS) ◄──────────────┘  status lines + final answer
```

## API

| Endpoint | Body | Answer |
|---|---|---|
| `POST /task` | `{"text", "lang": "hu", "satellite": "assist_satellite.x" \| null, "device_id", "source"}` | `{"accepted": true, "ack": "Szólok Claude-nak."}` at once, or `{"accepted": false, "reason": "no_key" \| "budget" \| "busy" \| "error", "say": "<Hungarian sentence>"}` |
| `POST /cancel` | | `{"cancelled": bool}` |
| `POST /quick` | `{"action": "like" \| "save_to_playlist" \| "list_playlists", "player", "playlist"}` | `{"ok", "say", ...}`; no Claude involved, answers in tens of milliseconds |
| `GET /health` | | `{"ok", "has_key", "model", "busy", "dry_run", "catalogue_age_h"}` |
| `GET /budget` | | `{"month", "spent_usd", "limit_usd", "requests"}` |

One task runs at a time. A new `/task` while one is running cancels the old one and is accepted (people rephrase).
A cancelled task says nothing. `/task` also includes a `task_id` in its answer.

`/quick` actions:
- `like`: adds the current track of the given player (or the one playing, else the default) to the favourites.
- `save_to_playlist`: adds the current track to the user's own playlist whose name best matches `playlist`
  (forgiving match, editable playlists only). Without a confident match it answers `ok: false` and lists the
  closest names in `say` and `closest`.
- `list_playlists`: the editable playlists as `playlists: [{name, uri, id}]`.

## The Claude loop

`voice_claude/loop.py` is a manual tool-use loop on the official `anthropic` Python SDK (`messages.create`,
adaptive thinking at the configured effort):

- **System prompt** (`prompt.py`): a Hungarian-speaking home assistant called Claude whose replies are read aloud:
  short spoken Hungarian, no markdown, lists, emoji or URLs, numbers in words. It also carries the behaviour rules:
  build mood queues on the user's own music first and pad with Tidal; verify artist and title on exact requests and
  say so when something isn't found; create playlists on Tidal and confirm name and count; always say what could
  not be done; never delete anything (there is no delete tool at all).
- **Library catalogue** (`catalogue.py`): artists, albums, tracks (title – artist, favourites marked), playlists
  (owner, editable, track count) and Jellyfin films and series with English, Hungarian and original titles and year.
  It goes into a second system block with `cache_control`, so after the first request it is a cache read.
  It is built from Music Assistant and Jellyfin, saved to `data/catalogue.json`, rebuilt every 6 hours and on
  `/task` when older. The text is sorted and contains nothing time-dependent, so the cache survives rebuilds when
  the library hasn't changed. Hungarian titles come from Jellyfin's remote search (TMDB) once per item and are
  cached in `data/titles_hu.json`.
- **Per-request context** (time, source, satellite, players and what they play) goes in the user turn, after the
  cached prefix.
- **Limits**: 12 model turns, 150 s wall time, $0.60 per task (all configurable). Hitting one stops the task and
  says a short Hungarian apology with the reason.

### Tools

| Tool | What it does |
|---|---|
| `search_music(query, media_types, limit, library_only)` | Music Assistant search over the library and Tidal |
| `get_playlist_tracks(playlist, limit)` | Tracks of a playlist by name, id or uri |
| `get_now_playing(player)` | What each player is playing |
| `play_music(uris, player, enqueue, radio_mode, shuffle)` | `player_queues/play_media` (replace / next / add), optional radio mode and shuffle |
| `create_playlist(name)` | New playlist on the configured provider (Tidal), refuses duplicates of own playlists |
| `add_to_playlist(playlist, uris)` | Adds to an own (editable) playlist only |
| `like(uri \| current, player)` | `music/favorites/add_item` |
| `search_movies(query)` | Catalogue match on any title plus a Jellyfin search |
| `play_movie(item, from_start)` | Starts a film, or a series' next episode, on the TV through Home Assistant's `jellyfin_panel` endpoint, resuming where it was left off. The TV takes up to a minute to wake, so this returns at once and a later failure is announced |
| `report_status(text)` | A short progress line spoken on the satellite |
| `web_search` (server tool) | At most 3 searches per task; dropped from the tool list once used up |

Tool results are compact JSON with trimmed fields (uri, name, artist, album, length, favourite, in library).

### Speech

- Status lines (`report_status`) are spoken at least 6 s apart, never in the first 4 s after the ack (so they
  don't talk over "Szólok Claude-nak."), and at most 4 per task. A line that comes too early is held and spoken as
  soon as allowed, unless the task finishes first; a newer line replaces a held one.
- If 15 s pass without any status and the task isn't done, it says "Még dolgozom rajta." once.
- The final answer is cleaned for TTS (markdown, URLs and emoji removed) and announced. Announcements are
  serialised, so a status line and the answer never overlap.
- Without a satellite in the request (e.g. a desktop app), it announces on `default_satellite`.

### Budget

Every API call is appended to `data/ledger.jsonl` with its usage (input, 5 min and 1 h cache writes, cache reads,
output, web searches) and its cost from the `pricing` table in the config. The monthly total uses the calendar
month in `timezone`. When it reaches `limits.monthly_usd`, `/task` answers `accepted: false, reason: "budget"`
and the voice says "Elértük a havi Claude keretet, ezt most nem tudom megcsinálni.". A running task also stops.
Set a hard limit on the API key's workspace in the Claude Console as well; the ledger is an estimate.

Each task (text, tools called, duration, cost, final answer, outcome) goes to `data/tasks.jsonl` and to the log
(journald under systemd).

## Home control

Claude can control the home only through a fixed allowlist in `config.json` (`home_control`, template in
`config.example.json`; logic in `voice_claude/home.py`):

- `ha_get_states(group | entity_ids)`: compact states of the entities listed under `readable` (lights, TV,
  speakers, tablet, phone, weather, sun, presence), plus `read_endpoints` such as the Jellyfin now-playing view.
- `get_weather_forecast(kind)`: `weather.get_forecasts` on `weather_entity` (read-only).
- `ha_action(action_id, params)`: one of the `actions`. Each has a description (Hungarian/English) that goes into
  the tool definition, a fixed `service` or `post` path with fixed `data`, and typed `params` (enum, entity list,
  integer range) that are validated before the call. Unknown actions or params are errors Claude sees.
- `set_volume(level, player)` and `play_music(..., volume)`: Music Assistant player volume in percent
  ("negyvenes hangerő" = 40), set before playback starts.

Whatever the config says, anything touching the intruder alarm, restarts, reloads, deletions, backups or shell
commands is dropped at load time. Every write is logged (`HA write ...`, or `[dry-run] would call HA ...`).
`home_control.manual` lines are appended to the system prompt as a house manual (device names, rooms, satellites,
what the scripts do).

## Setup

Needs Python 3.11+, a Music Assistant server (tested with 2.9) with a long-lived token, Home Assistant with a
long-lived token, optionally Jellyfin with an API key, and an Anthropic API key.

```bash
sudo mkdir -p /opt/voice/claude && cd /opt/voice/claude
python3 -m venv venv && venv/bin/pip install -r app/requirements.txt
# secrets: one value per file, mode 600, outside the repo
for f in ha.token ma.token jellyfin.key anthropic.key; do sudo install -m 600 /dev/null $f; done   # then fill them
cp app/config.example.json config.json   # and edit it
sudo cp app/voice-claude.service /etc/systemd/system/ && sudo systemctl enable --now voice-claude
curl localhost:8099/health
```

`deploy.sh` copies the code (and your local `config.json`, which git ignores) to the server and restarts the
service: `TARGET="ssh root@voice-host" ./deploy.sh`.

The `/opt/voice/claude` paths are only defaults: `secrets_dir`, `data_dir` and the `--config` path are all settings.

### Config (`config.example.json`)

| Key | Meaning |
|---|---|
| `listen` | host and port (8099) |
| `secrets_dir`, `data_dir` | where the secret files and the caches/ledgers live |
| `dry_run` | log every write and every announcement instead of doing it (also `--dry-run`) |
| `home_assistant.url`, `token_file` | Home Assistant REST API |
| `home_assistant.default_satellite` | `assist_satellite` entity used when a request has none |
| `home_assistant.jellyfin_play_path`, `jellyfin_play_device` | the HA view that wakes the TV and starts Jellyfin playback |
| `music_assistant.url`, `token_file` | Music Assistant websocket (`ws://host:8095/ws`) |
| `music_assistant.playlist_provider` | provider instance new playlists are created on (e.g. `tidal--xxxx`) |
| `music_assistant.default_player`, `player_aliases`, `player_hint` | default `media_player`, spoken names for each player, and one sentence for the prompt on how people name the players |
| `jellyfin.url`, `key_file`, `user` | the Jellyfin user whose library and progress are used |
| `anthropic.model`, `allowed_models`, `effort`, `max_tokens` | default model (`claude-sonnet-5-5`), allowed `claude-haiku-5-5` / `claude-opus-5-5` |
| `anthropic.web_search_tool`, `max_web_searches` | web search tool type per model and the per-task cap |
| `limits` | `max_turns`, `max_seconds`, `max_task_usd`, `monthly_usd` |
| `status` | the speech rate limit and the "still working" text |
| `catalogue` | refresh interval and size caps |
| `pricing` | USD per million tokens per model (input, cache writes, cache read, output) and per 1000 web searches |

Players are discovered from Home Assistant: every `media_player` with a Music Assistant `mass_player_type`
attribute; its `active_queue` attribute is the queue that gets played on. A request names a player ("a
nappaliban", "a Pi-n"), else the one playing is used, else `default_player`.

Prices in the example (USD per million tokens, from Anthropic's pricing page, November 2026):

| Model | Input | 5 min cache write | 1 h cache write | Cache read | Output |
|---|---|---|---|---|---|
| claude-sonnet-5-5 | 2.00 | 2.50 | 4.00 | 0.10 | 10.00 |
| claude-haiku-5-5 (prompts up to 100k tokens) | 0.10 | 0.125 | 0.20 | 0.01 | 0.50 |
| claude-opus-5-5 | 4.00 | 5.00 | 8.00 | 0.20 | 20.00 |

Web search: $10 per 1000 searches. Web search tool types: `web_search_20260209` on Sonnet 5.5 and Opus 5.5,
`web_search_20250305` on Haiku 5.5. If the API rejects the web search config, the task retries once without it.

## Tests

```bash
cd claude-worker
python -m unittest discover -s tests -t .          # offline: fake model, no network
python -m tests.live_readonly --config config.json # read-only against the real services; writes are dry-run
python -m tests.live_claude --config config.json --model claude-haiku-5-5 "játszd le a Daft Punk Get Lucky-t"
python -m tests.live_claude --config config.json --quick
```

- `tests/test_loop.py` drives the loop with a scripted fake model: a tool sequence and the final answer, the
  status rate limit (held and replaced lines, the per-task cap), the "still working" notice, the wall-time limit,
  the turn and cost limits, the web search cap, API errors, cancel, a new task cancelling the old one, the budget
  and missing-key refusals, plus pricing, the gate and TTS cleanup.
- `tests/live_readonly.py` builds the catalogue (and counts its tokens), runs every read tool against the real
  Music Assistant and Jellyfin, and runs every write tool with `dry_run`, printing the exact command it would send.
- `tests/live_claude.py` runs real Claude requests with dry-run tools and a dry-run speaker: nothing plays and
  nothing is announced, but the API calls are real and billed.

## Measurements (November 2026, real library: 337 tracks, 436 artists, 52 playlists, 79 films and series)

- Catalogue: about 27 000 characters, **15 200 tokens**; tools plus system prompt plus catalogue about 20 500
  tokens, all cached after the first request.
- Haiku 5.5: $0.0003 to $0.004 per task (a web-search task about $0.024, mostly the two searches), 2 to 9 s.
- Sonnet 5.5: about $0.07 for a task that has to write the cache (the first one after 5 idle minutes) and about
  $0.025 with a warm cache, 4 to 8 s.
- At ten requests a day, mostly cold: about $20 a month on Sonnet, under $1 on Haiku.

## Limitations

- Music Assistant's library is what it calls "in library"; its artist count (several hundred) also includes
  artists it only knows from tracks, so the catalogue lists library artists plus everyone on a library track.
- Playlist track counts are fetched for the user's own playlists only; editorial and smart playlists are listed
  without a count.
- `play_movie` relies on Home Assistant's `jellyfin_panel` component (`/api/jellyfin_panel/play`), which wakes an
  Android TV over ADB and starts the Moonfin client. Another setup needs its own endpoint there.
- "Current track" is the current item of the player's queue, so `like` also works on a paused or just-stopped player.
- The ledger is computed from the usage the API reports and the configured prices; it is not the Console's bill.
- No conversation memory between tasks: every request starts fresh.
