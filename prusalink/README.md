# prusalink-mcp

MCP server that drives a **Prusa XL** 3D printer through its local **PrusaLink** API. Ten tools
covering the whole print workflow: inspect, upload, start, pause, resume, stop.

## Why

3D printing is a physical process with a feedback loop, and the interesting part is making that
loop safe to hand to a model: a failed HTTP call is normal (printer busy, camera absent, file
missing), so every error is returned as structured JSON instead of raising. Digest auth is
handled once by a shared opener.

## Tools

| Tool | Purpose |
|---|---|
| `prusa_status` | state, temperatures (with targets), job progress, axes, speed/flow |
| `prusa_info` | serial, hostname, nozzle, MMU |
| `prusa_job` | current job: file, progress, remaining time |
| `prusa_files` | list files/folders on `/usb/` or `/local/` |
| `prusa_print` | start a file already on the printer |
| `prusa_pause` / `prusa_resume` / `prusa_stop` | job control |
| `prusa_snapshot` | camera snapshot (graceful when no camera) |
| `prusa_upload_and_print` | PUT a local `.bgcode` to `/usb/` then start it |

## Configuration

Credentials live in an env file, never in code. Point `MCP_ENV_FILE` at it (default
`~/.config/mcp/prusa-env`):

```bash
PRUSA_HOST=192.0.2.10    # your printer's LAN address
PRUSA_USER=maker
PRUSA_PASS=your-password
```

## Run

```bash
pip install "mcp<2"
MCP_ENV_FILE=~/.config/mcp/prusa-env python prusalink_mcp.py
```

Register in any MCP client:

```json
{
  "mcp": {
    "prusalink": {
      "type": "local",
      "command": ["python", "/path/to/prusalink-mcp/prusalink_mcp.py"]
    }
  }
}
```

## Notes

- PrusaLink **2.0** semantics: file upload is `PUT /api/v1/files/usb/{name}`; starting a job is
  `POST /api/v1/files/usb/{name}` with `{"command":"start"}`.
- Local mode uses **HTTP Digest** auth.

MIT.
