---
name: handoff
description: Keeps long conversations recoverable through a HANDOFF.md. Proactive use - in a long conversation (roughly 15+ exchanges, or large pasted material) that has accumulated decisions, constraints, finished and pending tasks, or shows drift (the user repeating information, answers contradicting earlier decisions), load this skill to decide whether to end your reply with a one-line offer to write a HANDOFF.md, starting with "**Handoff** —"; at most twice per conversation, never after the user declined, never in short or simple chats. On request - use it whenever the user asks to create, update or save a handoff, a HANDOFF.md, or a summary to continue the work in a new conversation. To continue from an existing HANDOFF.md, use the handoff-resume skill instead.
---

# Handoff for long conversations

This skill runs in claude.ai chat (it also works in Cowork and Claude Code). If the Claude Code
`context-handoff` plugin's own `handoff` skill, the one that runs `handoff.py` in a local repository,
is also available in this session, use that skill instead and stop here.

**What you can know.** You see the conversation as it is in your context. You cannot read its size in
tokens, how full the context window is, or whether older messages were summarised, unless that is
visible to you. Never quote a percentage or claim a measurement. Judge from what you can see.

## 1. Proposing a handoff (the user has not asked)

Propose only when **both** hold:

- **Volume**: the conversation is long: about 15 or more substantive exchanges, or large pasted
  documents or code, or work spread over a long session.
- **Value**: at least two of: two or more decisions or constraints stated; tasks finished and others
  still pending; the objective changed or narrowed; errors diagnosed or approaches ruled out; files or
  resources whose role matters; signs of drift.

Strong signs of drift are enough on their own: you contradicted an earlier decision, the user had to
repeat something, or you notice that an earlier part was summarised.

Do not propose in a short or simple conversation, in the middle of an urgent step (wait for a natural
milestone), or when a handoff was already produced here and little has changed since.

**Your memory is the conversation.** Before proposing, look back for your earlier proposals (they start
with `**Handoff** —`) and the user's reaction:

- declined ("no", "non", "pas besoin") or ignored → do not propose again in this conversation;
- "later" / "plus tard" → propose once more only after substantial new work (a new milestone, several
  new decisions);
- never more than 2 proposals in one conversation.

**How**: first answer the user's message completely. Then add one line at the very end, in the user's
language, naming what you actually observed, for example:

> **Handoff** — Cette conversation accumule beaucoup de contexte (4 décisions, 3 tâches en cours).
> Veux-tu que je prépare un HANDOFF.md pour la reprendre dans une nouvelle conversation ? (oui / plus tard / non)

Nothing else: no draft and no tool call before the user says yes.

## 2. Creating or updating the document

Consent is an explicit request, or a "yes" to your proposal. Do it in one pass: ask a question only if
the objective itself is unclear (then one question).

1. Read `references/format.md` in this skill's folder: header, template, certainty tags, size and
   sensitive-data rules.
2. Write the document from this conversation only: its messages, the files the user shared, the
   results shown. If an earlier HANDOFF.md is present (pasted, attached, or produced earlier here),
   update it: keep what is still valid, move finished items to Done, remove what is obsolete, and
   do not append a history of sessions.
3. Deliver it:
   - **You can run code or create files here** (code execution and file creation enabled): save the
     body to a draft file and run `python3 ${CLAUDE_SKILL_DIR}/scripts/check_handoff.py <draft>`
     (in chat, the skill folder is copied into the sandbox: use the script at `scripts/check_handoff.py`
     relative to this SKILL.md). Run it directly; no need to list the folder first. It masks secrets, checks the mandatory sections and the size, adds the
     header and writes `HANDOFF.md` to the folder shared with the user (`/mnt/user-data/outputs/` on
     claude.ai), or to the path given with `--out`. On exit code 2, fix what it reports and rerun, at most
     twice. Present the file to the user for download. In your reply, write 2–4 lines (what it covers,
     approximate size, redactions or warnings), not the document again.
   - **Otherwise**: output the complete document, header included, in a single ```markdown code block,
     and tell the user to save it as `HANDOFF.md`. Mask secrets yourself first.
4. Explain how to resume, in 1–2 lines: start a new conversation, attach `HANDOFF.md` (or paste it)
   and ask to resume from it; in a claude.ai Project, adding the file to the project's knowledge
   makes it available to every new conversation in the project. Say that you cannot write to their
   computer or their Git repository yourself, unless a tool for that is actually available in this
   conversation; if they work in a repository, they can put the file at its root and commit it.

Never present an assumption as a fact, never invent results, files or decisions, and never copy
secrets.
