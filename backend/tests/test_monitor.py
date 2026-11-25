import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from backend.app.core.monitor import (
    monitor_page,
    check_and_store,
)


class MonitorTests(unittest.TestCase):

    def test_monitor_page_extracts_text(self):
        html = """
        <html>
            <head><title>Test</title></head>
            <body>
                <h1>Hello CORNET</h1>
                <script>ignored content</script>
            </body>
        </html>
        """

        with patch(
            "backend.app.core.monitor.fetch_page",
            return_value=html,
        ):
            result = monitor_page("https://example.com")

        self.assertEqual(result["content"], "Hello CORNET")
        self.assertEqual(result["url"], "https://example.com")
        self.assertTrue(result["content_hash"])
        self.assertTrue(result["changed"])

    def test_monitor_page_detects_no_change(self):
        html = "<html><body>Hello CORNET</body></html>"

        with patch(
            "backend.app.core.monitor.fetch_page",
            return_value=html,
        ):
            first = monitor_page("https://example.com")

            second = monitor_page(
                "https://example.com",
                previous_hash=first["content_hash"],
            )

        self.assertFalse(second["changed"])

    def test_monitor_page_detects_change(self):
        first_html = "<html><body>Version 1</body></html>"
        second_html = "<html><body>Version 2</body></html>"

        with patch(
            "backend.app.core.monitor.fetch_page",
            side_effect=[first_html, second_html],
        ):
            first = monitor_page("https://example.com")

            second = monitor_page(
                "https://example.com",
                previous_hash=first["content_hash"],
            )

        self.assertTrue(second["changed"])

    def test_monitor_page_rejects_empty_content(self):
        html = "<html><head><title>Empty</title></head></html>"

        with patch(
            "backend.app.core.monitor.fetch_page",
            return_value=html,
        ):
            with self.assertRaises(ValueError):
                monitor_page("https://example.com")

    def test_check_and_store_uses_test_database(self):
        html = "<html><body>Hello CORNET</body></html>"

        with TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "test.db"

            with patch(
                "backend.app.core.monitor.fetch_page",
                return_value=html,
            ):
                result = check_and_store(
                    "https://example.com",
                    db_path=db_path,
                )

            self.assertEqual(result["source_id"], 1)
            self.assertEqual(result["snapshot_id"], 1)
            self.assertFalse(result["changed"])
            self.assertIsNone(result["previous_hash"])

    def test_check_and_store_saves_changes(self):
        first_html = "<html><body>Version 1</body></html>"
        second_html = "<html><body>Version 2</body></html>"

        with TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "test.db"

            with patch(
                "backend.app.core.monitor.fetch_page",
                side_effect=[first_html, second_html],
            ):
                first = check_and_store(
                    "https://example.com",
                    db_path=db_path,
                )

                second = check_and_store(
                    "https://example.com",
                    db_path=db_path,
                )

            self.assertFalse(first["changed"])
            self.assertTrue(second["changed"])
            self.assertEqual(second["previous_hash"], first["content_hash"])


if __name__ == "__main__":
    unittest.main()
