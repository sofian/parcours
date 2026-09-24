"""The `publications` handler: citekey resolution against a Zotero/Better
BibTeX CSL-JSON export, required-and-must-resolve citekey validation, and
DOI+fuzzy-title dedup (see SPECS.md, "publications (handler:
publications)")."""

import json

from ..matching import fuzzy_match
from ..validation import LintIssue
from .base import CategoryHandler, Match


class PublicationsHandler(CategoryHandler):
    def __init__(self, schema, context):
        super().__init__(schema, context)
        self._csl_by_key = self._load_csl_json()

    def _load_csl_json(self) -> dict:
        json_path = self.context.data_dir / self.schema.options["json"]
        if not json_path.is_file():
            return {}
        with open(json_path, "r", encoding="utf-8") as fh:
            records = json.load(fh)
        return {record["id"]: record for record in records}

    def resolve(self, citekey: str) -> dict | None:
        return self._csl_by_key.get(citekey)

    def validate(self, entry: dict) -> list[LintIssue]:
        citekey = entry.get("citekey") or ""
        if citekey and self.resolve(citekey) is None:
            return [LintIssue(
                self.schema.name, entry.get("id"), "citekey",
                f"citekey '{citekey}' does not resolve in the citation export",
            )]
        return []

    def find_matches(self, entry: dict, existing: list[dict]) -> list[Match]:
        matches = []
        entry_record = self.resolve(entry.get("citekey", ""))
        entry_doi = (entry_record or {}).get("DOI")

        for existing_row in existing:
            if existing_row.get("id") == entry.get("id"):
                continue

            if entry.get("citekey") and entry.get("citekey") == existing_row.get("citekey"):
                matches.append(Match(existing_row["id"], "duplicate", "Same citekey"))
                continue

            existing_record = self.resolve(existing_row.get("citekey", ""))
            existing_doi = (existing_record or {}).get("DOI")
            if entry_doi and existing_doi and entry_doi == existing_doi:
                matches.append(Match(existing_row["id"], "duplicate", "Same DOI"))
                continue

            if entry_record and existing_record:
                year_a = _csl_year(entry_record)
                year_b = _csl_year(existing_record)
                titles_match = fuzzy_match(
                    entry_record.get("title", ""), existing_record.get("title", "")
                )
                if year_a is not None and year_a == year_b and titles_match:
                    matches.append(Match(existing_row["id"], "duplicate", "Fuzzy title + same year"))

        return matches

    def match_citekey_by_title(self, title: str, year: int | None) -> str | None:
        """Fuzzy-title(+year) match against the loaded CSL-JSON export —
        used by the CCV importer to resolve a citekey for a record CCV
        never gives one for (see SPECS.md, "Import"). A year within 1 of
        the CCV-given year still counts as a match — real CVs and Zotero
        entries commonly disagree by a year (an "accepted"/presented
        year on the CV vs. an actual publication year in Zotero, or vice
        versa) — anything further apart is treated as a different work.
        Returns the citekey on exactly one confident match, None on no
        match or an ambiguous (more than one) match."""
        candidates = []
        for citekey, record in self._csl_by_key.items():
            if not fuzzy_match(title, record.get("title", "")):
                continue
            record_year = _csl_year(record)
            if year is not None and record_year is not None and abs(record_year - year) > 1:
                continue
            candidates.append(citekey)
        if len(candidates) == 1:
            return candidates[0]
        return None


def _csl_year(record: dict) -> int | None:
    """Real-world CSL-JSON exports don't reliably agree on whether
    `issued.date-parts`' year is an int or a numeric string (verified
    against a real ~1800-item Better BibTeX export: both types occur
    within the same file) — normalize to int so year comparisons here
    and in `find_matches` never silently fail on a type mismatch."""
    try:
        return int(record["issued"]["date-parts"][0][0])
    except (KeyError, IndexError, TypeError, ValueError):
        return None
