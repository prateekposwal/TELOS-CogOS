# TELOS — Lessons Learned (the memory the conversation forgets)

**Created:** 2026-08-11 | **Owner:** TELOS | **Rule:** see below.

## Why this directory exists

TELOS keeps learning things in conversation and then forgetting them,
because the learning was never written down. The architect keeps having to
re-teach the same lessons. This directory is the structural fix:
**conversation is not memory.**

A lesson that is not persisted must be re-taught. A lesson that is
persisted is an asset (Axiom 2.3 Kintsugi: failures stored as assets).

## The operational rule (mandatory)

> **After any bug / fix / misdiagnosis that took > 2 rounds of
> back-and-forth, write the lesson to `telos/lessons/` before the session
> closes.** Structured format: `date, symptom, root cause, fix, pattern,
> prevention`. Link the gap-tracker entry. Append, never overwrite.

Also:
- Any session that *fixed* a data-reliability or ops issue MUST verify the
  fix against the real surface (verify_as_user) and record the verification
  in the lesson record.
- Naming: `YYYY-MM-DD-<topic>.json` + optional `.md` companion for humans.
- Every lesson gets an ID `L-NN` and links to a gap-tracker gap ID (`G-NN`).
- Queryable: lessons are JSON; `grep`/`jq` over the directory works.

## Recorded lessons

| ID | Date | System | Domain | Symptom (one line) | Gap |
|----|------|--------|--------|--------------------|-----|
| L-01 | 2026-08-10 | BSAHI | data-capture | node_census skipped days (Aug 4, Aug 10) | G-25 |
| L-02 | 2026-08-10 | BSAHI | data-capture | Research runner manual-only, dead ~9 days | G-26 |
| L-03 | 2026-08-10 | BSAHI | data-capture | hashrate/mempool 'stale' was a file-count misjudgment | G-27 |
| L-04 | 2026-08-10 | BSAHI | security | GH013 hardcoded token blocked all pushes | G-28 |
| L-05 | 2026-08-10 | BSAHI | data-capture | btc-rpc 'stale' was a wrong-directory misdiagnosis | G-29 |
| L-00 | 2026-08-11 | TELOS | meta-learning | Lessons learned in conversation were never persisted — THE meta-gap | G-30 |

## Cross-reference

- **gap-tracker.json** — data-reliability gaps G-25..G-30 (closed), pattern P-06 added.
- **master-todo.md** — "Data-capture reliability" section.
- **AXIOMS.md** — Principle P2.0 "Conversation is not memory".
- **learnings.json** — populated `failure_patterns` from these lessons.
