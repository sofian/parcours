"""`person_list` field parsing. A `person_list` field always holds
`"Last, First; Last, First"` — semicolon-separated people, each
`Last, First` — so a citation-formatting step can sort by last name
instead of just displaying the string as typed (see SPECS.md,
"Category schemas (drafts)")."""

import re
from dataclasses import dataclass

_PERSON_PATTERN = re.compile(r"^(?P<last>[^,]+),\s*(?P<first>[^,]+)$")


class InvalidPersonListError(Exception):
    """Raised when a value isn't a valid `"Last, First; Last, First"`
    person list."""


@dataclass
class PersonName:
    last: str
    first: str


def parse_person_list(value: str) -> list[PersonName]:
    people = []
    for chunk in value.split(";"):
        chunk = chunk.strip()
        if not chunk:
            raise InvalidPersonListError(
                f"Empty entry in person list: {value!r}"
            )
        match = _PERSON_PATTERN.match(chunk)
        if not match:
            raise InvalidPersonListError(
                f"Not a valid 'Last, First' entry: {chunk!r} (in {value!r})"
            )
        last = match.group("last").strip()
        first = match.group("first").strip()
        if not last or not first:
            raise InvalidPersonListError(
                f"Not a valid 'Last, First' entry: {chunk!r} (in {value!r})"
            )
        people.append(PersonName(last=last, first=first))
    return people
