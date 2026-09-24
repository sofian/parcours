"""CCV (Canadian Common CV) → parco category field mapping, per-record
dedup, and the plan/write orchestration for `parco import ccv` (see
SPECS.md, "Import" and "CCV export structure"). Core layer: no
prompting/printing — see `cli/main.py`'s `import_app` for that."""

from dataclasses import dataclass, field
from typing import Callable

from . import ccv_xml as x


@dataclass
class ImportContext:
    default_currency: str
    own_name: tuple[str, str]  # (last, first)


@dataclass
class MappedRow:
    category: str
    fields: dict[str, str]
    ccv_label: str
    flag: str | None = None


@dataclass
class FlaggedRecord:
    ccv_label: str
    reason: str


MAPPERS: dict[str, Callable] = {}


def _register(*labels: str):
    def decorator(fn):
        for label in labels:
            MAPPERS[label] = fn
        return fn
    return decorator


def map_record(record_el, label: str, lang: str, ctx: ImportContext):
    """Dispatches to the mapper registered for `label`. Callers (Task 8)
    handle an unregistered label as either a known sub-record (ignored)
    or a genuinely unmapped record (reported as skipped)."""
    mapper = MAPPERS[label]
    return mapper(record_el, lang, ctx)


_DEGREE_TYPE = {
    "Bachelor's": "bachelors",
    "Bachelor’s Honours": "bachelors-honours",
    "Bachelor's Honours": "bachelors-honours",
    "Master's Thesis": "masters",
    "Master’s Thesis": "masters",
    "Doctorate": "doctorate",
    "Post-doctorate": "postdoc",
}

_DEGREE_STATUS = {
    "Completed": "completed",
    "In Progress": "in-progress",
    "Withdrawn": "withdrawn",
    "All But Degree": "all-but-degree",
}

_RECOGNITION_TYPE = {
    "Citation": "citation",
    "Distinction": "distinction",
    "Prize / Award": "prize",
}

_POSITION_STATUS = {
    "Full-time": "full-time",
    "Part-time": "part-time",
}

_YES_NO = {"Yes": "true", "No": "false"}


def _normalize_apostrophe(text: str) -> str:
    return text.replace("’", "'")


@_register("Degrees")
def _map_education(record_el, lang, ctx) -> MappedRow:
    degree_type_raw = _normalize_apostrophe(x.field_lov(record_el, "Degree Type"))
    degree_status_raw = x.field_lov(record_el, "Degree Status")
    specialization_fr, specialization_en = x.field_bilingual(record_el, "Specialization", lang)
    degree_name_fr, degree_name_en = x.field_bilingual(record_el, "Degree Name", lang)

    supervisor_names = [
        x.field_text(sup, "Supervisor Name")
        for sup in x.sub_records(record_el, "Supervisors")
    ]
    advisor = "; ".join(name for name in supervisor_names if name)

    return MappedRow(
        category="education",
        ccv_label="Degrees",
        fields={
            "degree_type": _DEGREE_TYPE.get(degree_type_raw, ""),
            "degree_name_en": degree_name_en,
            "degree_name_fr": degree_name_fr,
            "specialization_en": specialization_en,
            "specialization_fr": specialization_fr,
            "organization": x.field_organization(record_el),
            "degree_status": _DEGREE_STATUS.get(degree_status_raw, ""),
            "start_date": x.field_yearmonth(record_el, "Degree Start Date"),
            "end_date": x.field_yearmonth(record_el, "Degree Received Date"),
            "thesis_title": x.field_text(record_el, "Thesis Title"),
            "advisor": advisor,
            "note_en": "",
            "note_fr": "",
        },
    )


@_register("Presentations")
def _map_presentation(record_el, lang, ctx) -> MappedRow:
    title_fr, title_en = x.field_single_language(record_el, "Presentation Title", lang)
    event_fr, event_en = x.field_single_language(record_el, "Conference / Event Name", lang)
    description_fr, description_en = x.field_bilingual(record_el, "Description / Contribution Value", lang)

    raw_co_presenters = x.field_text(record_el, "Co-Presenters")
    co_presenters = x.try_person_list(raw_co_presenters)
    flag = None
    if raw_co_presenters and co_presenters is None:
        flag = f"co_presenters could not be parsed as 'Last, First' from CCV's raw value: {raw_co_presenters!r}"

    return MappedRow(
        category="presentations",
        ccv_label="Presentations",
        fields={
            "title_en": title_en,
            "title_fr": title_fr,
            "event_en": event_en,
            "event_fr": event_fr,
            "location": "",
            "invited": _YES_NO.get(x.field_lov(record_el, "Invited?"), ""),
            "keynote": _YES_NO.get(x.field_lov(record_el, "Keynote?"), ""),
            "date": x.field_year(record_el, "Presentation Year"),
            "description_en": description_en,
            "description_fr": description_fr,
            "co_presenters": co_presenters or "",
            "url": x.field_text(record_el, "URL"),
        },
        flag=flag,
    )


@_register("Recognitions")
def _map_recognitions(record_el, lang, ctx) -> MappedRow:
    recognition_type_raw = x.field_lov(record_el, "Recognition Type")
    description_fr, description_en = x.field_bilingual(record_el, "Description", lang)

    return MappedRow(
        category="recognitions",
        ccv_label="Recognitions",
        fields={
            "recognition_type": _RECOGNITION_TYPE.get(recognition_type_raw, ""),
            "name": x.field_text(record_el, "Recognition Name"),
            "organization": x.field_organization(record_el),
            "role": "recipient",
            "date": x.field_yearmonth(record_el, "Effective Date"),
            "end_date": x.field_yearmonth(record_el, "End Date"),
            "amount": x.field_text(record_el, "Amount"),
            "currency": x.field_lov(record_el, "Currency"),
            "description_en": description_en,
            "description_fr": description_fr,
        },
    )


@_register("Course Development")
def _map_teaching(record_el, lang, ctx) -> MappedRow:
    title_fr, title_en = x.field_single_language(record_el, "Course Title", lang)

    return MappedRow(
        category="teaching",
        ccv_label="Course Development",
        fields={
            "course_label": "",
            "title_en": title_en,
            "title_fr": title_fr,
            "role": x.field_text(record_el, "Role"),
            "organization": x.field_organization(record_el),
            "department": x.field_text(record_el, "Department"),
            "date": x.field_yearmonth(record_el, "Date First Taught"),
        },
    )


@_register("Broadcast Interviews")
def _map_press_broadcast(record_el, lang, ctx) -> MappedRow:
    description_fr, description_en = x.field_bilingual(record_el, "Description / Contribution Value", lang)
    return MappedRow(
        category="press",
        ccv_label="Broadcast Interviews",
        fields={
            "citekey": "",
            "author": x.field_text(record_el, "Interviewer"),
            "outlet": x.field_text(record_el, "Network"),
            "program": x.field_text(record_el, "Program"),
            "date": x.field_date(record_el, "First Broadcast Date"),
            "description_en": description_en,
            "description_fr": description_fr,
            "url": x.field_text(record_el, "URL"),
        },
    )


@_register("Text Interviews")
def _map_press_text(record_el, lang, ctx) -> MappedRow:
    description_fr, description_en = x.field_bilingual(record_el, "Description / Contribution Value", lang)
    return MappedRow(
        category="press",
        ccv_label="Text Interviews",
        fields={
            "citekey": "",
            "author": x.field_text(record_el, "Interviewer"),
            "outlet": x.field_text(record_el, "Forum"),
            "program": "",
            "date": x.field_date(record_el, "Publication Date"),
            "description_en": description_en,
            "description_fr": description_fr,
            "url": x.field_text(record_el, "URL"),
        },
    )


@_register("Academic Work Experience")
def _map_positions_academic(record_el, lang, ctx) -> MappedRow:
    title_fr, title_en = x.field_single_language(record_el, "Position Title", lang)
    return MappedRow(
        category="positions",
        ccv_label="Academic Work Experience",
        fields={
            "type": "academic",
            "title_en": title_en,
            "title_fr": title_fr,
            "organization": x.field_organization(record_el),
            "faculty": x.field_text(record_el, "Faculty / School / Campus"),
            "department": x.field_text(record_el, "Department"),
            "position_status": _POSITION_STATUS.get(x.field_lov(record_el, "Position Status"), ""),
            "start_date": x.field_yearmonth(record_el, "Start Date"),
            "end_date": x.field_yearmonth(record_el, "End Date"),
        },
    )


@_register("Non-academic Work Experience")
def _map_positions_non_academic(record_el, lang, ctx) -> MappedRow:
    title_fr, title_en = x.field_single_language(record_el, "Position Title", lang)
    return MappedRow(
        category="positions",
        ccv_label="Non-academic Work Experience",
        fields={
            "type": "non-academic",
            "title_en": title_en,
            "title_fr": title_fr,
            "organization": x.field_organization(record_el),
            "faculty": "",
            "department": x.field_text(record_el, "Unit / Division"),
            "position_status": "",
            "start_date": x.field_yearmonth(record_el, "Start Date"),
            "end_date": x.field_yearmonth(record_el, "End Date"),
        },
    )


@_register("Affiliations")
def _map_positions_affiliation(record_el, lang, ctx) -> MappedRow:
    title_fr, title_en = x.field_bilingual(record_el, "Position Title", lang)
    return MappedRow(
        category="positions",
        ccv_label="Affiliations",
        fields={
            "type": "affiliation",
            "title_en": title_en,
            "title_fr": title_fr,
            "organization": x.field_organization(record_el),
            "faculty": "",
            "department": x.field_text(record_el, "Department"),
            "position_status": "",
            "start_date": x.field_yearmonth(record_el, "Start Date"),
            "end_date": x.field_yearmonth(record_el, "End Date"),
        },
    )
