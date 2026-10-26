"""Small shared helpers."""

import datetime as _dt
import os
import tempfile
import time
from pathlib import Path


def now() -> float:
    # Tests freeze time through this variable.
    fake = os.environ.get("CONTEXT_HANDOFF_NOW")
    return float(fake) if fake else time.time()


def iso(ts: float) -> str:
    return _dt.datetime.fromtimestamp(ts, _dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(s: str):
    if not s:
        return None
    try:
        s = s.strip().replace("Z", "+00:00")
        d = _dt.datetime.fromisoformat(s)
        if d.tzinfo is None:
            d = d.replace(tzinfo=_dt.timezone.utc)
        return d.timestamp()
    except ValueError:
        return None


def human_age(seconds: float) -> str:
    seconds = max(0, int(seconds))
    if seconds < 3600:
        return f"{seconds // 60} min"
    if seconds < 86400:
        return f"{seconds / 3600:.1f} h"
    return f"{seconds / 86400:.1f} d"


def atomic_write_text(path, text: str) -> None:
    """Write via a temp file in the same directory, then rename.

    The previous file stays intact if anything fails before the rename.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix="." + path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        try:
            mode = os.stat(path).st_mode & 0o777 if path.exists() else 0o644
            os.chmod(tmp, mode)
        except OSError:
            pass
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def approx_tokens(text: str) -> int:
    return (len(text) + 3) // 4
