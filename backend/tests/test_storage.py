import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from backend.app.core.storage import (
    initialize_database,
    get_connection,
    add_source,
    get_source,
    get_latest_snapshot,
    save_check,
    set_source_schedule,
    list_due_sources,
    schedule_next_check,
)


class StorageTests(unittest.TestCase):

    def setUp(self):
        self.temp_dir = TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test.db"

        initialize_database(self.db_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_add_source(self):
        first_id = add_source(
            "https://example.com",
            self.db_path,
        )

        second_id = add_source(
            "https://example.com",
            self.db_path,
        )

        self.assertEqual(first_id, second_id)

    def test_save_first_snapshot(self):
        source_id = add_source(
            "https://example.com",
            self.db_path,
        )

        result = save_check(
            source_id,
            "Version 1",
            "hash_1",
            self.db_path,
        )

        self.assertFalse(result["changed"])
        self.assertIsNone(result["previous_hash"])

    def test_detect_content_change(self):
        source_id = add_source(
            "https://example.com",
            self.db_path,
        )

        save_check(
            source_id,
            "Version 1",
            "hash_1",
            self.db_path,
        )

        result = save_check(
            source_id,
            "Version 2",
            "hash_2",
            self.db_path,
        )

        self.assertTrue(result["changed"])
        self.assertEqual(result["previous_hash"], "hash_1")

    def test_change_creates_event(self):
        source_id = add_source(
            "https://example.com",
            self.db_path,
        )

        save_check(
            source_id,
            "Version 1",
            "hash_1",
            self.db_path,
        )

        save_check(
            source_id,
            "Version 2",
            "hash_2",
            self.db_path,
        )

        with get_connection(self.db_path) as connection:
            count = connection.execute(
                "SELECT COUNT(*) FROM events"
            ).fetchone()[0]

        self.assertEqual(count, 1)

    def test_latest_snapshot(self):
        source_id = add_source(
            "https://example.com",
            self.db_path,
        )

        save_check(
            source_id,
            "Version 1",
            "hash_1",
            self.db_path,
        )

        save_check(
            source_id,
            "Version 2",
            "hash_2",
            self.db_path,
        )

        snapshot = get_latest_snapshot(
            source_id,
            self.db_path,
        )

        self.assertEqual(snapshot["content"], "Version 2")
        self.assertEqual(snapshot["content_hash"], "hash_2")

    def test_active_source_schedule(self):
        source_id = add_source(
            "https://example.com",
            self.db_path,
        )

        set_source_schedule(
            source_id,
            interval_minutes=30,
            active=True,
            db_path=self.db_path,
        )

        due_sources = list_due_sources(self.db_path)

        self.assertEqual(len(due_sources), 1)
        self.assertEqual(due_sources[0]["id"], source_id)

    def test_inactive_source_is_not_due(self):
        source_id = add_source(
            "https://example.com",
            self.db_path,
        )

        set_source_schedule(
            source_id,
            interval_minutes=30,
            active=False,
            db_path=self.db_path,
        )

        self.assertEqual(list_due_sources(self.db_path), [])

    def test_inactive_source_schedule_does_not_change(self):
        source_id = add_source(
            "https://example.com",
            self.db_path,
        )

        set_source_schedule(
            source_id,
            interval_minutes=30,
            active=False,
            db_path=self.db_path,
        )

        before = get_source(source_id, self.db_path)

        schedule_next_check(source_id, self.db_path)

        after = get_source(source_id, self.db_path)

        self.assertEqual(
            before["next_check_at"],
            after["next_check_at"],
        )


if __name__ == "__main__":
    unittest.main()
