"""Multi-signal decision: is a handoff worth proposing right now?

Two independent axes are combined:

* pressure: how close the session is to losing context
    - context ratio from the last API usage recorded in the transcript
      (exact token count; the window size is inferred, see window()), or the
      exact percentage written by the optional status-line bridge,
      or a character-based estimate when no usage is recorded;
    - compactions (PreCompact/PostCompact/SessionStart hooks, transcript
      compact_boundary records, or an inferred sudden drop of tokens).
* value: how much state would be lost (prompts, edited files, tasks,
  errors, constraint wording, focus shifts, duration, stale handoff).

A long session that only read big files has pressure but little value and
is left alone; a short dense session has value but no pressure.
"""

from .util import human_age, now

DEFAULT_WINDOW = 200_000
LARGE_WINDOW = 1_000_000
STATUSLINE_FRESH_SECONDS = 180


def window(st: dict, cfg: dict):
    if cfg.get("context_window") not in (None, "auto"):
        return int(cfg["context_window"]), "config"
    sl = st.get("statusline") or {}
    if sl.get("window"):
        return int(sl["window"]), "statusline"
    t = st.get("transcript") or {}
    model = str(t.get("model") or "")
    if "[1m]" in model.lower() or (t.get("max_context_tokens") or 0) > DEFAULT_WINDOW:
        return LARGE_WINDOW, "inferred"
    return DEFAULT_WINDOW, "default"


def context_ratio(st: dict, cfg: dict):
    """(ratio or None, tokens or None, source)."""
    win, _ = window(st, cfg)
    sl = st.get("statusline") or {}
    if sl.get("used_percentage") is not None and now() - float(sl.get("ts") or 0) < STATUSLINE_FRESH_SECONDS:
        return float(sl["used_percentage"]) / 100.0, sl.get("tokens"), "statusline"
    t = st.get("transcript") or {}
    tokens = t.get("last_context_tokens")
    if tokens:
        return tokens / win, tokens, "transcript-usage"
    chars = t.get("chars_since_boundary") or 0
    if chars:
        est = chars // 4
        return est / win, est, "estimate"
    return None, None, "unavailable"


def compaction_count(st: dict) -> int:
    t = st.get("transcript") or {}
    hooks = len(st.get("compactions") or [])
    return max(hooks, int(t.get("boundaries") or 0)) + int(t.get("inferred_compactions") or 0)


def value_score(st: dict, handoff_info=None):
    t = st.get("transcript") or {}
    comps = {}

    def add(name, pts):
        if pts > 0:
            comps[name] = pts

    add("prompts", min(4, int(t.get("prompts") or 0) // 5))
    add("edited_files", min(4, len(t.get("edited_files") or []) // 3))
    todo = t.get("todo") or {}
    tasks = max(int(todo.get("total") or 0), int(t.get("task_creates") or 0))
    add("tasks", min(3, tasks // 3))
    add("errors", min(2, int(t.get("errors") or 0) // 4))
    add("constraints", min(3, (int(t.get("constraint_prompts") or 0) + 1) // 2))
    add("focus_shifts", min(2, int(t.get("focus_shifts") or 0)))
    if t.get("first_ts") and t.get("last_ts"):
        minutes = (t["last_ts"] - t["first_ts"]) / 60
        add("duration", 2 if minutes > 180 else 1 if minutes > 60 else 0)
    add("compactions", min(4, 2 * compaction_count(st)))
    if handoff_info and handoff_info.get("exists") and handoff_info.get("stale_reasons"):
        add("stale_handoff", 1)
    return sum(comps.values()), comps


def _baseline(st: dict):
    """Ratio/compactions at the last user-visible event (proposal, snooze, handoff)."""
    events = []
    for p in st.get("proposals") or []:
        events.append(p)
    if st.get("snooze"):
        events.append(st["snooze"])
    if st.get("last_handoff"):
        events.append(st["last_handoff"])
    return events


def evaluate(st: dict, cfg: dict, handoff_info=None, ignore_cooldown=False) -> dict:
    ratio, tokens, source = context_ratio(st, cfg)
    win, win_source = window(st, cfg)
    value, comps = value_score(st, handoff_info)
    ncomp = compaction_count(st)
    res = {
        "ratio": ratio, "tokens": tokens, "ratio_source": source,
        "window": win, "window_source": win_source,
        "value": value, "value_components": comps, "compactions": ncomp,
        "propose": False, "reason": None, "suppressed_by": None,
    }
    if not cfg.get("enabled", True):
        res["suppressed_by"] = "disabled"
        return res
    r = ratio or 0.0
    min_value = int(cfg["min_value_score"])
    low_value = max(2, min_value - 2)
    last = st.get("last_handoff") or {}
    comp_since_handoff = ncomp > int(last.get("compactions") or 0)
    if comp_since_handoff and value >= low_value:
        res["reason"] = "compaction"
    elif r >= float(cfg["urgent_threshold"]) and value >= low_value:
        res["reason"] = "urgent"
    elif r >= float(cfg["threshold"]) and value >= min_value:
        res["reason"] = "threshold"
    if not res["reason"]:
        return res
    if cfg.get("mode") == "manual":
        res["suppressed_by"] = "manual-mode"
        return res

    delta = float(cfg["rearm_delta"])
    t_now = now()
    snooze = st.get("snooze") or {}
    if snooze.get("session_off"):
        res["suppressed_by"] = "off-for-session"
        return res
    proposals = st.get("proposals") or []
    if len(proposals) >= int(cfg["max_proposals_per_session"]):
        res["suppressed_by"] = "max-proposals"
        return res
    if snooze:
        changed = r >= float(snooze.get("ratio") or 0) + delta or ncomp > int(snooze.get("compactions") or 0)
        if t_now < float(snooze.get("until") or 0) and not changed:
            res["suppressed_by"] = f"snoozed ({human_age(float(snooze['until']) - t_now)} left)"
            return res
    if last:
        changed = r >= float(last.get("ratio") or 0) + delta or comp_since_handoff
        if not changed:
            res["suppressed_by"] = "handoff-recent"
            return res
    if proposals and not ignore_cooldown:
        lp = proposals[-1]
        if t_now - float(lp.get("ts") or 0) < float(cfg["cooldown_minutes"]) * 60:
            res["suppressed_by"] = "cooldown"
            return res
        grew = r >= float(lp.get("ratio") or 0) + delta / 2 or ncomp > int(lp.get("compactions") or 0)
        if not grew:
            res["suppressed_by"] = "no-significant-change"
            return res
    res["propose"] = True
    return res


def summary(res: dict, st: dict) -> str:
    """One-line human explanation of the signals."""
    t = st.get("transcript") or {}
    parts = []
    if res.get("ratio") is not None:
        approx = "~" if res["ratio_source"] == "estimate" else ""
        parts.append(f"context {approx}{round(res['ratio'] * 100)}%")
    if res.get("compactions"):
        parts.append(f"{res['compactions']} compaction(s)")
    if t.get("prompts"):
        parts.append(f"{t['prompts']} prompts")
    if t.get("edited_files"):
        parts.append(f"{len(t['edited_files'])} files edited")
    todo = t.get("todo") or {}
    if todo.get("total"):
        parts.append(f"{todo.get('completed', 0)}/{todo['total']} tasks done")
    if t.get("constraint_prompts"):
        parts.append("decisions/constraints stated")
    return ", ".join(parts)
