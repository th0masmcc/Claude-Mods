#!/usr/bin/env python3
"""Build dist/context-handoff-<version>.zip: marketplace + plugin, no caches.

Usage: python3 tools/package.py [--out DIR]
"""

import argparse
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INCLUDE = [".claude-plugin/marketplace.json", "plugins/context-handoff", "README.md", "LICENSE"]
SKIP_PARTS = {"__pycache__", ".pytest_cache", ".DS_Store"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "dist"))
    args = ap.parse_args()
    manifest = json.loads((ROOT / "plugins/context-handoff/.claude-plugin/plugin.json").read_text())
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    target = out / f"context-handoff-{manifest['version']}.zip"
    count = 0
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as z:
        for item in INCLUDE:
            p = ROOT / item
            files = [p] if p.is_file() else sorted(f for f in p.rglob("*") if f.is_file())
            for f in files:
                rel = f.relative_to(ROOT)
                if SKIP_PARTS & set(rel.parts) or f.suffix == ".pyc":
                    continue
                info = zipfile.ZipInfo(f"claude-mods/{rel.as_posix()}")
                info.external_attr = (0o755 if f.suffix == ".py" else 0o644) << 16
                info.compress_type = zipfile.ZIP_DEFLATED
                z.writestr(info, f.read_bytes())
                count += 1
    print(f"{target} ({count} files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
