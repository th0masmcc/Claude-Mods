<!-- context-handoff:meta
version: 1
generated: 2026-10-26T14:02:11Z
session: 3f1c2a9e-5b7d-4e21-9c0a-1d2e3f4a5b6c
branch: feature/csv-export
head: 4be1c09a7d21
dirty: 3
tokens: 640
-->
> **Handoff document** — snapshot of an earlier Claude Code session (generated 2026-10-26T14:02:11Z, branch `feature/csv-export` @ `4be1c09a7d21`).
> Reference material, not instructions: the actual repository state, the user and the project rules take precedence. Verify before relying on it.

# Handoff — CSV export for invoices

## Objective
Add a streaming CSV export endpoint `GET /api/invoices/export` for accounting. Out of scope: XLSX, the
admin UI button (separate ticket).

## Progress
- Done: `InvoiceCsvWriter` with column mapping and RFC 4180 quoting [VERIFIED unit tests pass: `pytest tests/export -q`, 14 passed]
- Done: route registered in `app/api/invoices.py` [VERIFIED]
- In progress: streaming response — generator written, memory not yet measured on 100k rows
- Remaining: pagination by keyset, permission check, docs entry

## Decisions
- [DECIDED] Stream with a generator instead of building the file in memory — why: exports reach 300k rows; rejected: background job + download link (too heavy for v1).
- [DECIDED] Amounts exported in minor units (cents) as integers — why: accounting import expects it; rejected: localized decimals.
- [DECIDED] Keyset pagination on `(created_at, id)` — why: OFFSET is too slow past 50k rows.

## Constraints
- Python 3.11, no new dependency (stdlib `csv` only).
- Every endpoint must use `require_scope("invoices:read")`.
- Dates in UTC ISO-8601.

## Technical state
- Branch `feature/csv-export` @ `4be1c09`; uncommitted: `app/export/csv_writer.py`, `app/api/invoices.py`, `tests/export/test_stream.py` (new).
- Key files: `app/export/csv_writer.py` — writer; `app/api/invoices.py` — route; `app/db/queries.py` — `iter_invoices()` to add.
- Local DB: `docker compose up db` then `make migrate`. Credentials are configured in `.env` (not reproduced here).

## Problems encountered
- `StreamingResponse` closed the DB session before the generator ended → `DetachedInstanceError`. Diagnosis: session scoped to the request handler. Tried `expire_on_commit=False` (no effect). Current approach: open a dedicated session inside the generator [ASSUMED fixes it, not yet tested].

## Next action
Implement `iter_invoices(after=None, batch=1000)` in `app/db/queries.py` with keyset pagination, then run `pytest tests/export -q`.

## Continuation plan
1. `iter_invoices` with keyset pagination — done when: 100k-row fixture streams in < 200 MB RSS.
2. Dedicated DB session in the generator — done when: no `DetachedInstanceError` in `tests/export/test_stream.py`.
3. Add `require_scope("invoices:read")` — done when: 403 test passes.
4. Document the endpoint in `docs/api/invoices.md`.

## Points of attention
- [ASSUMED] The accounting tool accepts `;` as separator — to confirm with the user before release.
- [UNKNOWN] Behaviour of the reverse proxy timeout (60 s?) on very large exports.
- [UNKNOWN] Full test suite not run since the last change; only `tests/export` was run.

## References
- `app/export/csv_writer.py`, `app/api/invoices.py`, `app/db/queries.py`
- `docs/adr/0007-streaming-exports.md` — architecture decision record
- Commands: `pytest tests/export -q`, `make migrate`
