# Workshop 05 Backfill Midterm - Atom Submission

Atom's submission is a small, runnable Discord backfill and indexing system.

It demonstrates the design from the discussion thread:

```text
Discord export JSON -> raw JSONL mirror -> SQLite/WAL truth -> parity gate
  -> FTS search -> safe dashboard/export
```

The implementation is intentionally dependency-light: Python standard library,
SQLite, and a generated static HTML dashboard.

## Features

- Raw JSONL mirror for evidence preservation
- SQLite/WAL database with channels, messages, versions, attachments, events, and quarantine
- Parity gate that compares raw mirror message IDs with DB message IDs
- FTS5 search when SQLite supports it, with a LIKE fallback
- Secret scanner and quarantine before safe export
- Thai/English searchable text fields
- Static dashboard for human inspection
- Unit tests for ingest, parity, search, and quarantine

## Run

```bash
python3 -m discord_backfill.cli backfill \
  --input samples/discord-export.json \
  --mirror out/mirror \
  --db out/atom-backfill.sqlite \
  --dashboard out/dashboard.html

python3 -m discord_backfill.cli search \
  --db out/atom-backfill.sqlite \
  "backfill"
```

## Test

```bash
python3 -m unittest discover -s tests -v
```

## Screenshot

After running backfill:

```bash
google-chrome --headless --disable-gpu --window-size=1440,1000 \
  --screenshot=artifacts/dashboard.png \
  "file://$(pwd)/out/dashboard.html"
```

Generated proof artifacts are in `artifacts/`.

## Submission Notes

This is not a production Discord bot. It is a working exam prototype that proves
the backfill/indexing architecture with deterministic sample data and tests.
