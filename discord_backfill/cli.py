from __future__ import annotations

import argparse
import json
from pathlib import Path

from .pipeline import BackfillConfig, backfill, search_messages, status


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


if __name__ == "__main__":
    main()
