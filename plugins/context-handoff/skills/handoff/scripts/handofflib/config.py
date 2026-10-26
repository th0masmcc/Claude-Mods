"""Configuration: defaults < user file < project file < environment.

User file:    ~/.claude/context-handoff/config.json
Project file: <project>/.claude/context-handoff.json
Environment:  HANDOFF_<KEY> (e.g. HANDOFF_ENABLED=0). Setting these in the
              "env" block of a Claude Code settings.json is the native way
              to configure the plugin per user or per project.
"""

import json
import os
from pathlib import Path

from . import paths
from .util import atomic_write_text

DEFAULTS = {
    "enabled": True,
    "mode": "auto",                    # auto | manual
    "notify": "assistant",             # assistant | system | both
    "threshold": 0.60,                 # context ratio that makes a handoff worth proposing
    "urgent_threshold": 0.80,          # ratio above which a lower value score suffices
    "min_value_score": 4,              # how much "state worth preserving" is required
    "context_window": "auto",          # "auto" or an integer number of tokens
    "cooldown_minutes": 20,            # minimum delay between two proposals
    "max_proposals_per_session": 3,
    "decline_snooze_minutes": 120,     # silence after "/handoff snooze" or a refusal
    "rearm_delta": 0.15,               # context growth that counts as a significant change
    "max_tokens": 2000,                # hard cap on HANDOFF.md size (approx. tokens)
    "path": "HANDOFF.md",              # relative to the project root, or absolute
    "verbosity": "normal",             # quiet | normal | verbose
    "session_start_hint": True,        # tell Claude (in ~40 tokens) that a handoff exists
    "stale_hours": 72,
    "backups": 5,                      # previous versions kept outside the repository
}

CHOICES = {
    "mode": ("auto", "manual"),
    "notify": ("assistant", "system", "both"),
    "verbosity": ("quiet", "normal", "verbose"),
}

DESCRIPTIONS = {
    "enabled": "Master switch for detection and proposals",
    "mode": "auto = proposals when relevant; manual = only explicit /handoff commands",
    "notify": "assistant = Claude offers it in its reply; system = UI notice only (0 tokens); both",
    "threshold": "Context usage ratio (0-1) from which a handoff may be proposed",
    "urgent_threshold": "Context ratio from which a smaller value score suffices",
    "min_value_score": "Minimum session complexity score before proposing",
    "context_window": "Context window size in tokens, or 'auto'",
    "cooldown_minutes": "Minimum minutes between two proposals",
    "max_proposals_per_session": "Maximum proposals in one session",
    "decline_snooze_minutes": "Minutes of silence after a refusal / snooze",
    "rearm_delta": "Context growth (ratio) that re-arms proposals early",
    "max_tokens": "Maximum HANDOFF.md size in approximate tokens",
    "path": "Handoff document location (relative to project root or absolute)",
    "verbosity": "Amount of detail in notices and status output",
    "session_start_hint": "Mention an existing handoff to Claude at session start",
    "stale_hours": "Age after which a handoff is considered stale",
    "backups": "Number of previous versions kept in the plugin home",
}


def user_config_path() -> Path:
    return paths.home_dir() / "config.json"


def project_config_path(root) -> Path:
    return Path(root) / ".claude" / "context-handoff.json"


def _read_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def coerce(key: str, value):
    """Convert a raw value (string from CLI/env, or JSON) to the key's type.

    Raises ValueError on invalid input.
    """
    if key not in DEFAULTS:
        raise ValueError(f"unknown setting '{key}' (known: {', '.join(sorted(DEFAULTS))})")
    default = DEFAULTS[key]
    if isinstance(default, bool):
        if isinstance(value, bool):
            return value
        s = str(value).strip().lower()
        if s in ("1", "true", "yes", "on", "oui"):
            return True
        if s in ("0", "false", "no", "off", "non"):
            return False
        raise ValueError(f"{key} expects true/false, got {value!r}")
    if key == "context_window":
        if str(value).strip().lower() == "auto":
            return "auto"
        n = int(value)
        if n < 10000:
            raise ValueError("context_window must be 'auto' or >= 10000")
        return n
    if isinstance(default, float):
        f = float(value)
        if not 0 < f <= 1:
            raise ValueError(f"{key} must be between 0 and 1")
        return f
    if isinstance(default, int):
        n = int(value)
        if n < 0:
            raise ValueError(f"{key} must be >= 0")
        return n
    s = str(value).strip()
    if key in CHOICES and s not in CHOICES[key]:
        raise ValueError(f"{key} must be one of {', '.join(CHOICES[key])}")
    if not s:
        raise ValueError(f"{key} cannot be empty")
    return s


def load(root=None) -> dict:
    """Effective configuration, plus a "_sources" map for /handoff config."""
    cfg = dict(DEFAULTS)
    sources = {k: "default" for k in DEFAULTS}
    layers = [("user", _read_json(user_config_path()))]
    if root is not None:
        layers.append(("project", _read_json(project_config_path(root))))
    env_layer = {}
    for key in DEFAULTS:
        raw = os.environ.get("HANDOFF_" + key.upper())
        if raw is not None and raw != "":
            env_layer[key] = raw
    layers.append(("env", env_layer))
    for name, layer in layers:
        for key, raw in layer.items():
            if key not in DEFAULTS:
                continue
            try:
                cfg[key] = coerce(key, raw)
                sources[key] = name
            except (ValueError, TypeError):
                pass  # invalid values are ignored, defaults stay in force
    cfg["_sources"] = sources
    return cfg


def set_value(key: str, raw, scope: str, root=None) -> Path:
    value = coerce(key, raw)
    path = project_config_path(root) if scope == "project" else user_config_path()
    data = _read_json(path)
    data[key] = value
    atomic_write_text(path, json.dumps(data, indent=2, sort_keys=True) + "\n")
    return path


def unset_value(key: str, scope: str, root=None) -> Path:
    if key not in DEFAULTS:
        raise ValueError(f"unknown setting '{key}'")
    path = project_config_path(root) if scope == "project" else user_config_path()
    data = _read_json(path)
    if key in data:
        del data[key]
        atomic_write_text(path, json.dumps(data, indent=2, sort_keys=True) + "\n")
    return path
