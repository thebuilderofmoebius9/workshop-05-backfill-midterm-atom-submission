from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from discord_backfill.pipeline import BackfillConfig, backfill, parity, search_messages


ROOT = Path(__file__).resolve().parents[1]


class BackfillPipelineTest(unittest.TestCase):
    def run_backfill(self):
        tmp = tempfile.TemporaryDirectory()
        root = Path(tmp.name)
        result = backfill(
            BackfillConfig(
                input_path=ROOT / "samples" / "discord-export.json",
                mirror_dir=root / "mirror",
                db_path=root / "atom.sqlite",
                dashboard_path=root / "dashboard.html",
            )
        )
        return tmp, root, result

    def test_backfill_writes_mirror_db_and_dashboard(self):
        tmp, root, result = self.run_backfill()
        self.addCleanup(tmp.cleanup)

        self.assertTrue((root / "mirror" / "messages.jsonl").exists())
        self.assertTrue((root / "atom.sqlite").exists())
        self.assertTrue((root / "dashboard.html").exists())
        self.assertEqual(result["messages"], 4)
        self.assertEqual(result["attachments"], 1)
        self.assertTrue(result["parity"]["ok"])

    def test_quarantine_redacts_secret_like_content(self):
        tmp, root, _ = self.run_backfill()
        self.addCleanup(tmp.cleanup)

        con = sqlite3.connect(root / "atom.sqlite")
        row = con.execute("SELECT content_safe FROM messages WHERE id='1517300000000000004'").fetchone()
        hits = con.execute("SELECT count(*) FROM quarantine").fetchone()[0]
        con.close()

        self.assertIn("[REDACTED]", row[0])
        self.assertEqual(hits, 1)

    def test_search_finds_backfill_and_kikyo_lessons(self):
        tmp, root, _ = self.run_backfill()
        self.addCleanup(tmp.cleanup)

        backfill_rows = search_messages(root / "atom.sqlite", "backfill")
        kikyo_rows = search_messages(root / "atom.sqlite", "Kikyo")

        self.assertGreaterEqual(len(backfill_rows), 1)
        self.assertEqual(kikyo_rows[0]["id"], "1517300000000000003")

    def test_parity_detects_missing_message(self):
        tmp, root, _ = self.run_backfill()
        self.addCleanup(tmp.cleanup)

        con = sqlite3.connect(root / "atom.sqlite")
        con.row_factory = sqlite3.Row
        con.execute("DELETE FROM messages WHERE id='1517300000000000001'")
        con.commit()

        check = parity(
            con,
            [
                {"id": "1517300000000000001"},
                {"id": "1517300000000000002"}
            ],
        )
        con.close()

        self.assertFalse(check["ok"])
        self.assertIn("1517300000000000001", check["missing_in_db"])


if __name__ == "__main__":
    unittest.main()
