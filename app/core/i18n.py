"""Locale negotiation and gettext catalogs (compiled in memory from the .po files)."""

import io
from datetime import date
from pathlib import Path

from babel.dates import format_date
from babel.messages.mofile import write_mo
from babel.messages.pofile import read_po
from babel.support import NullTranslations, Translations

from app.core.config import LOCALES

LOCALES_DIR = Path(__file__).resolve().parents[1] / "locales"
BABEL_LOCALES = {"pt": "pt_BR", "en": "en"}
HTML_LANG = {"pt": "pt-BR", "en": "en"}


def _(message: str) -> str:
    """Mark a string for extraction; it is translated later, at render time."""
    return message


def load_translations(locale: str, locales_dir: Path = LOCALES_DIR) -> NullTranslations:
    babel_locale = BABEL_LOCALES[locale]
    po_file = locales_dir / babel_locale / "LC_MESSAGES" / "messages.po"
    if not po_file.is_file():
        return NullTranslations()
    with po_file.open("rb") as handle:
        catalog = read_po(handle, locale=babel_locale)
    buffer = io.BytesIO()
    write_mo(buffer, catalog)
    buffer.seek(0)
    return Translations(buffer)


def parse_accept_language(header: str | None) -> list[str]:
    """Return language ranges from an Accept-Language header, best first."""
    if not header:
        return []
    ranked: list[tuple[float, int, str]] = []
    for index, part in enumerate(header.split(",")):
        piece = part.strip()
        if not piece:
            continue
        language, _sep, params = piece.partition(";")
        quality = 1.0
        params = params.strip()
        if params.startswith("q="):
            try:
                quality = float(params[2:])
            except ValueError:
                continue
        if quality > 0:
            ranked.append((quality, index, language.strip().lower()))
    ranked.sort(key=lambda item: (-item[0], item[1]))
    return [language for _quality, _index, language in ranked]


def negotiate_locale(header: str | None, default: str) -> str:
    for language in parse_accept_language(header):
        primary = language.split("-")[0]
        if primary in LOCALES:
            return primary
    return default


def format_date_for(locale: str, value: date | None, pattern: str = "MMM yyyy") -> str:
    if value is None:
        return ""
    return format_date(value, format=pattern, locale=BABEL_LOCALES[locale])
