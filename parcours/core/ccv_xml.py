"""Generic CCV (Canadian Common CV) XML tree-walking primitives — no
category knowledge here, just the wire format (see SPECS.md, "CCV
export structure"). Category field mapping lives in `import_ccv.py`."""

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

from .names import InvalidPersonListError, parse_person_list


@dataclass
class CcvRecord:
    element: ET.Element
    label: str
    path: tuple[str, ...]


class CcvParseError(Exception):
    """Raised when the given file isn't parseable as XML."""


def parse_ccv_export(xml_path: Path) -> tuple[ET.Element, str]:
    try:
        tree = ET.parse(xml_path)
    except ET.ParseError as exc:
        raise CcvParseError(f"{xml_path} is not valid XML: {exc}") from exc
    root = tree.getroot()
    lang = root.get("lang") or "en"
    return root, lang


def find_records(root: ET.Element) -> list[CcvRecord]:
    parent_map = {child: parent for parent in root.iter() for child in parent}
    records = []
    for element in root.iter():
        if element.get("recordId") is not None:
            records.append(CcvRecord(
                element=element,
                label=element.get("label") or "",
                path=tuple(_ancestor_labels(element, parent_map)),
            ))
    return records


def _ancestor_labels(element: ET.Element, parent_map: dict) -> list[str]:
    labels = []
    current = element
    while current is not None:
        label = current.get("label")
        if label:
            labels.append(label)
        current = parent_map.get(current)
    return list(reversed(labels))


def _field_element(record_el: ET.Element, label: str) -> ET.Element | None:
    return record_el.find(f"field[@label='{label}']")


def field_text(record_el: ET.Element, label: str) -> str:
    field = _field_element(record_el, label)
    if field is None:
        return ""
    value = field.find("value")
    if value is None:
        return ""
    return (value.text or "").strip()


def field_year(record_el: ET.Element, label: str) -> str:
    return field_text(record_el, label)


def field_yearmonth(record_el: ET.Element, label: str) -> str:
    raw = field_text(record_el, label)
    if not raw or "/" not in raw:
        return ""
    year, month = raw.split("/", 1)
    try:
        return f"{year}-{int(month):02d}"
    except ValueError:
        return ""


def field_date(record_el: ET.Element, label: str) -> str:
    return field_text(record_el, label)


def field_lov(record_el: ET.Element, label: str) -> str:
    field = _field_element(record_el, label)
    if field is None:
        return ""
    lov = field.find("lov")
    if lov is None:
        return ""
    return (lov.text or "").strip()


def field_bilingual(record_el: ET.Element, label: str, default_lang: str) -> tuple[str, str]:
    field = _field_element(record_el, label)
    if field is None:
        return "", ""

    bilingual = field.find("bilingual")
    if bilingual is not None:
        french_el = bilingual.find("french")
        english_el = bilingual.find("english")
        french = (french_el.text or "").strip() if french_el is not None else ""
        english = (english_el.text or "").strip() if english_el is not None else ""
        if french or english:
            return french, english

    value = field.find("value")
    blob = (value.text or "").strip() if value is not None else ""
    if not blob:
        return "", ""
    return (blob, "") if default_lang == "fr" else ("", blob)


def field_single_language(record_el: ET.Element, label: str, default_lang: str) -> tuple[str, str]:
    """A `String`-typed field with no per-field language marker (e.g. a
    CCV title field) — routed to (french, english) by the export's own
    default language, exactly one side non-blank."""
    text = field_text(record_el, label)
    if not text:
        return "", ""
    return (text, "") if default_lang == "fr" else ("", text)


def field_organization(record_el: ET.Element, label: str = "Organization") -> str:
    field = _field_element(record_el, label)
    if field is not None:
        ref_table = field.find("refTable")
        if ref_table is not None:
            linked = ref_table.find("linkedWith[@label='Organization']")
            if linked is not None and linked.get("value"):
                return linked.get("value")
    return field_text(record_el, "Other Organization")


def sub_records(record_el: ET.Element, label: str) -> list[ET.Element]:
    return record_el.findall(f"section[@label='{label}']")


def try_person_list(raw: str) -> str | None:
    if not raw or not raw.strip():
        return None
    try:
        parse_person_list(raw)
    except InvalidPersonListError:
        return None
    return raw


_LIST_CONJUNCTION = re.compile(r"\s+(?:et|and)\s+", re.IGNORECASE)
_TRAILING_PERIOD = re.compile(r"\.\s*$")


def _invert_natural_order_name(name: str) -> str | None:
    """"First [Middle] Last" -> "Last, First [Middle]", treating the last
    whitespace-separated token as the surname — the same convention
    BibTeX/citeproc tools use. Returns None (never guesses further) for
    a single-token name with no given name to separate out."""
    tokens = name.split()
    if len(tokens) < 2:
        return None
    return f"{tokens[-1]}, {' '.join(tokens[:-1])}"


def try_person_list_lenient(raw: str) -> str | None:
    """A more forgiving fallback for CCV free-text name lists, tried only
    after `try_person_list` already failed. CCV consistently gives names
    in natural "First Last" order rather than parcours' canonical
    "Last, First" — verified against a real export's Co-Presenters,
    Other Investigators, and Contributors values, where this is the
    dominant failure mode, not an edge case. This coerces three real
    patterns into the canonical form: a trailing "." (a free-text
    full stop, not part of a name); a natural-language final
    conjunction ("A, B and C" / "A, B et C"); and each individual name
    being in natural order with no comma at all. Returns None — falling
    through to the existing manual-review flag, never a guess presented
    as fact — if any single name can't be confidently inverted (e.g. a
    lone single-token name)."""
    if not raw or not raw.strip():
        return None

    text = _TRAILING_PERIOD.sub("", raw.strip())
    text = _LIST_CONJUNCTION.sub(";", text)

    # By this point `try_person_list` has already rejected the raw value
    # as a whole, so it isn't a clean "Last, First; Last, First" list —
    # comma and semicolon are then used interchangeably as the
    # person-separator across real CCV exports (e.g. one list ending in
    # "... et X" normalizes its last separator to ";" above while the
    # earlier names are still comma-separated), so both are split on
    # here without trying to also treat a comma as a Last/First inverter.
    chunks = re.split(r"[;,]", text)

    people = []
    for chunk in chunks:
        chunk = chunk.strip()
        if not chunk:
            continue
        inverted = _invert_natural_order_name(chunk)
        if inverted is None:
            return None
        people.append(inverted)

    if not people:
        return None

    return try_person_list("; ".join(people))


def try_person_list_any(raw: str) -> str | None:
    """The strict format first (already-clean "Last, First; Last, First"
    data should never go through the lenient coercion's extra work), then
    the lenient fallback. Used everywhere a CCV person-list field is
    read, instead of each call site trying both itself."""
    return try_person_list(raw) or try_person_list_lenient(raw)
