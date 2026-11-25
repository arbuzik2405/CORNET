import hashlib
import re
import unicodedata


def normalize_text(content: str) -> str:
    text = unicodedata.normalize("NFKC", content)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def calculate_hash(content: str) -> str:
    normalized = normalize_text(content)
    return hashlib.sha256(
        normalized.encode("utf-8")
    ).hexdigest()


def has_changed(old_hash: str | None, new_hash: str) -> bool:
    if old_hash is None:
        return True

    return old_hash != new_hash
