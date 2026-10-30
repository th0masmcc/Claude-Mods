#!/usr/bin/env python3
"""Finalise a HANDOFF.md drafted in a claude.ai conversation.

Runs in the code-execution sandbox when it is available (standard library
only). It masks secrets, checks the required sections and the size, adds the
metadata header shared with the Claude Code plugin, and writes the file where
the user can download it.

  python3 check_handoff.py DRAFT.md [--out PATH] [--max-tokens 12000]

Exit codes: 0 written or unchanged, 1 usage/I-O error, 2 refused (fix and rerun).
Prints one JSON object describing the result.
"""

import argparse
import datetime as dt
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from redact import redact  # noqa: E402
from spec import approx_tokens, build_header, sections_found, strip_meta, validate  # noqa: E402

SHARED_OUTPUTS = Path("/mnt/user-data/outputs")  # files the user can download on claude.ai
MAX_TOKENS = 12000   # web documents carry the whole context: the conversation is the only source
LONG_DOC = 2500      # above this size, a document must explain itself


def self_containment_warnings(body: str) -> list:
    """A long handoff without context or glossary is usually unreadable on its own."""
    if approx_tokens(body) < LONG_DOC:
        return []
    found = sections_found(body)
    hints = {
        "context": "add a 'Context and background' section: the reader has only this file",
        "glossary": "add a 'Glossary' defining every label, code and abbreviation used",
        "agreements": "add 'Ways of working': Claude's role and the user's preferences",
    }
    return [msg for key, msg in hints.items() if key not in found]


def default_out() -> Path:
    base = SHARED_OUTPUTS if SHARED_OUTPUTS.is_dir() else Path.cwd()
    return base / "HANDOFF.md"


def write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".HANDOFF.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("draft")
    ap.add_argument("--out")
    ap.add_argument("--max-tokens", type=int, default=MAX_TOKENS)
    args = ap.parse_args(argv)
    try:
        raw = Path(args.draft).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        print(json.dumps({"status": "error", "error": f"cannot read draft: {e}"}))
        return 1
    body = strip_meta(raw).strip() + "\n"
    body, secrets = redact(body)
    errors, warnings = validate(body, args.max_tokens)
    warnings = self_containment_warnings(body) + warnings
    if errors:
        print(json.dumps({"status": "refused", "errors": errors, "warnings": warnings,
                          "secrets_redacted": secrets}, ensure_ascii=False))
        return 2
    out = Path(args.out) if args.out else default_out()
    if out.is_file():
        try:
            if strip_meta(out.read_text(encoding="utf-8")).strip() == body.strip():
                print(json.dumps({"status": "unchanged", "path": str(out), "secrets_redacted": secrets,
                                  "warnings": warnings}, ensure_ascii=False))
                return 0
        except (OSError, UnicodeDecodeError):
            pass
    meta = {
        "version": "1",
        "generated": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "claude-web",
        "tokens": str(approx_tokens(body)),
    }
    try:
        write_atomic(out, build_header(meta) + body)
    except OSError as e:
        print(json.dumps({"status": "error", "error": f"cannot write {out}: {e}"}))
        return 1
    print(json.dumps({"status": "written", "path": str(out), "tokens": approx_tokens(body),
                      "secrets_redacted": secrets, "warnings": warnings}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
