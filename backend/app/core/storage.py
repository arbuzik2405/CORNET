import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path


DB_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "cornet.db"
)


class DatabaseConnection:
    def __init__(self, db_path: Path):
        self.connection = sqlite3.connect(db_path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")

    def __enter__(self):
        return self.connection.__enter__()

    def __exit__(self, exc_type, exc_value, traceback):
        try:
            return self.connection.__exit__(
                exc_type,
                exc_value,
                traceback,
            )
        finally:
            self.connection.close()


def get_connection(db_path: Path = DB_PATH):
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return DatabaseConnection(db_path)


def initialize_database(db_path: Path = DB_PATH):
    with get_connection(db_path) as connection:
        connection.executescript("""
            CREATE TABLE IF NOT EXISTS sources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                last_checked_at TEXT
            );

            CREATE TABLE IF NOT EXISTS snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_id INTEGER NOT NULL,
                content TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                checked_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (source_id)
                    REFERENCES sources(id)
                    ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_id INTEGER NOT NULL,
                previous_hash TEXT NOT NULL,
                current_hash TEXT NOT NULL,
                detected_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (source_id)
                    REFERENCES sources(id)
                    ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS
                idx_snapshots_source_id
                ON snapshots(source_id);

            CREATE INDEX IF NOT EXISTS
                idx_events_source_id
                ON events(source_id);
        """)


        columns = {
            row["name"]
            for row in connection.execute(
                "PRAGMA table_info(sources)"
            ).fetchall()
        }

        if "check_interval_minutes" not in columns:
            connection.execute(
                """
                ALTER TABLE sources
                ADD COLUMN check_interval_minutes INTEGER
                NOT NULL DEFAULT 60
                """
            )

        if "is_active" not in columns:
            connection.execute(
                """
                ALTER TABLE sources
                ADD COLUMN is_active INTEGER
                NOT NULL DEFAULT 1
                """
            )

        if "next_check_at" not in columns:
            connection.execute(
                """
                ALTER TABLE sources
                ADD COLUMN next_check_at TEXT
                """
            )


def add_source(url: str, db_path: Path = DB_PATH) -> int:
    with get_connection(db_path) as connection:
        connection.execute(
            "INSERT OR IGNORE INTO sources (url) VALUES (?)",
            (url,),
        )

        row = connection.execute(
            "SELECT id FROM sources WHERE url = ?",
            (url,),
        ).fetchone()

        return row["id"]


def get_source(source_id: int, db_path: Path = DB_PATH):
    with get_connection(db_path) as connection:
        row = connection.execute(
            "SELECT * FROM sources WHERE id = ?",
            (source_id,),
        ).fetchone()

        return dict(row) if row else None


def get_latest_snapshot(
    source_id: int,
    db_path: Path = DB_PATH,
):
    with get_connection(db_path) as connection:
        row = connection.execute(
            """
            SELECT * FROM snapshots
            WHERE source_id = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (source_id,),
        ).fetchone()

        return dict(row) if row else None


def save_check(
    source_id: int,
    content: str,
    content_hash: str,
    db_path: Path = DB_PATH,
) -> dict:
    with get_connection(db_path) as connection:
        source = connection.execute(
            "SELECT id FROM sources WHERE id = ?",
            (source_id,),
        ).fetchone()

        if source is None:
            raise ValueError(f"Source {source_id} does not exist")

        previous = connection.execute(
            """
            SELECT content_hash FROM snapshots
            WHERE source_id = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (source_id,),
        ).fetchone()

        previous_hash = (
            previous["content_hash"] if previous else None
        )

        changed = (
            previous_hash is not None
            and previous_hash != content_hash
        )

        cursor = connection.execute(
            """
            INSERT INTO snapshots (
                source_id, content, content_hash
            )
            VALUES (?, ?, ?)
            """,
            (source_id, content, content_hash),
        )

        if changed:
            connection.execute(
                """
                INSERT INTO events (
                    source_id, previous_hash, current_hash
                )
                VALUES (?, ?, ?)
                """,
                (source_id, previous_hash, content_hash),
            )

        connection.execute(
            """
            UPDATE sources
            SET last_checked_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (source_id,),
        )

        return {
            "snapshot_id": cursor.lastrowid,
            "changed": changed,
            "previous_hash": previous_hash,
            "current_hash": content_hash,
        }


def list_sources(db_path: Path = DB_PATH) -> list[dict]:
    with get_connection(db_path) as connection:
        rows = connection.execute(
            "SELECT * FROM sources ORDER BY id"
        ).fetchall()

        return [dict(row) for row in rows]


def set_source_schedule(
    source_id: int,
    interval_minutes: int = 60,
    active: bool = True,
    db_path: Path = DB_PATH,
) -> None:
    if interval_minutes < 1:
        raise ValueError("Interval must be at least 1 minute")

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    with get_connection(db_path) as connection:
        cursor = connection.execute(
            """
            UPDATE sources
            SET check_interval_minutes = ?,
                is_active = ?,
                next_check_at = ?
            WHERE id = ?
            """,
            (interval_minutes, int(active), now, source_id),
        )

        if cursor.rowcount == 0:
            raise ValueError(f"Source {source_id} does not exist")


def list_due_sources(
    db_path: Path = DB_PATH,
) -> list[dict]:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    with get_connection(db_path) as connection:
        rows = connection.execute(
            """
            SELECT *
            FROM sources
            WHERE is_active = 1
              AND (
                  next_check_at IS NULL
                  OR next_check_at <= ?
              )
            ORDER BY next_check_at, id
            """,
            (now,),
        ).fetchall()

        return [dict(row) for row in rows]


def schedule_next_check(
    source_id: int,
    db_path: Path = DB_PATH,
) -> None:
    with get_connection(db_path) as connection:
        source = connection.execute(
            """
            SELECT check_interval_minutes, is_active
            FROM sources
            WHERE id = ?
            """,
            (source_id,),
        ).fetchone()

        if source is None:
            raise ValueError(f"Source {source_id} does not exist")

        if not source["is_active"]:
            return

        next_check = (
            datetime.now(timezone.utc)
            + timedelta(minutes=source["check_interval_minutes"])
        ).isoformat(timespec="seconds")

        connection.execute(
            """
            UPDATE sources
            SET next_check_at = ?
            WHERE id = ?
            """,
            (next_check, source_id),
        )
