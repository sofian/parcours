"""Count-only aggregation for `parco stats` (see SPECS.md, "CLI" ->
"Stats"). Takes rows already fetched and filtered (via
`query_category_rows` and, for free-text search, `cli/wizard.py`'s
`search_rows`) and aggregates them in Python — one consistent
fetch-then-filter-then-aggregate pipeline rather than mixing SQL-side
and Python-side stages, since `--search` is already Python-side.
Core layer: no printing, no prompting."""

from collections import Counter

from .dates import InvalidDateError, parse_partial_date
from .schema import CategorySchema


class UnknownStatsField(Exception):
    """Raised when `--by` names a field that isn't in the category's
    schema, or is the literal "year" for a category with no
    `default_date_field()`."""


def aggregate_counts(schema: CategorySchema, rows: list[dict], by: str) -> list[tuple[str, int]]:
    if by == "year":
        date_field = schema.default_date_field()
        if date_field is None:
            raise UnknownStatsField(f"'{schema.name}' has no date field to group by year")
        counter: Counter = Counter()
        for row in rows:
            value = row.get(date_field)
            if not value:
                continue
            try:
                counter[str(parse_partial_date(value).year)] += 1
            except InvalidDateError:
                continue
        return sorted(counter.items(), key=lambda pair: pair[0])

    if schema.get_field(by) is None:
        raise UnknownStatsField(f"Unknown field '{by}' for category '{schema.name}'")

    counter = Counter(row.get(by) or "(blank)" for row in rows)
    return sorted(counter.items(), key=lambda pair: pair[0])
