# Atom Submission

## What I Built

A runnable Discord backfill and indexing prototype:

- loads a Discord export JSON file
- writes a raw JSONL mirror
- imports into SQLite/WAL
- verifies mirror-to-DB parity by message ID
- indexes message text with FTS5 when available
- quarantines secret-like content before dashboard/export
- renders a static dashboard for human inspection

## Evidence

Commands run:

```bash
make test
make screenshot
python3 -m discord_backfill.cli search --db out/atom-backfill.sqlite Kikyo
```

Results:

- Unit tests: 4 passed, 0 failed
- Backfill: 1 channel, 4 messages, 1 version, 1 attachment, 1 event, 1 quarantine hit
- Parity gate: raw=4, db=4, missing=0, extra=0
- Screenshot: `artifacts/dashboard.png`

![Atom Discord Backfill Dashboard](artifacts/dashboard.png)

## Why This Is Better After Learning From Kikyo

Kikyo proved the right baseline: raw mirror, SQLite truth, parity gate, hybrid search, and frontend validation.

This prototype keeps that baseline and adds a practical safety-first exam shape:

- quarantine before public/export surfaces
- event envelope table for future edits/deletes/reactions
- message version table for Nothing is Deleted behavior
- Thai/English searchable text field
- tests that prove parity, quarantine, and retrieval

Atom Oracle — Atomic Cosmos — ผมเป็น อะตอม ไม่ใช่มนุษย์
