# Creating or updating HANDOFF.md

Goal: a compact, faithful snapshot that lets a *new* session continue the work without re-reading this
conversation. Your own context (this conversation, including any compaction summary) is the source; do
not read the transcript file and do not re-read files only to fill the document.

## 1. Gather facts (one command)

`HANDOFF gather --session <session id>` (the `HANDOFF` command and session id are given in SKILL.md)

It prints JSON: `handoff_path`, `existing` (hash, staleness), `expect`, `token_budget`, `git`
(branch, HEAD, uncommitted files — sensitive files are flagged and must not be opened), files edited
in this session, task list state and `write_command`.

## 2. Existing document

If `existing.exists` is true, Read `handoff_path` first. For each item decide: still valid → keep
(rephrase only if needed); done → move to "Done" in one line or drop; obsolete or contradicted by the
current state → remove or correct. Never append a new "session N" section: the document describes the
*current* state, it is not a log. If `existing.managed` is false (hand-written file), preserve its
useful content inside the structure below.

## 3. Write the content

Use the user's language for the text (headings may stay in English). Target `token_budget` tokens or
less; never exceed `max_tokens`. Omit a section entirely when it has nothing useful, except
**Objective** and **Next action** which are mandatory. Tag statements whose certainty matters:

- `[VERIFIED]` observed in this session (command output, test run, file content)
- `[DECIDED]` confirmed by the user or explicitly agreed, with the reason
- `[ASSUMED]` believed but not checked
- `[UNKNOWN]` open question / not determined

Never invent progress, test results or decisions: tests not run since the last change are `[UNKNOWN]`.
No conversation excerpts, no long logs (an error excerpt is at most 3 lines), no secrets, tokens,
passwords or `.env` values (describe them as "configured in .env" at most). Put paths relative to the
project root in backticks: `/handoff resume` checks that they exist.

```markdown
# Handoff — <short task title>

## Objective
<expected end result and scope; what is explicitly out of scope>

## Progress
- Done: … [VERIFIED]
- In progress: … (state where it stopped)
- Remaining: …

## Decisions
- [DECIDED] <decision> — why: <reason>; rejected: <alternative> (<why>)

## Constraints
- <architecture, conventions, business rules, limits to respect>

## Technical state
- Branch `<branch>` @ `<head>`; uncommitted: <short summary from gather, not the full list>
- Key files/modules: `path` — role
- Environment: <runtime, services, commands needed>

## Problems encountered
- <error> → diagnosis: … → tried without success: … → status [VERIFIED|ASSUMED]

## Next action
<one precise, immediately executable action>

## Continuation plan
1. <step> — done when: <validation criterion>

## Points of attention
- [ASSUMED] / [UNKNOWN] <hypotheses, risks, dependencies, open questions>

## References
- `path/or/doc` — why it matters; useful commands: `…`
```

## 4. Save it (the script redacts secrets, validates, backs up and writes atomically)

Run `write_command` from step 1 with the document on stdin, using a quoted heredoc so nothing is
expanded by the shell:

```
<write_command> <<'HANDOFF_EOF_7f3a'
...document...
HANDOFF_EOF_7f3a
```

- Exit 2 (refused): read the message. Too long → condense; missing section → add it; "changed since
  it was read" → run `gather` again, re-read the file, merge. Retry at most twice.
- Exit 3 (I/O error, e.g. permissions): do not retry blindly. Report it and suggest
  `/handoff config set path <writable-path>.md`; the previous file is untouched.

## 5. Report (2–4 lines)

Path, status (created / updated / unchanged), approximate size, redactions or warnings reported by
the script, and: "In a new session, run `/handoff resume`." Do not commit, push or add the file to
`.gitignore`; mention that committing it is the user's choice.
