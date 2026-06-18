from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .pipeline import BackfillConfig, backfill, fetch_channel_export, search_messages, status


def main() -> None:
    parser = argparse.ArgumentParser(description="Discord backfill/index prototype")
    sub = parser.add_subparsers(dest="command", required=True)

    p_backfill = sub.add_parser("backfill", help="ingest a Discord export")
    p_backfill.add_argument("--input", required=True, type=Path)
    p_backfill.add_argument("--mirror", required=True, type=Path)
    p_backfill.add_argument("--db", required=True, type=Path)
    p_backfill.add_argument("--dashboard", required=True, type=Path)

    p_search = sub.add_parser("search", help="search indexed messages")
    p_search.add_argument("--db", required=True, type=Path)
    p_search.add_argument("query")
    p_search.add_argument("--limit", type=int, default=10)

    p_status = sub.add_parser("status", help="show index status")
    p_status.add_argument("--db", required=True, type=Path)

    p_fetch = sub.add_parser("fetch-discord", help="fetch real Discord channel data into export JSON")
    p_fetch.add_argument("--channel-id", required=True)
    p_fetch.add_argument("--guild-id", required=True)
    p_fetch.add_argument("--guild-name", default="Discord Guild")
    p_fetch.add_argument("--channel-name", default="discord-channel")
    p_fetch.add_argument("--limit", type=int, default=100)
    p_fetch.add_argument("--output", required=True, type=Path)
    p_fetch.add_argument("--redact", action="store_true", help="redact secret-like text before writing the export")

    args = parser.parse_args()

    if args.command == "backfill":
        result = backfill(
            BackfillConfig(
                input_path=args.input,
                mirror_dir=args.mirror,
                db_path=args.db,
                dashboard_path=args.dashboard,
            )
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.command == "search":
        rows = search_messages(args.db, args.query, limit=args.limit)
        print(json.dumps(rows, ensure_ascii=False, indent=2))
    elif args.command == "status":
        print(json.dumps(status(args.db), ensure_ascii=False, indent=2))
    elif args.command == "fetch-discord":
        token = os.environ.get("DISCORD_BOT_TOKEN")
        if not token:
            raise SystemExit("DISCORD_BOT_TOKEN is required")
        result = fetch_channel_export(
            token=token,
            guild_id=args.guild_id,
            guild_name=args.guild_name,
            channel_id=args.channel_id,
            channel_name=args.channel_name,
            limit=args.limit,
            output_path=args.output,
            redact_output=args.redact,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
