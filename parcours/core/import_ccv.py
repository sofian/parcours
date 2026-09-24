"""CCV (Canadian Common CV) → parco category field mapping, per-record
dedup, and the plan/write orchestration for `parco import ccv` (see
SPECS.md, "Import" and "CCV export structure"). Core layer: no
prompting/printing — see `cli/main.py`'s `import_app` for that."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import ccv_xml as x
from .data import load_category_rows
from .entries import generate_id, write_all_rows
from .handlers import load_handler
from .handlers.base import HandlerContext
from .identity import load_identity
from .repo import load_repo_config
from .schema import load_all_schemas


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


SUB_RECORD_LABELS = frozenset({
    "Supervisors", "Funding Sources", "Other Investigators",
    "Areas of Research", "Research Disciplines", "Fields of Application",
    "Disciplines Trained In", "Research Specialization Keywords",
    "Student Country of Citizenship", "Project Funding Sources",
})


@dataclass
class ImportReport:
    to_write: list[MappedRow] = field(default_factory=list)
    flagged: list[FlaggedRecord] = field(default_factory=list)
    notes: list[FlaggedRecord] = field(default_factory=list)
    skipped_labels: dict[str, int] = field(default_factory=dict)
    dedup_matches: dict[int, list] = field(default_factory=dict)


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

_SUPERVISION_ROLE = {
    "Principal Supervisor": "principal-supervisor",
    "Co-Supervisor": "co-supervisor",
}

_OUTREACH_ACTIVITY_TYPE = {
    "Business Innovation": "business-innovation",
    "Community Engagement": "community-engagement",
    "Consulting for Industry": "industry-consulting",
    "Involvement in/Creation of Start-up": "startup-involvement",
    "Technology, Product, Process, Service Improvement/Development": "technology-improvement",
}

_OUTREACH_STAKEHOLDER = {
    "General Public": "general-public",
    "Industrial Association/Producer Group": "industry-association",
    "Industry/Business-Medium (100 to 500 employees)": "industry-business",
    "Private Not-for-Profit Organization": "private-nonprofit",
    "Utility": "utility",
}


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


@_register("Graduate Examination Activities")
def _map_service_graduate_examination(record_el, lang, ctx) -> MappedRow:
    return MappedRow(
        category="service",
        ccv_label="Graduate Examination Activities",
        fields={
            "type": "graduate-examination",
            "role": x.field_lov(record_el, "Graduate Examination Activity Role"),
            "organization": x.field_organization(record_el),
            "start_date": x.field_yearmonth(record_el, "Start Date"),
            "end_date": x.field_yearmonth(record_el, "End Date"),
            "detail": x.field_text(record_el, "Student Name"),
        },
    )


@_register("Research Funding Application Assessment Activities")
def _map_service_funding_review(record_el, lang, ctx) -> MappedRow:
    return MappedRow(
        category="service",
        ccv_label="Research Funding Application Assessment Activities",
        fields={
            "type": "funding-review",
            "role": x.field_lov(record_el, "Funding Reviewer Role"),
            "organization": x.field_organization(record_el),
            "start_date": x.field_yearmonth(record_el, "Start Date"),
            "end_date": x.field_yearmonth(record_el, "End Date"),
            "detail": x.field_text(record_el, "Committee Name"),
        },
    )


@_register("Community and Volunteer Activities")
def _map_service_volunteer(record_el, lang, ctx) -> MappedRow:
    description_fr, description_en = x.field_bilingual(record_el, "Activity Description", lang)
    detail = description_en or description_fr
    return MappedRow(
        category="service",
        ccv_label="Community and Volunteer Activities",
        fields={
            "type": "volunteer",
            "role": x.field_text(record_el, "Role"),
            "organization": x.field_organization(record_el),
            "start_date": x.field_yearmonth(record_el, "Start Date"),
            "end_date": x.field_yearmonth(record_el, "End Date"),
            "detail": detail,
        },
    )


@_register("Committee Memberships")
def _map_service_committee(record_el, lang, ctx) -> MappedRow:
    return MappedRow(
        category="service",
        ccv_label="Committee Memberships",
        fields={
            "type": "committee",
            "role": x.field_lov(record_el, "Role"),
            "organization": x.field_organization(record_el),
            "start_date": x.field_yearmonth(record_el, "Membership Start Date"),
            "end_date": x.field_yearmonth(record_el, "Membership End Date"),
            "detail": x.field_text(record_el, "Committee Name"),
        },
    )


@_register("Program Development")
def _map_service_program_development(record_el, lang, ctx) -> MappedRow:
    description_fr, description_en = x.field_bilingual(record_el, "Program Description", lang)
    program_title = x.field_text(record_el, "Program Title")
    description = description_en or description_fr
    detail = f"{program_title}: {description}" if description else program_title
    return MappedRow(
        category="service",
        ccv_label="Program Development",
        fields={
            "type": "program-development",
            "role": x.field_text(record_el, "Role"),
            "organization": x.field_organization(record_el),
            "start_date": x.field_yearmonth(record_el, "Date First Taught"),
            "end_date": "",
            "detail": detail,
        },
    )


@_register("Knowledge and Technology Translation")
def _map_outreach(record_el, lang, ctx) -> MappedRow:
    description_fr, description_en = x.field_bilingual(record_el, "Activity Description", lang)
    return MappedRow(
        category="outreach",
        ccv_label="Knowledge and Technology Translation",
        fields={
            "activity_type": _OUTREACH_ACTIVITY_TYPE.get(
                x.field_lov(record_el, "Knowledge and Technology Translation Activity Type"), ""
            ),
            "target_stakeholder": _OUTREACH_STAKEHOLDER.get(x.field_lov(record_el, "Target Stakeholder"), ""),
            "organization": x.field_text(record_el, "Group/Organization/Business Serviced"),
            "role": x.field_text(record_el, "Role"),
            "start_date": x.field_yearmonth(record_el, "Start Date"),
            "end_date": x.field_yearmonth(record_el, "End Date"),
            "description_en": description_en,
            "description_fr": description_fr,
            "url": x.field_text(record_el, "References / Citations / Web Sites"),
        },
    )


@_register("Student/Postdoctoral Supervision")
def _map_students(record_el, lang, ctx) -> MappedRow:
    degree_type_raw = _normalize_apostrophe(x.field_lov(record_el, "Degree Type or Postdoctoral Status"))
    degree_status_raw = x.field_lov(record_el, "Student Degree Status")
    return MappedRow(
        category="students",
        ccv_label="Student/Postdoctoral Supervision",
        fields={
            "student_name": x.field_text(record_el, "Student Name"),
            "role": _SUPERVISION_ROLE.get(x.field_lov(record_el, "Supervision Role"), ""),
            "institution": x.field_text(record_el, "Student Institution"),
            "degree_type": _DEGREE_TYPE.get(degree_type_raw, ""),
            "degree_status": _DEGREE_STATUS.get(degree_status_raw, ""),
            "supervision_start_date": x.field_yearmonth(record_el, "Supervision Start Date"),
            "supervision_end_date": x.field_yearmonth(record_el, "Supervision End Date"),
            "degree_start_date": x.field_yearmonth(record_el, "Student Degree Start Date"),
            "degree_end_date": x.field_yearmonth(record_el, "Student Degree Received Date"),
            "thesis_title": x.field_text(record_el, "Thesis/Project Title"),
            "present_position": x.field_text(record_el, "Present Position"),
            "present_organization": x.field_text(record_el, "Present Organization"),
        },
    )


_ARTWORK_ROLE = {
    "Author": "author",
    "Auteur": "author",
    "Artist": "author",
    "Principal investigator": "author",
    "Collaborator": "collaborator",
    "Artist collaborator": "collaborator",
}


def _remove_self_from_contributors(raw: str, own_name: tuple[str, str]) -> str:
    """`own_name` is (last, first). Removes an exact 'Last, First' match
    (whitespace-normalized) before the parse-as-validation-gate runs —
    `co_authors` never includes you (see SPECS.md, `artworks` notes)."""
    if not raw:
        return raw
    own_last, own_first = own_name
    own_formatted = f"{own_last}, {own_first}".strip().lower()
    remaining = [
        chunk for chunk in (part.strip() for part in raw.split(";"))
        if chunk and chunk.lower() != own_formatted
    ]
    return "; ".join(remaining)


def _map_artwork_common(record_el, lang, ctx, title_label: str, date_field, date_label: str, ccv_label: str) -> MappedRow:
    title_fr, title_en = x.field_single_language(record_el, title_label, lang)
    description_fr, description_en = x.field_bilingual(record_el, "Description / Contribution Value", lang)
    role_raw = x.field_text(record_el, "Contribution Role")

    raw_contributors = x.field_text(record_el, "Contributors")
    filtered_contributors = _remove_self_from_contributors(raw_contributors, ctx.own_name)
    co_authors = x.try_person_list(filtered_contributors)
    flag = None
    if filtered_contributors and co_authors is None:
        flag = f"co_authors could not be parsed as 'Last, First' from CCV's raw Contributors value: {raw_contributors!r}"

    return MappedRow(
        category="artworks",
        ccv_label=ccv_label,
        fields={
            "title_en": title_en,
            "title_fr": title_fr,
            "role": _ARTWORK_ROLE.get(role_raw, "author"),
            "date": date_field(record_el, date_label)[:4],
            "description_en": description_en,
            "description_fr": description_fr,
            "co_authors": co_authors or "",
            "collaborators": "",
            "url": x.field_text(record_el, "URL"),
        },
        flag=flag,
    )


@_register("Visual Artworks")
def _map_visual_artwork(record_el, lang, ctx) -> MappedRow:
    return _map_artwork_common(record_el, lang, ctx, "Artwork Title", x.field_yearmonth, "Publication Date", "Visual Artworks")


@_register("Audio Recordings")
def _map_audio_recording(record_el, lang, ctx) -> MappedRow:
    return _map_artwork_common(record_el, lang, ctx, "Piece Title", x.field_date, "Release Date", "Audio Recordings")


@_register("Artistic Exhibitions")
def _map_exhibition(record_el, lang, ctx) -> MappedRow:
    title_fr, title_en = x.field_single_language(record_el, "Title of Work", lang)
    return MappedRow(
        category="exhibitions",
        ccv_label="Artistic Exhibitions",
        fields={
            "title_en": title_en,
            "title_fr": title_fr,
            "event": "",
            "venue": x.field_text(record_el, "Venue"),
            "location": "",
            "curator": "",
            "start_date": x.field_date(record_el, "Date of First Performance"),
            "end_date": "",
        },
    )


_GRANT_ROLE = {
    "Principal Applicant": "pi",
    "Principal Investigator": "pi",
    "Co-applicant": "co-pi",
    "Co-investigator": "co-pi",
    "Collaborator": "collaborator",
}

_GRANT_STATUS = {
    "Awarded": "awarded",
    "Completed": "awarded",
    "Declined": "declined",
}


@_register("Research Funding History")
def _map_grant(record_el, lang, ctx) -> MappedRow:
    title_fr, title_en = x.field_single_language(record_el, "Funding Title", lang)
    project_description_fr, project_description_en = x.field_bilingual(record_el, "Project Description", lang)
    research_uptake_fr, research_uptake_en = x.field_bilingual(record_el, "Research Uptake", lang)
    note_en = "\n\n".join(part for part in (project_description_en, research_uptake_en) if part)
    note_fr = "\n\n".join(part for part in (project_description_fr, research_uptake_fr) if part)

    funding_sources = x.sub_records(record_el, "Funding Sources")
    flags = []
    funder = program = amount = currency = ""
    if funding_sources:
        first_source = funding_sources[0]
        funder = x.field_lov(first_source, "Funding Organization") or x.field_text(first_source, "Other Funding Organization")
        program = x.field_text(first_source, "Program Name")
        amount = x.field_text(first_source, "Total Funding")
        currency = x.field_lov(first_source, "Currency of Total Funding")
        if len(funding_sources) > 1:
            extra_funders = [
                (x.field_lov(src, "Funding Organization") or x.field_text(src, "Other Funding Organization"))
                for src in funding_sources[1:]
            ]
            flags.append(
                f"{len(funding_sources)} Funding Sources found for this grant — "
                f"using the first ({funder!r}); the rest need manual review: {', '.join(extra_funders)}"
            )

    other_investigators = x.sub_records(record_el, "Other Investigators")
    co_investigators = ""
    if other_investigators:
        names = [x.field_text(inv, "Investigator Name") for inv in other_investigators]
        names = [n for n in names if n]
        joined = "; ".join(names)
        parsed = x.try_person_list(joined)
        if parsed:
            co_investigators = parsed
        else:
            flags.append(
                f"co_investigators needs manual entry — CCV gives unsplit investigator name(s): {', '.join(names)}"
            )

    return MappedRow(
        category="grants",
        ccv_label="Research Funding History",
        fields={
            "title_en": title_en,
            "title_fr": title_fr,
            "funder": funder,
            "program": program,
            "role": _GRANT_ROLE.get(x.field_lov(record_el, "Funding Role"), ""),
            "status": _GRANT_STATUS.get(x.field_lov(record_el, "Funding Status"), ""),
            "start_date": x.field_yearmonth(record_el, "Funding Start Date"),
            "end_date": x.field_yearmonth(record_el, "Funding End Date"),
            "amount": amount,
            "currency": currency or ctx.default_currency,
            "co_investigators": co_investigators,
            "note_en": note_en,
            "note_fr": note_fr,
        },
        flag="; ".join(flags) or None,
    )


@dataclass
class ZoteroCandidate:
    title: str
    year: int | None
    ccv_label: str


_ZOTERO_CANDIDATE_FIELDS = {
    "Journal Articles": ("Article Title", x.field_year, "Year"),
    "Books": ("Book Title", x.field_year, "Year"),
    "Book Chapters": ("Chapter Title", x.field_year, "Year"),
    "Thesis/Dissertation": ("Dissertation Title", x.field_year, "Completion Year"),
    "Magazine Entries": ("Article Title", x.field_year, "Year"),
    "Reports": ("Report Title", x.field_year, "Year Submitted"),
    "Online Resources": ("Title", x.field_year, "Year posted online"),
    "Conference Publications": ("Publication Title", x.field_year, "Year"),
    "Exhibition Catalogues": ("Catalogue Title", x.field_yearmonth, "Publication Date"),
}

ZOTERO_MATCHED_LABELS = frozenset(_ZOTERO_CANDIDATE_FIELDS)


def extract_zotero_candidate(record_el, label: str, lang: str) -> ZoteroCandidate:
    title_field, year_fn, year_label = _ZOTERO_CANDIDATE_FIELDS[label]
    title_fr, title_en = x.field_single_language(record_el, title_field, lang)
    title = title_en or title_fr
    raw_year = year_fn(record_el, year_label)
    try:
        year = int(raw_year[:4]) if raw_year else None
    except ValueError:
        year = None
    return ZoteroCandidate(title=title, year=year, ccv_label=label)


def plan_import(data_dir: Path, xml_path: Path) -> ImportReport:
    root, lang = x.parse_ccv_export(xml_path)
    records = x.find_records(root)

    identity = load_identity(data_dir / "identity.yaml")
    own_name = (identity["name"]["last"], identity["name"]["first"])
    repo_config = load_repo_config(data_dir)
    default_currency = repo_config.get("currency", {}).get("default", "")
    ctx = ImportContext(default_currency=default_currency, own_name=own_name)

    schemas = load_all_schemas(data_dir / "categories")
    handlers = {
        name: load_handler(schema, HandlerContext(data_dir=data_dir))
        for name, schema in schemas.items()
    }
    existing_rows_by_category = {
        name: load_category_rows(data_dir, name) for name in schemas
    }

    report = ImportReport()

    for record in records:
        label = record.label
        if label in SUB_RECORD_LABELS:
            continue

        if label in ZOTERO_MATCHED_LABELS:
            candidate = extract_zotero_candidate(record.element, label, lang)
            category = "catalog" if label == "Exhibition Catalogues" else "publications"
            handler = handlers.get(category)
            citekey = handler.match_citekey_by_title(candidate.title, candidate.year) if handler else None
            if citekey is None:
                report.flagged.append(FlaggedRecord(
                    ccv_label=label,
                    reason=f"No confident Zotero match for {candidate.title!r} ({candidate.year}) — needs a citekey",
                ))
                continue
            schema = schemas[category]
            mapped = MappedRow(
                category=category,
                ccv_label=label,
                fields={name: "" for name in schema.field_names() if name != "id"} | {"citekey": citekey},
            )
        elif label in MAPPERS:
            mapped = map_record(record.element, label, lang, ctx)
        else:
            report.skipped_labels[label] = report.skipped_labels.get(label, 0) + 1
            continue

        if mapped.flag:
            report.notes.append(FlaggedRecord(ccv_label=mapped.ccv_label, reason=mapped.flag))

        row_index = len(report.to_write)
        report.to_write.append(mapped)

        handler = handlers.get(mapped.category)
        if handler is not None:
            candidate_row = {"id": "", **mapped.fields}
            matches = handler.find_matches(candidate_row, existing_rows_by_category[mapped.category])
            if matches:
                report.dedup_matches[row_index] = matches

    return report


def write_import(data_dir: Path, report: ImportReport) -> list[str]:
    schemas = load_all_schemas(data_dir / "categories")
    touched: set[str] = set()

    for mapped in report.to_write:
        schema = schemas[mapped.category]
        rows = load_category_rows(data_dir, mapped.category)
        row_id = generate_id(data_dir, mapped.category)
        rows.append({"id": row_id, **mapped.fields})
        write_all_rows(data_dir / f"{mapped.category}.csv", schema.field_names(), rows)
        touched.add(f"{mapped.category}.csv")

    return sorted(touched)
