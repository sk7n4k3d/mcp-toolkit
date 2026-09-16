#!/usr/bin/env python3
"""ollama-watch — poll a model catalogue, notify on change (new / updated / removed).

Source of truth: the public model list endpoint (JSON, no auth).
  - name        : model name
  - modified_at : publication / re-edition date
  - digest      : also changes on re-edition

Detection logic (state.json):
  - NEW     : name never seen before   -> strong signal
  - UPDATED : known name, newer digest or modified_at
  - REMOVED : name disappeared from the catalogue

First run (no state.json): initialise state WITHOUT notifying
(otherwise every existing model is announced).

Notification: POST to a notification topic configured via env vars.
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

OLLAMA_API = os.environ.get("OLLAMA_API", "https://ollama.com/api/tags")
NTFY_URL = os.environ.get("NTFY_URL", "http://ntfy:80")
NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "Ollama")
STATE_FILE = Path(os.environ.get("STATE_FILE", "/data/state.json"))
NOTIFY_FIRST_RUN = os.environ.get("NOTIFY_FIRST_RUN", "0") == "1"
TIMEOUT = int(os.environ.get("HTTP_TIMEOUT", "30"))

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "ollama-watch/1.0"})


def log(msg: str) -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def fetch_models() -> dict[str, dict]:
    """Return {name: {modified_at, digest, size}} from the tags endpoint."""
    r = SESSION.get(OLLAMA_API, timeout=TIMEOUT)
    r.raise_for_status()
    data = r.json()
    models = {}
    for m in data.get("models", []):
        name = m.get("name")
        if not name:
            continue
        models[name] = {
            "modified_at": m.get("modified_at", ""),
            "digest": m.get("digest", ""),
            "size": m.get("size", 0),
        }
    return models


def load_state() -> dict | None:
    if not STATE_FILE.exists():
        return None
    try:
        return json.loads(STATE_FILE.read_text())
    except (json.JSONDecodeError, OSError) as e:
        log(f"WARN state unreadable ({e}), starting fresh")
        return None


def save_state(models: dict[str, dict]) -> None:
    """Atomic write: temp file + os.replace, so a crash can't corrupt state."""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "models": models,
    }
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True))
    tmp.replace(STATE_FILE)


def _header_safe(value: str) -> str:
    """HTTP clients encode headers as latin-1, but notification services read
    them as UTF-8: accents sent naively come out as mojibake and emoji crash
    the send. Encode to UTF-8, decode as latin-1, so the re-encoded bytes
    arrive as the intended UTF-8."""
    return value.encode("utf-8").decode("latin-1")


def notfy(title: str, message: str, tags: str, priority: str = "default") -> bool:
    """POST to the notification endpoint. Returns True if accepted (2xx)."""
    try:
        r = SESSION.post(
            f"{NTFY_URL.rstrip('/')}/{NTFY_TOPIC}",
            data=message.encode("utf-8"),
            headers={
                "Title": _header_safe(title),
                "Tags": _header_safe(tags),
                "Priority": _header_safe(priority),
            },
            timeout=TIMEOUT,
        )
        if r.status_code >= 300:
            log(f"WARN notify HTTP {r.status_code}: {r.text[:200]}")
            return False
        return True
    except requests.RequestException as e:
        log(f"ERROR notify: {e}")
        return False


def run_once() -> int:
    log(f"fetch {OLLAMA_API}")
    try:
        current = fetch_models()
    except Exception as e:
        log(f"ERROR fetch: {e}")
        return 1

    log(f"{len(current)} models retrieved")

    previous_state = load_state()

    if previous_state is None:
        save_state(current)
        log("first run: state initialised (no notification)")
        if NOTIFY_FIRST_RUN:
            names = "\n".join(sorted(current))
            notfy(
                f"Init ({len(current)} models)",
                f"Initial state recorded.\n\n{names}",
                "new,ollama",
            )
        return 0

    prev = previous_state.get("models", {})

    new = sorted(set(current) - set(prev))
    removed = sorted(set(prev) - set(current))

    updated = []
    for name in sorted(set(current) & set(prev)):
        c, p = current[name], prev[name]
        if c.get("digest") and p.get("digest") and c["digest"] != p["digest"]:
            updated.append(name)
        elif c.get("modified_at") and c["modified_at"] != p.get("modified_at"):
            updated.append(name)

    if not (new or removed or updated):
        log("no change")
        save_state(current)
        return 0

    lines = []
    if new:
        lines.append(f"NEW ({len(new)})")
        for n in new:
            lines.append(f"  - {n}  ({current[n]['modified_at'][:10]})")
    if updated:
        lines.append(f"\nUPDATED ({len(updated)})")
        for n in updated:
            lines.append(f"  - {n}  ({current[n]['modified_at'][:10]})")
    if removed:
        lines.append(f"\nREMOVED ({len(removed)})")
        for n in removed:
            lines.append(f"  - {n}")

    message = "\n".join(lines)
    log("changes detected:\n" + message)

    if new:
        title = f"{len(new)} new model(s)"
        if len(new) == 1:
            title = f"new: {new[0]}"
        tags = "new,llama,ollama"
        priority = "high"
    elif removed:
        title = f"{len(removed)} model(s) removed"
        tags = "warning,ollama"
        priority = "high"
    else:
        title = f"{len(updated)} model(s) updated"
        tags = "recycle,ollama"
        priority = "default"

    notfy(title, message, tags, priority)
    save_state(current)
    log("state saved")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Watch a model catalogue, notify on change"
    )
    parser.add_argument("--loop", action="store_true", help="run in a loop")
    parser.add_argument(
        "--interval", type=int, default=21600, help="seconds between runs"
    )
    args = parser.parse_args()

    if not args.loop:
        return run_once()

    while True:
        try:
            run_once()
        except Exception as e:  # never let the loop die
            log(f"ERROR run: {e}")
        time.sleep(args.interval)


if __name__ == "__main__":
    sys.exit(main())
