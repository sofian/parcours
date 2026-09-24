"""Generic CCV (Canadian Common CV) XML tree-walking primitives — no
category knowledge here, just the wire format (see SPECS.md, "CCV
export structure"). Category field mapping lives in `import_ccv.py`."""

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

from .names import InvalidPersonListError, parse_person_list


@dataclass
class CcvRecord:
    element: ET.Element
    label: str
    path: tuple[str, ...]


def parse_ccv_export(xml_path: Path) -> tuple[ET.Element, str]:
    tree = ET.parse(xml_path)
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
                label=element.get("label"),
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
    return f"{year}-{int(month):02d}"


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
