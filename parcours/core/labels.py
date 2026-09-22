"""Loads `labels.csv`: the flat lookup for UI-facing strings *and* the
content glossary (e.g. `category: location`) — see SPECS.md, "Labels /
translations"."""

import csv
from dataclasses import dataclass
from pathlib import Path


@dataclass
class LabelEntry:
    id: str
    category: str
    en: str
    fr: str


class LabelsTable:
    def __init__(self, entries: list[LabelEntry]):
        self._entries = entries
        self._by_key: dict[tuple[str, str], LabelEntry] = {
            (e.category, e.id): e for e in entries
        }

    def lookup(self, category: str, id_: str, lang: str) -> str | None:
        entry = self._by_key.get((category, id_))
        if entry is None:
            return None
        value = entry.en if lang == "en" else entry.fr
        return value or None

    def resolve_or_literal(self, category: str, id_: str, lang: str) -> str:
        """Look up a glossary/UI label; fall back to the literal id if
        unmatched, so an unrecognized value never blocks anything (see
        SPECS.md's location-glossary fallback rule)."""
        value = self.lookup(category, id_, lang)
        return value if value is not None else id_

    def missing_translations(self) -> list[LabelEntry]:
        """Entries with a blank English or French side — the "missing
        translation = fail loudly" rule applies to labels.csv's own
        finite set of UI strings, not to per-row category content."""
        return [e for e in self._entries if not e.en.strip() or not e.fr.strip()]


def load_labels(path: Path) -> LabelsTable:
    entries = []
    with open(path, "r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            entries.append(
                LabelEntry(
                    id=row["id"],
                    category=row["category"],
                    en=row.get("en", ""),
                    fr=row.get("fr", ""),
                )
            )
    return LabelsTable(entries)
