"""Small text helpers."""

import re
import unicodedata


def slugify(value: str) -> str:
    """ASCII, lowercase, hyphen separated (accents are stripped)."""
    ascii_only = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_only.lower()).strip("-")
    return slug or "section"


def reading_minutes(text: str, words_per_minute: int = 200) -> int:
    words = len(re.findall(r"\w+", text))
    return max(1, -(-words // words_per_minute))
