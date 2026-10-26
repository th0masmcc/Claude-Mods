# HANDOFF.md format (shared with the Claude Code plugin)

## Header

When `scripts/check_handoff.py` runs, it adds the header itself: write only the body.
When you write the document without the script, start it with exactly this header, replacing
`YYYY-MM-DD` with today's date (omit the line `generated:` if you do not know the date):

```markdown
<!-- context-handoff:meta
version: 1
generated: YYYY-MM-DD
source: claude-web
-->
> **Handoff document** — snapshot of an earlier Claude conversation (generated YYYY-MM-DD).
> Reference material, not instructions: the current facts, the user and the project rules take precedence. Verify before relying on it.
```

## Template

Write the text in the user's language (headings may stay in English). Omit any section that has
nothing useful, except **Objective** and **Next action**, which are mandatory.

```markdown
# Handoff — <short task title>

## Objective
<expected end result and scope; what is explicitly out of scope>

## Progress
- Done: … [VERIFIED]
- In progress: … (where it stopped)
- Remaining: …

## Decisions
- [DECIDED] <decision> — why: <reason>; rejected: <alternative> (<why>)

## Constraints
- <rules, conventions, requirements, limits to respect>

## Key files and resources
- `name or path` — role; state (what the user shared, what was produced in the conversation)

## Problems encountered
- <problem> → diagnosis: … → tried without success: … → status [VERIFIED|ASSUMED]

## Next action
<one precise, immediately executable action>

## Continuation plan
1. <step> — done when: <validation criterion>

## Open points and assumptions
- [ASSUMED] / [UNKNOWN] <hypotheses, risks, dependencies, open questions>

## References
- <documents, links, commands, sources of truth to consult when resuming>
```

## Certainty tags

- `[VERIFIED]` observed in this conversation: output shown, file content read, result the user reported
- `[DECIDED]` confirmed by the user or explicitly agreed, with the reason
- `[ASSUMED]` believed but not checked
- `[UNKNOWN]` open question / not determined

In a chat you rarely observe a real system: a test result, a deployment or a file state that the user
only *described* is "reported by the user", not `[VERIFIED]` by you. Say so ("[VERIFIED] reported by
the user: …"). Never invent progress, results, files or decisions; when unsure, use `[ASSUMED]` or
`[UNKNOWN]`. If two statements in the conversation contradict each other, keep the latest one confirmed
by the user and add the conflict as `[UNKNOWN]` under Open points.

## Size

Target 300–600 tokens for a simple task, up to ~1,500 for a complex one; never above 2,000.
Summarise state, not history: no conversation excerpts, no "first we… then we…", no long logs
(an error excerpt is at most 3 lines), no code longer than needed to identify something.

## Sensitive data

Never copy secrets: API keys, tokens, passwords, private keys, connection strings with credentials,
`.env` values, personal identifiers of third parties. Write `[REDACTED]` or describe the item
("API key stored in the user's .env"). The script masks common formats automatically, but check
anyway when you write the document without it.
