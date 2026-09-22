"""Required/vocab/require_one_of/date-precision checks that apply to
*every* category regardless of handler — "A handler owns: extra field
validation beyond required/vocab checks" (SPECS.md, "Category handlers")."""

from dataclasses import dataclass

from .dates import InvalidDateError, meets_precision_floor
from .schema import CategorySchema
from .vocab import is_valid_value


@dataclass
class LintIssue:
    category: str
    row_id: str | None
    field: str | None
    message: str
    severity: str = "error"


def _is_blank(value) -> bool:
    return value is None or (isinstance(value, str) and value.strip() == "")


def validate_common(schema: CategorySchema, entry: dict, vocab: dict) -> list[LintIssue]:
    issues: list[LintIssue] = []
    row_id = entry.get("id")

    for f in schema.fields:
        if f.generated:
            continue
        value = entry.get(f.name)
        blank = _is_blank(value)

        if f.required and blank:
            issues.append(LintIssue(
                schema.name, row_id, f.name, f"'{f.name}' is required but blank",
            ))
            continue

        if blank:
            continue

        if f.vocab and not is_valid_value(vocab, f.vocab, value):
            issues.append(LintIssue(
                schema.name, row_id, f.name,
                f"'{value}' is not a valid value for vocab '{f.vocab}'",
            ))

        if f.type == "date" and f.precision:
            try:
                if not meets_precision_floor(value, f.precision):
                    issues.append(LintIssue(
                        schema.name, row_id, f.name,
                        f"'{f.name}' must have at least {f.precision} precision, got '{value}'",
                    ))
            except InvalidDateError:
                issues.append(LintIssue(
                    schema.name, row_id, f.name, f"'{f.name}' is not a valid date: '{value}'",
                ))

    for group in schema.require_one_of:
        if not any(not _is_blank(entry.get(name)) for name in group):
            issues.append(LintIssue(
                schema.name, row_id, None, f"At least one of {group} must be filled",
            ))

    return issues
