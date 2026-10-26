#!/usr/bin/env python3
"""Build the distributable archives into dist/ and check their structure.

  dist/context-handoff-web-<v>.zip   claude.ai: Customize > Plugins > Add > Upload plugin
                                     (a single top-level folder holding .claude-plugin/plugin.json)
  dist/context-handoff-code-<v>.zip  Claude Code: marketplace folder with both plugins, for
                                     `claude plugin marketplace add <extracted folder>`

Usage: python3 tools/package.py [--out DIR] [--only web|code]
"""

import argparse
import json
import re
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "plugins/context-handoff-web"
CODE = ROOT / "plugins/context-handoff"
SKIP_PARTS = {"__pycache__", ".pytest_cache", ".DS_Store", "tests"}
WEB_SKIP_TOP = {"tests", "docs"}            # not needed by claude.ai
MAX_FILES, MAX_BYTES = 5000, 200 * 1024 * 1024  # claude.ai plugin limits


def _files(base: Path, skip_top=()):
    for f in sorted(base.rglob("*")):
        if not f.is_file():
            continue
        rel = f.relative_to(base)
        if SKIP_PARTS & set(rel.parts) or f.suffix == ".pyc" or rel.parts[0] in skip_top:
            continue
        yield f, rel


def _add(z: zipfile.ZipFile, arcname: str, f: Path) -> None:
    info = zipfile.ZipInfo(arcname, date_time=(2026, 1, 1, 0, 0, 0))  # reproducible archives
    info.external_attr = (0o755 if f.suffix == ".py" else 0o644) << 16
    info.compress_type = zipfile.ZIP_DEFLATED
    z.writestr(info, f.read_bytes())


def build_web(out: Path) -> Path:
    version = json.loads((WEB / ".claude-plugin/plugin.json").read_text())["version"]
    target = out / f"context-handoff-web-{version}.zip"
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as z:
        for f, rel in _files(WEB, WEB_SKIP_TOP):
            _add(z, f"context-handoff-web/{rel.as_posix()}", f)
    return target


def build_code(out: Path) -> Path:
    version = json.loads((CODE / ".claude-plugin/plugin.json").read_text())["version"]
    target = out / f"context-handoff-code-{version}.zip"
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as z:
        for item in (".claude-plugin/marketplace.json", "README.md", "LICENSE"):
            _add(z, f"claude-mods/{item}", ROOT / item)
        for plugin in (CODE, WEB):
            for f, rel in _files(plugin):
                _add(z, f"claude-mods/plugins/{plugin.name}/{rel.as_posix()}", f)
    return target


def check_web_zip(path: Path) -> list:
    """Problems that would make claude.ai refuse the upload (empty list = OK)."""
    problems = []
    with zipfile.ZipFile(path) as z:
        infos = [i for i in z.infolist() if not i.is_dir()]
        names = [i.filename for i in infos]
        tops = {n.split("/", 1)[0] for n in names}
        if len(tops) != 1:
            problems.append(f"archive must hold a single top-level folder, found {sorted(tops)}")
        manifests = [n for n in names if n.endswith(".claude-plugin/plugin.json")]
        if len(manifests) != 1 or manifests[0].count("/") != 2:
            problems.append(f"expected exactly one <folder>/.claude-plugin/plugin.json, found {manifests}")
            return problems
        top = manifests[0].split("/", 1)[0]
        if any(n.startswith(f"{top}/bin/") for n in names):
            problems.append("a top-level bin/ directory prevents installation on claude.ai")
        if len(infos) > MAX_FILES or sum(i.file_size for i in infos) > MAX_BYTES:
            problems.append("plugin exceeds 5,000 files or 200 MB")
        manifest = json.loads(z.read(f"{top}/.claude-plugin/plugin.json"))
        for key in ("name", "version", "description"):
            if not manifest.get(key):
                problems.append(f"plugin.json: missing {key}")
        skills = {n.split("/")[2] for n in names if n.startswith(f"{top}/skills/") and n.count("/") >= 3}
        if not skills:
            problems.append("no skills/<name>/SKILL.md")
        for s in sorted(skills):
            md = f"{top}/skills/{s}/SKILL.md"
            if md not in names:
                problems.append(f"skills/{s}: SKILL.md missing")
                continue
            text = z.read(md).decode("utf-8")
            m = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
            fm = dict(re.findall(r"^(name|description):\s*(.*)$", m.group(1), re.MULTILINE)) if m else {}
            if fm.get("name") != s:
                problems.append(f"skills/{s}: frontmatter name must equal the folder name")
            if not re.fullmatch(r"[a-z0-9-]{1,64}", fm.get("name", "")):
                problems.append(f"skills/{s}: invalid name")
            if not 0 < len(fm.get("description", "")) <= 1024:
                problems.append(f"skills/{s}: description must be 1-1024 characters")
            if text.count("\n") >= 500:
                problems.append(f"skills/{s}: SKILL.md should stay under 500 lines")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "dist"))
    ap.add_argument("--only", choices=("web", "code"))
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    status = 0
    if args.only in (None, "web"):
        web = build_web(out)
        problems = check_web_zip(web)
        with zipfile.ZipFile(web) as z:
            count = len([i for i in z.infolist() if not i.is_dir()])
        print(f"{web} ({count} files) - structure: {'OK' if not problems else 'INVALID'}")
        for p in problems:
            print("  -", p)
        status = 1 if problems else 0
    if args.only in (None, "code"):
        code = build_code(out)
        print(f"{code}")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
