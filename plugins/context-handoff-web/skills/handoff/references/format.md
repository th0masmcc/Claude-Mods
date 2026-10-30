# HANDOFF.md format (shared with the Claude Code plugin)

The reader is a new conversation that has **only this document**. It cannot see this conversation,
the user's repository, or any other file unless the user attaches it. Everything needed to continue
at the same level of understanding must be in the document, or explicitly pointed to with what it
contains.

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

## Size: proportional to the conversation

The goal is fidelity, not brevity. A handoff that is too short costs far more (lost context,
decisions re-argued, work redone) than a few thousand extra tokens.

| Conversation | Typical size |
| --- | --- |
| Short task, a few decisions | 400–1,000 tokens |
| Long conversation, one project | 2,000–5,000 tokens |
| Very long thread (many phases, measurements, rules, produced texts) | 5,000–10,000 tokens |

Never drop a decision, constraint, rule, measured figure, rejected option or open question to save
space. Save space on wording instead: no narration ("first we… then we…"), no repetition, no
politeness, short bullets. The hard limit checked by the script is 12,000 tokens; if the content
really exceeds it, keep the core document complete and move long verbatim texts out (see Appendix).

## Template

Write the text in the user's language (headings may stay in English). Omit a section only when it
has nothing useful; **Objective** and **Next action** are mandatory. For a long conversation,
**Context**, **Glossary** and **Ways of working** are expected.

```markdown
# Handoff — <short task title>

## Context and background
<who the user is and what they are trying to achieve beyond this task; how the project got here
(phases, turning points, why the current approach was chosen); what earlier work exists and where>

## Objective
<expected end result and scope; what is explicitly out of scope, and why>

## Ways of working
- <role of Claude in this work (adviser, writes code, writes prompts for another tool…)>
- <the user's preferences: language, level of detail, format, what to avoid, how to propose changes>
- <process rules agreed (one change at a time, measure before/after, ask before…)>

## Glossary
- **<label, code, abbreviation or name used in this document>** — <its meaning in this project>

## Progress
- Done: … [VERIFIED]
- In progress: … (exactly where it stopped)
- Remaining: …

## Decisions
- [DECIDED] <decision> — why: <reason>; rejected: <alternative> (<why>); since: <date or phase if known>

## Constraints
- <rules, conventions, requirements, limits to respect, with their reason>

## Key figures
- <measurement or number> — <what it measures, date or period, source> [VERIFIED|ASSUMED]

## Key files and resources
- `name or path` — role; state; what it contains that matters here; where it lives

## Problems encountered
- <problem> → diagnosis: … → tried without success: … → status [VERIFIED|ASSUMED]

## Next action
<one precise, immediately executable action, with what to check first>

## Continuation plan
1. <step> — done when: <validation criterion>

## Open points and assumptions
- [ASSUMED] / [UNKNOWN] <hypotheses, risks, dependencies, open questions, ideas not yet decided>

## References
- <documents, links, commands, sources of truth to consult when resuming, and what each holds>

## Appendix: texts produced in the conversation
<only texts that are needed to continue and costly to recreate: final versions of prompts, rules,
specifications, configurations, message templates. Verbatim, each under its own ### heading.>
```

## Self-containment rules

- **Define every label.** Any numbered criterion, profile letter, step letter, code name, internal
  term or abbreviation that appears in the document is defined in the Glossary or where it is used
  ("criterion 9 (CVE identified only by CERT-FR: delay…)"). A bare "criteria 9, 10 and 11" is not
  acceptable.
- **Keep the why.** Each decision, rule and threshold keeps its reason and, when it was debated,
  the rejected alternatives. Without the reason, the next conversation will re-argue it.
- **Keep the numbers.** Measured values, thresholds, counts, dates and identifiers (CVE, commit,
  ticket, version) are copied exactly, with what they measure and when.
- **External sources are pointers, not substitutes.** When something is "in the repository's
  HANDOFF.md" or "in file X", say what the reader will find there, and still summarise here the part
  needed to understand the next action.
- **Order is meaningful.** Lists of steps appear in execution order; if labels are not in
  alphabetical order, say so explicitly.

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

## Sensitive data

Never copy secrets: API keys, tokens, passwords, private keys, connection strings with credentials,
`.env` values, personal identifiers of third parties. Write `[REDACTED]` or describe the item
("API key stored in the user's .env"). The script masks common formats automatically, but check
anyway when you write the document without it.
