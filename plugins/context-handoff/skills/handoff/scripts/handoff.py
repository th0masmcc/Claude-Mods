#!/usr/bin/env python3
"""context-handoff command-line entry point.

  handoff.py hook                      hook dispatcher (JSON on stdin)
  handoff.py status    [--session ID] [--json]
  handoff.py config    [show | set KEY VALUE | unset KEY] [--scope user|project]
  handoff.py snooze    [--minutes N] [--off] [--session ID]
  handoff.py unsnooze  [--session ID]
  handoff.py gather    [--session ID]           facts for /handoff create
  handoff.py write     --expect HASH|none [--session ID] < body.md
  handoff.py verify                              divergences for /handoff resume
  handoff.py statusline                          optional status-line bridge

Exit codes: 0 ok, 1 usage error, 2 refused (validation), 3 I/O error.
The "hook" command always exits 0 so that it can never disturb Claude Code.
"""

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from handofflib import VERSION, config, detect, document, gitinfo, hooks, paths, state, transcript  # noqa: E402
from handofflib.util import human_age, iso, now  # noqa: E402


def _emit(obj) -> None:
    sys.stdout.write(json.dumps(obj, ensure_ascii=False))
    sys.stdout.write("\n")


def cmd_hook(_args) -> int:
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
        handler = hooks.HANDLERS.get(payload.get("hook_event_name") or "")
        if handler:
            out = handler(payload)
            if out:
                _emit(out)
    except Exception as e:  # never break the user's session
        state.log_error(f"hook {type(e).__name__}: {e}")
    return 0


def _resolve_session(args, root):
    sid = getattr(args, "session", None) or ""
    if not sid or "${" in sid:
        sid = os.environ.get("CLAUDE_SESSION_ID") or os.environ.get("CLAUDE_CODE_SESSION_ID") or ""
    if not sid:
        latest = state.latest_project_session(root) or {}
        sid = latest.get("session_id") or ""
    return sid


def _session_state(args, root, refresh=True):
    sid = _resolve_session(args, root)
    st = state.load_session(sid) if sid else state.new_session_state("")
    if refresh and not st.get("transcript_path"):
        latest = state.latest_project_session(root) or {}
        if latest.get("session_id") == sid and latest.get("transcript_path"):
            st["transcript_path"] = latest["transcript_path"]
    if refresh and st.get("transcript_path"):
        st["transcript"] = transcript.scan(st.get("transcript") or {}, st["transcript_path"])
        if sid:
            state.save_session(st)
    return sid, st


def _pct(r):
    return "n/a" if r is None else f"{round(r * 100)}%"


def cmd_status(args) -> int:
    root = paths.project_root()
    cfg = config.load(root)
    sid, st = _session_state(args, root)
    hinfo = document.info(root, cfg)
    res = detect.evaluate(st, cfg, hinfo, ignore_cooldown=False)
    if args.json:
        _emit({"session": sid, "root": str(root), "evaluation": res, "handoff": hinfo,
               "transcript": {k: v for k, v in (st.get("transcript") or {}).items() if k != "vocab"}})
        return 0
    t = st.get("transcript") or {}
    lines = [f"context-handoff {VERSION} — project {root}"]
    lines.append(f"enabled: {cfg['enabled']} | mode: {cfg['mode']} | notify: {cfg['notify']} | "
                 f"threshold: {_pct(cfg['threshold'])} (urgent {_pct(cfg['urgent_threshold'])}) | min value: {cfg['min_value_score']}")
    lines.append(f"session: {sid or 'unknown (no hook has run yet in this project)'}")
    tok = f" ({res['tokens']:,} tokens)" if res.get("tokens") else ""
    lines.append(f"context: {_pct(res['ratio'])}{tok} of {res['window']:,} [ratio source: {res['ratio_source']}, window: {res['window_source']}]")
    if t.get("partial"):
        lines.append("note: transcript too large, only its tail was analysed; counters are partial")
    lines.append(f"compactions: {res['compactions']} | value score: {res['value']} {res['value_components'] or ''}")
    lines.append(f"activity: {t.get('prompts', 0)} prompts, {t.get('tool_calls', 0)} tool calls, "
                 f"{len(t.get('edited_files') or [])} files edited, {t.get('errors', 0)} tool errors, "
                 f"{t.get('focus_shifts', 0)} focus shift(s)")
    if res["propose"]:
        decision = f"would propose now (reason: {res['reason']})"
    elif res["reason"]:
        decision = f"relevant ({res['reason']}) but suppressed: {res['suppressed_by']}"
    elif res.get("suppressed_by"):
        decision = f"inactive: {res['suppressed_by']}"
    else:
        decision = "not needed yet"
    lines.append(f"decision: {decision}")
    lines.append(f"proposals this session: {len(st.get('proposals') or [])}/{cfg['max_proposals_per_session']}")
    sn = st.get("snooze")
    if sn:
        if sn.get("session_off"):
            lines.append("snooze: off for this session")
        elif float(sn.get("until") or 0) > now():
            lines.append(f"snooze: {human_age(float(sn['until']) - now())} left (re-armed early on +{_pct(cfg['rearm_delta'])} context or a compaction)")
    if hinfo.get("exists"):
        stale = "; ".join(hinfo.get("stale_reasons") or []) or "fresh"
        lines.append(f"handoff: {hinfo['path']} (~{hinfo.get('tokens')} tokens, {human_age(hinfo.get('age_seconds') or 0)} old) — {stale}")
    else:
        lines.append(f"handoff: none at {hinfo['path']}")
    if cfg["verbosity"] == "verbose":
        lines.append(f"transcript: {st.get('transcript_path') or 'unknown'}")
        lines.append(f"state dir: {paths.home_dir()}")
    print("\n".join(lines))
    return 0


def cmd_config(args) -> int:
    root = paths.project_root()
    action = args.action or "show"
    try:
        if action == "show":
            cfg = config.load(root)
            src = cfg.pop("_sources")
            for k in sorted(config.DEFAULTS):
                print(f"{k} = {json.dumps(cfg[k])}  [{src[k]}]  — {config.DESCRIPTIONS[k]}")
            print(f"\nuser file: {config.user_config_path()}\nproject file: {config.project_config_path(root)}"
                  "\nenv override: HANDOFF_<KEY> (e.g. in the \"env\" block of settings.json)")
            return 0
        if action == "set":
            if len(args.rest) != 2:
                print("usage: config set KEY VALUE", file=sys.stderr)
                return 1
            path = config.set_value(args.rest[0], args.rest[1], args.scope, root)
            print(f"{args.rest[0]} = {json.dumps(config.coerce(args.rest[0], args.rest[1]))} saved in {path}")
            return 0
        if action == "unset":
            if len(args.rest) != 1:
                print("usage: config unset KEY", file=sys.stderr)
                return 1
            path = config.unset_value(args.rest[0], args.scope, root)
            print(f"{args.rest[0]} reset to default in {path}")
            return 0
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    except OSError as e:
        print(f"error: cannot save configuration: {e}", file=sys.stderr)
        return 3
    print(f"unknown config action '{action}' (show | set | unset)", file=sys.stderr)
    return 1


def cmd_snooze(args) -> int:
    root = paths.project_root()
    cfg = config.load(root)
    sid, st = _session_state(args, root)
    if not sid:
        print("error: no session found; pass --session", file=sys.stderr)
        return 1
    if args.clear:
        st["snooze"] = None
        state.save_session(st)
        print("proposals re-enabled for this session")
        return 0
    minutes = args.minutes if args.minutes is not None else cfg["decline_snooze_minutes"]
    ratio, _, _ = detect.context_ratio(st, cfg)
    st["snooze"] = {"ts": now(), "until": now() + minutes * 60, "ratio": ratio or 0,
                    "compactions": detect.compaction_count(st), "session_off": bool(args.off)}
    state.save_session(st)
    if args.off:
        print("handoff proposals disabled for the rest of this session (/handoff config set enabled false to disable everywhere)")
    else:
        print(f"handoff proposals snoozed for {minutes} min, or until the context grows by "
              f"{_pct(cfg['rearm_delta'])} or a compaction happens")
    return 0


def cmd_gather(args) -> int:
    root = paths.project_root()
    cfg = config.load(root)
    sid, st = _session_state(args, root)
    git = document.git_snapshot(root, cfg)
    hinfo = document.info(root, cfg, git)
    t = st.get("transcript") or {}
    ratio, tokens, source = detect.context_ratio(st, cfg)
    complexity = detect.value_score(st, hinfo)[0]
    budget = min(int(cfg["max_tokens"]), 600 + 150 * complexity)
    out = {
        "project_root": str(root),
        "handoff_path": hinfo["path"],
        "existing": {k: hinfo.get(k) for k in ("exists", "hash", "tokens", "managed", "stale_reasons", "meta") if k in hinfo},
        "expect": hinfo.get("hash") or "none",
        "token_budget": budget,
        "max_tokens": cfg["max_tokens"],
        "session": sid,
        "context": {"ratio": None if ratio is None else round(ratio, 3), "source": source,
                    "compactions": detect.compaction_count(st)},
        "session_activity": {
            "prompts": t.get("prompts", 0),
            "edited_files": [document._rel_display(p, root) for p in (t.get("edited_files") or [])][-40:],
            "todo": t.get("todo"),
            "tool_errors": t.get("errors", 0),
        },
        "git": git,
        "write_command": f"{hooks.script_cmd()} write --session {sid} --expect {hinfo.get('hash') or 'none'}",
    }
    _emit(out)
    return 0


def cmd_write(args) -> int:
    root = paths.project_root()
    cfg = config.load(root)
    if args.path:
        cfg["path"] = args.path
    sid, st = _session_state(args, root, refresh=False)
    body = sys.stdin.read()
    if not body.strip():
        print("error: empty document on stdin", file=sys.stderr)
        return 1
    try:
        res = document.write(root, cfg, body, sid, args.expect)
    except document.WriteError as e:
        print(f"error: {e}", file=sys.stderr)
        return e.code
    if sid and res.get("status") in ("created", "updated", "unchanged"):
        ratio, _, _ = detect.context_ratio(st, cfg)
        st["last_handoff"] = {"ts": now(), "ratio": ratio or 0, "compactions": detect.compaction_count(st),
                              "path": res["path"]}
        state.save_session(st)
    _emit(res)
    return 0


def cmd_verify(args) -> int:
    root = paths.project_root()
    cfg = config.load(root)
    if args.path:
        cfg["path"] = args.path
    res = document.verify(root, cfg)
    if not res.get("exists"):
        print(f"no handoff document at {res['path']}", file=sys.stderr)
        return 2
    res.pop("hash", None)
    _emit(res)
    return 0


def cmd_statusline(args) -> int:
    """Optional bridge: record the exact context usage given to status lines."""
    try:
        data = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        data = {}
    sid = data.get("session_id")
    cw = data.get("context_window") or {}
    pct = cw.get("used_percentage")
    if sid:
        try:
            st = state.load_session(sid)
            st["statusline"] = {"ts": now(), "window": cw.get("context_window_size"),
                                "used_percentage": pct, "tokens": cw.get("total_input_tokens")}
            if data.get("transcript_path"):
                st["transcript_path"] = data["transcript_path"]
            state.save_session(st)
        except OSError:
            pass
    if not args.quiet:
        print(f"ctx {round(pct)}%" if isinstance(pct, (int, float)) else "ctx --")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="handoff.py", description="context-handoff for Claude Code")
    p.add_argument("--version", action="version", version=VERSION)
    sub = p.add_subparsers(dest="cmd")
    sub.add_parser("hook")
    s = sub.add_parser("status")
    s.add_argument("--session")
    s.add_argument("--json", action="store_true")
    c = sub.add_parser("config")
    c.add_argument("action", nargs="?")
    c.add_argument("rest", nargs="*")
    c.add_argument("--scope", choices=("user", "project"), default="user")
    z = sub.add_parser("snooze")
    z.add_argument("--session")
    z.add_argument("--minutes", type=int)
    z.add_argument("--off", action="store_true", help="disable proposals for the rest of the session")
    z.add_argument("--clear", action="store_true", help="cancel the snooze")
    u = sub.add_parser("unsnooze")
    u.add_argument("--session")
    g = sub.add_parser("gather")
    g.add_argument("--session")
    w = sub.add_parser("write")
    w.add_argument("--session")
    w.add_argument("--expect", required=True, help="hash printed by gather, or 'none'")
    w.add_argument("--path")
    v = sub.add_parser("verify")
    v.add_argument("--path")
    sl = sub.add_parser("statusline")
    sl.add_argument("--quiet", action="store_true")
    args = p.parse_args(argv)
    if args.cmd == "unsnooze":
        args.clear, args.minutes, args.off = True, None, False
        return cmd_snooze(args)
    handlers = {"hook": cmd_hook, "status": cmd_status, "config": cmd_config, "snooze": cmd_snooze,
                "gather": cmd_gather, "write": cmd_write, "verify": cmd_verify, "statusline": cmd_statusline}
    if args.cmd not in handlers:
        p.print_help()
        return 1
    return handlers[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
