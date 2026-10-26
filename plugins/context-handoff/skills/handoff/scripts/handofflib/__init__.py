"""Core library for the context-handoff Claude Code plugin.

Standard library only (Python 3.8+). Every hook entry point must stay fast
(< ~100 ms on typical sessions) and must never fail loudly: Claude Code keeps
working even if this package is broken.
"""

VERSION = "1.0.0"
