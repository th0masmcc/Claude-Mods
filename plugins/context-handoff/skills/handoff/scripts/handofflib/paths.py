"""Filesystem locations: plugin home, project root, per-project keys."""

import hashlib
import os
import subprocess
from pathlib import Path


def home_dir() -> Path:
    """Directory holding config, per-session state and backups.

    Lives outside every repository so that detection never touches project
    files. Overridable with CONTEXT_HANDOFF_HOME (used by the tests).
    """
    override = os.environ.get("CONTEXT_HANDOFF_HOME")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".claude" / "context-handoff"


def git_toplevel(cwd: str):
    try:
        out = subprocess.run(
            ["git", "-C", cwd, "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=3,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    top = out.stdout.strip()
    return top or None


def project_root(cwd=None) -> Path:
    """Git top-level when available, else CLAUDE_PROJECT_DIR, else cwd."""
    cwd = cwd or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    top = git_toplevel(cwd)
    if top:
        return Path(top)
    env_dir = os.environ.get("CLAUDE_PROJECT_DIR")
    if env_dir and Path(env_dir).is_dir():
        return Path(env_dir)
    return Path(cwd)


def project_key(root) -> str:
    return hashlib.sha256(str(Path(root).resolve()).encode("utf-8")).hexdigest()[:16]


def handoff_path(root, configured: str) -> Path:
    p = Path(os.path.expanduser(configured or "HANDOFF.md"))
    if not p.is_absolute():
        p = Path(root) / p
    return p
