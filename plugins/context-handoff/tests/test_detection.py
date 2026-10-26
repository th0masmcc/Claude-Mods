"""Detection and proposal behaviour, exercised through the real hook entry point."""

import json
import unittest

from helpers import BASE_TS, Base, rich_session


class DetectionTests(Base):
    def test_short_session_no_proposal(self):
        tr = self.transcript
        tr.prompt("Fix the typo in README").assistant(tokens=12_000,
                                                      tools=[("Edit", {"file_path": "/p/README.md"})])
        tr.prompt("thanks").assistant(tokens=13_000)
        self.assertIsNone(self.prompt_hook())
        st = self.run_cli("status", "--session", "s1", check=0).stdout
        self.assertIn("decision: not needed yet", st)

    def test_long_rich_session_proposes_once(self):
        rich_session(self.transcript, final_tokens=130_000)  # 65 % of 200k
        out = self.prompt_hook()
        self.assertIsNotNone(out)
        ctx = out["hookSpecificOutput"]["additionalContext"]
        self.assertIn("/handoff create", ctx)
        self.assertIn("Never create it without consent", ctx)
        self.assertNotIn("systemMessage", out)  # default notify=assistant
        self.assertLess(len(ctx) / 4, 160, "proposal must stay cheap in tokens")
        # Next messages: no repetition (cooldown, then no significant change).
        self.assertIsNone(self.prompt_hook())
        self.set_now(BASE_TS + 3600)
        self.assertIsNone(self.prompt_hook())

    def test_long_but_simple_session_left_alone(self):
        tr = self.transcript
        tr.prompt("Read the logs and tell me what you see")
        for i in range(6):
            tr.assistant(tokens=30_000 * (i + 1), tools=[("Read", {"file_path": f"/var/log/big{i}.log"})])
            tr.tool_result()
        # 180k / 200k = 90 % but nothing worth preserving
        self.assertIsNone(self.prompt_hook())
        st = json.loads(self.run_cli("status", "--session", "s1", "--json", check=0).stdout)
        self.assertGreaterEqual(st["evaluation"]["ratio"], 0.89)
        self.assertFalse(st["evaluation"]["propose"])

    def test_detectable_compaction(self):
        rich_session(self.transcript, final_tokens=60_000, prompts=10, files=6)
        self.assertIsNone(self.prompt_hook())  # 30 %: no pressure yet
        out = self.hook("PreCompact", trigger="auto")
        self.assertIn("automatic compaction", out["systemMessage"])
        self.transcript.boundary(pre_tokens=170_000)
        self.hook("PostCompact", trigger="auto", compact_summary="...")
        self.hook("SessionStart", source="compact")
        self.transcript.prompt("go on").assistant(tokens=25_000)
        st = json.loads(self.run_cli("status", "--session", "s1", "--json", check=0).stdout)
        self.assertEqual(st["evaluation"]["compactions"], 1, "hooks and boundary must be deduplicated")
        out = self.prompt_hook()
        self.assertIn("compacted", out["hookSpecificOutput"]["additionalContext"])

    def test_undetectable_compaction_inferred_from_token_drop(self):
        rich_session(self.transcript, final_tokens=150_000, prompts=10, files=6)
        # no PreCompact/PostCompact hook and no boundary record: only a drop
        self.transcript.assistant(tokens=20_000)
        self.set_now(BASE_TS)
        st = json.loads(self.run_cli("status", "--session", "s1", "--json", check=0).stdout)
        self.assertEqual(st["transcript"]["inferred_compactions"], 1)
        out = self.prompt_hook()
        self.assertIsNotNone(out)
        self.assertIn("compacted", out["hookSpecificOutput"]["additionalContext"])

    def test_refusal_respected_until_significant_change(self):
        rich_session(self.transcript, final_tokens=124_000)          # 62 %
        self.assertIsNotNone(self.prompt_hook())
        self.run_cli("snooze", "--session", "s1", check=0)           # user declines: 120 min
        self.set_now(BASE_TS + 30 * 60)
        self.transcript.prompt("next").assistant(tokens=130_000)     # +3 %: not significant
        self.assertIsNone(self.prompt_hook())
        self.set_now(BASE_TS + 40 * 60)
        self.transcript.prompt("next").assistant(tokens=160_000)     # +18 %: significant change
        self.assertIsNotNone(self.prompt_hook())

    def test_snooze_expiry_alone_does_not_renag(self):
        rich_session(self.transcript, final_tokens=124_000)
        self.assertIsNotNone(self.prompt_hook())
        self.run_cli("snooze", "--session", "s1", check=0)
        self.set_now(BASE_TS + 3 * 3600)                             # snooze expired
        self.transcript.prompt("next").assistant(tokens=126_000)     # but nothing changed
        self.assertIsNone(self.prompt_hook())
        st = self.run_cli("status", "--session", "s1", check=0).stdout
        self.assertIn("no-significant-change", st)

    def test_snooze_blocks_within_delay(self):
        rich_session(self.transcript, final_tokens=124_000)
        self.run_cli("snooze", "--session", "s1", "--minutes", "60", check=0)
        self.assertIsNone(self.prompt_hook())
        st = self.run_cli("status", "--session", "s1", check=0).stdout
        self.assertIn("snoozed", st)

    def test_off_for_session_then_back_on(self):
        rich_session(self.transcript, final_tokens=170_000)
        self.run_cli("snooze", "--off", "--session", "s1", check=0)
        self.assertIsNone(self.prompt_hook())
        self.run_cli("unsnooze", "--session", "s1", check=0)
        self.assertIsNotNone(self.prompt_hook())

    def test_other_session_unaffected_by_session_off(self):
        rich_session(self.transcript, final_tokens=170_000)
        self.run_cli("snooze", "--off", "--session", "s1", check=0)
        self.assertIsNotNone(self.prompt_hook(session="s2"))

    def test_disabled_and_manual_mode(self):
        rich_session(self.transcript, final_tokens=170_000)
        self.env["HANDOFF_ENABLED"] = "false"
        self.assertIsNone(self.prompt_hook())
        del self.env["HANDOFF_ENABLED"]
        self.run_cli("config", "set", "mode", "manual", check=0)
        self.assertIsNone(self.prompt_hook())
        st = self.run_cli("status", "--session", "s1", check=0).stdout
        self.assertIn("manual-mode", st)

    def test_max_proposals_per_session(self):
        self.run_cli("config", "set", "max_proposals_per_session", "2", check=0)
        tokens = 124_000
        rich_session(self.transcript, final_tokens=tokens)
        shown = 0
        for k in range(6):
            self.set_now(BASE_TS + k * 3600)
            if self.prompt_hook():
                shown += 1
            tokens += 20_000
            self.transcript.prompt("more").assistant(tokens=min(tokens, 199_000))
        self.assertEqual(shown, 2)

    def test_slash_command_prompt_is_never_interrupted(self):
        rich_session(self.transcript, final_tokens=170_000)
        self.assertIsNone(self.prompt_hook("/handoff status"))
        self.assertIsNone(self.prompt_hook("yes please create the handoff"))

    def test_system_notify_mode_costs_no_model_tokens(self):
        rich_session(self.transcript, final_tokens=170_000)
        self.run_cli("config", "set", "notify", "system", check=0)
        out = self.prompt_hook()
        self.assertIn("/handoff create", out["systemMessage"])
        self.assertNotIn("hookSpecificOutput", out)

    def test_statusline_bridge_gives_exact_window(self):
        rich_session(self.transcript, final_tokens=300_000)  # > 200k: window inferred as 1M
        st = json.loads(self.run_cli("status", "--session", "s1", "--json", check=0).stdout)
        self.assertEqual(st["evaluation"]["window"], 1_000_000)
        payload = {"session_id": "s1", "context_window": {"context_window_size": 400_000, "used_percentage": 75,
                                                           "total_input_tokens": 300_000}}
        out = self.run_cli("statusline", stdin=json.dumps(payload), check=0).stdout
        self.assertEqual(out.strip(), "ctx 75%")
        st = json.loads(self.run_cli("status", "--session", "s1", "--json", check=0).stdout)
        self.assertEqual(st["evaluation"]["ratio_source"], "statusline")
        self.assertEqual(st["evaluation"]["window"], 400_000)

    def test_no_usage_data_falls_back_to_estimate(self):
        tr = self.transcript
        for i in range(12):
            tr.prompt(f"step {i}: we must not break the API " + "x" * 2000)
            tr._add({"type": "assistant", "message": {"content": [{"type": "text", "text": "y" * 40_000},
                     {"type": "tool_use", "name": "Edit", "input": {"file_path": f"/p/f{i}.py"}}]}})
        st = json.loads(self.run_cli("status", "--session", "s1", "--json", check=0).stdout)
        self.assertEqual(st["evaluation"]["ratio_source"], "estimate")
        self.assertGreater(st["evaluation"]["ratio"], 0.6)

    def test_hook_survives_garbage(self):
        p = self.run_cli("hook", stdin="not json", check=0)
        self.assertEqual(p.stdout, "")
        self.transcript.raw('{"type": "assistant", "message": {"usage": "weird"}}\n{broken\n{"partial": ')
        self.assertIsNone(self.prompt_hook())
        payload = {"hook_event_name": "UserPromptSubmit", "session_id": "s9", "cwd": str(self.proj),
                   "transcript_path": str(self.tmp / "missing.jsonl"), "prompt": "x"}
        p = self.run_cli("hook", stdin=json.dumps(payload), check=0)
        self.assertEqual(p.stdout, "")

    def test_incremental_scan_handles_partial_lines(self):
        from handofflib import transcript
        tr = self.transcript
        tr.prompt("first prompt we must keep").assistant(tokens=5000)
        stats = transcript.scan({}, str(tr.path))
        off = stats["offset"]
        tr.raw('{"type": "user", "message": {"content": "second')
        stats = transcript.scan(stats, str(tr.path))
        self.assertEqual(stats["offset"], off)
        self.assertEqual(stats["prompts"], 1)
        tr.raw(' prompt"}}\n')
        stats = transcript.scan(stats, str(tr.path))
        self.assertEqual(stats["prompts"], 2)

    def test_sidechain_and_meta_records_ignored(self):
        from handofflib import transcript
        tr = self.transcript
        tr._add({"type": "user", "isSidechain": True, "message": {"content": "subagent prompt"}})
        tr._add({"type": "user", "isMeta": True, "message": {"content": "meta"}})
        tr._add({"type": "user", "message": {"content": "<command-name>/handoff</command-name>"}})
        tr._add({"type": "assistant", "isSidechain": True,
                 "message": {"usage": {"input_tokens": 190_000}, "content": []}})
        stats = transcript.scan({}, str(tr.path))
        self.assertEqual(stats["prompts"], 0)
        self.assertIsNone(stats["last_context_tokens"])


if __name__ == "__main__":
    unittest.main()
