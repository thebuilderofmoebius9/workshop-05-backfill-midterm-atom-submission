from __future__ import annotations

import html
import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SECRET_PATTERNS = [
    ("github classic token", re.compile(r"ghp_[A-Za-z0-9_]{20,}")),
    ("github fine-grained token", re.compile(r"github_pat_[A-Za-z0-9_]{20,}")),
    ("slack token", re.compile(r"xox[baprs]-[A-Za-z0-9-]{20,}")),
    ("openai-style key", re.compile(r"sk-[A-Za-z0-9_-]{20,}")),
    ("aws access key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("secret-like assignment", re.compile(r"(?i)(token|secret|password|api[_-]?key)\s*[:=]\s*['\"]?[^'\"\s]{8,}")),
]


@dataclass(frozen=True)
class BackfillConfig:
    input_path: Path
    mirror_dir: Path
    db_path: Path
    dashboard_path: Path


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_text(text: str) -> str:
    return " ".join(text.replace("\u200b", "").lower().split())


def redact(text: str) -> tuple[str, list[str]]:
    hits: list[str] = []
    safe = text
    for label, pattern in SECRET_PATTERNS:
        if pattern.search(safe):
            hits.append(label)
            safe = pattern.sub("[REDACTED]", safe)
    return safe, hits


def load_export(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text())
    if "guild" not in data or "channels" not in data:
        raise ValueError("export must contain guild and channels")
    return data


def iter_messages(data: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    guild = data["guild"]
    for channel in data.get("channels", []):
        for message in channel.get("messages", []):
            row = dict(message)
            row["guild_id"] = guild["id"]
            row["guild_name"] = guild.get("name", guild["id"])
            row["channel_id"] = channel["id"]
            row["channel_name"] = channel.get("name", channel["id"])
            row["thread_id"] = message.get("thread_id")
            row["thread_name"] = message.get("thread_name")
            rows.append(row)
    rows.sort(key=lambda r: (r.get("created_at", ""), r["id"]))
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    return con


SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS channels (
  id TEXT PRIMARY KEY,
  guild_id TEXT NOT NULL,
  name TEXT NOT NULL,
  raw_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS messages (
  id TEXT PRIMARY KEY,
  guild_id TEXT NOT NULL,
  channel_id TEXT NOT NULL,
  thread_id TEXT,
  author_id TEXT,
  author_name TEXT,
  content_raw TEXT NOT NULL,
  content_safe TEXT NOT NULL,
  content_searchable TEXT NOT NULL,
  created_at TEXT NOT NULL,
  edited_at TEXT,
  raw_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS message_versions (
  message_id TEXT NOT NULL,
  version INTEGER NOT NULL,
  content_safe TEXT NOT NULL,
  edited_at TEXT,
  raw_json TEXT NOT NULL,
  PRIMARY KEY (message_id, version)
);
CREATE TABLE IF NOT EXISTS attachments (
  id TEXT PRIMARY KEY,
  message_id TEXT NOT NULL,
  filename TEXT NOT NULL,
  content_type TEXT,
  size INTEGER,
  url TEXT
);
CREATE TABLE IF NOT EXISTS event_envelopes (
  event_id TEXT PRIMARY KEY,
  event_type TEXT NOT NULL,
  message_id TEXT,
  channel_id TEXT,
  created_at TEXT NOT NULL,
  raw_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS quarantine (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  message_id TEXT NOT NULL,
  reason TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS backfill_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at TEXT NOT NULL,
  source TEXT NOT NULL,
  raw_messages INTEGER NOT NULL,
  db_messages INTEGER NOT NULL,
  parity_ok INTEGER NOT NULL
);
"""


def reset_db(con: sqlite3.Connection) -> None:
    con.executescript(
        """
        DROP TABLE IF EXISTS messages_fts;
        DELETE FROM channels;
        DELETE FROM messages;
        DELETE FROM message_versions;
        DELETE FROM attachments;
        DELETE FROM event_envelopes;
        DELETE FROM quarantine;
        DELETE FROM backfill_runs;
        """
    )


def fts_available(con: sqlite3.Connection) -> bool:
    try:
        con.execute("CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(id, content_searchable)")
        return True
    except sqlite3.DatabaseError:
        return False


def import_to_db(con: sqlite3.Connection, data: dict[str, Any], messages: list[dict[str, Any]]) -> None:
    reset_db(con)
    for channel in data.get("channels", []):
        con.execute(
            "INSERT INTO channels(id, guild_id, name, raw_json) VALUES (?, ?, ?, ?)",
            (channel["id"], data["guild"]["id"], channel.get("name", channel["id"]), json.dumps(channel, ensure_ascii=False)),
        )

    for message in messages:
        safe, hits = redact(message.get("content", ""))
        searchable = normalize_text(" ".join([safe, message.get("author_name", ""), message.get("channel_name", ""), message.get("thread_name") or ""]))
        con.execute(
            """
            INSERT INTO messages(
              id, guild_id, channel_id, thread_id, author_id, author_name,
              content_raw, content_safe, content_searchable, created_at, edited_at, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                message["id"],
                message["guild_id"],
                message["channel_id"],
                message.get("thread_id"),
                message.get("author_id"),
                message.get("author_name"),
                message.get("content", ""),
                safe,
                searchable,
                message["created_at"],
                message.get("edited_at"),
                json.dumps(message, ensure_ascii=False, sort_keys=True),
            ),
        )
        versions = message.get("versions") or []
        for idx, version in enumerate(versions, start=1):
            version_safe, version_hits = redact(version.get("content", ""))
            con.execute(
                """
                INSERT INTO message_versions(message_id, version, content_safe, edited_at, raw_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (message["id"], idx, version_safe, version.get("edited_at"), json.dumps(version, ensure_ascii=False)),
            )
            hits.extend(version_hits)
        for attachment in message.get("attachments", []):
            con.execute(
                """
                INSERT INTO attachments(id, message_id, filename, content_type, size, url)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    attachment["id"],
                    message["id"],
                    attachment["filename"],
                    attachment.get("content_type"),
                    attachment.get("size"),
                    attachment.get("url"),
                ),
            )
        for event in message.get("events", []):
            con.execute(
                """
                INSERT INTO event_envelopes(event_id, event_type, message_id, channel_id, created_at, raw_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    event["id"],
                    event["type"],
                    message["id"],
                    message["channel_id"],
                    event["created_at"],
                    json.dumps(event, ensure_ascii=False),
                ),
            )
        for hit in sorted(set(hits)):
            con.execute(
                "INSERT INTO quarantine(message_id, reason, created_at) VALUES (?, ?, ?)",
                (message["id"], hit, utc_now()),
            )

    if fts_available(con):
        con.execute("DELETE FROM messages_fts")
        con.execute("INSERT INTO messages_fts(id, content_searchable) SELECT id, content_searchable FROM messages")
    con.commit()


def parity(con: sqlite3.Connection, raw_messages: list[dict[str, Any]]) -> dict[str, Any]:
    raw_ids = {m["id"] for m in raw_messages}
    db_ids = {row["id"] for row in con.execute("SELECT id FROM messages")}
    missing_in_db = sorted(raw_ids - db_ids)
    extra_in_db = sorted(db_ids - raw_ids)
    return {
        "ok": not missing_in_db and not extra_in_db,
        "raw_count": len(raw_ids),
        "db_count": len(db_ids),
        "missing_in_db": missing_in_db,
        "extra_in_db": extra_in_db,
    }


def backfill(config: BackfillConfig) -> dict[str, Any]:
    data = load_export(config.input_path)
    messages = iter_messages(data)
    write_jsonl(config.mirror_dir / "messages.jsonl", messages)
    write_jsonl(config.mirror_dir / "channels.jsonl", data.get("channels", []))
    con = connect(config.db_path)
    import_to_db(con, data, messages)
    check = parity(con, messages)
    con.execute(
        "INSERT INTO backfill_runs(created_at, source, raw_messages, db_messages, parity_ok) VALUES (?, ?, ?, ?, ?)",
        (utc_now(), str(config.input_path), check["raw_count"], check["db_count"], int(check["ok"])),
    )
    con.commit()
    render_dashboard(con, config.dashboard_path, check)
    result = status(config.db_path)
    result["parity"] = check
    con.close()
    if not check["ok"]:
        raise RuntimeError(f"parity failed: {check}")
    return result


def status(db_path: Path) -> dict[str, Any]:
    con = connect(db_path)
    tables = {
        "channels": "SELECT count(*) c FROM channels",
        "messages": "SELECT count(*) c FROM messages",
        "versions": "SELECT count(*) c FROM message_versions",
        "attachments": "SELECT count(*) c FROM attachments",
        "events": "SELECT count(*) c FROM event_envelopes",
        "quarantine": "SELECT count(*) c FROM quarantine",
    }
    result = {name: con.execute(sql).fetchone()["c"] for name, sql in tables.items()}
    con.close()
    return result


def search_messages(db_path: Path, query: str, limit: int = 10) -> list[dict[str, Any]]:
    con = connect(db_path)
    rows: list[sqlite3.Row]
    try:
        rows = con.execute(
            """
            SELECT m.id, m.channel_id, m.author_name, m.content_safe, m.created_at
            FROM messages_fts f
            JOIN messages m ON m.id = f.id
            WHERE messages_fts MATCH ?
            ORDER BY rank
            LIMIT ?
            """,
            (query, limit),
        ).fetchall()
    except sqlite3.DatabaseError:
        like = f"%{normalize_text(query)}%"
        rows = con.execute(
            """
            SELECT id, channel_id, author_name, content_safe, created_at
            FROM messages
            WHERE content_searchable LIKE ?
            ORDER BY created_at
            LIMIT ?
            """,
            (like, limit),
        ).fetchall()
    result = [dict(row) for row in rows]
    con.close()
    return result


def render_dashboard(con: sqlite3.Connection, path: Path, check: dict[str, Any]) -> None:
    counts = {
        "channels": con.execute("SELECT count(*) c FROM channels").fetchone()["c"],
        "messages": con.execute("SELECT count(*) c FROM messages").fetchone()["c"],
        "attachments": con.execute("SELECT count(*) c FROM attachments").fetchone()["c"],
        "quarantine": con.execute("SELECT count(*) c FROM quarantine").fetchone()["c"],
    }
    messages = con.execute(
        """
        SELECT m.id, c.name channel_name, m.author_name, m.content_safe, m.created_at
        FROM messages m JOIN channels c ON c.id=m.channel_id
        ORDER BY m.created_at
        """
    ).fetchall()
    quarantined = con.execute(
        "SELECT message_id, reason FROM quarantine ORDER BY id"
    ).fetchall()
    path.parent.mkdir(parents=True, exist_ok=True)
    cards = "\n".join(
        f"<article><strong>{html.escape(row['author_name'] or 'unknown')}</strong>"
        f"<small>#{html.escape(row['channel_name'])} · {html.escape(row['created_at'])} · {html.escape(row['id'])}</small>"
        f"<p>{html.escape(row['content_safe'])}</p></article>"
        for row in messages
    )
    quarantine_html = "\n".join(
        f"<li><code>{html.escape(row['message_id'])}</code> quarantined by <code>{html.escape(row['reason'])}</code></li>"
        for row in quarantined
    ) or "<li>No quarantine hits</li>"
    path.write_text(
        f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Atom Discord Backfill Dashboard</title>
  <style>
    :root {{ color-scheme: dark; font-family: Inter, system-ui, sans-serif; background: #111318; color: #edf0f4; }}
    body {{ margin: 0; }}
    header {{ padding: 32px 40px; background: #20242d; border-bottom: 1px solid #343a46; }}
    h1 {{ margin: 0 0 8px; font-size: 32px; }}
    .status {{ color: {"#7ee787" if check["ok"] else "#ff7b72"}; font-weight: 700; }}
    main {{ padding: 28px 40px; display: grid; gap: 24px; }}
    .stats {{ display: grid; grid-template-columns: repeat(4, minmax(120px, 1fr)); gap: 12px; }}
    .stat, article, section {{ background: #1c212b; border: 1px solid #343a46; border-radius: 8px; padding: 16px; }}
    .stat b {{ display: block; font-size: 28px; }}
    article small {{ display: block; margin-top: 4px; color: #9aa4b2; }}
    article p {{ line-height: 1.55; }}
    code {{ color: #f7c767; }}
  </style>
</head>
<body>
  <header>
    <h1>Atom Discord Backfill Dashboard</h1>
    <div>Parity gate: <span class="status">{html.escape(str(check["ok"]))}</span> · raw={check["raw_count"]} db={check["db_count"]}</div>
  </header>
  <main>
    <section class="stats">
      <div class="stat"><b>{counts["channels"]}</b> channels</div>
      <div class="stat"><b>{counts["messages"]}</b> messages</div>
      <div class="stat"><b>{counts["attachments"]}</b> attachments</div>
      <div class="stat"><b>{counts["quarantine"]}</b> quarantine hits</div>
    </section>
    <section>
      <h2>Secret quarantine</h2>
      <ul>{quarantine_html}</ul>
    </section>
    <section>
      <h2>Messages</h2>
      {cards}
    </section>
  </main>
</body>
</html>
""",
        encoding="utf-8",
    )
