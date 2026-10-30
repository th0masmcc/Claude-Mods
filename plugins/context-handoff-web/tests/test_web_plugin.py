"""Static and functional checks of the claude.ai (web) plugin.

What can be checked without claude.ai: the manifest and skill format the
docs require, the upload archive layout, the finalisation script that runs in
the code-execution sandbox, the shared format with the Claude Code plugin,
and the cross-compatibility of documents between both versions.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

WEB = Path(__file__).resolve().parents[1]
ROOT = WEB.parents[1]
CODE = ROOT / "plugins" / "context-handoff"
SCRIPT = WEB / "skills" / "handoff" / "scripts" / "check_handoff.py"
SHARED_SRC = CODE / "skills" / "handoff" / "scripts" / "handofflib"

sys.path.insert(0, str(ROOT / "tools"))
import package  # noqa: E402

DOC = """# Handoff — pricing page rewrite

## Objective
Rewrite the pricing page copy for the three plans. Out of scope: design changes.

## Progress
- Done: Starter and Pro copy validated by the user [VERIFIED reported by the user]
- Remaining: Enterprise copy

## Decisions
- [DECIDED] Monthly prices shown first — why: most customers pay monthly; rejected: annual first.

## Key files and resources
- `pricing-v2.docx` — the user's draft, shared in the conversation

## Next action
Draft the Enterprise plan copy in the same tone (3 bullet points, 1 CTA).

## Open points and assumptions
- [ASSUMED] Legal does not need to review the copy
- [UNKNOWN] Final Enterprise price
"""


def frontmatter(text):
    m = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    return dict(re.findall(r"^([a-z-]+):\s*(.*)$", m.group(1), re.MULTILINE)) if m else {}


class Structure(unittest.TestCase):
    def test_manifest(self):
        m = json.loads((WEB / ".claude-plugin" / "plugin.json").read_text())
        self.assertEqual(m["name"], "context-handoff-web")
        self.assertRegex(m["name"], r"^[a-z0-9]+(-[a-z0-9]+)*$")
        for key in ("displayName", "version", "description", "license"):
            self.assertTrue(m.get(key), key)
        self.assertEqual(os.listdir(WEB / ".claude-plugin"), ["plugin.json"])

    def test_only_components_that_chat_loads(self):
        # Chat ignores hooks and agents; a top-level bin/ blocks installation entirely.
        for forbidden in ("bin", "hooks", "agents", ".mcp.json", "commands"):
            self.assertFalse((WEB / forbidden).exists(), forbidden)

    def test_skills_follow_the_agent_skills_spec(self):
        skills = sorted(p.name for p in (WEB / "skills").iterdir() if p.is_dir())
        self.assertEqual(skills, ["handoff", "handoff-resume"])
        for name in skills:
            text = (WEB / "skills" / name / "SKILL.md").read_text()
            fm = frontmatter(text)
            self.assertEqual(fm.get("name"), name)
            self.assertRegex(name, r"^[a-z0-9-]{1,64}$")
            self.assertTrue(0 < len(fm["description"]) <= 1024, f"{name}: {len(fm['description'])} chars")
            self.assertNotIn("<", fm["description"])  # no XML-like tags in descriptions
            self.assertLess(text.count("\n"), 500)
            self.assertEqual(set(fm), {"name", "description"}, "only fields every surface reads")

    def test_referenced_files_exist(self):
        skill = WEB / "skills" / "handoff"
        text = (skill / "SKILL.md").read_text()
        for ref in ("references/format.md", "scripts/check_handoff.py"):
            self.assertIn(ref, text)
            self.assertTrue((skill / ref).is_file(), ref)

    def test_no_false_automation_claims(self):
        text = " ".join((WEB / "skills" / s / "SKILL.md").read_text() for s in ("handoff", "handoff-resume"))
        self.assertIn("never quote a percentage", text.lower())
        self.assertNotRegex(text.lower(), r"\bhook(s)? (run|fire|detect)")

    def test_shared_modules_identical_to_claude_code_copy(self):
        for name in ("spec.py", "redact.py"):
            self.assertEqual((WEB / "skills/handoff/scripts" / name).read_bytes(),
                             (SHARED_SRC / name).read_bytes(),
                             f"{name} differs: run python3 tools/sync_shared.py")

    def test_format_reference_matches_shared_spec(self):
        sys.path.insert(0, str(SHARED_SRC.parent))
        from handofflib import spec
        fmt = (WEB / "skills/handoff/references/format.md").read_text()
        header = spec.build_header({"version": "1", "generated": "YYYY-MM-DD", "source": "claude-web"}).strip()
        self.assertIn(header, fmt, "header example must be exactly what the script generates")
        template = re.search(r"## Template.*?```markdown\n(.*?)\n```", fmt, re.DOTALL).group(1)
        heads = re.findall(r"^## (.+)$", template, re.MULTILINE)
        known = dict(spec.SECTIONS, **spec.EXTRA_SECTIONS)
        mapped = []
        for h in heads:
            keys = [k for k, rx in known.items() if re.search(rx, h.lower())]
            self.assertTrue(keys, f"template heading '{h}' is not recognised by the validator")
            mapped.append(keys[0])
        self.assertEqual(len(set(mapped)), len(mapped), "each heading maps to a distinct section")
        self.assertEqual(set(mapped), set(known))
        for tag in spec.TAGS:
            self.assertIn(f"[{tag}]", fmt)

    def test_marketplace_lists_both_plugins(self):
        mk = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text())
        entries = {p["name"]: p for p in mk["plugins"]}
        self.assertEqual(entries["context-handoff-web"]["source"], "./plugins/context-handoff-web")
        self.assertEqual(entries["context-handoff"]["source"], "./plugins/context-handoff")
        for name, folder in (("context-handoff-web", WEB), ("context-handoff", CODE)):
            v = json.loads((folder / ".claude-plugin" / "plugin.json").read_text())["version"]
            self.assertEqual(entries[name]["version"], v)


class Archive(unittest.TestCase):
    def setUp(self):
        self.out = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.out, ignore_errors=True)

    def test_upload_archive_layout(self):
        z = package.build_web(self.out)
        self.assertEqual(package.check_web_zip(z), [])
        with zipfile.ZipFile(z) as f:
            names = f.namelist()
        self.assertIn("context-handoff-web/.claude-plugin/plugin.json", names)
        self.assertIn("context-handoff-web/README.md", names)
        self.assertIn("context-handoff-web/LICENSE", names)
        self.assertFalse([n for n in names if "/tests/" in n or "__pycache__" in n or n.endswith(".pyc")])

    def test_archive_is_reproducible(self):
        a = package.build_web(self.out).read_bytes()
        b = package.build_web(self.out).read_bytes()
        self.assertEqual(a, b)

    def test_committed_archive_matches_sources(self):
        version = json.loads((WEB / ".claude-plugin" / "plugin.json").read_text())["version"]
        committed = ROOT / "dist" / f"context-handoff-web-{version}.zip"
        self.assertTrue(committed.is_file(), "run: python3 tools/package.py --only web")
        self.assertEqual(committed.read_bytes(), package.build_web(self.out).read_bytes(),
                         "dist/ archive is out of date: run python3 tools/package.py --only web")

    def test_checker_rejects_bad_archives(self):
        bad = self.out / "bad.zip"
        with zipfile.ZipFile(bad, "w") as f:
            f.writestr("a/.claude-plugin/plugin.json", '{"name": "x", "version": "1", "description": "d"}')
            f.writestr("a/bin/tool", "x")
            f.writestr("a/skills/Bad/SKILL.md", "---\nname: other\ndescription: d\n---\n")
            f.writestr("extra.txt", "beside the folder")
        problems = " ".join(package.check_web_zip(bad))
        self.assertIn("single top-level folder", problems)
        self.assertIn("bin/", problems)
        self.assertIn("folder name", problems)

    def test_code_archive_still_contains_marketplace_and_both_plugins(self):
        z = package.build_code(self.out)
        with zipfile.ZipFile(z) as f:
            names = set(f.namelist())
        for n in ("claude-mods/.claude-plugin/marketplace.json",
                  "claude-mods/plugins/context-handoff/hooks/hooks.json",
                  "claude-mods/plugins/context-handoff/skills/handoff/scripts/handoff.py",
                  "claude-mods/plugins/context-handoff-web/skills/handoff/SKILL.md"):
            self.assertIn(n, names)


class FinaliseScript(unittest.TestCase):
    """check_handoff.py, run as in the claude.ai code-execution sandbox."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        # The sandbox receives a copy of the skill folder only.
        self.skill = self.tmp / "handoff"
        shutil.copytree(WEB / "skills" / "handoff", self.skill)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_check(self, body, *args):
        draft = self.tmp / "draft.md"
        draft.write_text(body)
        p = subprocess.run([sys.executable, "-I", str(self.skill / "scripts" / "check_handoff.py"), str(draft), *args],
                           capture_output=True, text=True, cwd=str(self.tmp), timeout=30)
        return p.returncode, json.loads(p.stdout)

    def test_writes_document_with_shared_header(self):
        code, res = self.run_check(DOC, "--out", str(self.tmp / "out" / "HANDOFF.md"))
        self.assertEqual(code, 0, res)
        self.assertEqual(res["status"], "written")
        text = (self.tmp / "out" / "HANDOFF.md").read_text()
        self.assertTrue(text.startswith("<!-- context-handoff:meta\nversion: 1\ngenerated: "))
        self.assertIn("source: claude-web", text)
        self.assertIn("snapshot of an earlier Claude conversation", text)
        self.assertNotIn("Claude Code session", text)

    def test_default_output_falls_back_to_working_directory(self):
        code, res = self.run_check(DOC)
        self.assertEqual(code, 0)
        expected = Path("/mnt/user-data/outputs/HANDOFF.md") if Path("/mnt/user-data/outputs").is_dir() \
            else self.tmp / "HANDOFF.md"
        self.assertEqual(Path(res["path"]), expected)

    def test_idempotent_and_header_not_duplicated(self):
        out = str(self.tmp / "HANDOFF.md")
        self.run_check(DOC, "--out", out)
        first = Path(out).read_text()
        code, res = self.run_check(first, "--out", out)  # model re-submits the full file
        self.assertEqual(res["status"], "unchanged")
        self.assertEqual(Path(out).read_text().count("context-handoff:meta"), 1)

    def test_refuses_incomplete_or_oversized(self):
        code, res = self.run_check("# H\n\n## Progress\n- x\n", "--out", str(self.tmp / "H.md"))
        self.assertEqual(code, 2)
        self.assertEqual(len(res["errors"]), 2)
        self.assertFalse((self.tmp / "H.md").exists())
        code, res = self.run_check(DOC, "--max-tokens", "50", "--out", str(self.tmp / "H.md"))
        self.assertEqual(code, 2)
        self.assertIn("too long", res["errors"][0])

    def test_long_documents_are_accepted(self):
        # A very long thread needs a long handoff: 2,000 tokens was too small in real use.
        body = DOC + "\n## Context and background\n" + ("- detail line with figures 42 and reasons\n" * 700)
        code, res = self.run_check(body, "--out", str(self.tmp / "H.md"))
        self.assertEqual(code, 0, res)
        self.assertGreater(res["tokens"], 7000)

    def test_hard_limit_still_enforced(self):
        body = DOC + "\n## Context and background\n" + ("x" * 50_000)
        code, res = self.run_check(body, "--out", str(self.tmp / "H.md"))
        self.assertEqual(code, 2)
        self.assertIn("12000", res["errors"][0])

    def test_long_document_without_context_or_glossary_is_flagged(self):
        body = DOC + "\n## References\n" + ("- criteria 9, 10 and 11 apply to profile C\n" * 300)
        code, res = self.run_check(body, "--out", str(self.tmp / "H.md"))
        self.assertEqual(code, 0)
        joined = " ".join(res["warnings"])
        for word in ("Context and background", "Glossary", "Ways of working"):
            self.assertIn(word, joined)
        complete = body + "\n## Context and background\nx\n\n## Ways of working\ny\n\n## Glossary\n- **C** — z\n"
        code, res = self.run_check(complete, "--out", str(self.tmp / "H2.md"))
        self.assertFalse([w for w in res["warnings"] if "add a" in w])

    def test_short_document_not_flagged_for_glossary(self):
        code, res = self.run_check(DOC, "--out", str(self.tmp / "H.md"))
        self.assertFalse([w for w in res["warnings"] if "Glossary" in w])

    def test_masks_secrets(self):
        leaky = DOC + "\n## References\n- key: sk-ant-" + "x" * 30 + "\n- DB_PASSWORD=correcthorse\n"
        code, res = self.run_check(leaky, "--out", str(self.tmp / "H.md"))
        text = (self.tmp / "H.md").read_text()
        self.assertNotIn("sk-ant-xxxx", text)
        self.assertNotIn("correcthorse", text)
        self.assertEqual(set(res["secrets_redacted"]), {"anthropic-key", "secret-assignment"})

    def test_unwritable_output_reported(self):
        (self.tmp / "file").write_text("x")
        code, res = self.run_check(DOC, "--out", str(self.tmp / "file" / "HANDOFF.md"))
        self.assertEqual(code, 1)
        self.assertEqual(res["status"], "error")


class CrossCompatibility(unittest.TestCase):
    """A document made on the web resumes in Claude Code, and vice versa."""

    def test_web_document_accepted_by_claude_code_write_and_verify(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            skill = tmp / "handoff"
            shutil.copytree(WEB / "skills" / "handoff", skill)
            draft = tmp / "d.md"
            draft.write_text(DOC)
            web_out = tmp / "web.md"
            subprocess.run([sys.executable, "-I", str(skill / "scripts/check_handoff.py"), str(draft), "--out", str(web_out)],
                           check=True, capture_output=True)
            proj = tmp / "proj"
            proj.mkdir()
            env = dict(os.environ, CONTEXT_HANDOFF_HOME=str(tmp / "home"))
            cli = str(CODE / "skills/handoff/scripts/handoff.py")
            p = subprocess.run([sys.executable, cli, "write", "--expect", "none"], input=web_out.read_text(),
                               capture_output=True, text=True, cwd=str(proj), env=env)
            self.assertEqual(p.returncode, 0, p.stderr)
            text = (proj / "HANDOFF.md").read_text()
            self.assertEqual(text.count("context-handoff:meta"), 1)
            self.assertIn("source: claude-code", text)
            v = json.loads(subprocess.run([sys.executable, cli, "verify"], capture_output=True, text=True,
                                          cwd=str(proj), env=env).stdout)
            self.assertEqual(v["tags"]["DECIDED"], 1)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_claude_code_example_is_recognised_by_web_spec(self):
        sys.path.insert(0, str(WEB / "skills/handoff/scripts"))
        import spec as webspec
        example = (CODE / "examples" / "HANDOFF.example.md").read_text()
        meta = webspec.parse_meta(example)
        self.assertEqual(meta["branch"], "feature/csv-export")
        errors, _ = webspec.validate(webspec.strip_meta(example), 2000)
        self.assertEqual(errors, [])

    def test_web_example_is_valid(self):
        sys.path.insert(0, str(WEB / "skills/handoff/scripts"))
        import spec as webspec
        example = (WEB / "examples" / "HANDOFF.example.md").read_text()
        self.assertEqual(webspec.parse_meta(example).get("source"), "claude-web")
        errors, warnings = webspec.validate(webspec.strip_meta(example), 2000)
        self.assertEqual(errors, [])
        self.assertFalse([w for w in warnings if "tags" in w])


if __name__ == "__main__":
    unittest.main()
