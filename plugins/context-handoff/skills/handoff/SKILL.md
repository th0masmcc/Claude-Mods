---
name: handoff
description: Save or resume the operational state of a long Claude Code session (local project, helper script) through a HANDOFF.md file. Use in Claude Code when the user runs /handoff, accepts an offer to save the session state, asks to create/update a handoff, or asks to resume work from HANDOFF.md.
argument-hint: "[create | resume | status | config [set KEY VALUE] | snooze [MIN] | off | on]"
---

# /handoff

This skill needs Claude Code: a local project and `python3` to run the helper script. In claude.ai
chat (no local project, hooks not loaded), use the `handoff` / `handoff-resume` skills of the
`context-handoff-web` plugin instead, or tell the user to install it from Customize > Plugins.

Helper script (Python 3, read-only except for HANDOFF.md and its own state):
`python3 "${CLAUDE_SKILL_DIR}/scripts/handoff.py" <command>` — written `HANDOFF` below.
Session id: `${CLAUDE_SESSION_ID}`.

Arguments received: `$ARGUMENTS`

Dispatch on the first word of the arguments:

- **(empty)** — run `HANDOFF status --session ${CLAUDE_SESSION_ID}`. Summarise it in at most 3 lines
  (context use, why a handoff is or is not useful, existing document). Then ask the user whether to
  create/update the handoff. Do not create it without a clear yes. If yes, continue as `create`.
- **create** / **update** / **save** — read `${CLAUDE_SKILL_DIR}/create.md` and follow it exactly.
  The user's explicit command (or their "yes" to an offer) is the consent.
- **resume** — read `${CLAUDE_SKILL_DIR}/resume.md` and follow it exactly.
- **status** — run `HANDOFF status --session ${CLAUDE_SESSION_ID}` and reply with its output verbatim
  in a code block, without commentary or questions.
- **config** — with no further words run `HANDOFF config show`; otherwise pass the words through,
  e.g. `HANDOFF config set threshold 0.7` (add `--scope project` only if the user asks for a
  project-level setting). Show the output.
- **snooze** [minutes] — `HANDOFF snooze --session ${CLAUDE_SESSION_ID} [--minutes N]`.
- **off** — `HANDOFF snooze --off --session ${CLAUDE_SESSION_ID}` (rest of this session). For a
  permanent switch-off use `HANDOFF config set enabled false`.
- **on** — `HANDOFF unsnooze --session ${CLAUDE_SESSION_ID}`.
- anything else — show the list of sub-commands above in one short line each.

Rules for every sub-command: never commit, push or modify source files; never print secrets or the
content of `.env`/key files; keep your own messages short.
