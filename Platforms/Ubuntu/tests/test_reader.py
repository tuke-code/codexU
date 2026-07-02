from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from codexu_ubuntu.models import TaskColumnKind
from codexu_ubuntu.reader import CodexUsageReader, parse_session_usage


class CodexUsageReaderTests(unittest.TestCase):
    def test_reads_sqlite_jsonl_archived_sessions_and_automations(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            codex_home = Path(temp_dir)
            rollout = codex_home / "sessions" / "2026" / "07" / "rollout-main.jsonl"
            archived_rollout = codex_home / "archived_sessions" / "rollout-old.jsonl"
            rollout.parent.mkdir(parents=True)
            archived_rollout.parent.mkdir(parents=True)
            now = datetime.now().astimezone()
            self._write_token_events(rollout, now, [1200, 2100])
            self._write_token_events(archived_rollout, now, [300])
            self._write_database(codex_home, rollout, now)
            self._write_automation(codex_home)

            snapshot = CodexUsageReader(
                codex_home,
                enable_app_server=False,
            ).load()

            self.assertIsNotNone(snapshot.local)
            assert snapshot.local is not None
            self.assertEqual(snapshot.local.thread_count, 3)
            self.assertGreater(snapshot.local.today_tokens, 0)
            self.assertEqual(len(snapshot.local.daily_buckets), 7)

            self.assertIsNotNone(snapshot.local.detailed_usage)
            assert snapshot.local.detailed_usage is not None
            self.assertEqual(snapshot.local.detailed_usage.parsed_file_count, 2)
            self.assertEqual(snapshot.local.detailed_usage.token_event_count, 3)
            self.assertEqual(
                snapshot.local.detailed_usage.lifetime.tokens.visible_total_tokens,
                2400,
            )

            self.assertIsNotNone(snapshot.task_board)
            assert snapshot.task_board is not None
            counts = {
                column.id: column.count for column in snapshot.task_board.columns
            }
            self.assertEqual(counts[TaskColumnKind.ACTIVE], 1)
            self.assertEqual(counts[TaskColumnKind.PENDING], 1)
            self.assertEqual(counts[TaskColumnKind.SCHEDULED], 1)
            self.assertEqual(counts[TaskColumnKind.DONE], 1)

    def test_parse_session_usage_handles_counter_reset(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "rollout-reset.jsonl"
            now = datetime.now().astimezone()
            self._write_token_event(path, now - timedelta(minutes=2), 2000)
            with path.open("a", encoding="utf-8") as handle:
                handle.write("\n")
            self._write_token_event(path, now, 500, append=True)

            parsed = parse_session_usage(path)

            self.assertIsNotNone(parsed)
            assert parsed is not None
            self.assertEqual(parsed.token_event_count, 2)
            self.assertEqual(
                sum(delta.tokens.total_tokens for delta in parsed.deltas),
                2500,
            )

    def _write_database(
        self,
        codex_home: Path,
        rollout: Path,
        now: datetime,
    ) -> None:
        db_path = codex_home / "state_5.sqlite"
        connection = sqlite3.connect(db_path)
        try:
            connection.execute(
                """
                CREATE TABLE threads (
                  id TEXT,
                  title TEXT,
                  preview TEXT,
                  tokens_used INTEGER,
                  updated_at INTEGER,
                  recency_at INTEGER,
                  created_at INTEGER,
                  archived INTEGER,
                  archived_at INTEGER,
                  model TEXT,
                  cwd TEXT,
                  rollout_path TEXT
                );
                """
            )
            rows = [
                (
                    "thread-active-1234",
                    "Active task",
                    "Active preview",
                    1500,
                    int(now.timestamp()),
                    int(now.timestamp()),
                    int(now.timestamp()),
                    0,
                    None,
                    "chat-latest",
                    "/work/active",
                    str(rollout),
                ),
                (
                    "thread-pending-5678",
                    "Pending task",
                    "Pending preview",
                    2_500_000,
                    int((now - timedelta(hours=3)).timestamp()),
                    int((now - timedelta(hours=3)).timestamp()),
                    int(now.timestamp()),
                    0,
                    None,
                    "gpt-5-codex",
                    "/work/pending",
                    "",
                ),
                (
                    "thread-done-9999",
                    "Done task",
                    "Done preview",
                    700,
                    int((now - timedelta(hours=1)).timestamp()),
                    int((now - timedelta(hours=1)).timestamp()),
                    int(now.timestamp()),
                    1,
                    int(now.timestamp()),
                    "gpt-5-codex",
                    "/work/done",
                    "",
                ),
            ]
            connection.executemany(
                "INSERT INTO threads VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);",
                rows,
            )
            connection.commit()
        finally:
            connection.close()

    def _write_automation(self, codex_home: Path) -> None:
        automation = codex_home / "automations" / "daily" / "automation.toml"
        automation.parent.mkdir(parents=True)
        automation.write_text(
            '\n'.join(
                [
                    'id = "daily"',
                    'name = "Daily review"',
                    'kind = "cron"',
                    'status = "ACTIVE"',
                    'rrule = "DTSTART:20260702T090000Z\\nRRULE:FREQ=DAILY"',
                    "updated_at = 1782963600",
                ]
            )
            + "\n",
            encoding="utf-8",
        )

    def _write_token_events(
        self,
        path: Path,
        now: datetime,
        totals: list[int],
    ) -> None:
        for index, total in enumerate(totals):
            self._write_token_event(
                path,
                now + timedelta(seconds=index),
                total,
                append=index > 0,
            )

    def _write_token_event(
        self,
        path: Path,
        timestamp: datetime,
        total: int,
        *,
        append: bool = False,
    ) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "timestamp": timestamp.isoformat(),
            "payload": {
                "type": "token_count",
                "info": {
                    "total_token_usage": {
                        "input_tokens": total // 2,
                        "cached_input_tokens": total // 4,
                        "output_tokens": total // 3,
                        "reasoning_output_tokens": 0,
                        "total_tokens": total,
                    }
                },
            },
        }
        mode = "a" if append else "w"
        with path.open(mode, encoding="utf-8") as handle:
            handle.write(json.dumps(payload) + "\n")


if __name__ == "__main__":
    unittest.main()
