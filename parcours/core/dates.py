"""ISO partial date parsing and comparison. `date` fields always hold
`2024`, `2024-09`, or `2024-09-30`; `precision` on a schema field is a
*minimum*, never a ceiling (see SPECS.md, "Category schemas (drafts)")."""

import calendar
import re
from dataclasses import dataclass
from datetime import date

_PATTERNS = [
    (re.compile(r"^\d{4}-\d{2}-\d{2}$"), "day"),
    (re.compile(r"^\d{4}-\d{2}$"), "month"),
    (re.compile(r"^\d{4}$"), "year"),
]

_PRECISION_RANK = {"year": 0, "month": 1, "day": 2}


class InvalidDateError(Exception):
    """Raised when a value isn't a valid ISO partial date."""


@dataclass
class PartialDate:
    year: int
    month: int | None
    day: int | None
    precision: str

    def start_bound(self) -> tuple[int, int, int]:
        return (self.year, self.month or 1, self.day or 1)

    def end_bound(self) -> tuple[int, int, int]:
        month = self.month or 12
        day = self.day or calendar.monthrange(self.year, month)[1]
        return (self.year, month, day)


def parse_partial_date(value: str) -> PartialDate:
    for pattern, precision in _PATTERNS:
        if pattern.match(value):
            parts = value.split("-")
            year = int(parts[0])
            month = int(parts[1]) if len(parts) > 1 else None
            day = int(parts[2]) if len(parts) > 2 else None
            try:
                # The regex above only checks digit *shape* (e.g. "13" passes
                # as a month); constructing a real date catches an
                # out-of-range month/day like "2024-13" or "2024-02-30".
                date(year, month or 1, day or 1)
            except ValueError as exc:
                raise InvalidDateError(f"Not a valid date: {value!r} ({exc})") from exc
            return PartialDate(year=year, month=month, day=day, precision=precision)
    raise InvalidDateError(f"Not a valid ISO partial date: {value!r}")


def meets_precision_floor(value: str, minimum: str) -> bool:
    """True if `value` is at least as precise as `minimum` (year < month < day)."""
    parsed = parse_partial_date(value)
    return _PRECISION_RANK[parsed.precision] >= _PRECISION_RANK[minimum]


def same_year(a: str, b: str) -> bool:
    return parse_partial_date(a).year == parse_partial_date(b).year


_OPEN_ENDED = (9999, 12, 31)


def ranges_overlap(
    start_a: str, end_a: str | None, start_b: str, end_b: str | None
) -> bool:
    """True if [start_a, end_a] and [start_b, end_b] intersect. A blank
    or `"present"` end means ongoing (open-ended)."""
    a_start = parse_partial_date(start_a).start_bound()
    b_start = parse_partial_date(start_b).start_bound()
    a_end = parse_partial_date(end_a).end_bound() if end_a and end_a != "present" else _OPEN_ENDED
    b_end = parse_partial_date(end_b).end_bound() if end_b and end_b != "present" else _OPEN_ENDED
    return a_start <= b_end and b_start <= a_end
