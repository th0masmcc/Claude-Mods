"""Read-only Git inspection. Never modifies the repository."""

import re
import subprocess

MAX_LIST = 40
SENSITIVE_RE = re.compile(
    r"(^|/)(\.env(\..*)?|\.envrc|\.netrc|\.npmrc|\.pypirc|id_[rd]sa[^/]*|id_ecdsa[^/]*|id_ed25519[^/]*|"
    r"credentials[^/]*|secrets?[^/]*|[^/]*\.(pem|key|p12|pfx|keystore|jks|kdbx))$",
    re.IGNORECASE,
)


def is_sensitive_path(path: str) -> bool:
    return bool(SENSITIVE_RE.search(path.replace("\\", "/")))


def _git(root, *args, timeout=5):
    try:
        out = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True, text=True, timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    return out.stdout


def snapshot(root, exclude=()) -> dict:
    """Compact description of the repository state (or {"is_repo": False}).

    ``exclude``: paths relative to the root to ignore (the handoff itself).
    """
    if _git(root, "rev-parse", "--is-inside-work-tree") is None:
        return {"is_repo": False}
    info = {"is_repo": True}
    branch = (_git(root, "rev-parse", "--abbrev-ref", "HEAD") or "").strip()
    info["branch"] = branch or None
    head = (_git(root, "rev-parse", "--short=12", "HEAD") or "").strip()
    info["head"] = head or None  # None: repository without commits
    upstream = (_git(root, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}") or "").strip()
    info["upstream"] = upstream or None
    if upstream:
        counts = (_git(root, "rev-list", "--left-right", "--count", "HEAD...@{u}") or "").split()
        if len(counts) == 2:
            info["ahead"], info["behind"] = int(counts[0]), int(counts[1])
    status = _git(root, "status", "--porcelain=v1", "-z", "--untracked-files=normal") or ""
    staged, unstaged, untracked = [], [], []
    entries = status.split("\0")
    i = 0
    while i < len(entries):
        e = entries[i]
        i += 1
        if len(e) < 4:
            continue
        x, y, path = e[0], e[1], e[3:]
        if x in "RC":
            i += 1  # skip the rename source
        if path in exclude:
            continue
        label = path + (" [sensitive: content not read]" if is_sensitive_path(path) else "")
        if x == "?" and y == "?":
            untracked.append(label)
            continue
        if x not in " ?":
            staged.append(f"{x} {label}")
        if y not in " ?":
            unstaged.append(f"{y} {label}")
    info["dirty_count"] = len(staged) + len(unstaged) + len(untracked)
    info["staged"] = staged[:MAX_LIST]
    info["unstaged"] = unstaged[:MAX_LIST]
    info["untracked"] = untracked[:MAX_LIST]
    info["truncated"] = max(len(staged), len(unstaged), len(untracked)) > MAX_LIST
    if head:
        info["diffstat"] = (_git(root, "diff", "--shortstat", "HEAD") or "").strip() or None
        log = _git(root, "log", "-5", "--format=%h %s") or ""
        info["recent_commits"] = [l for l in log.splitlines() if l.strip()]
    stash = _git(root, "stash", "list") or ""
    info["stashes"] = len([l for l in stash.splitlines() if l.strip()])
    return info


def commits_since(root, sha: str):
    """None if ``sha`` is unknown (rebased/other clone), else list of commits."""
    if not sha or _git(root, "cat-file", "-e", f"{sha}^{{commit}}") is None:
        return None
    log = _git(root, "log", "--format=%h %s", f"{sha}..HEAD") or ""
    return [l for l in log.splitlines() if l.strip()]

