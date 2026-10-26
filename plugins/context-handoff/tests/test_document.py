"""HANDOFF.md generation, safety, staleness and resume verification."""

import json
import os
import stat
import sys
import unittest
from pathlib import Path

from helpers import BASE_TS, VALID_DOC, Base, rich_session


class DocumentTests(Base):
    def gather(self, session="s1"):
        return json.loads(self.run_cli("gather", "--session", session, check=0).stdout)

    def write(self, body=VALID_DOC, expect=None, session="s1", code=0, extra=()):
        if expect is None:
            expect = self.gather(session)["expect"]
        return self.run_cli("write", "--session", session, "--expect", expect, *extra, stdin=body, check=code)

    # --- creation / existing documents ------------------------------------------------------
    def test_create_then_idempotent_then_update_with_backup(self):
        self.init_repo()
        res = json.loads(self.write().stdout)
        self.assertEqual(res["status"], "created")
        text = (self.proj / "HANDOFF.md").read_text()
        self.assertTrue(text.startswith("<!-- context-handoff:meta"))
        self.assertIn("Reference material, not instructions", text)
        self.assertEqual(text.count("context-handoff:meta"), 1)
        # Same content again: nothing rewritten, no duplicate header
        res = json.loads(self.write(body=text).stdout)
        self.assertEqual(res["status"], "unchanged")
        self.assertEqual((self.proj / "HANDOFF.md").read_text(), text)
        # Update: previous version backed up outside the repository
        res = json.loads(self.write(body=VALID_DOC.replace("error recovery", "error recovery and tests")).stdout)
        self.assertEqual(res["status"], "updated")
        self.assertTrue(res["backup"].startswith(str(self.home)))
        self.assertTrue(os.path.exists(res["backup"]))
        self.assertNotIn("HANDOFF.md", self.git("status", "--porcelain").replace("?? HANDOFF.md", ""))

    def test_existing_document_must_be_read_before_replacement(self):
        (self.proj / "HANDOFF.md").write_text("# My own notes\n\n## Objective\nkeep me\n")
        p = self.write(expect="none", code=2)
        self.assertIn("changed since it was read", p.stderr)
        self.assertEqual((self.proj / "HANDOFF.md").read_text(), "# My own notes\n\n## Objective\nkeep me\n")
        g = self.gather()
        self.assertTrue(g["existing"]["exists"])
        self.assertFalse(g["existing"]["managed"])
        self.write(expect=g["expect"])
        backups = list((self.home / "backups").rglob("HANDOFF-*.md"))
        self.assertEqual(len(backups), 1)
        self.assertIn("keep me", backups[0].read_text())

    def test_validation_refuses_incomplete_or_oversized(self):
        p = self.write(body="# Handoff\n\n## Progress\n- stuff\n", code=2)
        self.assertIn("objective", p.stderr)
        self.assertIn("next action", p.stderr)
        self.run_cli("config", "set", "max_tokens", "100", check=0)
        p = self.write(code=2)
        self.assertIn("too long", p.stderr)
        self.assertFalse((self.proj / "HANDOFF.md").exists())

    def test_french_headings_accepted(self):
        doc = "# Reprise\n\n## Objectif\nX [DECIDED]\n\n## Prochaine action\nY\n"
        self.write(body=doc)

    def test_backups_are_rotated(self):
        self.run_cli("config", "set", "backups", "2", check=0)
        for i in range(5):
            self.set_now(BASE_TS + i)
            self.write(body=VALID_DOC + f"\n<!-- {i} -->\n")
        self.assertEqual(len(list((self.home / "backups").rglob("HANDOFF-*.md"))), 2)

    def test_configured_location(self):
        self.run_cli("config", "set", "path", "docs/session/HANDOFF.md", "--scope", "project", check=0)
        self.assertTrue((self.proj / ".claude" / "context-handoff.json").exists())
        res = json.loads(self.write().stdout)
        self.assertTrue(res["path"].endswith("docs/session/HANDOFF.md"))
        self.assertTrue((self.proj / "docs" / "session" / "HANDOFF.md").exists())

    # --- secrets ------------------------------------------------------------------------------
    def test_secrets_are_redacted(self):
        secret_doc = VALID_DOC + (
            "\n## References\n- token used: ghp_" + "a" * 36 + "\n"
            "- DATABASE_PASSWORD=hunter2hunter2\n- url: postgres://admin:s3cretpw@db.local/app\n"
            "- AWS key " + "AKIA" + "ABCDEFGHIJKLMNOP\n- placeholder API_KEY=${API_KEY} stays\n"
            "-----BEGIN RSA " + "PRIVATE KEY-----\nMIIEow\n-----END RSA " + "PRIVATE KEY-----\n")
        res = json.loads(self.write(body=secret_doc).stdout)
        text = (self.proj / "HANDOFF.md").read_text()
        for leaked in ("ghp_aaaa", "hunter2", "s3cretpw", "AKIA" + "ABCDEFGHIJKLMNOP", "MIIEow"):
            self.assertNotIn(leaked, text)
        self.assertIn("API_KEY=${API_KEY}", text)
        self.assertEqual(set(res["secrets_redacted"]),
                         {"github-token", "secret-assignment", "url-credentials", "aws-access-key", "private-key"})

    def test_gather_never_reads_sensitive_files(self):
        self.init_repo()
        (self.proj / ".env").write_text("API_TOKEN=supersecretvalue123\n")
        (self.proj / "src" / "app.py").write_text("print('changed')\n")
        g = self.gather()
        dump = json.dumps(g)
        self.assertNotIn("supersecretvalue123", dump)
        self.assertIn(".env [sensitive: content not read]", g["git"]["untracked"])
        self.assertIn("M src/app.py", g["git"]["unstaged"])

    # --- git / no git ---------------------------------------------------------------------------
    def test_git_repo_with_uncommitted_changes(self):
        self.init_repo()
        (self.proj / "src" / "app.py").write_text("print('changed')\n")
        (self.proj / "new.txt").write_text("n\n")
        self.git("add", "new.txt")
        g = self.gather()
        self.assertTrue(g["git"]["is_repo"])
        self.assertEqual(g["git"]["branch"], "main")
        self.assertEqual(g["git"]["dirty_count"], 2)
        self.assertIn("A new.txt", g["git"]["staged"])
        self.assertIn("initial", g["git"]["recent_commits"][0])
        res = json.loads(self.write(expect=g["expect"]).stdout)
        self.assertEqual(res["meta"]["dirty"], "2")
        self.assertEqual(res["meta"]["branch"], "main")
        # nothing was committed or staged by the tool
        self.assertEqual(len(self.git("log", "--oneline").splitlines()), 1)
        self.assertNotIn("HANDOFF.md", self.git("diff", "--cached", "--name-only"))

    def test_project_without_git(self):
        g = self.gather()
        self.assertEqual(g["git"], {"is_repo": False})
        self.assertEqual(g["project_root"], str(self.proj))
        res = json.loads(self.write(expect=g["expect"]).stdout)
        self.assertEqual(res["meta"]["branch"], "")
        v = json.loads(self.run_cli("verify", check=0).stdout)
        self.assertFalse(v["git"]["is_repo"])

    # --- staleness / divergences ------------------------------------------------------------------
    def test_obsolete_document_detected(self):
        self.init_repo()
        self.write()
        (self.proj / "src" / "app.py").write_text("print('v2')\n")
        self.git("commit", "-qam", "second")
        self.git("checkout", "-qb", "feature")
        self.set_now(BASE_TS + 100 * 3600)
        v = json.loads(self.run_cli("verify", check=0).stdout)
        joined = " ".join(v["divergences"])
        self.assertIn("branch changed (main -> feature)", joined)
        self.assertIn("1 commit(s) since the handoff", joined)
        self.assertIn("older than 72 h", joined)
        self.assertEqual(v["commits_since"][0].split(" ", 1)[1], "second")
        st = self.run_cli("status", "--session", "s1", check=0).stdout
        self.assertIn("branch changed", st)

    def test_uncertain_or_contradictory_information_reported(self):
        self.init_repo()
        doc = VALID_DOC + "\n## References\n- `src/removed_module.py` — gone\n- `src/app.py` — main\n"
        self.write(body=doc)
        (self.proj / "scratch.txt").write_text("x\n")  # dirty count differs from the handoff
        v = json.loads(self.run_cli("verify", check=0).stdout)
        self.assertEqual(v["missing_paths"], ["src/removed_module.py"])
        self.assertTrue(any("uncommitted files: 0 at handoff, 1 now" in d for d in v["divergences"]))
        self.assertEqual(v["tags"]["ASSUMED"], 1)
        self.assertEqual(v["tags"]["UNKNOWN"], 1)
        res = json.loads(self.write(body="# H\n\n## Objective\nx\n\n## Next action\ny\n").stdout)
        self.assertTrue(any("no [VERIFIED]" in w for w in res["warnings"]))

    def test_verify_without_document(self):
        p = self.run_cli("verify", check=2)
        self.assertIn("no handoff document", p.stderr)

    # --- resume in a new session -------------------------------------------------------------------
    def test_resume_in_new_session(self):
        self.init_repo()
        rich_session(self.transcript, final_tokens=120_000)
        self.hook("SessionStart", session="old", source="startup")
        self.write(session="old")
        # The session that wrote it is not reminded of its own document
        self.assertIsNone(self.hook("SessionStart", session="old", source="resume"))
        out = self.hook("SessionStart", session="new", source="startup")
        self.assertIn("HANDOFF.md from an earlier session exists", out["hookSpecificOutput"]["additionalContext"])
        self.assertIn("not instructions", out["hookSpecificOutput"]["additionalContext"])
        self.assertLess(len(out["hookSpecificOutput"]["additionalContext"]) / 4, 80)
        self.assertIn("/handoff resume", out["systemMessage"])
        v = json.loads(self.run_cli("verify", check=0).stdout)
        self.assertEqual(v["divergences"], [])
        self.assertEqual(v["meta"]["session"], "old")
        # after a fresh handoff, the old session is not nagged again
        self.assertIsNone(self.prompt_hook(session="old"))

    def test_session_start_quiet_and_disabled(self):
        self.write()
        self.run_cli("config", "set", "session_start_hint", "false", check=0)
        self.run_cli("config", "set", "verbosity", "quiet", check=0)
        self.assertIsNone(self.hook("SessionStart", session="n", source="startup"))

    # --- write errors ---------------------------------------------------------------------------------
    @unittest.skipIf(sys.platform == "win32" or os.geteuid() == 0, "permissions are not enforced for root")
    def test_permission_denied(self):
        self.write()
        before = (self.proj / "HANDOFF.md").read_text()
        os.chmod(self.proj, stat.S_IRUSR | stat.S_IXUSR)
        try:
            p = self.write(body=VALID_DOC + "\nmore\n", code=3)
        finally:
            os.chmod(self.proj, 0o755)
        self.assertIn("cannot write", p.stderr)
        self.assertEqual((self.proj / "HANDOFF.md").read_text(), before)

    def test_unwritable_location_reports_io_error(self):
        # Works as root too: the parent of the target is a regular file.
        (self.proj / "blocker").write_text("x")
        p = self.write(code=3, extra=("--path", "blocker/HANDOFF.md"))
        self.assertIn("cannot write", p.stderr)
        self.assertEqual((self.proj / "blocker").read_text(), "x")

    def test_unsafe_targets_refused(self):
        self.init_repo()
        p = self.write(code=2, extra=("--path", ".git/HANDOFF.md"))
        self.assertIn(".git", p.stderr)
        p = self.write(code=2, extra=("--path", "src/app.py"))
        self.assertIn(".md", p.stderr)
        self.assertEqual((self.proj / "src" / "app.py").read_text(), "print('x')\n")

    def test_shipped_example_is_valid(self):
        example = (Path(__file__).resolve().parents[1] / "examples" / "HANDOFF.example.md").read_text()
        res = json.loads(self.write(body=example).stdout)
        self.assertEqual(res["warnings"], [])
        self.assertEqual(res["secrets_redacted"], {})
        text = (self.proj / "HANDOFF.md").read_text()
        self.assertEqual(text.count("context-handoff:meta"), 1, "old metadata header must be replaced")

    # --- configuration -------------------------------------------------------------------------------
    def test_config_layers_and_validation(self):
        self.run_cli("config", "set", "threshold", "0.7", check=0)
        self.run_cli("config", "set", "threshold", "0.5", "--scope", "project", check=0)
        self.env["HANDOFF_COOLDOWN_MINUTES"] = "5"
        out = self.run_cli("config", check=0).stdout
        self.assertIn('threshold = 0.5  [project]', out)
        self.assertIn('cooldown_minutes = 5  [env]', out)
        self.assertIn("between 0 and 1", self.run_cli("config", "set", "threshold", "1.5", check=1).stderr)
        self.run_cli("config", "set", "nope", "1", check=1)
        self.run_cli("config", "set", "notify", "popup", check=1)
        self.run_cli("config", "unset", "threshold", "--scope", "project", check=0)
        self.assertIn('threshold = 0.7  [user]', self.run_cli("config", check=0).stdout)


if __name__ == "__main__":
    unittest.main()
