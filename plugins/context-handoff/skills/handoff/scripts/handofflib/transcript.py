"""Incremental, local analysis of the Claude Code session transcript (JSONL).

Only metadata and cheap counters are kept: no conversation text is stored.
Prompt vocabulary is kept as truncated hashes, solely to notice changes of
topic. Each hook call reads only the bytes appended since the previous call.

Fields relied upon (observed in Claude Code 2.x transcripts):
  assistant records : message.usage.{input_tokens, cache_read_input_tokens,
                      cache_creation_input_tokens}, message.model,
                      message.content[].type == "tool_use"
  user records      : message.content (str | list), toolUseResult, isMeta
  system records    : subtype == "compact_boundary", compactMetadata.preTokens
  every record      : timestamp, isSidechain
Unknown/missing fields are simply ignored, so format drift degrades the
signals instead of breaking the hook.
"""

import json
import os
import re
import zlib

from .util import parse_iso

MAX_SCAN_BYTES = 16 * 1024 * 1024   # beyond this, only the tail is analysed
TAIL_BYTES = 4 * 1024 * 1024
MAX_FILES = 200
MAX_VOCAB = 800

EDIT_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
TASK_TOOLS = {"TaskCreate"}

_CONSTRAINT_RE = re.compile(
    r"\b(must|must not|never|always|do not|don't|avoid|instead of|rather than|required|"
    r"requirement|constraint|decided|decision|we will use|keep using|"
    r"doit|doivent|jamais|toujours|ne pas|ne jamais|évite|éviter|plutôt|obligatoire|"
    r"contrainte|décidé|décision|exigence|interdit|impératif)\b",
    re.IGNORECASE,
)
_WORD_RE = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ_][A-Za-zÀ-ÖØ-öø-ÿ0-9_.-]{3,}")
_STOP = set(
    """this that with from have will would could should there their what when where which
    while about into then than them they your yours just like also make some more most
    only very much need want please thanks thank does done okay sure here file files code
    dans pour avec cette mais sont plus tout tous faire fait être avoir peux veux merci
    comme quand aussi bien encore alors donc leur leurs notre votre nous vous elle elles
    sans sous chez entre fichier fichiers""".split()
)


def empty_stats() -> dict:
    return {
        "path": "", "offset": 0, "partial": False,
        "first_ts": None, "last_ts": None,
        "prompts": 0, "tool_calls": 0, "errors": 0,
        "edited_files": [], "todo": None, "task_creates": 0,
        "constraint_prompts": 0, "focus_shifts": 0, "vocab": [],
        "last_context_tokens": None, "max_context_tokens": 0, "model": None,
        "chars_since_boundary": 0,
        "boundaries": 0, "last_boundary_ts": None, "last_boundary_pre_tokens": None,
        "inferred_compactions": 0,
    }


def _prompt_text(record):
    """Return the text of a genuine human prompt, else None."""
    if record.get("toolUseResult") is not None or record.get("isMeta") or record.get("isSidechain"):
        return None
    msg = record.get("message") or {}
    content = msg.get("content")
    if isinstance(content, str):
        text = content
    elif isinstance(content, list):
        parts = []
        for item in content:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "tool_result":
                return None
            if item.get("type") == "text":
                parts.append(item.get("text") or "")
        text = "\n".join(parts)
    else:
        return None
    text = text.strip()
    if not text or text.startswith("<"):
        # <command-name>, <local-command-stdout>, <system-reminder>... are not prompts
        return None
    return text


def _content_chars(record) -> int:
    msg = record.get("message")
    if not isinstance(msg, dict):
        return 0
    content = msg.get("content")
    if isinstance(content, str):
        return len(content)
    total = 0
    if isinstance(content, list):
        for item in content:
            if isinstance(item, dict):
                for key in ("text", "content", "thinking"):
                    v = item.get(key)
                    if isinstance(v, str):
                        total += len(v)
                    elif isinstance(v, list):
                        total += len(json.dumps(v))
                if item.get("type") == "tool_use":
                    total += len(json.dumps(item.get("input") or {}))
    return total


def _vocab_hashes(text: str):
    words = {w.lower().strip(".-_") for w in _WORD_RE.findall(text[:4000])}
    return {zlib.crc32(w.encode("utf-8")) & 0xFFFFFF for w in words if w and w not in _STOP}


def _on_prompt(stats: dict, text: str) -> None:
    stats["prompts"] += 1
    if _CONSTRAINT_RE.search(text):
        stats["constraint_prompts"] += 2 if len(text) > 2000 else 1
    words = _vocab_hashes(text)
    known = set(stats["vocab"])
    if stats["prompts"] >= 3 and len(words) >= 6 and known:
        overlap = len(words & known) / len(words)
        if overlap < 0.15:
            stats["focus_shifts"] += 1
    merged = list(known | words)
    if len(merged) > MAX_VOCAB:
        merged = merged[-MAX_VOCAB:]
    stats["vocab"] = merged


def _on_assistant(stats: dict, record: dict) -> None:
    msg = record.get("message") or {}
    if msg.get("model") and not str(msg.get("model")).startswith("<"):
        stats["model"] = msg.get("model")
    usage = msg.get("usage")
    if isinstance(usage, dict):
        tokens = 0
        for key in ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"):
            v = usage.get(key)
            if isinstance(v, (int, float)):
                tokens += int(v)
        if tokens > 0:
            prev = stats.get("last_context_tokens")
            # A large drop without a compact_boundary record means the
            # compaction happened but was not observable directly.
            if prev and prev > 50_000 and tokens < prev * 0.5 and not stats.get("_boundary_since_usage"):
                stats["inferred_compactions"] += 1
                stats["chars_since_boundary"] = 0
            stats["last_context_tokens"] = tokens
            stats["max_context_tokens"] = max(stats.get("max_context_tokens") or 0, tokens)
            stats["_boundary_since_usage"] = False
    content = msg.get("content")
    if isinstance(content, list):
        for item in content:
            if not isinstance(item, dict) or item.get("type") != "tool_use":
                continue
            stats["tool_calls"] += 1
            name = item.get("name") or ""
            inp = item.get("input") if isinstance(item.get("input"), dict) else {}
            if name in EDIT_TOOLS:
                fp = inp.get("file_path") or inp.get("notebook_path")
                if isinstance(fp, str) and fp and fp not in stats["edited_files"]:
                    stats["edited_files"].append(fp)
                    del stats["edited_files"][:-MAX_FILES]
            elif name == "TodoWrite" and isinstance(inp.get("todos"), list):
                todos = [t for t in inp["todos"] if isinstance(t, dict)]
                stats["todo"] = {
                    "total": len(todos),
                    "completed": sum(1 for t in todos if t.get("status") == "completed"),
                    "in_progress": sum(1 for t in todos if t.get("status") == "in_progress"),
                }
            elif name in TASK_TOOLS:
                stats["task_creates"] += 1


def _on_user(stats: dict, record: dict) -> None:
    content = (record.get("message") or {}).get("content")
    if isinstance(content, list):
        for item in content:
            if isinstance(item, dict) and item.get("type") == "tool_result" and item.get("is_error"):
                stats["errors"] += 1
    text = _prompt_text(record)
    if text is not None:
        _on_prompt(stats, text)


def process_record(stats: dict, record: dict) -> None:
    if not isinstance(record, dict):
        return
    ts = parse_iso(record.get("timestamp") or "")
    if ts:
        if stats["first_ts"] is None:
            stats["first_ts"] = ts
        stats["last_ts"] = ts
    rtype = record.get("type")
    if rtype == "system" and record.get("subtype") == "compact_boundary":
        stats["boundaries"] += 1
        stats["last_boundary_ts"] = ts
        meta = record.get("compactMetadata") or {}
        stats["last_boundary_pre_tokens"] = meta.get("preTokens")
        stats["chars_since_boundary"] = 0
        stats["_boundary_since_usage"] = True
        return
    if record.get("isSidechain"):
        return
    if rtype in ("user", "assistant"):
        stats["chars_since_boundary"] += _content_chars(record)
    if rtype == "assistant":
        _on_assistant(stats, record)
    elif rtype == "user":
        _on_user(stats, record)


def scan(stats, path: str) -> dict:
    """Update ``stats`` with the bytes appended to ``path`` since last call."""
    if not stats or stats.get("path") != path:
        stats = empty_stats()
        stats["path"] = path
    base = empty_stats()
    for k, v in base.items():
        stats.setdefault(k, v)
    try:
        size = os.path.getsize(path)
    except OSError:
        return stats
    offset = int(stats.get("offset") or 0)
    if size < offset:                       # truncated or replaced: start over
        stats = empty_stats()
        stats["path"] = path
        offset = 0
    if size - offset > MAX_SCAN_BYTES:
        offset = size - TAIL_BYTES
        stats["partial"] = True
    if size == offset:
        return stats
    with open(path, "rb") as f:
        f.seek(offset)
        data = f.read(size - offset)
    if stats["partial"] and offset and offset == size - TAIL_BYTES:
        nl = data.find(b"\n")               # resynchronise on a line boundary
        if nl < 0:
            return stats
        offset += nl + 1
        data = data[nl + 1:]
    end = data.rfind(b"\n")
    if end < 0:
        return stats                         # incomplete line, wait for more
    for line in data[: end + 1].splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except ValueError:
            continue
        process_record(stats, record)
    stats["offset"] = offset + end + 1
    return stats
