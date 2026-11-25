import unittest
from unittest.mock import patch

from backend.app.core.scheduler import run_pending_checks
from backend.app.core.storage import DB_PATH


class SchedulerTests(unittest.TestCase):

    @patch("backend.app.core.scheduler.check_and_store")
    @patch("backend.app.core.scheduler.list_due_sources")
    def test_no_due_sources(self, mock_list, mock_check):
        mock_list.return_value = []

        run_pending_checks()

        mock_check.assert_not_called()

    @patch("backend.app.core.scheduler.check_and_store")
    @patch("backend.app.core.scheduler.list_due_sources")
    def test_processes_multiple_sources(self, mock_list, mock_check):
        mock_list.return_value = [
            {"id": 1, "url": "https://example.com"},
            {"id": 2, "url": "https://example.org"},
        ]

        mock_check.side_effect = [
            {"changed": False},
            {"changed": True},
        ]

        run_pending_checks()

        self.assertEqual(mock_check.call_count, 2)
        mock_check.assert_any_call("https://example.com", DB_PATH)
        mock_check.assert_any_call("https://example.org", DB_PATH)

    @patch("backend.app.core.scheduler.schedule_next_check")
    @patch("backend.app.core.scheduler.check_and_store")
    @patch("backend.app.core.scheduler.list_due_sources")
    def test_error_schedules_retry(
        self,
        mock_list,
        mock_check,
        mock_schedule,
    ):
        mock_list.return_value = [
            {"id": 1, "url": "https://example.com"},
        ]

        mock_check.side_effect = RuntimeError("Network error")

        run_pending_checks()

        mock_schedule.assert_called_once_with(1, DB_PATH)

    @patch("backend.app.core.scheduler.schedule_next_check")
    @patch("backend.app.core.scheduler.check_and_store")
    @patch("backend.app.core.scheduler.list_due_sources")
    def test_schedule_error_does_not_stop_scheduler(
        self,
        mock_list,
        mock_check,
        mock_schedule,
    ):
        mock_list.return_value = [
            {"id": 1, "url": "https://example.com"},
        ]

        mock_check.side_effect = RuntimeError("Network error")
        mock_schedule.side_effect = RuntimeError("Database error")

        run_pending_checks()


if __name__ == "__main__":
    unittest.main()
