"""The `{field}` template mini-language used by `views.yaml`'s field
mappings, `profiles/*.yaml`'s `meta.output`, and identity variant
resolution (see SPECS.md, "views.yaml (draft)"). Pure functions over
plain dicts — no file I/O, no category/schema knowledge."""

import re

_PLACEHOLDER = re.compile(r"\{(\w+(?:\|\w+)*)\}")
_OPTIONAL = re.compile(r"\[\[(.*?)\]\]")


def resolve_field(row: dict, field_name: str, language: str):
    """Returns the raw resolved value (any type) for one field name,
    auto-resolving a bilingual pair (`<field>_en`/`<field>_fr`) by
    language — falling back to the other language if the profile's own
    is blank or entirely absent, so a value is never dropped just from
    a language mismatch — or to a plain (non-suffixed) field if no
    bilingual pair exists."""
    primary_key = f"{field_name}_{language}"
    other_language = "fr" if language == "en" else "en"
    other_key = f"{field_name}_{other_language}"

    if primary_key in row or other_key in row:
        value = row.get(primary_key)
        if value:
            return value
        other_value = row.get(other_key)
        if other_value:
            return other_value
        return value
    return row.get(field_name)


def _resolve_alternatives(row: dict, spec: str, language: str):
    """`{a|b|c}`: the first of the listed fields with a non-blank value
    (each resolved bilingually), e.g. an untitled festival entry falling
    back to its event name."""
    value = None
    for field_name in spec.split("|"):
        value = resolve_field(row, field_name, language)
        if value:
            return value
    return value


def resolve_template(template, row: dict, language: str):
    """`template` is a plain field name with no braces at all (direct
    copy, any type), a bare `"{field}"` (bilingual-resolved via
    `resolve_field`; passed through unchanged if the resolved value is
    already a list — needed for `PublicationEntry.authors`), a compound
    string mixing `{field}`s and literal text (always stringified), or a
    list of any of the above (each resolved independently, blank/falsy
    results dropped — used for `highlights`). A placeholder may list
    fallbacks, `{title|event}`, taking the first non-blank one. A
    `[[...]]` segment, literal text included, is dropped when every field
    inside it is blank, e.g. `{title}[[. Curator: {curator}]].` A `label_*`
    field is translated text and never counts as content there."""
    if isinstance(template, list):
        resolved = [resolve_template(item, row, language) for item in template]
        return [value for value in resolved if value]

    if not isinstance(template, str):
        return template

    if "{" not in template:
        return row.get(template)

    bare_match = _PLACEHOLDER.fullmatch(template)
    if bare_match:
        return _resolve_alternatives(row, bare_match.group(1), language)

    def _substitute(match):
        value = _resolve_alternatives(row, match.group(1), language)
        return str(value) if value else ""

    def _keep_if_filled(match):
        segment = match.group(1)
        filled = any(
            _resolve_alternatives(row, spec, language)
            for spec in _PLACEHOLDER.findall(segment)
            if not spec.startswith("label_")
        )
        return segment if filled else ""

    template = _OPTIONAL.sub(_keep_if_filled, template)

    # A blank field leaves its literal separator dangling ("Online, " from
    # "{city}, {country}" for an online event) — trim those at the ends.
    return _PLACEHOLDER.sub(_substitute, template).strip(" ,;:–—")
