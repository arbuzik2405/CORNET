import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from backend.app.core.scheduler import run_pending_checks
from backend.app.core.storage import (
    initialize_database,
    add_source,
    set_source_schedule,
    get_source,
    get_latest_snapshot,
    list_due_sources,
)


class SchedulerIntegrationTests(unittest.TestCase):

    @patch("backend.app.core.monitor.fetch_page")
    def test_failed_check_schedules_next_attempt(self, mock_fetch):
        with TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "test_cornet.db"
            url = "https://example.com"

            initialize_database(db_path)

            source_id = add_source(url, db_path)

            set_source_schedule(
                source_id,
                interval_minutes=60,
                active=True,
                db_path=db_path,
            )

            mock_fetch.side_effect = RuntimeError("Network error")

            run_pending_checks(db_path)

            source = get_source(source_id, db_path)

            self.assertIsNotNone(source["next_check_at"])

            self.assertIsNone(
                get_latest_snapshot(source_id, db_path)
            )

            due_sources = list_due_sources(db_path)

            self.assertEqual(len(due_sources), 0)

            mock_fetch.assert_called_once_with(url)


if __name__ == "__main__":
    unittest.main()
