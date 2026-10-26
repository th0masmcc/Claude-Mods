"""HANDOFF.md metadata, validation, controlled writing and verification."""

import hashlib
import os
import re
import shutil
from pathlib import Path

from . import gitinfo, paths
from .redact import redact
from .spec import (REQUIRED, SECTIONS, TAG_RE, build_header, parse_meta,  # noqa: F401
                   strip_meta, tag_counts, validate)
from .util import approx_tokens, atomic_write_text, human_age, iso, now, parse_iso

PATH_RE = re.compile(r"`([A-Za-z0-9_.@~-]*[/.][A-Za-z0-9_./@-]+)`")


def _rel_display(path: str, root) -> str:
    try:
        return str(Path(path).resolve().relative_to(Path(root).resolve()))
    except (ValueError, OSError):
        return path


def git_snapshot(root, cfg) -> dict:
    """Repository snapshot that ignores the handoff document itself."""
    target = paths.handoff_path(root, cfg["path"])
    try:
        rel = str(target.resolve().relative_to(Path(root).resolve())).replace(os.sep, "/")
    except (ValueError, OSError):
        rel = None
    return gitinfo.snapshot(root, exclude=(rel,) if rel else ())


def body_hash(text: str) -> str:
    norm = "\n".join(l.rstrip() for l in strip_meta(text).strip().splitlines())
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()[:16]


def file_hash(path: Path):
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()[:16]
    except OSError:
        return None


def _backup(target: Path, root, keep: int):
    if not target.exists() or keep <= 0:
        return None
    d = paths.home_dir() / "backups" / paths.project_key(root)
    d.mkdir(parents=True, exist_ok=True)
    stamp = iso(now()).replace(":", "").replace("-", "")
    dest = d / f"HANDOFF-{stamp}.md"
    n = 1
    while dest.exists():
        dest = d / f"HANDOFF-{stamp}-{n}.md"
        n += 1
    shutil.copy2(str(target), str(dest))
    olds = sorted(d.glob("HANDOFF-*.md"))
    for old in olds[:-keep]:
        try:
            old.unlink()
        except OSError:
            pass
    return dest


class WriteError(Exception):
    def __init__(self, message, code=2):
        super().__init__(message)
        self.code = code


def check_target(target: Path, root) -> None:
    resolved = target.resolve() if target.exists() else target.parent.resolve() / target.name
    if ".git" in resolved.parts:
        raise WriteError("refusing to write inside a .git directory")
    if target.exists() and not target.is_file():
        raise WriteError(f"{target} exists and is not a regular file")
    if target.suffix.lower() not in (".md", ".markdown"):
        raise WriteError("the handoff path must end with .md")


def write(root, cfg, body: str, session_id: str, expect: str, git=None) -> dict:
    """Validate, redact and atomically write the handoff.

    ``expect`` is the hash printed by ``gather`` for the existing file (or
    "none"): the write is refused if the file changed in between, which
    guarantees that an existing document was read before being replaced.
    """
    target = paths.handoff_path(root, cfg["path"])
    check_target(target, root)
    current = file_hash(target)
    if (expect or "none") != (current or "none"):
        raise WriteError(
            f"{target.name} changed since it was read (expected {expect}, found {current or 'none'}). "
            "Run 'gather' again, re-read the file and merge."
        )
    body = strip_meta(body).strip() + "\n"
    body, secrets = redact(body)
    errors, warnings = validate(body, int(cfg["max_tokens"]))
    if errors:
        raise WriteError("; ".join(errors))
    git = git if git is not None else git_snapshot(root, cfg)
    result = {"path": str(target), "secrets_redacted": secrets, "warnings": warnings}
    if target.exists():
        try:
            existing = target.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            raise WriteError(f"cannot read existing {target}: {e}", 3)
        if body_hash(existing) == body_hash(body):
            result["status"] = "unchanged"
            return result
    meta = {
        "version": "1",
        "generated": iso(now()),
        "source": "claude-code",
        "session": session_id or "",
        "branch": git.get("branch") if git.get("is_repo") else "",
        "head": git.get("head") if git.get("is_repo") else "",
        "dirty": str(git.get("dirty_count", 0)) if git.get("is_repo") else "",
        "tokens": str(approx_tokens(body)),
    }
    text = build_header(meta) + body
    try:
        backup = _backup(target, root, int(cfg["backups"]))
    except OSError as e:
        raise WriteError(f"cannot back up the existing document ({e}); nothing was changed", 3)
    try:
        atomic_write_text(target, text)
    except OSError as e:
        raise WriteError(f"cannot write {target}: {e.strerror or e}. The previous file is untouched; "
                         "fix the permissions or choose another location with '/handoff config set path <file>'", 3)
    result.update(status="updated" if backup else "created", backup=str(backup) if backup else None,
                  tokens=approx_tokens(body), meta=meta)
    return result


def info(root, cfg, git=None) -> dict:
    """Existence, metadata and staleness of the handoff document."""
    target = paths.handoff_path(root, cfg["path"])
    out = {"path": str(target), "exists": target.is_file()}
    if not out["exists"]:
        return out
    try:
        text = target.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        out["error"] = str(e)
        return out
    meta = parse_meta(text)
    out.update(meta=meta, hash=file_hash(target), tokens=approx_tokens(text), managed=bool(meta))
    generated = parse_iso(meta.get("generated", "")) or target.stat().st_mtime
    out["age_seconds"] = now() - generated
    stale = []
    if out["age_seconds"] > float(cfg["stale_hours"]) * 3600:
        stale.append(f"older than {cfg['stale_hours']} h ({human_age(out['age_seconds'])})")
    git = git if git is not None else git_snapshot(root, cfg)
    if git.get("is_repo") and meta:
        if meta.get("branch") and git.get("branch") and meta["branch"] != git["branch"]:
            stale.append(f"branch changed ({meta['branch']} -> {git['branch']})")
        if meta.get("head") and git.get("head") and not git["head"].startswith(meta["head"][:7]):
            since = gitinfo.commits_since(root, meta["head"])
            if since is None:
                stale.append(f"recorded commit {meta['head']} not found (rebase or other clone?)")
            elif since:
                stale.append(f"{len(since)} commit(s) since the handoff")
    if not meta:
        stale.append("no context-handoff metadata (hand-written or older format)")
    out["stale_reasons"] = stale
    return out


def verify(root, cfg) -> dict:
    """Compare the handoff with the actual repository, for /handoff resume."""
    git = git_snapshot(root, cfg)
    res = info(root, cfg, git)
    if not res.get("exists"):
        return res
    meta = res.get("meta") or {}
    res["git"] = {k: git.get(k) for k in ("is_repo", "branch", "head", "upstream", "ahead", "behind", "dirty_count")}
    divergences = list(res.get("stale_reasons") or [])
    if git.get("is_repo"):
        if meta.get("head"):
            since = gitinfo.commits_since(root, meta["head"])
            if since:
                res["commits_since"] = since[:10]
        then = meta.get("dirty")
        now_dirty = git.get("dirty_count", 0)
        if then not in (None, "") and str(now_dirty) != then:
            divergences.append(f"uncommitted files: {then} at handoff, {now_dirty} now")
        res["dirty_now"] = (git.get("staged") or []) + (git.get("unstaged") or []) + (git.get("untracked") or [])
        res["dirty_now"] = res["dirty_now"][:20]
    elif meta.get("branch"):
        divergences.append("the handoff was written in a Git repository but no repository is detected now")
    try:
        body = strip_meta(Path(res["path"]).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError):
        body = ""
    missing = []
    seen = set()
    for m in PATH_RE.finditer(body):
        p = m.group(1).rstrip(".:,")
        if p in seen or "://" in p or p.startswith(("-", "~")) or re.match(r"^\d+(\.\d+)+$", p):
            continue
        seen.add(p)
        candidate = Path(p) if os.path.isabs(p) else Path(root) / p
        if ("/" in p or re.search(r"\.[A-Za-z]{1,6}$", p)) and not candidate.exists():
            missing.append(p)
    if missing:
        divergences.append(f"{len(missing)} referenced path(s) not found")
        res["missing_paths"] = missing[:20]
    res["divergences"] = divergences
    res["tags"] = tag_counts(body)
    return res
