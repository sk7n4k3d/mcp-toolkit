# ollama-watch

Small polling service that watches a model catalogue and pushes a notification **only when
something changes** — new model, updated model, or a model that disappeared.

Not an MCP server. It's the kind of small operational glue that runs unattended for months.

## Why it's written the way it is

**State diffing, not blind notification.** It keeps a `state.json` of every model it has seen
(name → digest + modified date) and compares each poll. You get an alert on *change*, never a
message every cycle. The first run initialises the state silently (otherwise it would announce
every model that already exists).

**Atomic state writes.** The state is written to a temp file and `os.replace`d into position, so a
crash mid-write can't leave a truncated JSON that breaks the next run.

**Header encoding done correctly.** Notification services read headers as UTF-8 while HTTP clients
encode them as latin-1 — naive code turns accented characters into mojibake and crashes outright on
emoji. `_header_safe()` round-trips through latin-1 so the bytes arrive as intended UTF-8.

## Run with Docker

```bash
docker compose up -d
```

`docker-compose.yml` expects an external network shared with the notification service. Adjust the
`networks` block and the `NTFY_URL` / `NTFY_TOPIC` environment variables to your setup.

## Run directly

```bash
pip install requests
STATE_FILE=./state.json NTFY_URL=http://localhost:80 NTFY_TOPIC=MyTopic \
  python watch.py --loop --interval 21600
```

`--interval` is in seconds (default 21600 = 6 h).

## Environment

| Variable | Default | Purpose |
|---|---|---|
| `NTFY_URL` | `http://ntfy:80` | notification endpoint |
| `NTFY_TOPIC` | `Ollama` | notification topic |
| `STATE_FILE` | `/data/state.json` | persisted state |
| `NOTIFY_FIRST_RUN` | `0` | set `1` to announce the initial catalogue |
| `HTTP_TIMEOUT` | `30` | request timeout (s) |

MIT. See the repository root for the licence.
