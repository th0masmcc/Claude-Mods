#!/usr/bin/env python3
"""Copy the shared HANDOFF.md format modules into the web plugin.

Canonical copies live in the Claude Code plugin (handofflib/). The web
plugin's skill folder must be self-contained, because claude.ai copies only
that folder into its code-execution sandbox. Run after editing spec.py or
redact.py; tests fail while the copies differ.
"""

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "plugins/context-handoff/skills/handoff/scripts/handofflib"
DST = ROOT / "plugins/context-handoff-web/skills/handoff/scripts"
SHARED = ("spec.py", "redact.py")

if __name__ == "__main__":
    for name in SHARED:
        shutil.copyfile(SRC / name, DST / name)
        print(f"{SRC / name} -> {DST / name}")
