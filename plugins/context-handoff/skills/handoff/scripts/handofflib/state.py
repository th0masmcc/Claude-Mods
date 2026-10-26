"""Per-session and per-project state, stored in the plugin home."""

import json
import os
import re
from pathlib import Path

from . import paths
from .util import atomic_write_text, now

_SAFE_ID = re.compile(r"[^A-Za-z0-9_.-]")


def _sessions_dir() -> Path:
    return paths.home_dir() / "sessions"


def _session_file(session_id: str) -> Path:
    sid = _SAFE_ID.sub("_", session_id or "unknown")[:128]
    return _sessions_dir() / f"{sid}.json"


def new_session_state(session_id: str) -> dict:
    return {
        "session_id": session_id,
        "created": now(),
        "transcript": {},          # incremental scan, see transcript.py
        "compactions": [],         # [{"ts", "trigger", "source"}]
        "proposals": [],           # [{"ts", "ratio", "reason"}]
        "snooze": None,            # {"until", "ratio", "compactions", "session_off"}
        "last_handoff": None,      # {"ts", "ratio", "compactions"}
        "statusline": None,        # {"ts", "window", "used_percentage"}
        "pending_compaction": None,
    }


def load_session(session_id: str) -> dict:
    path = _session_file(session_id)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            base = new_session_state(session_id)
            base.update(data)
            return base
    except (OSError, ValueError):
        pass
    return new_session_state(session_id)


def save_session(st: dict) -> None:
    st["updated"] = now()
    atomic_write_text(_session_file(st.get("session_id")), json.dumps(st, separators=(",", ":")))


def remember_project_session(root, session_id: str, transcript_path: str = "") -> None:
    """Map project -> latest session, so CLI commands find the right state."""
    p = paths.home_dir() / "projects" / (paths.project_key(root) + ".json")
    data = {"root": str(root), "session_id": session_id, "transcript_path": transcript_path, "ts": now()}
    atomic_write_text(p, json.dumps(data))


def latest_project_session(root):
    p = paths.home_dir() / "projects" / (paths.project_key(root) + ".json")
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def prune_old_sessions(max_age_days: int = 30) -> int:
    d = _sessions_dir()
    if not d.is_dir():
        return 0
    cutoff = now() - max_age_days * 86400
    removed = 0
    for f in d.glob("*.json"):
        try:
            if f.stat().st_mtime < cutoff:
                f.unlink()
                removed += 1
        except OSError:
            pass
    return removed


def log_error(message: str) -> None:
    """Append to a small local log; never raises."""
    try:
        p = paths.home_dir() / "errors.log"
        p.parent.mkdir(parents=True, exist_ok=True)
        if p.exists() and p.stat().st_size > 200_000:
            p.write_text("", encoding="utf-8")
        with open(p, "a", encoding="utf-8") as f:
            f.write(f"{int(now())} {message}\n")
    except OSError:
        pass
