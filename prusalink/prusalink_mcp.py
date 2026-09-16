#!/usr/bin/env python3
"""MCP PrusaLink — control a Prusa XL 5T over its local PrusaLink API.

Protocol source: the official OpenAPI spec (github.com/prusa3d/Prusa-Link-Web).
Auth: HTTP Digest (PrusaLink's local mode).

Credentials are read from an env file (never hardcoded). Its location is taken
from the MCP_ENV_FILE environment variable, defaulting to
~/.config/mcp/prusa-env, with the format:

    PRUSA_HOST=192.0.2.10
    PRUSA_USER=maker
    PRUSA_PASS=secret
"""

import json
import os
import time
import urllib.error
import urllib.request
from urllib.request import HTTPDigestAuthHandler, HTTPPasswordMgrWithDefaultRealm

from mcp.server.fastmcp import FastMCP

ENV_FILE = os.path.expanduser(
    os.environ.get("MCP_ENV_FILE", "~/.config/mcp/prusa-env")
)


def _load_env(path: str) -> dict:
    env = {}
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip()
    except FileNotFoundError:
        pass
    return env


_env = _load_env(ENV_FILE)

HOST = _env.get("PRUSA_HOST", "127.0.0.1")
USER = _env.get("PRUSA_USER", "maker")
PASS = _env.get("PRUSA_PASS", "")
BASE = f"http://{HOST}"
TIMEOUT = 25

_mgr = HTTPPasswordMgrWithDefaultRealm()
_mgr.add_password(None, BASE, USER, PASS)
_opener = urllib.request.build_opener(
    urllib.request.HTTPDigestAuthHandler(_mgr)
)

mcp = FastMCP("prusalink")


def _fetch(req: urllib.request.Request, timeout: int = TIMEOUT):
    return _opener.open(req, timeout=timeout)


def _get(path: str, accept: str = "application/json") -> dict:
    req = urllib.request.Request(BASE + path, headers={"Accept": accept})
    with _fetch(req) as r:
        return json.loads(r.read().decode())


def _post(path: str, data: dict | None = None, method: str = "POST") -> dict:
    body = json.dumps(data).encode() if data else b""
    req = urllib.request.Request(
        BASE + path,
        data=body,
        method=method,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
    )
    # A device-level HTTP error is a normal outcome here, not a crash:
    # surface it as structured JSON so the model can react.
    try:
        with _fetch(req) as r:
            txt = r.read().decode()
            return json.loads(txt) if txt else {"status": r.status}
    except urllib.error.HTTPError as e:
        return {"error": e.code, "message": e.read().decode()[:200]}


@mcp.tool()
def prusa_status() -> str:
    """Printer status: state, temperatures (targets included), job progress,
    axis positions, speed/flow."""
    return json.dumps(_get("/api/v1/status"), indent=1)


@mcp.tool()
def prusa_info() -> str:
    """Printer info: serial, hostname, nozzle, mmu."""
    return json.dumps(_get("/api/v1/info"), indent=1)


@mcp.tool()
def prusa_job() -> str:
    """Current job: file being printed, progress, remaining time."""
    return json.dumps(_get("/api/v1/job"), indent=1)


@mcp.tool()
def prusa_files(path: str = "/usb/") -> str:
    """List files/folders on a storage (e.g. /usb/ or /local/)."""
    return json.dumps(_get(f"/api/v1/files{path}"), indent=1)


@mcp.tool()
def prusa_print(path: str) -> str:
    """Start printing a file already present on the printer.
    path e.g. '/usb/part.bgcode'. Does NOT upload."""
    return json.dumps(_post(f"/api/v1/files{path}", {"command": "start"}))


@mcp.tool()
def prusa_pause() -> str:
    """Pause the running print."""
    return json.dumps(_post("/api/v1/job/pause"))


@mcp.tool()
def prusa_resume() -> str:
    """Resume a paused print."""
    return json.dumps(_post("/api/v1/job/resume"))


@mcp.tool()
def prusa_stop() -> str:
    """Stop the current job."""
    return json.dumps(_post("/api/v1/job/stop"))


@mcp.tool()
def prusa_snapshot() -> str:
    """Grab a snapshot from the PrusaLink camera (if one is attached)."""
    try:
        return json.dumps(_get("/api/v1/cameras/snap"), indent=1)
    except urllib.error.HTTPError as e:
        return json.dumps({"error": e.code, "message": "no camera"})


@mcp.tool()
def prusa_upload_and_print(local_path: str, remote_name: str | None = None) -> str:
    """Upload a local .bgcode/.gcode file to /usb/ then start the print."""
    if not os.path.exists(local_path):
        return json.dumps({"error": "file not found", "path": local_path})
    name = remote_name or os.path.basename(local_path)
    remote = f"/usb/{name}"
    # PrusaLink 2.0: upload-by-PUT = PUT /api/v1/files/usb/{name}
    data = open(local_path, "rb").read()
    req = urllib.request.Request(
        BASE + f"/api/v1/files{remote}",
        data=data,
        method="PUT",
        headers={"Content-Type": "application/octet-stream"},
    )
    try:
        with _fetch(req, timeout=300) as r:
            upload_result = {"upload": r.status}
    except urllib.error.HTTPError as e:
        return json.dumps(
            {"error": "upload", "code": e.code, "message": e.read().decode()[:200]}
        )
    time.sleep(1)
    start = _post(f"/api/v1/files{remote}", {"command": "start"})
    return json.dumps(
        {"upload": upload_result.get("upload"), "start": start}
    )


if __name__ == "__main__":
    mcp.run(transport="stdio")
