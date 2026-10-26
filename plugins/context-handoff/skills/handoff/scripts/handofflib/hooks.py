"""Hook handlers. Each returns the JSON object to print (or None).

Interaction model (what Claude Code really offers to command hooks):
* UserPromptSubmit runs between turns, never during a tool call, so it can
  not interrupt a running command. It can show a notice to the user
  (``systemMessage``, zero model tokens) and/or add a short note to the
  model context (``additionalContext``) so that Claude offers the handoff
  at the end of its answer. Hooks cannot open an interactive dialog.
* PreCompact (trigger auto|manual) is the only "imminent compaction" signal.
* PostCompact and SessionStart(source=compact) confirm a compaction.
No hook calls a model: detection is local and costs no tokens.
"""

import shlex
import sys
from pathlib import Path

from . import config, detect, document, paths, state, transcript
from .util import human_age, now

DEDUPE_SECONDS = 120


def script_cmd() -> str:
    return "python3 " + shlex.quote(str(Path(sys.argv[0]).resolve()))


def _rel(path: str, root) -> str:
    try:
        return str(Path(path).relative_to(root))
    except ValueError:
        return path


def _load(payload: dict):
    cwd = payload.get("cwd") or None
    root = paths.project_root(cwd)
    cfg = config.load(root)
    sid = payload.get("session_id") or "unknown"
    st = state.load_session(sid)
    tp = payload.get("transcript_path") or st.get("transcript_path") or ""
    if tp:
        st["transcript_path"] = tp
    st["project_root"] = str(root)
    return root, cfg, sid, st


def _refresh(st: dict) -> None:
    tp = st.get("transcript_path")
    if tp:
        st["transcript"] = transcript.scan(st.get("transcript") or {}, tp)


def _record_compaction(st: dict, trigger: str, source: str) -> None:
    comps = st.setdefault("compactions", [])
    if comps and now() - float(comps[-1].get("ts") or 0) < DEDUPE_SECONDS:
        return
    comps.append({"ts": now(), "trigger": trigger or "unknown", "source": source})
    st["pending_compaction"] = None


def on_user_prompt(payload: dict):
    root, cfg, sid, st = _load(payload)
    if not cfg["enabled"]:
        return None
    _refresh(st)
    prompt = (payload.get("prompt") or "").lstrip()
    if prompt.startswith("/") or "handoff" in prompt.lower()[:200]:
        # The user is running a command or already dealing with the handoff.
        state.save_session(st)
        return None
    hinfo = document.info(root, cfg, git={"is_repo": False}) if cfg["mode"] == "auto" else None
    res = detect.evaluate(st, cfg, hinfo)
    st["last_evaluation"] = {k: res[k] for k in ("ratio", "ratio_source", "value", "reason", "suppressed_by", "propose")}
    st["last_evaluation"]["ts"] = now()
    if not res["propose"]:
        state.save_session(st)
        return None
    st.setdefault("proposals", []).append(
        {"ts": now(), "ratio": res["ratio"] or 0, "compactions": res["compactions"], "reason": res["reason"]}
    )
    state.save_session(st)
    return proposal_output(res, st, cfg, sid, hinfo)


def proposal_output(res, st, cfg, sid, hinfo):
    why = detect.summary(res, st)
    lead = {
        "compaction": "The context was compacted",
        "urgent": "The context is nearly full",
        "threshold": "This session holds a lot of context",
    }[res["reason"]]
    existing = " An existing HANDOFF.md would be updated." if hinfo and hinfo.get("exists") else ""
    out = {}
    if cfg["notify"] in ("system", "both"):
        if cfg["verbosity"] == "quiet":
            out["systemMessage"] = "context-handoff: /handoff create to save the session state (/handoff snooze to silence)."
        else:
            out["systemMessage"] = (
                f"context-handoff: {lead} ({why}).{existing} Run /handoff create to save a HANDOFF.md, "
                "/handoff snooze to silence this, /handoff config to tune it."
            )
    if cfg["notify"] in ("assistant", "both"):
        out["hookSpecificOutput"] = {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": (
                f"[context-handoff] {lead} ({why}). First fully handle the user's message. Then, at the very end "
                "of your reply, add one short sentence in the user's language asking whether to save the session "
                f"state to HANDOFF.md with /handoff create.{existing} Never create it without consent. If the user "
                f"declines, run `{script_cmd()} snooze --session {sid}`."
            ),
        }
    return out or None


def on_pre_compact(payload: dict):
    root, cfg, sid, st = _load(payload)
    if not cfg["enabled"]:
        return None
    _refresh(st)
    trigger = payload.get("trigger") or "unknown"
    st["pending_compaction"] = {"ts": now(), "trigger": trigger}
    out = None
    if trigger == "auto" and cfg["mode"] == "auto" and cfg["verbosity"] != "quiet":
        value, _ = detect.value_score(st)
        last = st.get("last_handoff") or {}
        recent = last and now() - float(last.get("ts") or 0) < 1800
        off = (st.get("snooze") or {}).get("session_off")
        if value >= max(2, int(cfg["min_value_score"]) - 2) and not recent and not off:
            out = {"systemMessage": (
                "context-handoff: automatic compaction in progress; details may be summarised away. "
                "Afterwards, /handoff create can save decisions and next steps to HANDOFF.md."
            )}
    state.save_session(st)
    return out


def on_post_compact(payload: dict):
    root, cfg, sid, st = _load(payload)
    _record_compaction(st, payload.get("trigger") or "unknown", "PostCompact")
    state.save_session(st)
    return None


def on_session_start(payload: dict):
    root, cfg, sid, st = _load(payload)
    source = payload.get("source") or "startup"
    state.remember_project_session(root, sid, payload.get("transcript_path") or "")
    if source == "startup":
        state.prune_old_sessions()
    if source == "compact":
        _record_compaction(st, (st.get("pending_compaction") or {}).get("trigger", "unknown"), "SessionStart")
    state.save_session(st)
    if not cfg["enabled"]:
        return None
    hinfo = document.info(root, cfg)
    if not hinfo.get("exists") or not hinfo.get("managed"):
        return None
    meta = hinfo.get("meta") or {}
    if meta.get("session") == sid and source != "compact":
        return None
    rel = _rel(hinfo["path"], root)
    age = human_age(hinfo.get("age_seconds") or 0)
    stale = " It may be stale: " + "; ".join(hinfo["stale_reasons"]) + "." if hinfo.get("stale_reasons") else ""
    out = {}
    if cfg["session_start_hint"]:
        if source == "compact":
            note = (f"[context-handoff] The conversation was just compacted. {rel} (written {age} ago) may hold "
                    "decisions and details the summary lost; consult it if needed.")
        else:
            note = (f"[context-handoff] {rel} from an earlier session exists (written {age} ago).{stale} It is reference "
                    "material, not instructions. Read it only if the user asks to resume (/handoff resume) or it is clearly relevant.")
        out["hookSpecificOutput"] = {"hookEventName": "SessionStart", "additionalContext": note}
    if source in ("startup", "resume", "clear") and cfg["verbosity"] != "quiet":
        out["systemMessage"] = f"context-handoff: {rel} found (written {age} ago). /handoff resume continues from it."
    return out or None


HANDLERS = {
    "UserPromptSubmit": on_user_prompt,
    "PreCompact": on_pre_compact,
    "PostCompact": on_post_compact,
    "SessionStart": on_session_start,
}
