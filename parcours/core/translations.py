"""Loads `translations.csv`: the flat lookup for UI-facing strings *and*
the content glossary (e.g. `category: location`) — see SPECS.md,
"Translations". Also owns add/edit/delete for translation rows (`parco
translation ...`), reusing `entries.py`'s generic CSV-write and
auto-commit helpers rather than duplicating them."""

import csv
from dataclasses import dataclass
from pathlib import Path

from .entries import git_commit, is_file_dirty, write_all_rows

_FIELDNAMES = ["id", "category", "en", "fr"]


@dataclass
class TranslationEntry:
    id: str
    category: str
    en: str
    fr: str


class TranslationNotFound(Exception):
    """Raised by edit_translation/delete_translation for a (category, id)
    pair that doesn't exist in translations.csv."""


class TranslationExists(Exception):
    """Raised by add_translation when the (category, id) pair already
    exists — use edit_translation to change it instead."""


class TranslationsTable:
    """`(category, id)` lookups are case-insensitive — a location typed
    as "Montreal" must match a glossary entry added as "montreal", since
    a human would never expect capitalization alone to create two
    different places. The original casing is preserved on `TranslationEntry`
    for display; only the lookup key is folded."""

    def __init__(self, entries: list[TranslationEntry]):
        self._entries = entries
        self._by_key: dict[tuple[str, str], TranslationEntry] = {
            (e.category.lower(), e.id.lower()): e for e in entries
        }

    def all(self) -> list[TranslationEntry]:
        return list(self._entries)

    def exists(self, category: str, id_: str) -> bool:
        return (category.lower(), id_.lower()) in self._by_key

    def get(self, category: str, id_: str) -> TranslationEntry | None:
        return self._by_key.get((category.lower(), id_.lower()))

    def lookup(self, category: str, id_: str, lang: str) -> str | None:
        entry = self._by_key.get((category.lower(), id_.lower()))
        if entry is None:
            return None
        value = entry.en if lang == "en" else entry.fr
        return value or None

    def resolve_or_literal(self, category: str, id_: str, lang: str) -> str:
        """Look up a glossary/UI translation; fall back to the literal id
        if unmatched, so an unrecognized value never blocks anything (see
        SPECS.md's location-glossary fallback rule)."""
        value = self.lookup(category, id_, lang)
        return value if value is not None else id_

    def missing_translations(self) -> list[TranslationEntry]:
        """Entries with a blank English or French side — the "missing
        translation = fail loudly" rule applies to translations.csv's own
        finite set of UI strings, not to per-row category content."""
        return [e for e in self._entries if not e.en.strip() or not e.fr.strip()]


def load_translations(path: Path) -> TranslationsTable:
    entries = []
    with open(path, "r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            entries.append(
                TranslationEntry(
                    id=row["id"],
                    category=row["category"],
                    en=row.get("en") or "",
                    fr=row.get("fr") or "",
                )
            )
    return TranslationsTable(entries)


def _translations_path(data_dir: Path) -> Path:
    return data_dir / "translations.csv"


def _load_translations_or_empty(path: Path) -> TranslationsTable:
    if not path.is_file():
        return TranslationsTable([])
    return load_translations(path)


def _entry_row(entry: TranslationEntry) -> dict:
    return {"id": entry.id, "category": entry.category, "en": entry.en, "fr": entry.fr}


def _matches(entry: TranslationEntry, category: str, id_: str) -> bool:
    return entry.category.lower() == category.lower() and entry.id.lower() == id_.lower()


def add_translation(data_dir: Path, category: str, id_: str, en: str, fr: str) -> TranslationEntry:
    table = _load_translations_or_empty(_translations_path(data_dir))
    if table.exists(category, id_):
        raise TranslationExists(f"A translation for category '{category}' id '{id_}' already exists")

    new_entry = TranslationEntry(id=id_, category=category, en=en, fr=fr)
    rows = [_entry_row(e) for e in table.all()] + [_entry_row(new_entry)]
    was_already_dirty = is_file_dirty(data_dir, "translations.csv")
    write_all_rows(_translations_path(data_dir), _FIELDNAMES, rows)
    git_commit(data_dir, "translations.csv", f"Added translation {category}:{id_}", was_already_dirty)
    return new_entry


def edit_translation(data_dir: Path, category: str, id_: str, en: str, fr: str) -> TranslationEntry:
    table = _load_translations_or_empty(_translations_path(data_dir))
    current = table.get(category, id_)
    if current is None:
        raise TranslationNotFound(f"No translation for category '{category}' id '{id_}'")

    # Preserve the stored category/id casing — editing changes en/fr,
    # never silently renames the glossary key's casing.
    updated = TranslationEntry(id=current.id, category=current.category, en=en, fr=fr)
    rows = [
        _entry_row(updated) if _matches(e, category, id_) else _entry_row(e)
        for e in table.all()
    ]
    was_already_dirty = is_file_dirty(data_dir, "translations.csv")
    write_all_rows(_translations_path(data_dir), _FIELDNAMES, rows)
    git_commit(data_dir, "translations.csv", f"Edited translation {category}:{id_}", was_already_dirty)
    return updated


def delete_translation(data_dir: Path, category: str, id_: str) -> None:
    table = _load_translations_or_empty(_translations_path(data_dir))
    if not table.exists(category, id_):
        raise TranslationNotFound(f"No translation for category '{category}' id '{id_}'")

    rows = [_entry_row(e) for e in table.all() if not _matches(e, category, id_)]
    was_already_dirty = is_file_dirty(data_dir, "translations.csv")
    write_all_rows(_translations_path(data_dir), _FIELDNAMES, rows)
    git_commit(data_dir, "translations.csv", f"Deleted translation {category}:{id_}", was_already_dirty)
