"""The `{field}` template mini-language used by `views.yaml`'s field
mappings, `profiles/*.yaml`'s `meta.output`, and identity variant
resolution (see SPECS.md, "views.yaml (draft)"). Pure functions over
plain dicts — no file I/O, no category/schema knowledge."""

import re

_PLACEHOLDER = re.compile(r"\{(\w+)\}")


def resolve_field(row: dict, field_name: str, language: str):
    """Returns the raw resolved value (any type) for one field name,
    auto-resolving a bilingual pair (`<field>_en`/`<field>_fr`) by
    language — falling back to the other language if the profile's own
    is blank, so a value is never dropped just from a language mismatch
    — or to a plain (non-suffixed) field if no bilingual pair exists."""
    primary_key = f"{field_name}_{language}"
    if primary_key in row:
        value = row.get(primary_key)
        if value:
            return value
        other_language = "fr" if language == "en" else "en"
        other_value = row.get(f"{field_name}_{other_language}")
        if other_value:
            return other_value
        return value
    return row.get(field_name)


def resolve_template(template, row: dict, language: str):
    """`template` is a plain field name with no braces at all (direct
    copy, any type), a bare `"{field}"` (bilingual-resolved via
    `resolve_field`; passed through unchanged if the resolved value is
    already a list — needed for `PublicationEntry.authors`), a compound
    string mixing `{field}`s and literal text (always stringified), or a
    list of any of the above (each resolved independently, blank/falsy
    results dropped — used for `highlights`)."""
    if isinstance(template, list):
        resolved = [resolve_template(item, row, language) for item in template]
        return [value for value in resolved if value]

    if not isinstance(template, str):
        return template

    if "{" not in template:
        return row.get(template)

    bare_match = _PLACEHOLDER.fullmatch(template)
    if bare_match:
        return resolve_field(row, bare_match.group(1), language)

    def _substitute(match):
        value = resolve_field(row, match.group(1), language)
        return str(value) if value else ""

    return _PLACEHOLDER.sub(_substitute, template)
