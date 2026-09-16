# mcp-toolkit

Small, production-tested **Model Context Protocol (MCP)** servers I use daily. Each one wraps a real
system I actually operate — not a toy demo. They all follow the same pattern: a thin, defensive
layer that turns a system's API into tools an LLM can call safely.

Model Context Protocol is how you let a language model act on real systems. The hard parts are not
the "hello world" tool — they are auth, error handling, timeouts, and not silently swallowing
failures. That's what these servers focus on.

## Servers

| Server | What it does | Tools |
|---|---|---|
| [`prusalink/`](prusalink/) | Pilots a Prusa XL 3D printer over its local PrusaLink API (Digest auth): status, job, files, print control, upload+print | 10 |
| [`cad/`](cad/) | Headless CAD pipeline: OpenSCAD → STL → sliced G-code, plus STL inspection and transform | 6 |
| [`ollama-watch/`](ollama-watch/) | Not an MCP server — a small polling service that watches a model catalogue and pushes notifications (state diffing, no duplicate alerts) | — |

## Design notes

**FastMCP, stdio transport.** All servers expose tools over stdio, which is what desktop MCP clients
expect. No long-running HTTP daemon to secure when you don't need one.

**Credentials never in code.** `prusalink/` reads its host and credentials from an env file
(`PRUSA_HOST`, `PRUSA_USER`, `PRUSA_PASS`) whose path is configurable. Nothing is committed.

**Errors are returned, not raised into the void.** Wrapping a flaky local device means HTTP errors
are normal: they come back as structured JSON the model can reason about, instead of killing the
tool call.

**State diffing.** `ollama-watch/` keeps a `state.json` and only notifies on *changes* (new /
updated / removed), so you get signal instead of a message every poll. Atomic writes, so a crash
mid-write can't corrupt the state.

## Quick start

```bash
# PrusaLink MCP
export MCP_ENV_FILE=~/.config/mcp/prusa-env   # PRUSA_HOST, PRUSA_USER, PRUSA_PASS
python prusalink/prusalink_mcp.py

# CAD MCP (needs openscad + prusa-slicer on PATH)
python cad/cad_mcp.py
```

Register it in any MCP-capable client, e.g.:

```json
{
  "mcp": {
    "prusalink": {
      "type": "local",
      "command": ["python", "/path/to/mcp-toolkit/prusalink/prusalink_mcp.py"]
    }
  }
}
```

## Requirements

- Python 3.10+
- `mcp` (FastMCP v1: `pip install "mcp<2"`)
- `cad/`: `openscad`, `prusa-slicer` on PATH
- `ollama-watch/`: `requests`

## License

MIT — see [LICENSE](LICENSE).
