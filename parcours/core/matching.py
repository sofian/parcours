"""Shared fuzzy-string matching used by dedup rules (see SPECS.md,
"Category schemas (drafts)": the `fuzzy` matcher)."""

import difflib


def fuzzy_match(a: str, b: str, threshold: float = 0.8) -> bool:
    if not a or not b:
        return False
    ratio = difflib.SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()
    return ratio >= threshold
