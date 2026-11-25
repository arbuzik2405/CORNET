import logging
import time
from pathlib import Path

from .monitor import check_and_store
from .storage import (
    DB_PATH,
    list_due_sources,
    schedule_next_check,
)


logger = logging.getLogger("cornet.scheduler")

POLL_INTERVAL_SECONDS = 30


def run_pending_checks(db_path: Path = DB_PATH) -> None:
    sources = list_due_sources(db_path)

    if not sources:
        logger.info("No sources due for checking")
        return

    logger.info("Found %s sources to check", len(sources))

    for source in sources:
        source_id = source["id"]
        url = source["url"]

        try:
            result = check_and_store(url, db_path)

            logger.info(
                "Source %s checked. Changed: %s",
                source_id,
                result["changed"],
            )

        except Exception:
            logger.exception(
                "Failed to check source %s: %s",
                source_id,
                url,
            )

            try:
                schedule_next_check(source_id, db_path)
            except Exception:
                logger.exception(
                    "Failed to schedule retry for source %s",
                    source_id,
                )


def run_scheduler() -> None:
    logger.info("CORNET scheduler started")

    while True:
        try:
            run_pending_checks()
        except Exception:
            logger.exception("Scheduler cycle failed")

        time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    run_scheduler()
