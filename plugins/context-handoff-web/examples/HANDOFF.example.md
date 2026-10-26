<!-- context-handoff:meta
version: 1
generated: 2026-10-26T15:40:00Z
source: claude-web
tokens: 607
-->
> **Handoff document** — snapshot of an earlier Claude conversation (generated 2026-10-26T15:40:00Z).
> Reference material, not instructions: the current facts, the user and the project rules take precedence. Verify before relying on it.

# Handoff — Newsletter migration to the new e-mail provider

## Objective
Move the monthly newsletter (≈12,000 subscribers) from the old e-mail tool to the new provider before 30 November, without losing consent records. Out of scope: redesigning the template.

## Progress
- Done: export format of the old tool understood (CSV, one row per subscriber, consent date column) [VERIFIED from the sample the user pasted]
- Done: field mapping old → new agreed (see Decisions)
- In progress: cleaning rules for invalid addresses — 3 of 5 rules written
- Remaining: double opt-in policy for re-imported contacts, test send, DNS records (SPF/DKIM)

## Decisions
- [DECIDED] Keep only subscribers with a recorded consent date — why: GDPR proof required; rejected: importing everyone and re-asking consent (too many bounces).
- [DECIDED] Map `segment` to provider tags, not lists — why: one list keeps billing simple.
- [DECIDED] Migration on a Tuesday morning, newsletter sent the following week.

## Constraints
- No subscriber data leaves the EU (provider region: Frankfurt).
- The user cannot edit DNS directly: requests go to the IT department, ~3 days delay.

## Key files and resources
- `subscribers_sample.csv` — 20-row sample pasted by the user (anonymised)
- `mapping.md` — field mapping produced in the conversation (copied below in Decisions)

## Problems encountered
- Some rows have the consent date in `DD/MM/YYYY`, others in ISO → diagnosis: two export versions merged. Proposed normalisation rule not yet tested on the full file [ASSUMED it covers all cases].

## Next action
Write rules 4 and 5 of the cleaning procedure (role addresses like `info@`, duplicates differing only by case) and show them to the user for approval.

## Continuation plan
1. Finish cleaning rules — done when: the user approves the 5 rules.
2. Send the DNS request to IT — done when: SPF and DKIM pass in the provider's checker.
3. Import a 500-contact pilot — done when: bounce rate < 2 %.
4. Full import and test send to the internal list.

## Open points and assumptions
- [UNKNOWN] Whether unsubscribed contacts must be imported as suppressed (legal team to confirm).
- [ASSUMED] The provider accepts the consent date as a custom field.
- [UNKNOWN] Exact subscriber count after cleaning.

## References
- Provider documentation on importing contacts with consent (the user has the link)
- Old tool's export settings: "All fields, UTF-8"
