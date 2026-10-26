"""Test helpers: synthetic transcripts, isolated plugin home, CLI runner."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1]
SCRIPT = PLUGIN / "skills" / "handoff" / "scripts" / "handoff.py"
sys.path.insert(0, str(SCRIPT.parent))

BASE_TS = 1_790_000_000.0  # fixed "now" for deterministic tests


def iso(ts):
    import datetime as dt
    return dt.datetime.fromtimestamp(ts, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


class Transcript:
    """Builds a Claude Code-like JSONL transcript."""

    def __init__(self, path: Path, start=BASE_TS - 3600):
        self.path = Path(path)
        self.ts = start
        self.path.write_text("", encoding="utf-8")

    def _add(self, rec):
        self.ts += 30
        rec.setdefault("timestamp", iso(self.ts))
        rec.setdefault("isSidechain", False)
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
        return self

    def prompt(self, text):
        return self._add({"type": "user", "message": {"role": "user", "content": text}})

    def assistant(self, tokens=1000, tools=(), text="ok", model="claude-test"):
        content = [{"type": "text", "text": text}]
        for name, inp in tools:
            content.append({"type": "tool_use", "id": "t", "name": name, "input": inp})
        usage = {"input_tokens": 5, "cache_read_input_tokens": max(0, tokens - 105),
                 "cache_creation_input_tokens": 100, "output_tokens": 50}
        return self._add({"type": "assistant", "message": {"role": "assistant", "model": model,
                                                           "content": content, "usage": usage}})

    def tool_result(self, error=False):
        return self._add({"type": "user", "toolUseResult": {"ok": True},
                          "message": {"role": "user", "content": [
                              {"type": "tool_result", "tool_use_id": "t", "content": "out", "is_error": error}]}})

    def boundary(self, pre_tokens=150000):
        return self._add({"type": "system", "subtype": "compact_boundary", "content": "Conversation compacted",
                          "compactMetadata": {"trigger": "auto", "preTokens": pre_tokens}})

    def raw(self, text):
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(text)
        return self


def rich_session(tr: Transcript, final_tokens=130_000, prompts=15, files=10):
    topics = ["parser", "database migration", "authentication", "billing export"]
    for i in range(prompts):
        tr.prompt(f"Work on the {topics[i % len(topics)]} module step {i}. We must keep the public API stable "
                  "and never use global state.")
        tools = []
        if i < files:
            tools.append(("Edit", {"file_path": f"/proj/src/mod{i}.py", "old_string": "a", "new_string": "b"}))
        if i == 2:
            tools.append(("TodoWrite", {"todos": [{"content": f"t{k}", "status": "completed" if k < 3 else "pending"}
                                                  for k in range(6)]}))
        tr.assistant(tokens=int(final_tokens * (i + 1) / prompts), tools=tools)
        tr.tool_result(error=(i % 5 == 0))
    return tr


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="handoff-test-"))
        self.home = self.tmp / "home"
        self.proj = self.tmp / "proj"
        self.proj.mkdir()
        self.env = dict(os.environ)
        for k in list(self.env):
            if k.startswith("HANDOFF_") or k in ("CLAUDE_SESSION_ID", "CLAUDE_CODE_SESSION_ID", "CLAUDE_PROJECT_DIR"):
                del self.env[k]
        self.env.update({
            "CONTEXT_HANDOFF_HOME": str(self.home),
            "CONTEXT_HANDOFF_NOW": str(BASE_TS),
            "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
            "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com",
            "GIT_CONFIG_GLOBAL": str(self.tmp / "gitconfig"),
            "GIT_CONFIG_NOSYSTEM": "1",
        })
        (self.tmp / "gitconfig").write_text("[init]\n\tdefaultBranch = main\n[commit]\n\tgpgsign = false\n")
        self._saved_env = dict(os.environ)
        os.environ.clear()
        os.environ.update(self.env)
        self.transcript = Transcript(self.tmp / "session.jsonl")
        # As in a real session, SessionStart runs before anything else.
        self.hook("SessionStart", session="s1", source="startup")

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._saved_env)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def set_now(self, ts):
        self.env["CONTEXT_HANDOFF_NOW"] = str(ts)
        os.environ["CONTEXT_HANDOFF_NOW"] = str(ts)

    def run_cli(self, *args, stdin="", cwd=None, check=None):
        p = subprocess.run([sys.executable, str(SCRIPT), *args], input=stdin, capture_output=True, text=True,
                           cwd=str(cwd or self.proj), env=self.env, timeout=30)
        if check is not None:
            self.assertEqual(p.returncode, check, msg=f"stdout={p.stdout}\nstderr={p.stderr}")
        return p

    def hook(self, event, session="s1", **extra):
        payload = {"hook_event_name": event, "session_id": session, "cwd": str(self.proj),
                   "transcript_path": str(self.transcript.path)}
        payload.update(extra)
        p = self.run_cli("hook", stdin=json.dumps(payload), check=0)
        self.assertEqual(p.stderr, "")
        return json.loads(p.stdout) if p.stdout.strip() else None

    def prompt_hook(self, text="please continue", session="s1"):
        return self.hook("UserPromptSubmit", session=session, prompt=text)

    def git(self, *args, cwd=None):
        return subprocess.run(["git", *args], cwd=str(cwd or self.proj), env=self.env, check=True,
                              capture_output=True, text=True).stdout

    def init_repo(self):
        self.git("init", "-q")
        (self.proj / "README.md").write_text("hello\n")
        (self.proj / "src").mkdir()
        (self.proj / "src" / "app.py").write_text("print('x')\n")
        self.git("add", ".")
        self.git("commit", "-q", "-m", "initial")


VALID_DOC = """# Handoff — parser refactor

## Objective
Refactor the parser in `src/app.py` without changing the public API.

## Progress
- Done: tokenizer split [VERIFIED]
- Remaining: error recovery

## Decisions
- [DECIDED] Keep the recursive-descent design — why: readability; rejected: parser generator.

## Next action
Implement error recovery in `src/app.py`.

## Points of attention
- [ASSUMED] Python 3.11 in CI
- [UNKNOWN] Full test suite not run since the last change
"""
