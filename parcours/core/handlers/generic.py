"""The default handler: reads a category's declarative `dedup:` rules
from its schema rather than implementing anything category-specific
(see SPECS.md, "Category handlers")."""

from ..dates import ranges_overlap, same_year
from ..matching import fuzzy_match
from .base import CategoryHandler, Match


class GenericHandler(CategoryHandler):
    def find_matches(self, entry: dict, existing: list[dict]) -> list[Match]:
        matches = []
        for rule in self.schema.dedup:
            for existing_row in existing:
                if existing_row.get("id") == entry.get("id"):
                    continue
                if self._rule_matches(rule, entry, existing_row):
                    matches.append(Match(
                        existing_row_id=existing_row["id"],
                        kind=rule.outcome,
                        reason=f"Matched dedup rule {rule.conditions}",
                    ))
        return matches

    def _rule_matches(self, rule, entry: dict, existing_row: dict) -> bool:
        return all(self._condition_matches(cond, entry, existing_row) for cond in rule.conditions)

    def _condition_matches(self, cond: dict, entry: dict, existing_row: dict) -> bool:
        if "exact" in cond:
            names = cond["exact"] if isinstance(cond["exact"], list) else [cond["exact"]]
            return any(entry.get(n) == existing_row.get(n) for n in names if entry.get(n))
        if "fuzzy" in cond:
            names = cond["fuzzy"] if isinstance(cond["fuzzy"], list) else [cond["fuzzy"]]
            return any(fuzzy_match(entry.get(n, ""), existing_row.get(n, "")) for n in names)
        if "overlap" in cond:
            start_field, end_field = cond["overlap"]
            return ranges_overlap(
                entry.get(start_field), entry.get(end_field),
                existing_row.get(start_field), existing_row.get(end_field),
            )
        if "same_year" in cond:
            field_name = cond["same_year"]
            a, b = entry.get(field_name), existing_row.get(field_name)
            return bool(a and b and same_year(a, b))
        raise ValueError(f"Unknown dedup matcher: {cond}")
