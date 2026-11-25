from pathlib import Path

from .page_fetcher import fetch_page
from .content_extractor import extract_text
from .change_detector import calculate_hash, has_changed
from .storage import (
    DB_PATH,
    initialize_database,
    add_source,
    save_check,
    schedule_next_check,
)

def monitor_page(url: str, previous_hash: str | None = None) -> dict:
    html = fetch_page(url)
    content = extract_text(html)

    if not content:
        raise ValueError("Page contains no extractable text")

    current_hash = calculate_hash(content)

    return {
        "url": url,
        "content": content,
        "content_hash": current_hash,
        "changed": has_changed(previous_hash, current_hash),
    }


def check_and_store(
    url: str,
    db_path: Path = DB_PATH,
) -> dict:
    initialize_database(db_path)

    source_id = add_source(url, db_path)

    result = monitor_page(url)

    saved = save_check(
        source_id=source_id,
        content=result["content"],
        content_hash=result["content_hash"],
        db_path=db_path,
    )

    schedule_next_check(source_id, db_path)

    return {
        **result,
        "source_id": source_id,
        "snapshot_id": saved["snapshot_id"],
        "changed": saved["changed"],
        "previous_hash": saved["previous_hash"],
    }

