import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from backend.app.core.monitor import check_and_store
from backend.app.core.storage import (
    get_connection,
    get_latest_snapshot,
    get_source,
)


class IntegrationTests(unittest.TestCase):

    @patch("backend.app.core.monitor.fetch_page")
    def test_full_monitoring_cycle(self, mock_fetch):
        with TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "test_cornet.db"

            mock_fetch.side_effect = [
                "<html><body><h1>Version 1</h1></body></html>",
                "<html><body><h1>Version 2</h1></body></html>",
            ]

            url = "https://example.com"

            first = check_and_store(url, db_path)

            self.assertFalse(first["changed"])
            self.assertEqual(first["content"], "Version 1")

            source = get_source(first["source_id"], db_path)
            self.assertIsNotNone(source)

            first_snapshot = get_latest_snapshot(
                first["source_id"],
                db_path,
            )

            self.assertEqual(
                first_snapshot["content"],
                "Version 1",
            )

            second = check_and_store(url, db_path)

            self.assertTrue(second["changed"])
            self.assertEqual(second["content"], "Version 2")
            self.assertEqual(
                second["source_id"],
                first["source_id"],
            )

            second_snapshot = get_latest_snapshot(
                second["source_id"],
                db_path,
            )

            self.assertEqual(
                second_snapshot["content"],
                "Version 2",
            )

            with get_connection(db_path) as connection:
                events = connection.execute(
                    "SELECT * FROM events WHERE source_id = ?",
                    (first["source_id"],),
                ).fetchall()

            self.assertEqual(len(events), 1)
            self.assertEqual(
                events[0]["previous_hash"],
                first["content_hash"],
            )
            self.assertEqual(
                events[0]["current_hash"],
                second["content_hash"],
            )

            mock_fetch.assert_called_with(url)
            self.assertEqual(mock_fetch.call_count, 2)


    @patch("backend.app.core.monitor.fetch_page")
    def test_network_error_does_not_create_snapshot(
        self,
        mock_fetch,
    ):
        with TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "test_cornet.db"
            url = "https://example.com"

            mock_fetch.side_effect = RuntimeError("Network error")

            with self.assertRaises(RuntimeError):
                check_and_store(url, db_path)

            source = get_source(1, db_path)
            self.assertIsNotNone(source)

            snapshot = get_latest_snapshot(1, db_path)
            self.assertIsNone(snapshot)

            with get_connection(db_path) as connection:
                events = connection.execute(
                    "SELECT * FROM events WHERE source_id = 1"
                ).fetchall()

            self.assertEqual(len(events), 0)
            mock_fetch.assert_called_once_with(url)


if __name__ == "__main__":
    unittest.main()
